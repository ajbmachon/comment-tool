"""Replay the search gate on stored escalations, with no model call.

For every stored escalated comment: would `compose.search_could_settle` have started a search on its
first answer, and if a search ran and settled the comment, the decision the gate takes away. Round 3 and
the lib sweep asked one stale question, not the three the gate reads, so their answers cannot be replayed here;
`gate_first_answers.py` asks the three on their stored packets instead.
usage: python3 gate_replay.py
"""

import json
from collections import Counter
from pathlib import Path

import compose

HERE = Path(__file__).resolve().parent
STORED = {"round 4": ["round4/pass.jsonl"]}


def first_answer(row: dict) -> dict:
    return row.get("first_answer", row)


def escalated_first(row: dict) -> bool:
    return "escalate" in first_answer(row)


def reasons(row: dict) -> list[str]:
    return [reason.split()[0] for reason in first_answer(row)["escalate"]["reasons"]]


def replayed(row: dict) -> dict:
    searched_before = "search" in row
    searched_now = compose.search_could_settle(first_answer(row)["probabilities"])
    settled_by_search = row.get("decided_by") == "jev+rule after find_code"
    return {"location": row.get("location", row.get("case_id")), "reasons": reasons(row),
            "searched_before": searched_before, "searched_now": searched_now,
            "decision_lost": settled_by_search and not searched_now,
            "action_after_search": row["action"] if settled_by_search else None}


def rows_of(paths: list[str]) -> list[dict]:
    return [json.loads(line) for path in paths for line in (HERE / path).read_text().splitlines()]


def main() -> None:
    for name, paths in STORED.items():
        cases = [replayed(row) for row in rows_of(paths) if escalated_first(row)]
        print(f"{name}: {len(cases)} escalated on the first answer; searched before {sum(c['searched_before'] for c in cases)}, "
              f"searched under the gate {sum(c['searched_now'] for c in cases)}")
        print("  reasons:", dict(Counter(reason for c in cases for reason in c["reasons"])))
        print("  decisions a search had settled and the gate takes away:",
              [(c["location"], c["action_after_search"]) for c in cases if c["decision_lost"]])
        print("  searched under the gate:", [c["location"] for c in cases if c["searched_now"]])


if __name__ == "__main__":
    main()
