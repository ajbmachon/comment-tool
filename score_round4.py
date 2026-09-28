"""Pre-registered scoring for round 4, frozen before any round-4 Jev or Sol call.

Answer key: the round-4 rule (`round4/compose_round4.py`, a byte copy of `compose.py` as frozen) applied to Sol's blind yes/no labels on the exact packet
(true 1, false 0, ambiguous 0.5). Readout A decides on the first answer; it escalates when a
decision-path value lies strictly inside the band. Bars: at least 70 of 100 decided on their own,
and at least 90 of 100 of those matching the key.

Beside the bars, and not counted towards them:
- the stale split alone: the round-3 rule (one stale question, still asked and labelled) on the
  same Jev answers and the same Sol labels, against its own key;
- how often each rule fires "fix stale comment", for Jev and in each key;
- agreement of each yes/no answer with Sol at 0.5, ambiguous labels left out;
- the action after the code search, for escalated comments.
usage: python3 score_round4.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

from data_root import DATA

sys.path.insert(0, str(DATA / "round3"))
sys.path.insert(0, str(DATA / "round4"))
import compose_frozen  # noqa: E402
import compose_round4 as compose  # noqa: E402

ROUND = DATA / "round4"
SOL_TRUTH = {"true": 1.0, "false": 0.0, "ambiguous": 0.5}
DECIDED_BAR, MATCH_BAR = 0.70, 0.90


def rows(path: Path) -> dict:
    return {row["case_id"]: row for row in map(json.loads, path.read_text().splitlines())}


def sol_probabilities(label: dict) -> dict:
    return {q: SOL_TRUTH[a["label"]] for q, a in label["verdict"]["answers"].items() if "label" in a}


def first_answer(row: dict) -> dict:
    return row.get("first_answer", row)


def readouts(rule, passes: dict, labels: dict, facts: dict) -> dict:
    result = {}
    for cid, row in passes.items():
        jev = first_answer(row)["probabilities"]
        result[cid] = {"a": rule.readout_a(jev, facts[cid]), "escalated": bool(rule.escalation_reasons(jev, facts[cid])),
                       "key": rule.readout_a(sol_probabilities(labels[cid]), facts[cid])}
    return result


def summary(name: str, result: dict) -> str:
    n = len(result)
    decided = [cid for cid, r in result.items() if not r["escalated"]]
    hits = [cid for cid in decided if result[cid]["a"] == result[cid]["key"]]
    misses = sorted(set(decided) - set(hits))
    alone = sum(r["a"] == r["key"] for r in result.values())
    return (f"{name}: A alone matches its key on {alone} of {n}; decided {len(decided)} of {n}; "
            f"of those {len(hits)} of {len(decided)} match; decided mistakes {misses}")


def bars(result: dict) -> str:
    n = len(result)
    decided = [cid for cid, r in result.items() if not r["escalated"]]
    hits = sum(result[cid]["a"] == result[cid]["key"] for cid in decided)
    decided_ok = len(decided) >= DECIDED_BAR * n
    match_ok = bool(decided) and hits >= MATCH_BAR * len(decided)
    return f"bars: decided {len(decided)}/{n} {'met' if decided_ok else 'missed'}; match {hits}/{len(decided)} {'met' if match_ok else 'missed'}"


def stale_counts(name: str, result: dict) -> str:
    fired = [cid for cid, r in result.items() if r["a"] == "fix_stale"]
    keyed = [cid for cid, r in result.items() if r["key"] == "fix_stale"]
    return f"{name}: Jev fires fix_stale on {len(fired)} {fired}; the key says fix_stale on {len(keyed)} {keyed}"


def agreement_lines(passes: dict, labels: dict) -> list[str]:
    lines = []
    for question in first_answer(next(iter(passes.values())))["probabilities"]:
        pairs = [(first_answer(passes[cid])["probabilities"][question] >= 0.5, labels[cid]["verdict"]["answers"][question]["label"])
                 for cid in passes]
        scored = [(jev, sol == "true") for jev, sol in pairs if sol != "ambiguous"]
        lines.append(f"  {question:<28} {sum(j == s for j, s in scored)} of {len(scored)}")
    return lines


def after_search_line(passes: dict) -> str:
    searched = {cid: row for cid, row in passes.items() if "search" in row}
    outcomes = Counter(row["search"]["outcome"] for row in searched.values())
    resolved = [cid for cid, row in searched.items() if row["decided_by"] == "jev+rule after find_code"]
    return f"searches {len(searched)}: outcomes {dict(outcomes)}; resolved after the search {len(resolved)} {resolved}"


def main() -> None:
    passes, labels = rows(ROUND / "pass.jsonl"), rows(ROUND / "sol-labels.jsonl")
    facts = {cid: case["code_facts"] for cid, case in rows(ROUND / "cases.jsonl").items()}
    round4 = readouts(compose, passes, labels, facts)
    old_stale = readouts(compose_frozen, passes, labels, facts)
    print("Before (round 3, frozen): decided 26 of 30; of those 23 of 26 match (88 of 100)")
    print(summary("Round 4 (three stale questions)", round4))
    print(bars(round4))
    print(summary("Same answers, round-3 rule (one stale question)", old_stale))
    print(stale_counts("Round-4 rule", round4))
    print(stale_counts("Round-3 rule", old_stale))
    print("Jev agreement with Sol at 0.5, ambiguous left out:")
    print("\n".join(agreement_lines(passes, labels)))
    print(after_search_line(passes))


if __name__ == "__main__":
    main()
