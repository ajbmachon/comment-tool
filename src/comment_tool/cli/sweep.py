"""Directory comment sweep on jev-navigator: read-only, one unit at a time, at one commit.

Every file is read from git objects at the commit (`CodeIndex.at_commit`); the checkout is never
touched. `comment_discovery` turns every block `find_comments` returns into one case, and code
settles tool directives (keep) and commented-out code (remove). Jev judges the rest with the frozen
questions in one `ask_all` request per comment, on the lines above the comment and the code
`code_described_by_comment` returns. An escalated comment gets one `find_code` search for the code
it describes only when `compose.search_could_settle` says more code could settle it: the doubt is
about staleness and the detail the comment names is not in the shown code. The stop question may
end that search. Before "fix stale comment" fires, `definition_fetch` fetches the definitions behind
the conditions in the described code; a condition name without a definition escalates. Code a fetch
or a search adds goes in `code.elsewhere`, and only the three stale questions are asked again: every
other answer stays the first packet's. A comment that names a detail the shown code lacks carries
`stale_check`, since its staleness was not checked. Each round of the search appends what it opened to a `History`, and the
caller's stop question asks whether that history holds what the comment talks about. The row keeps
the search as found, searched and not found, or not yet inspected, with the places and the history
behind it. When the search finds new code, Jev is asked again on the wider state. Every Jev
exchange is journaled and every request kept (own repositories only). The tool only classifies: a
decided "rewrite" carries a `rewrite_job` (what the comment documents, the old comment and why, from
`rewrite_packet`) for the calling agent or another system, which writes the new comment.

usage: uv run comment-sweep \
         <repository> <commit> <parent dir> <out dir> [--only <unit> ...]
"""

import json
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev_navigator.directives.find_code import FindResult, Outcome, StopRule, find_code
from jev_navigator.directives.places import place_for_line
from jev_navigator.history import FETCHED, HistoryTooLargeError
from jev_navigator.index import tools
from jev_navigator.index.code_index import CodeIndex
from jev_navigator.index.spans import CodeSlice
from jev_navigator.judgments.judge import CallCapReachedError, Judge
from jev_navigator.judgments.questions import Check, Criterion

import comment_tool.core.compose as compose
from comment_tool.claims.list_claims import checked_list_claim, list_claim_for, with_list_claim_question
from comment_tool.claims.rewrite_packet import rewrite_job
from comment_tool.core import request_budget
from comment_tool.core.comment_discovery import FoundComment, code_decision, found_comments
from comment_tool.core.comment_review import (
    MEASURED_CONTEXT,
    CommentCase,
    QuestionSet,
    comment_state,
    described_after,
    question_set,
    recomposed,
    review_comment,
    stale_reask_checks,
    with_escalation,
)
from comment_tool.core.definition_fetch import fetch_definitions
from comment_tool.journal.journaled_client import journaled_judge
from comment_tool.questions import path as questions_path

QUESTIONS = questions_path("questions.round5.json")
"""The current questions: round 4's, with `is_noise` excluding one-sentence doc summaries (Andre, 08:10 CEST)."""
SOURCE = re.compile(r"\.(py|ts|tsx)$")
NOT_SOURCE = re.compile(r"\.test\.|\.spec\.|_test\.py$|test-support|generated|\.d\.ts$|__tests__|/e2e/|/tests?/")
MAX_UNIT_FILES = 300
THREE_OUTCOMES = {Outcome.FOUND: "found", Outcome.STOP_RULE: "found", Outcome.NOTHING_LEFT: "searched_not_found",
                  Outcome.BUDGET: "not_yet_inspected", Outcome.UNSURE_ONLY: "not_yet_inspected",
                  Outcome.SCOPE_INCOMPLETE: "not_yet_inspected", Outcome.CANCELLED: "not_yet_inspected"}
"""A search over a scope with unparsed files never says the code is absent."""
COMMENT_WORKERS = 6
HOLDS_WHAT_COMMENT_IS_ABOUT = Check(
    name="history_holds_commented_code",
    instructions="Does a `code` field in `fetched` contain the statement, value or condition that `comment.text` is about?",
    yes=Criterion(
        "One fetched span holds the line or block `comment.text` talks about: the check, constant, call or step it names.",
        not_for="Code that only calls it, sits near it, or shares a word with the comment.",
        examples=("The comment says 'retry three times' and a fetched span holds the retry loop with its limit.",),
    ),
    no=Criterion(
        "No fetched span holds what `comment.text` talks about.",
        examples=("The comment is about the retry limit and the fetched spans only format log messages.",),
    ),
)
"""The caller-defined stop question: a concrete property of the collected evidence, never 'is it enough'.
It reads only the fetched code (`STOP_SECTIONS`), not the search's own per-place verdicts: the view the
Sol stop labels were given (the lead's ruling, 28.09.2026)."""
STOP_SECTIONS = (FETCHED,)


def source_files(repository: Path, commit: str, parent: str) -> list[str]:
    listed = tools.git(["ls-tree", "-r", "--name-only", commit, "--", parent], repository).splitlines()
    return [path for path in listed if SOURCE.search(path) and not NOT_SOURCE.search(path)]


