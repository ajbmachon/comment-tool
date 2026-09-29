"""Readout A, readout B and A+B with escalation, scored against blind Sol labels. No new Jev calls.

A case escalates when B's top action probability is below the cut-off, the chosen function's
argument top probability is below it, a Noul on A's decision path sits inside the uncertain band
(1 - cut-off, cut-off), or A and B pick different actions. The cut-off 0.60 is fixed up front
(self-consistency cookbook); 0.50 and 0.70 are shown only as a sensitivity check.
usage: python3 escalate.py
"""

import json

from comment_tool.config import DATA
from research.analysis.compare_labels import rows
from research.analysis.compare_readouts import jev_answers, matches, readout_a_jev

VALUE = ("explains_hard_code", "states_hidden_rule", "teaches_needed_knowledge", "points_to_owner")


def path_nouls(answers: dict, facts: dict) -> dict:
    """The quantities readout A actually branches on for this case, as probabilities."""
    p = {q: a["noul"] for q, a in answers.items() if a["type"] == "noul"}
    value = max(p[q] for q in VALUE)
    read = {"contradicts_code": p["contradicts_code"], "value (max of four)": value}
    code_time = bool(facts["dates"] or facts["ticket_refs"])
    if not code_time:
        read["has_time_reference"] = p["has_time_reference"]
    if value < 0.5:
        read["name_would_replace"] = p["name_would_replace"]
        read["problem (max of restates, noise)"] = max(p["only_restates_code"], p["is_noise"])
    return read


def escalation_reasons(answers: dict, facts: dict, cutoff: float) -> list[str]:
    reasons = []
    action = answers["action"]
    if max(action["probabilities"].values()) < cutoff:
        reasons.append(f"action top {max(action['probabilities'].values()):.2f}")
    call = action["choice"]
    if call in ("refactor_instead", "link_owner"):
        top = max(answers[f"{call}.kind"]["probabilities"].values())
        if top < cutoff:
            reasons.append(f"{call}.kind top {top:.2f}")
    for name, value in path_nouls(answers, facts).items():
        if 1 - cutoff < value < cutoff:
            reasons.append(f"{name} {value:.2f}")
    a, b = readout_a_jev(answers, facts), call
    if not matches(a, b):
        reasons.append(f"A {a} vs B {b}")
    return reasons


def score(cases, jev, facts, sol, cutoff: float) -> dict:
    decided = hits = caught = wrong_total = 0
    escalated = []
    for cid in cases:
        sol_action = sol[cid]["verdict"]["answers"]["action"]["choice"]
        a = readout_a_jev(jev[cid], facts[cid])
        b = jev[cid]["action"]["choice"]
        wrong = not (matches(a, sol_action) and matches(b, sol_action))
        wrong_total += wrong
        reasons = escalation_reasons(jev[cid], facts[cid], cutoff)
        if reasons:
            escalated.append((cid, sol_action, a, b, reasons, wrong))
            caught += wrong
        else:
            decided += 1
            hits += matches(b, sol_action)
    return {"decided": decided, "hits": hits, "escalated": escalated, "caught": caught, "wrong_total": wrong_total}


def main() -> None:
    sol = rows(str(DATA / "sol-labels.jsonl"))
    jev = jev_answers()
    facts = {c["case_id"]: c["code_facts"] for c in map(json.loads, (DATA / "cases.jsonl").read_text().splitlines())}
    cases = sorted(set(sol) & set(jev))
    n = len(cases)
    a_hits = sum(matches(readout_a_jev(jev[c], facts[c]), sol[c]["verdict"]["answers"]["action"]["choice"]) for c in cases)
    b_hits = sum(matches(jev[c]["action"]["choice"], sol[c]["verdict"]["answers"]["action"]["choice"]) for c in cases)
    print(f"A alone: {a_hits}/{n} agree with Sol, all decided automatically")
    print(f"B alone: {b_hits}/{n} agree with Sol, all decided automatically")
    for cutoff in (0.5, 0.6, 0.7):
        r = score(cases, jev, facts, sol, cutoff)
        print(f"\nA+B with escalate at {cutoff:.2f}: decided {r['decided']}/{n}, agree with Sol on {r['hits']}/{r['decided']} decided; "
              f"escalated {len(r['escalated'])}/{n}; escalations that were A-or-B mistakes {r['caught']} of {r['wrong_total']} mistakes")
        if cutoff == 0.6:
            for cid, sol_action, a, b, reasons, wrong in r["escalated"]:
                mark = "mistake caught" if wrong else "A and B both right"
                print(f"  {cid}: Sol {sol_action}, A {a}, B {b}; {mark}; route calling LLM; because {'; '.join(reasons)}")


if __name__ == "__main__":
    main()
