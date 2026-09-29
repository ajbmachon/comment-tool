"""Export real loop traces of chosen sweep rows, step by step, from stored requests and answers only.

Each step records its name, the input state as short excerpts with file:line@commit, the questions
asked, the raw probabilities, the rule or threshold applied, the decision, what it fetched next or
why it stopped, and which of the three outcomes it reached. Nothing is recomputed from a model.

usage: python3 export_traces.py <sweep dir> <out json> <location> [<location> ...]
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from comment_tool.config import DATA

sys.path.insert(0, str(DATA / "round3"))
from compose_frozen import (  # the rule round 3 and the lib sweep were measured with
    CUTOFF,
    ESCALATION_BAND,
    decision_path,
)

from comment_tool.core.extract_cases import code_facts, comment_prefix

EXCERPT_CHARS = 160
LIBRARY = "jev-navigator@81b5498"
TOOL_FILES = ("sweep.py", "comment_review.py", "compose.py", "questions.json", "extract_cases.py")
SEARCH_PREFIX = "the code this comment describes: "
FOUND_BY_CODE = "found: code located the attached code; no search ran"
DESCRIBED = "found: code_described_by_comment supplied the described code; no search ran"
KEPT_BY_CODE = "docstring, jsdoc, header, tool_directive and declaration comments are kept by code"


def excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT_CHARS else flat[: EXCERPT_CHARS - 1] + "…"


def at(source: dict | None) -> str | None:
    if not source:
        return None
    first, last = source["lines"]
    return f"{source['file']}:{first}-{last}@{source['commit'][:10]}"


def load_records(sweep: Path) -> list[dict]:
    return [json.loads(line) for line in (sweep / "answers.jsonl").read_text().splitlines()]


def question_texts(record: dict) -> dict:
    """One entry per wording; a question asked once per candidate says how many times it was asked."""
    names = Counter(qid.split("@")[0] for qid in record["request"]["questions"])
    texts = {qid.split("@")[0]: q["instructions"] for qid, q in record["request"]["questions"].items()}
    return {name: text if names[name] == 1 else f"(asked {names[name]} times, once per candidate) {text}"
            for name, text in texts.items()}


def raw_values(record: dict) -> dict:
    values = {}
    for qid, answer in record["answers"].items():
        name = qid.split("@")[0] + (("#" + qid.split("#")[1]) if "#" in qid else "")
        values[name] = answer.get("noul") if answer["type"] == "noul" else {
            "choice": answer.get("choice"), "confidence": answer.get("confidence"), "probabilities": answer["probabilities"],
            **({"score": answer["score"]} if answer["type"] == "score" else {})}
        if answer["type"] == "score":
            values[name].pop("choice")
    return values


def discovery_step(row: dict) -> dict:
    code_decided = row["decided_by"] == "code"
    return {
        "step": "find_comments (code, no model)",
        "input": {"comment": excerpt(row["comment"]), "at": f"{row['location']}@{row['commit'][:10]}", "kind": row["kind"]},
        "questions": [], "raw_probabilities": {},
        "rule": KEPT_BY_CODE + "; commented-out code is removed by code; everything else goes to Jev",
        "decision": f"{row['action']} ({row['reason']})" if code_decided else "send to Jev",
        "next": "stop: decided by code" if code_decided else "build the packet: lines above and code_described_by_comment",
        "outcome": FOUND_BY_CODE if code_decided else None,
    }


def judgment_steps(row: dict, record: dict, label: str, retried: bool = False) -> list[dict]:
    state = record["request"]["state"]
    evidence = row["evidence"]
    judge_step = {
        "step": f"ask_all ({label})",
        "input": {"comment": excerpt(state["comment"]["text"]),
                  "before_comment": {"at": at(evidence["before_comment"]), "excerpt": excerpt(state["code"]["before_comment"])},
                  "after_comment": {"at": at(evidence["after_comment"]), "excerpt": excerpt(state["code"]["after_comment"])}},
        "questions": question_texts(record), "raw_probabilities": raw_values(record),
        "served_model": record["model"], "request_sha256": record["request_sha256"],
        "rule": "one request, all questions over the same state", "decision": "answers recorded", "next": "apply rule A",
        "outcome": None,
    }
    low, high = ESCALATION_BAND
    facts = code_facts(row["comment"].split("\n"), comment_prefix(row["location"].rsplit(":", 1)[0]))
    path = decision_path(row["probabilities"], facts)
    rule_step = {
        "step": f"rule A ({label})",
        "input": {"code_facts": facts},
        "questions": [], "raw_probabilities": path,
        "rule": f"compose.readout_a at cut-off {CUTOFF}; escalate when a decision-path value lies strictly between {low} and {high}",
        "decision": row["action"] + (f"; escalate: {row['escalate']['reasons']}" if "escalate" in row else ""),
        "next": _after_rule(row, retried),
        "outcome": None if "escalate" in row and not retried else row.get("search", {}).get("outcome", DESCRIBED),
    }
    return [judge_step, rule_step]


def _after_rule(row: dict, retried: bool) -> str:
    if "escalate" not in row:
        return "stop: decided"
    return "stop: still unclear after one search; escalate" if retried else "search for the code the comment describes"


def search_steps(row: dict, records: list[dict]) -> list[dict]:
    description = SEARCH_PREFIX + row["comment"]
    opened = sorted((r for r in records if r["request"]["state"].get("target", {}).get("description") == description),
                    key=lambda r: r["recorded_at"])
    steps = []
    for number, record in enumerate(opened, 1):
        state, values = record["request"]["state"], raw_values(record)
        found = values.get("contains_target")
        limits = record["thresholds"]
        verdict = ("found" if found >= limits["noul_yes_at"] else "not the target" if found <= limits["noul_no_at"] else "unsure")
        candidates = {f"{c['signature'][:110]}": values.get(f"could_contain_target#{i}") for i, c in enumerate(state["candidates"])}
        steps.append({
            "step": f"find_code opens place {number} (rounds of up to 2 places run at once; numbered by completion)",
            "input": {"slice": f"{state['slice']['file']}:{state['slice']['lines']}@{row['commit'][:10]}",
                      "excerpt": excerpt(state["slice"]["code"]), "candidates_offered": len(state["candidates"])},
            "questions": question_texts(record), "raw_probabilities": {"contains_target": found, "candidates": candidates,
                                                                      "open_first": values.get("open_first")},
            "served_model": record["model"], "request_sha256": record["request_sha256"], "thresholds_recorded": limits,
            "rule": (f"found at >= {limits['noul_yes_at']}, not the target at <= {limits['noul_no_at']}, otherwise unsure; "
                     f"candidates queue best first by probability (a low score only deprioritizes); open_first counts at "
                     f"confidence >= {limits['choice_min_confidence']}"),
            "decision": verdict,
            "next": "found; the search stops after this round" if verdict == "found" else "queue its candidates; open the next best places if budget and worth-opening allow",
            "outcome": "found" if verdict == "found" else None,
        })
    search = row["search"]
    steps.append({
        "step": "find_code stops (code)",
        "input": {"steps": search["steps"], "calls": search["calls"], "library_outcome": search["library_outcome"]},
        "questions": [], "raw_probabilities": {},
        "rule": "stop on found; on budget (6 steps or 6 calls, depth 2, beam 2); or when nothing queued is worth opening",
        "decision": search["outcome"],
        "next": {"found": [at(f) for f in search["found"]],
                 "searched_not_target": [at(f) for f in search["searched_not_target"]],
                 "opened_unsure": [at(f) for f in search["opened_unsure"]],
                 "not_inspected": [f"{n['reason']}: {n['signature'][:100]}" for n in search["not_inspected"]],
                 "unproven_call_edges": search["unproven_call_edges"]},
        "outcome": search["outcome"],
    })
    return steps


def final_step(row: dict) -> dict:
    escalated = "escalate" in row
    return {
        "step": "result",
        "input": {"decided_by": row["decided_by"]}, "questions": [], "raw_probabilities": {},
        "rule": "an escalated row goes to the calling agent with the one unclear question; a human only if it cannot decide",
        "decision": "escalate to calling agent" if escalated else row["action"],
        "next": "calling agent reviews the edit against the whole file at this commit" if escalated else "edit proposal, checked against the file before applying",
        "outcome": (row.get("search") or {}).get("outcome", FOUND_BY_CODE if row["decided_by"] == "code" else DESCRIBED),
    }


def trace(row: dict, records: dict[str, dict], all_records: list[dict]) -> dict:
    steps = [discovery_step(row)]
    if row["decided_by"] != "code":
        first = row.get("first_answer", row)
        steps += judgment_steps({**row, **first}, records[first["request_sha256"]], "described code")
        if "search" in row:
            steps += search_steps(row, all_records)
        if "first_answer" in row:
            steps += judgment_steps(row, records[row["request_sha256"]], "described code plus found code", retried=True)
    steps.append(final_step(row))
    return {"location": f"{row['location']}@{row['commit']}", "comment": row["comment"], "steps": steps}


def provenance(records: list[dict]) -> dict:
    return {"library": LIBRARY,
            "tool_file_sha256": {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest() for name in TOOL_FILES},
            "served_models": sorted({record["model"] for record in records})}


def stored_path_matches(row: dict) -> bool:
    """The exporter's recomputed rule path equals the one the sweep stored for its final answer."""
    facts = code_facts(row["comment"].split("\n"), comment_prefix(row["location"].rsplit(":", 1)[0]))
    return decision_path(row["probabilities"], facts) == row["decision_path"]


def main() -> None:
    sweep, out, locations = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3:]
    rows = {row["location"]: row for path in sweep.glob("apps-*.jsonl") for row in map(json.loads, path.read_text().splitlines())}
    all_records = load_records(sweep)
    by_hash = {record["request_sha256"]: record for record in all_records}
    out.parent.mkdir(parents=True, exist_ok=True)
    traces = [trace(rows[location], by_hash, all_records) for location in locations]
    judged = [rows[location] for location in locations if "decision_path" in rows[location]]
    print(f"recomputed rule path equals the stored one on {sum(map(stored_path_matches, judged))} of {len(judged)} judged rows")
    out.write_text(json.dumps({"produced_by": provenance(all_records), "source": str(sweep), "traces": traces}, indent=2) + "\n")
    print(f"{len(traces)} traces written to {out}")


if __name__ == "__main__":
    main()
