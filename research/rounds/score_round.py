"""Score readout A, readout B and A+B with escalation against blind Sol labels for one round.

Escalate when B's top action probability is below the cut-off, the chosen argument's top probability
is below it, a quantity on A's decision path is inside (1 - cut-off, cut-off), or A and B differ.
The cut-off 0.60 is fixed; 0.50 and 0.70 are a sensitivity check only.
usage: python3 score_round.py <round_dir>
"""

import json
import sys
from pathlib import Path

from comment_tool.config import DATA

sys.path.insert(0, str(DATA / "round3"))
from compose_frozen import (  # the rule round 3 and the lib sweep were measured with
    decision_path,
    readout_a,
)

SOL_TRUTH = {"true": 1.0, "false": 0.0, "ambiguous": 0.5}
SAME_ACTION = {("rewrite", "link_owner"), ("link_owner", "rewrite")}


def load_rows(path: Path) -> dict:
    return {r["case_id"]: r for r in map(json.loads, path.read_text().splitlines()) if "verdict" in r}


def matches(ours: str, sol: str) -> bool:
    return ours == sol or (ours, sol) in SAME_ACTION


def nouls(answers: dict) -> dict:
    return {q: a["noul"] for q, a in answers.items() if a["type"] == "noul"}


def escalation_reasons(answers: dict, facts: dict, cutoff: float) -> list[str]:
    reasons = []
    top = max(answers["action"]["probabilities"].values())
    if top < cutoff:
        reasons.append(f"action top {top:.2f}")
    call = answers["action"]["choice"]
    if call in ("refactor_instead", "link_owner"):
        argument_top = max(answers[f"{call}.kind"]["probabilities"].values())
        if argument_top < cutoff:
            reasons.append(f"{call}.kind top {argument_top:.2f}")
    for name, value in decision_path(nouls(answers), facts).items():
        if 1 - cutoff < value < cutoff:
            reasons.append(f"{name} {value:.2f}")
    a = readout_a(nouls(answers), facts)
    if not matches(a, call):
        reasons.append(f"A {a} vs B {call}")
    return reasons


def main() -> None:
    root = Path(sys.argv[1])
    sol = load_rows(root / "sol-labels.jsonl")
    jev = {r["case_id"]: r["response"]["answers"] for r in (json.loads(p.read_text()) for p in sorted((root / "run").glob("*.json")))}
    facts = {c["case_id"]: c["code_facts"] for c in map(json.loads, (root / "cases.jsonl").read_text().splitlines())}
    cases = sorted(set(sol) & set(jev))
    n = len(cases)
    truth = {c: sol[c]["verdict"]["answers"]["action"]["choice"] for c in cases}
    a_of = {c: readout_a(nouls(jev[c]), facts[c]) for c in cases}
    b_of = {c: jev[c]["action"]["choice"] for c in cases}
    wrong = {c for c in cases if not (matches(a_of[c], truth[c]) and matches(b_of[c], truth[c]))}
    print(f"{n} cases. Sol actions: {dict(sorted(__import__('collections').Counter(truth.values()).items()))}")
    print("| Readout | Decided automatically | Match Sol, of decided | Escalated | A-or-B mistakes escalated |")
    print("|---|---|---|---|---|")
    print(f"| A alone | {n} of {n} | {sum(matches(a_of[c], truth[c]) for c in cases)} of {n} | 0 | - |")
    print(f"| B alone | {n} of {n} | {sum(matches(b_of[c], truth[c]) for c in cases)} of {n} | 0 | - |")
    detail = []
    for cutoff in (0.5, 0.6, 0.7):
        escalated = {c: escalation_reasons(jev[c], facts[c], cutoff) for c in cases}
        escalated = {c: r for c, r in escalated.items() if r}
        decided = [c for c in cases if c not in escalated]
        hits = sum(matches(b_of[c], truth[c]) for c in decided)
        print(f"| A+B, escalate at {cutoff:.2f} | {len(decided)} of {n} | {hits} of {len(decided)} | {len(escalated)} | {len(wrong & set(escalated))} of {len(wrong)} |")
        if cutoff == 0.6:
            detail = [(c, escalated.get(c)) for c in cases]
    print("\nAt 0.60, per case (Sol / A / B, and why escalated):")
    for c, reasons in detail:
        status = "escalated: " + "; ".join(reasons) if reasons else "decided"
        flag = " MISTAKE" if c in wrong else ""
        print(f"  {c}: Sol {truth[c]}, A {a_of[c]}, B {b_of[c]}{flag}; {status}")
    print("\nJev Noul agreement with Sol at 0.5 (ambiguous excluded):")
    for q in nouls(jev[cases[0]]):
        pairs = [(jev[c][q]["noul"] >= 0.5, sol[c]["verdict"]["answers"][q]["label"]) for c in cases]
        scored = [(j, s == "true") for j, s in pairs if s != "ambiguous"]
        print(f"  {q:<26} {sum(j == s for j, s in scored)}/{len(scored)}")


if __name__ == "__main__":
    main()
