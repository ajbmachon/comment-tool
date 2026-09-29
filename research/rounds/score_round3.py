"""Score the round-3 arms, keeping judgment, retrieval and run-to-run noise apart.

- Judgment: rule A on Jev's answers against the answer key on the same packet (the rule applied to
  Sol's yes/no labels for that exact packet; Sol's direct action pick is shown, not counted).
- Retrieval: how often the answer key changed when the packet changed, compared with how often it
  changed when Sol relabelled an identical packet.
- Noise: the same packets asked twice (without and with the Score question).
usage: python3 score_round3.py
"""

import json
import sys
from pathlib import Path

from comment_tool.config import DATA

sys.path.insert(0, str(DATA / "round3"))
from compose_frozen import (  # the rule round 3 and the lib sweep were measured with
    escalation_reasons,
    readout_a,
)

SOL_TRUTH = {"true": 1.0, "false": 0.0, "ambiguous": 0.5}
NOISE_POINTS = 0.02


def rows(path: Path) -> dict:
    return {row["case_id"]: row for row in map(json.loads, path.read_text().splitlines())}


def jev_probabilities(arm: Path) -> dict:
    if not (arm / "run").exists():
        return {cid: row["probabilities"] for cid, row in rows(arm / "pass.jsonl").items()}
    runs = (json.loads(p.read_text()) for p in (arm / "run").glob("*.json"))
    return {r["case_id"]: {q: a["noul"] for q, a in r["response"]["answers"].items() if a["type"] == "noul"} for r in runs}


def answer_key(label: dict, facts: dict) -> str:
    answers = label["verdict"]["answers"]
    return readout_a({q: SOL_TRUTH[a["label"]] for q, a in answers.items() if "label" in a}, facts)


def judged(arm: Path, labels: Path) -> dict:
    facts = {cid: c["code_facts"] for cid, c in rows(DATA / "round3" / "cases.jsonl").items()}
    sol, jev = rows(labels), jev_probabilities(arm)
    return {cid: {"a": readout_a(jev[cid], facts[cid]), "escalated": bool(escalation_reasons(jev[cid], facts[cid])),
                  "key": answer_key(sol[cid], facts[cid]), "direct": sol[cid]["verdict"]["answers"]["action"]["choice"]}
            for cid in sorted(jev)}


def judgment_line(name: str, result: dict) -> str:
    decided = [cid for cid, r in result.items() if not r["escalated"]]
    hits = [cid for cid in decided if result[cid]["a"] == result[cid]["key"]]
    misses = [cid for cid in decided if cid not in hits]
    alone = sum(r["a"] == r["key"] for r in result.values())
    return (f"{name}: A alone matches the key on {alone} of {len(result)}; decided {len(decided)} of {len(result)}; "
            f"of those {len(hits)} of {len(decided)} match; decided mistakes {misses}")


def retrieval_lines() -> list[str]:
    old_cases, new_cases = rows(DATA / "round3" / "cases.jsonl"), rows(DATA / "round3-nav-described" / "cases.jsonl")
    old_labels, new_labels = rows(DATA / "round3" / "sol-labels.jsonl"), rows(DATA / "round3-nav-described" / "sol-labels.fresh.jsonl")
    lines = []
    for same in (True, False):
        ids = [cid for cid in old_cases if (old_cases[cid]["state"] == new_cases[cid]["state"]) == same]
        facts = {cid: old_cases[cid]["code_facts"] for cid in ids}
        moved = [cid for cid in ids if answer_key(old_labels[cid], facts[cid]) != answer_key(new_labels[cid], facts[cid])]
        kind = "identical packets (Sol relabelled the same input)" if same else "changed packets"
        lines.append(f"{kind}: answer key changed on {len(moved)} of {len(ids)} {moved}")
    return lines


def noise_lines(first: Path, second: Path) -> list[str]:
    a, b = jev_probabilities(first), jev_probabilities(second)
    pairs = [(a[cid][q], b[cid][q]) for cid in a for q in a[cid]]
    moved = sum(abs(x - y) > NOISE_POINTS for x, y in pairs)
    crossed = sum((x >= 0.5) != (y >= 0.5) for x, y in pairs)
    largest = max(abs(x - y) for x, y in pairs)
    return [f"same packets asked twice: {moved} of {len(pairs)} Noul answers moved more than {NOISE_POINTS:.2f}, "
            f"{crossed} crossed 0.5, largest move {largest:.2f}"]


def main() -> None:
    fresh = DATA / "round3-nav-described" / "sol-labels.fresh.jsonl"
    print(judgment_line("Before (frozen round 3, pre-registered)", judged(DATA / "round3", DATA / "round3" / "sol-labels.jsonl")))
    print(judgment_line("After, no Score (described cut, post-hoc)", judged(DATA / "round3-nav-described", fresh)))
    print(judgment_line("After, ask_all with Score (same packets)", judged(DATA / "round3-ask-all", fresh)))
    for line in retrieval_lines() + noise_lines(DATA / "round3-nav-described", DATA / "round3-ask-all"):
        print(line)


if __name__ == "__main__":
    main()