def sweep_units(files: list[str], parent: str) -> list[tuple[str, list[str]]]:
    """Each child directory is one unit; the parent's own files are split into units of MAX_UNIT_FILES."""
    root = parent.rstrip("/")
    children: dict[str, list[str]] = {}
    top: list[str] = []
    for path in files:
        rest = path[len(root) + 1 :]
        if "/" in rest:
            children.setdefault(f"{root}/{rest.split('/')[0]}", []).append(path)
        else:
            top.append(path)
    units = sorted(children.items())
    return units + [(f"{root}#{i // MAX_UNIT_FILES + 1}", top[i : i + MAX_UNIT_FILES]) for i in range(0, len(top), MAX_UNIT_FILES)]


def search_record(result: FindResult) -> dict:
    """The search in the three outcomes, with the places and history behind it; not inspected is never absence."""
    stop = result.stop_judgment
    return {
        "outcome": THREE_OUTCOMES[result.outcome],
        "library_outcome": str(result.outcome),
        "found": [_visited(visit) for visit in result.found],
        "searched_not_target": [_visited(visit) for visit in result.searched],
        "opened_unsure": [_visited(visit) for visit in result.unsure],
        "not_inspected": [{"place": n.place_key, "signature": n.signature, "reason": n.reason, "priority": n.priority}
                          for n in result.not_inspected],
        "unproven_call_edges": [n.signature for n in result.not_inspected if _unproven(n.signature)],
        "history": [step.to_json() for step in result.history.steps] if result.history else [],
        "stop_question": None if stop is None else {"outcome": str(stop.outcome), "probability": stop.probability,
                                                    "tokens": stop.tokens, "evictions": list(stop.evictions)},
        "unparsed_files": sorted(result.unparsed_files),
        "steps": result.steps,
        "calls": result.calls,
    }


def _visited(visit) -> dict:
    return {**visit.code.source(), "place": visit.place_key, "path": list(visit.path), "probability": visit.probability}


def _unproven(signature: str) -> bool:
    """Places reached over a call edge the parser could only guess (candidate) or not bind (unresolved)."""
    return ", candidate:" in signature or ", unresolved:" in signature


def search_for_described_code(index: CodeIndex, judge: Judge, case: CommentCase) -> FindResult | None:
    """One search; `find_code` runs it on its own scope of `judge`, so its budget counts only its
    calls. None when the search could not be run at all, which is not a finding that the code is
    absent anywhere: the places it did not read stay uninspected, and the caller decides."""
    start = [place_for_line(index, case.file, case.last_line, "comment")]
    stop_rule = StopRule(HOLDS_WHAT_COMMENT_IS_ABOUT, shared={"comment": {"text": case.text}}, sections=STOP_SECTIONS)
    try:
        return find_code(index, judge, f"the code this comment describes: {case.text}", start,
                         commit=index.commit, stop_rule=stop_rule)
    except (HistoryTooLargeError, CallCapReachedError):
        return None


def reasked_on_elsewhere(index: CodeIndex, judge: Judge, case: CommentCase, questions: QuestionSet, row: dict,
                         extra: list[CodeSlice]) -> dict | None:
    """Only the stale questions, asked again with `extra` in `code.elsewhere`; every other answer
    stays the first packet's. None when `extra` holds nothing the described code does not.

    Places that do not all fit in one request are asked in as many requests as they need, because
    one place does not answer another place's question, and a packet above a route's request-token
    limit is refused rather than answered. The lowest answer per question wins: a place that shows
    the detail contradicts a place that hides it, and `stale_of` is the lowest of its three parts.
    A place larger on its own than one request may be is escalated, never cut down."""
    before, after = MEASURED_CONTEXT(index, case)
    new = [piece for piece in extra if piece.text not in after.text]
    if not new:
        return None
    checks = stale_reask_checks(questions)
    units = [[piece] for piece in new]

    def packet_of(pieces: list[CodeSlice]) -> dict:
        return comment_state(case, before, after, tuple(pieces))

    def too_big(packet: list[CodeSlice]) -> bool:
        return not request_budget.packet_fits(judge, packet_of(list(packet)))

    packets = request_budget.packets_fitting(judge, units, too_big)
    if packets is None:
        too_big_here = [unit[0] for unit in units if too_big(list(unit))]
        return with_escalation(row, [f"staleness is not checkable on this evidence: {len(too_big_here)} "
                                    f"{'place' if len(too_big_here) == 1 else 'places'} of it will not "
                                    "fit a request this run's routes accept"])
    answers: dict[str, float] = {}
    digests: list[str] = []
    for packet in packets:
        asked = judge.ask_all(packet_of(packet), checks=checks)
        answers = request_budget.lowest_answers(answers, {name: result.probability
                                                          for name, result in asked.checks.items()})
        digests.append(asked.request_sha256)
    reask = {"probabilities": answers, "request_sha256": digests, "packets": len(packets),
             "elsewhere": [piece.source() for piece in new]}
    return {**recomposed(row, {**row["probabilities"], **answers}, case), "stale_reask": reask,
            "first_answer": _first(row)}


