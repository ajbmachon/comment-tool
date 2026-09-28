"""Compare Jev readout A (Nouls composed in code) and readout B (the dispatched action) with blind Sol labels.

Cut-offs stay at the 0.5 direction boundary here; per-question agreement with Sol's Noul labels is
reported so cut-offs can later be fitted on Sol labels and checked on held-out cases.
usage: python3 compare_readouts.py
"""

import json
from collections import Counter
from pathlib import Path

from compare_labels import A_TO_ACTION, readout_a, rows

HERE = Path(__file__).resolve().parent
LINK_EQUIVALENT = {("rewrite", "link_owner"), ("link_owner", "rewrite")}

def jev_answers() -> dict:
    out = {}
    for path in sorted((HERE / "run").glob("*.json")):
        record = json.loads(path.read_text())
        out[record["case_id"]] = record["response"]["answers"]
    return out

def readout_a_jev(answers: dict, facts: dict) -> str:
    view = {q: {"label": "true" if a["noul"] >= 0.5 else "false"} for q, a in answers.items() if a["type"] == "noul"}
    return A_TO_ACTION[readout_a(view, facts)]

def readout_b_jev(answers: dict) -> tuple[str, str | None, float]:
    call = answers["action"]["choice"]
    confidence = answers["action"]["confidence"]
    kind = None
    if call in ("refactor_instead", "link_owner"):
        argument = answers[f"{call}.kind"]
        kind, confidence = argument["choice"], min(confidence, argument["confidence"])
    return call, kind, confidence

def matches(ours: str, sol: str) -> bool:
    return ours == sol or (ours, sol) in LINK_EQUIVALENT

def main() -> None:
    sol = rows(str(HERE / "sol-labels.jsonl"))
    jev = jev_answers()
    facts = {c["case_id"]: c["code_facts"] for c in map(json.loads, (HERE / "cases.jsonl").read_text().splitlines())}
    cases = sorted(set(sol) & set(jev))
    a_hits = b_hits = strict_b = 0
    lines = []
    for cid in cases:
        sol_action = sol[cid]["verdict"]["answers"]["action"]["choice"]
        a = readout_a_jev(jev[cid], facts[cid])
        b, kind, conf = readout_b_jev(jev[cid])
        a_hits += matches(a, sol_action)
        b_hits += matches(b, sol_action)
        strict_b += b == sol_action
        if not (matches(a, sol_action) and matches(b, sol_action)):
            lines.append(f"  {cid}: Sol {sol_action:<16} A {a:<16} B {b}{'(' + kind + ')' if kind else ''} conf {conf:.2f}")
    print(f"{len(cases)} cases with both Sol labels and Jev answers")
    print(f"A agrees with Sol on {a_hits}; B agrees on {b_hits} (rewrite and link_owner counted as one); B exact {strict_b}")
    print("Cases where A or B differs from Sol:")
    print("\n".join(lines))
    print("\nPer-question agreement of Jev (0.5 boundary) with Sol's Noul labels, ambiguous excluded:")
    nouls = [q for q, a in jev[cases[0]].items() if a["type"] == "noul"]
    for q in nouls:
        hits = total = 0
        misses = []
        for cid in cases:
            label = sol[cid]["verdict"]["answers"][q]["label"]
            if label == "ambiguous":
                continue
            total += 1
            ok = (jev[cid][q]["noul"] >= 0.5) == (label == "true")
            hits += ok
            if not ok:
                misses.append(f"{cid}(Sol {label}, Jev {jev[cid][q]['noul']:.2f})")
        print(f"  {q:<26} {hits}/{total}  {' '.join(misses)}")
    levels = [(sol[c]["verdict"]["answers"]["change_risk_without_comment"]["level"], jev[c]["change_risk_without_comment"]["score"]) for c in cases]
    close = sum(abs(s - j) <= 0.5 for s, j in levels)
    print(f"\nScore: Jev expected level within 0.5 of Sol's level on {close} of {len(levels)}")
    kinds = Counter()
    for c in cases:
        for q in ("refactor_instead.kind", "link_owner.kind"):
            kinds[q] += jev[c][q]["choice"] == sol[c]["verdict"]["answers"][q]["choice"]
    print("Argument agreement with Sol (all cases, as if chosen):", dict(kinds))

if __name__ == "__main__":
    main()
