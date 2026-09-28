"""Compare blind Sol labels with the proposer draft, a partial earlier Sol pass, and the composition rule.

Readout A is applied to Sol's own Noul labels (true 1, false 0, ambiguous 0.5) at the 0.5 direction
boundary, to check that the rule reproduces Sol's chosen action before any Jev answer exists.
usage: python3 compare_labels.py
"""

import json
from collections import Counter
from pathlib import Path

VALUE = ("explains_hard_code", "states_hidden_rule", "teaches_needed_knowledge", "points_to_owner")
A_TO_ACTION = {"stale_fix": "fix_stale", "rename_or_extract": "refactor_instead", "removal": "remove",
               "rewrite": "rewrite", "keep": "keep"}
DRAFT_TO_ACTION = {"rewrite": "rewrite", "remove": "remove", "keep": "keep", "ambiguous": "ambiguous"}


def rows(path: str) -> dict:
    return {r["case_id"]: r for r in map(json.loads, Path(path).read_text().splitlines()) if "verdict" in r}


def p(answer: dict) -> float:
    return {"true": 1.0, "false": 0.0, "ambiguous": 0.5}[answer["label"]]


def readout_a(answers: dict, facts: dict) -> str:
    value = max(p(answers[q]) for q in VALUE)
    time_ref = p(answers["has_time_reference"]) >= 0.5 or bool(facts["dates"] or facts["ticket_refs"])
    problem = max(p(answers["only_restates_code"]), p(answers["is_noise"])) >= 0.5 or time_ref or facts["unowned_todo"]
    if p(answers["contradicts_code"]) >= 0.5:
        return "stale_fix"
    if value < 0.5 and p(answers["name_would_replace"]) >= 0.5:
        return "rename_or_extract"
    if value < 0.5 and problem:
        return "removal"
    if value >= 0.5 and time_ref:
        return "rewrite"
    return "keep"


def main() -> None:
    sol = rows("sol-labels.jsonl")
    earlier = rows("sol-labels.v3-questions-partial.jsonl")
    draft = json.loads(Path("labels.provisional.json").read_text())["labels"]
    facts = {c["case_id"]: c["code_facts"] for c in map(json.loads, Path("cases.jsonl").read_text().splitlines())}
    actions = {cid: r["verdict"]["answers"]["action"]["choice"] for cid, r in sol.items()}
    print("Sol actions:", dict(Counter(actions.values())))
    for q in ("refactor_instead.kind", "link_owner.kind"):
        print(f"Sol {q} where chosen:", {cid: sol[cid]["verdict"]["answers"][q]["choice"] for cid, a in actions.items() if q.startswith(a)})
    print("Sol score levels:", dict(Counter(r["verdict"]["answers"]["change_risk_without_comment"]["level"] for r in sol.values())))
    nouls = [q for q, a in next(iter(sol.values()))["verdict"]["answers"].items() if "label" in a]
    for q in nouls:
        print(f"  {q:<26}", dict(Counter(r["verdict"]["answers"][q]["label"] for r in sol.values())))
    print("\nDraft vs Sol action:")
    agree = 0
    for cid in sorted(sol):
        mine = DRAFT_TO_ACTION[draft[cid]["outcome"]]
        agree += mine == actions[cid]
        if mine != actions[cid]:
            print(f"  {cid}: draft {mine}, Sol {actions[cid]} ({sol[cid]['verdict']['answers']['action']['note'][:140]})")
    print(f"  agree {agree} of {len(sol)}")
    print("\nReadout A applied to Sol's Nouls vs Sol's action:")
    agree = 0
    for cid in sorted(sol):
        a = A_TO_ACTION[readout_a(sol[cid]["verdict"]["answers"], facts[cid])]
        same = a == actions[cid] or (a == "rewrite" and actions[cid] == "link_owner")
        agree += same
        if not same:
            print(f"  {cid}: rule gives {a}, Sol chose {actions[cid]}")
    print(f"  agree {agree} of {len(sol)}")
    print("\nLabel stability, earlier partial Sol pass (same packets, same wording for these questions):")
    shared = [q for q in nouls if all(q in r["verdict"]["answers"] for r in earlier.values())]
    same = total = 0
    for cid in sorted(set(sol) & set(earlier)):
        for q in shared:
            total += 1
            if sol[cid]["verdict"]["answers"][q]["label"] == earlier[cid]["verdict"]["answers"][q]["label"]:
                same += 1
            else:
                print(f"  {cid} {q}: {earlier[cid]['verdict']['answers'][q]['label']} -> {sol[cid]['verdict']['answers'][q]['label']}")
    print(f"  same {same} of {total} labels over {len(set(sol) & set(earlier))} cases")
    errors = [json.loads(l) for l in Path("sol-labels.jsonl").read_text().splitlines() if "error" in json.loads(l)]
    print(f"\nerrors recorded: {len(errors)}")


if __name__ == "__main__":
    main()
