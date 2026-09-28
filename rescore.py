"""Rescore rounds 1 and 2 from stored answers: readout A decides, B only suggests the phrasing.

A escalates when a quantity on its decision path lies strictly between 0.40 and 0.60. Code facts are
recomputed from the stored comment text with the current rules (dates inside names do not count).
Each round is scored against two references: Sol's direct action pick, and Sol's own yes/no labels
combined by the same rule (true 1, false 0, ambiguous 0.5). Round 1 asked one "explains hard code"
question; both halves of the split question take its value there.
usage: python3 rescore.py
"""

import json
import sys
from pathlib import Path

from data_root import DATA

sys.path.insert(0, str(DATA / "round3"))
from compose_frozen import (  # the rule round 3 and the lib sweep were measured with
    escalation_reasons,
    readout_a,
)

from extract_cases import code_facts
from score_round import load_rows, matches, nouls

ROUNDS = {"Round 1 (32 comments, rule order fixed after seeing them)": DATA,
          "Round 2 (30 fresh comments, after the fact)": DATA / "round2"}
SOL_TRUTH = {"true": 1.0, "false": 0.0, "ambiguous": 0.5}


def with_split_halves(p: dict) -> dict:
    if "explains_hard_code" in p:
        return {**p, "code_is_hard_to_follow": p["explains_hard_code"], "explains_how_or_why": p["explains_hard_code"]}
    return p


def facts_of(case: dict) -> dict:
    prefix = "#" if case["state"]["code"]["language"] == "python" else "//"
    return code_facts(case["state"]["comment"]["text"].split("\n"), prefix)


def escalates(p: dict, facts: dict) -> bool:
    return bool(escalation_reasons(p, facts))


def score(root: Path) -> dict:
    sol = load_rows(root / "sol-labels.jsonl")
    jev = {r["case_id"]: r["response"]["answers"] for r in (json.loads(p.read_text()) for p in sorted((root / "run").glob("*.json")))}
    cases = {c["case_id"]: c for c in map(json.loads, (root / "cases.jsonl").read_text().splitlines())}
    ids = sorted(set(sol) & set(jev))
    out = {"n": len(ids), "rows": []}
    for cid in ids:
        facts = facts_of(cases[cid])
        p = with_split_halves(nouls(jev[cid]))
        sol_answers = sol[cid]["verdict"]["answers"]
        sol_p = with_split_halves({q: SOL_TRUTH[a["label"]] for q, a in sol_answers.items() if "label" in a})
        out["rows"].append({
            "id": cid, "a": readout_a(p, facts), "escalate": escalates(p, facts),
            "direct": sol_answers["action"]["choice"], "combined": readout_a(sol_p, facts),
            "b": jev[cid]["action"]["choice"],
        })
    return out


def summary(result: dict, reference: str) -> str:
    rows, n = result["rows"], result["n"]
    decided = [r for r in rows if not r["escalate"]]
    hits = sum(matches(r["a"], r[reference]) for r in decided)
    wrong = [r for r in rows if not matches(r["a"], r[reference])]
    caught = sum(r["escalate"] for r in wrong)
    all_hits = sum(matches(r["a"], r[reference]) for r in rows)
    return (f"A alone {all_hits} of {n}; decided {len(decided)} of {n}, match {hits} of {len(decided)}; "
            f"escalated {n - len(decided)}; A mistakes escalated {caught} of {len(wrong)}")


def main() -> None:
    for name, root in ROUNDS.items():
        result = score(root)
        print(f"\n{name}")
        for reference, label in (("direct", "(a) Sol's direct action"), ("combined", "(b) Sol's labels combined by the rule")):
            print(f"  {label}: {summary(result, reference)}")
        ceiling = sum(matches(r["combined"], r["direct"]) for r in result["rows"])
        print(f"  (b) matches (a) on {ceiling} of {result['n']}")
        print(f"  B suggestion matches (a) on {sum(matches(r['b'], r['direct']) for r in result['rows'])} of {result['n']}")
        for r in result["rows"]:
            if not (matches(r["a"], r["direct"]) and matches(r["a"], r["combined"])):
                print(f"    {r['id']}: A {r['a']}{' (escalated)' if r['escalate'] else ''}, (a) {r['direct']}, (b) {r['combined']}")


if __name__ == "__main__":
    main()
