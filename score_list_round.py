"""Pre-registered scoring for the first labelled list-claim run, written before any Jev or Sol call.

Answer key: `compose.list_claim` applied to Sol's blind labels (true 1, false 0, ambiguous 0.5) for A
and for each entry. Six lists cannot carry bars, so this reports counts only:
- per list, the tool's list outcome (stale, naming the failing entries; escalate, also for a name
  without a definition; or nothing) against
  the key's, and the controls' expected outcome (every entry passes: nothing to fix);
- A's agreement with Sol at 0.5;
- each entry's agreement with Sol at 0.5, and how many entries Jev put at 0.20 or less (the only answers
  that may decide) with Sol's label for each of them.
Ambiguous labels are left out of agreement counts.

Names without a definition are found again with the current rule, from git only. Since the lead's
post-freeze change (28.09.2026), a name imported from a package passes, so a list the stored run
stopped at the definition check may now reach B, whose per-entry answers were never asked: it is
shown as not scored rather than as the "nothing" its empty entries would give.
usage: uv run python score_list_round.py
"""

import json

from jev_navigator.index.code_index import CodeIndex

import compose
from comment_discovery import found_comments
from data_root import DATA
from list_claims import LIST_CLAIM, entry_items, list_claim_for
from sample_round4 import REPOSITORIES

ROUND = DATA / "list-round"
SOL_TRUTH = {"true": 1.0, "false": 0.0, "ambiguous": 0.5}


def rows(name: str) -> dict:
    return {row["case_id"]: row for row in map(json.loads, (ROUND / name).read_text().splitlines())}


def outcome(claim: compose.ListClaim) -> str:
    if claim.fails:
        return f"stale: {len(claim.failing)} failing"
    return "escalate" if claim.reasons else "nothing"


def jev_claim(row: dict) -> compose.ListClaim:
    return compose.list_claim(row["probabilities"][LIST_CLAIM], row.get("list_claim", {}).get("entries", {}))


def key_claim(case: dict, label: dict) -> compose.ListClaim:
    entries = {item["code"]: SOL_TRUTH[answer["label"]] for item, answer in zip(case["items"], label["entries"], strict=True)}
    return compose.list_claim(SOL_TRUTH[label["A"]["label"]], entries)


def unresolved_now(case: dict) -> tuple[tuple[str, ...], bool]:
    """The names still without a definition, and whether B's items rebuild exactly as labelled."""
    provenance = case["provenance"]
    path, first_line = provenance["path"], provenance["comment_lines"][0]
    index = CodeIndex.at_commit(REPOSITORIES[provenance["repository"]][0], provenance["commit"], [path])
    found = next(f for f in found_comments(index, [path]) if f.case.first_line == first_line)
    prepared = entry_items(index, path, list_claim_for(index, found.case))
    return prepared.unresolved, list(prepared.items) == case["items"]


def tool_outcome(row: dict, unresolved: tuple[str, ...]) -> str:
    if unresolved:
        return f"escalate: no definition for {list(unresolved)}"
    if row.get("list_claim", {}).get("unresolved"):
        return f"not scored: B never asked (the stored run stopped at {row['list_claim']['unresolved']}, which now pass)"
    return outcome(jev_claim(row))


def entry_pairs(case: dict, row: dict, label: dict) -> list[tuple[float, str]]:
    entries = row.get("list_claim", {}).get("entries", {})
    return [(entries[item["code"]], answer["label"]) for item, answer in zip(case["items"], label["entries"], strict=True)
            if item["code"] in entries]


def main() -> None:
    cases, passes, labels = rows("cases.jsonl"), rows("pass.jsonl"), rows("sol-labels.jsonl")
    a_agree, pairs = [], []
    for cid, case in cases.items():
        row, label = passes[cid], labels[cid]["verdict"]
        key = key_claim(case, label)
        unresolved, same_items = unresolved_now(case)
        tool = tool_outcome(row, unresolved)
        print(f"{cid} ({case['role']}): tool {tool}{'' if same_items else ' (B items changed)'} | key {outcome(key)} | A jev "
              f"{row['probabilities'][LIST_CLAIM]:.2f} sol {label['A']['label']} | action {row['action']}"
              f"{' escalated ' + str(row['escalate']['reasons']) if 'escalate' in row else ''}")
        if label["A"]["label"] != "ambiguous":
            a_agree.append((row["probabilities"][LIST_CLAIM] >= compose.CUTOFF) == (label["A"]["label"] == "true"))
        pairs += entry_pairs(case, row, label)
    scored = [(p, sol) for p, sol in pairs if sol != "ambiguous"]
    deciding = [(round(p, 2), sol) for p, sol in pairs if p <= compose.ENTRY_NO_BAR]
    print(f"A agrees with Sol on {sum(a_agree)} of {len(a_agree)}")
    print(f"Entries: agree with Sol at 0.5 on {sum((p >= compose.CUTOFF) == (sol == 'true') for p, sol in scored)} of {len(scored)}")
    print(f"Entries at 0.20 or less (may decide): {len(deciding)}, with Sol's labels {deciding}")


if __name__ == "__main__":
    main()
