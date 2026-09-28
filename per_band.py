"""Accuracy by confidence band for every labelled comment, from stored answers only (no model call).

For each round, the rule the tool now applies (or, for round 3, the rule it was measured with) is run
on Jev's stored answers and on Sol's labels for the same packet. A decided comment's confidence is its
deciding answer's: for "fix stale comment", the stale value; for every other action, the weakest
answer on its decision path, read in the direction the rule took (`max(p, 1 - p)`). Round 4 uses the
stale answers asked again after the definition fetch (`round4-definitions-elsewhere/`), as the tool
decides today.

The band table applies the whole rule, including the provisional "fix stale comment" bar
(`compose.STALE_DECIDES_AT`). The second part lists the stale verdicts the band alone leaves decided,
and, at each candidate value of "the code's version differs", which of them a bar sends to the
calling agent instead, right and wrong.
usage: python3 per_band.py
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import compose
from data_root import DATA

sys.path.insert(0, str(DATA / "round3"))
import compose_frozen  # the round-3 rule, with its single stale question

SOL_TRUTH = {"true": 1.0, "false": 0.0, "ambiguous": 0.5}
BANDS = ((0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01))
DIFFERS = "code_differs_from_comment"
CANDIDATE_BARS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90)
NOT_A_DOC = {"doc_comment": False}


def rows(path: Path) -> dict:
    return {row["case_id"]: row for row in map(json.loads, path.read_text().splitlines())}


def sol(label: dict) -> dict:
    return {q: SOL_TRUTH[a["label"]] for q, a in label["verdict"]["answers"].items() if "label" in a}


def round3() -> list[dict]:
    cases = rows(DATA / "round3" / "cases.jsonl")
    labels = rows(DATA / "round3-nav-described" / "sol-labels.fresh.jsonl")
    runs = (json.loads(path.read_text()) for path in (DATA / "round3-nav-described" / "run").glob("*.json"))
    jev = {r["case_id"]: {q: a["noul"] for q, a in r["response"]["answers"].items() if a["type"] == "noul"} for r in runs}
    return [entry("round 3", cid, jev[cid], sol(labels[cid]), cases[cid]["code_facts"], compose_frozen, "contradicts_code")
            for cid in sorted(jev)]


def round4() -> list[dict]:
    cases, passes = rows(DATA / "round4" / "cases.jsonl"), rows(DATA / "round4" / "pass.jsonl")
    labels, reasked = rows(DATA / "round4" / "sol-labels.jsonl"), rows(DATA / "round4-definitions-elsewhere" / "rows.jsonl")
    result = []
    for cid, row in passes.items():
        p = dict(row.get("first_answer", row)["probabilities"])
        p.update(reasked.get(cid, {}).get("stale_reask", {}).get("probabilities", {}))
        result.append(entry("round 4", cid, p, sol(labels[cid]), {**NOT_A_DOC, **cases[cid]["code_facts"]}, compose, "stale"))
    return result


def doc_round(name: str, folder: str) -> list[dict]:
    cases, passes, labels = (rows(DATA / folder / f) for f in ("cases.jsonl", "pass.jsonl", "sol-labels.jsonl"))
    return [entry(name, cid, row.get("first_answer", row)["probabilities"], sol(labels[cid]), cases[cid]["code_facts"],
                  compose, "stale") for cid, row in passes.items()]


def entry(round_name: str, cid: str, p: dict, key_p: dict, facts: dict, rule, stale_name: str) -> dict:
    action = rule.readout_a(p, facts)
    band = rule.band_reasons if rule is compose else rule.escalation_reasons
    return {"round": round_name, "case": cid, "p": p, "action": action, "key": rule.readout_a(key_p, facts),
            "escalated": bool(rule.escalation_reasons(p, facts)), "escalated_by_band": bool(band(p, facts)),
            "confidence": confidence(rule, p, facts, action, stale_name)}


def confidence(rule, p: dict, facts: dict, action: str, stale_name: str) -> float:
    path = rule.decision_path(p, facts)
    if action == "fix_stale":
        return path[stale_name]
    return min(max(value, 1 - value) for value in path.values())


def band_of(value: float) -> str:
    return next(f"{low:.2f}-{min(high, 1.0):.2f}" for low, high in BANDS if low <= value < high)


def band_table(entries: list[dict]) -> list[str]:
    counts = defaultdict(lambda: [0, 0])
    for e in entries:
        if not e["escalated"]:
            cell = counts[(e["action"], band_of(e["confidence"]))]
            cell[0] += 1
            cell[1] += e["action"] == e["key"]
    return [f"  {action:<17} {band}: {right} of {n} right" for (action, band), (n, right) in sorted(counts.items())]


def stale_lines(entries: list[dict]) -> list[str]:
    lines = []
    for e in entries:
        if e["action"] == "fix_stale" and not e["escalated_by_band"]:
            parts = {q: round(e["p"][q], 2) for q in (*compose.STALE_PARTS, "contradicts_code") if q in e["p"]}
            lines.append(f"  {e['round']} {e['case']}: {parts} key {e['key']} -> {'right' if e['key'] == 'fix_stale' else 'WRONG'}")
    return lines


def bar_lines(entries: list[dict]) -> list[str]:
    stale = [e for e in entries if e["action"] == "fix_stale" and not e["escalated_by_band"] and DIFFERS in e["p"]]
    lines = []
    for bar in CANDIDATE_BARS:
        sent = [e for e in stale if e["p"][DIFFERS] < bar]
        wrong = [e["case"] for e in sent if e["key"] != "fix_stale"]
        right = [e["case"] for e in sent if e["key"] == "fix_stale"]
        kept = [e for e in stale if e["p"][DIFFERS] >= bar]
        lines.append(f"  bar {bar:.2f}: sends {len(sent)} to the calling agent ({len(wrong)} wrong verdicts removed {wrong}, "
                     f"{len(right)} right ones lost {right}); still decided {len(kept)}, "
                     f"{sum(e['key'] == 'fix_stale' for e in kept)} of them right")
    return lines


def main() -> None:
    rounds = [round3(), round4(), doc_round("docs 1", "docs"), doc_round("docs 2", "docs2")]
    everything = [e for entries in rounds for e in entries]
    for entries in [*rounds, everything]:
        name = entries[0]["round"] if entries is not everything else "all rounds"
        decided = [e for e in entries if not e["escalated"]]
        print(f"{name}: decided {len(decided)} of {len(entries)}, right {sum(e['action'] == e['key'] for e in decided)}")
        print("\n".join(band_table(entries)))
    print("Every 'fix stale comment' the band alone leaves decided:")
    print("\n".join(stale_lines(everything)))
    print(f"Bar on 'the code's version differs' (applied: {compose.STALE_DECIDES_AT:.2f}; rounds with the three stale questions):")
    print("\n".join(bar_lines(everything)))


if __name__ == "__main__":
    main()
