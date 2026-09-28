"""Ask the round-4 questions on the stored packets of comments that escalated before the three
stale questions existed, so the search gate can be replayed on them.

Round 3 and the lib sweep asked one stale question; the gate reads the three. Round 3's packets come
from its cases file, as sent. The lib sweep's come from the answer store, which keeps a copy of each
request with its keys sorted: not the bytes the sweep sent, and Jev can answer the two differently
(the library verifier, 28.09.2026: 0.83 against 0.70 on one packet). Each packet is asked once and
journaled. The output rows carry the first answer, the round-4 escalation reasons and the gate's
verdict. The lib numbers are re-asked from the journal's exact bytes once the library stores them.
usage: run-slot -- uv run --project <jev-navigator> --extra typesafe python gate_first_answers.py <out dir>
"""

import glob
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import compose
from comment_facts import facts_of
from comment_review import question_set
from data_root import DATA
from extract_cases import comment_prefix
from journaled_client import journaled_judge
from run_round4 import ROUND4_QUESTIONS
from sweep import COMMENT_WORKERS

LIB = DATA / "pass/lib-a3bde2aa-rebuilt"


def stored_states(answers_path: Path) -> dict:
    return {row["request_sha256"]: row["request"]["state"] for row in map(json.loads, answers_path.read_text().splitlines())}


def lib_escalations() -> list[dict]:
    states = stored_states(LIB / "answers.jsonl")
    rows = [json.loads(line) for path in sorted(glob.glob(str(LIB / "apps-*.jsonl"))) for line in Path(path).read_text().splitlines()]
    return [{"source": "lib sweep", "location": row["location"], "comment": row["comment"],
             "settled_by_search": row["decided_by"] == "jev+rule after find_code",
             "state": states[row.get("first_answer", row)["request_sha256"]]}
            for row in rows if "search" in row]


def round3_escalations() -> list[dict]:
    cases = {case["case_id"]: case for case in map(json.loads, (DATA / "round3-nav-described/cases.jsonl").read_text().splitlines())}
    passes = [json.loads(line) for line in (DATA / "round3-nav-described/pass.jsonl").read_text().splitlines()]
    by_location = {f"{c['provenance']['path']}:{c['provenance']['comment_lines'][0]}": c for c in cases.values()}
    return [{"source": "round 3", "location": row["location"], "comment": row["comment"], "settled_by_search": False,
             "state": by_location[row["location"]]["state"]} for row in passes if "escalate" in row]


def gated(judge, questions, stored: dict) -> dict:
    answers = judge.ask_all(stored["state"], checks=questions.checks, picks=questions.picks, scores=questions.scores)
    p = {name: result.probability for name, result in answers.checks.items()}
    path = stored["location"].rsplit(":", 1)[0]
    facts = {**facts_of(stored["comment"], comment_prefix(path)), "doc_comment": False}
    return {key: stored[key] for key in ("source", "location", "settled_by_search")} | {
        "request_sha256": answers.request_sha256, "probabilities": p,
        "escalation_reasons": compose.escalation_reasons(p, facts), "searched_under_gate": compose.search_could_settle(p)}


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    stored = round3_escalations() + lib_escalations()
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    judge = journaled_judge(out, {"heedvane", "analysis-engine"})
    with ThreadPoolExecutor(COMMENT_WORKERS) as pool:
        rows = list(pool.map(lambda s: gated(judge, questions, s), stored))
    (out / "gated.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(f"asked {len(rows)}; Jev calls {judge.calls}")


if __name__ == "__main__":
    main()