def checked_stale(index: CodeIndex, judge: Judge, case: CommentCase, questions: QuestionSet, row: dict) -> dict:
    """Before "fix stale comment" fires: the definitions behind the described code's conditions join
    the packet and the questions are asked again. A condition name without a definition escalates."""
    described = described_after(index, case)
    found = fetch_definitions(index.git_root, index.commit, described.span)
    record = {"fetched": [piece.source() for piece in found.fetched], "unresolved": list(found.unresolved),
              "unknown": list(found.unknown)}
    if found.escalation_reasons():
        return with_escalation({**row, "definitions": record}, found.escalation_reasons())
    reasked = reasked_on_elsewhere(index, judge, case, questions, row, list(found.fetched))
    return {**(reasked or row), "definitions": record}


def judged(index: CodeIndex, judge: Judge, case: CommentCase, questions: QuestionSet) -> dict:
    literal = list_claim_for(index, case)
    asked = with_list_claim_question(questions) if literal else questions
    row = review_comment(index, judge, case, asked, MEASURED_CONTEXT)
    row = {**row, **stale_record(row["probabilities"])}
    if row["action"] == "fix_stale":
        row = checked_stale(index, judge, case, asked, row)
    if literal:
        row = checked_list_claim(index, judge, case, literal, row)
    if "escalate" not in row:
        return {**row, "decided_by": "jev+rule after definition_fetch" if "first_answer" in row else "jev+rule"}
    if not compose.search_could_settle(row.get("first_answer", row)["probabilities"]):
        return {**row, "decided_by": "escalated"}
    result = search_for_described_code(index, judge, case)
    if result is None:
        return {**with_escalation(row, ["the search for the described code could not be run: its evidence "
                                       "outgrew the input budget this run's routes accept"]),
                "search": {"outcome": "not_yet_inspected", "unfinished": True}, "decided_by": "escalated"}
    search = search_record(result)
    first = row.get("first_answer") or _first(row)
    reasked = reasked_on_elsewhere(index, judge, case, questions, row, [visit.code for visit in result.found])
    if reasked is not None:
        row = {**reasked, "first_answer": first}
        if "escalate" not in row:
            return {**row, "search": search, "decided_by": "jev+rule after find_code"}
    return {**row, "search": search, "decided_by": "escalated"}


def stale_record(probabilities: dict) -> dict:
    """`stale_check` when staleness could not be checked on the shown code; nothing otherwise."""
    check = compose.stale_check(probabilities)
    return {"stale_check": check} if check else {}


def _first(row: dict) -> dict:
    return {key: row[key] for key in ("probabilities", "decision_path", "action", "escalate", "request_sha256", "evidence")
            if key in row}


def review_found(index: CodeIndex, judge: Judge, found: FoundComment, questions: QuestionSet) -> dict:
    decided = code_decision(found)
    row = decided if decided is not None else judged(index, judge, found.case, questions)
    state = row.pop("state", None)
    if row["action"] == "rewrite" and "escalate" not in row:
        row["rewrite_job"] = _rewrite_job(index, found, row, state)
    return {"location": f"{found.case.file}:{found.case.first_line}", "commit": index.commit, "kind": found.kind,
            "comment": found.case.text, **row}


def _rewrite_job(index: CodeIndex, found: FoundComment, row: dict, state: dict) -> dict:
    documented = {"lines": row["evidence"]["after_comment"]["lines"], "code": state["code"]["after_comment"]}
    return rewrite_job(index.git_root, index.commit, found.case, found.kind, documented, row["probabilities"])


def sweep_unit(repository: Path, commit: str, files: list[str], judge: Judge, questions: QuestionSet) -> list[dict]:
    index = CodeIndex.at_commit(repository, commit, files)
    with ThreadPoolExecutor(COMMENT_WORKERS) as pool:
        return list(pool.map(lambda found: review_found(index, judge, found, questions), found_comments(index, files)))


def outcome_of(row: dict) -> str:
    return "escalate" if "escalate" in row else row["action"]


def main() -> None:
    repository, commit, parent, out = Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4])
    only = set(sys.argv[sys.argv.index("--only") + 1 :]) if "--only" in sys.argv else None
    out.mkdir(parents=True, exist_ok=True)
    commit = tools.git(["rev-parse", "--verify", f"{commit}^{{commit}}"], repository).strip()
    questions = question_set(json.loads(QUESTIONS.read_text()))
    judge = journaled_judge(out, {repository.name})
    totals = Counter()
    for unit, files in sweep_units(source_files(repository, commit, parent), parent):
        if only is not None and unit not in only:
            continue
        rows = sweep_unit(repository, commit, files, judge, questions)
        slug = re.sub(r"[^a-z0-9]+", "-", unit.lower()).strip("-")
        (out / f"{slug}.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
        counts = Counter(outcome_of(row) for row in rows)
        counts.update(row["stale_check"] for row in rows if "stale_check" in row)
        totals.update(counts)
        print(unit, len(files), "files", dict(counts), flush=True)
    print("TOTAL", dict(totals), "Jev calls (comment requests)", judge.calls, flush=True)


if __name__ == "__main__":
    main()
