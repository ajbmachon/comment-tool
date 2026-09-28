"""Pre-registered scoring for round 6, frozen before any Jev or Sol call on its 30 comments.

Round 6 measures the whole tool as an agent calls it (`classify.py --diff`): comments recent merged pull
requests touched, inline and doc mixed as drawn. It folds in item 9: the parts are measured together.

Answer key: the current rule (`compose`) applied to Sol's blind labels on the exact first packet (true 1,
false 0, ambiguous 0.5), with the comment's code facts. For a comment whose list check ran, the key's
action is "fix stale comment" when `compose.list_claim` on Sol's list labels fails, and rule A's otherwise.

Bars, on the tool's final row (after the definition fetch, the gated search, the stale bar and the list
check): at least 70 of 100 decided, and at least 90 of 100 of those matching the key. A row the tool
escalates is not decided, whatever its reason; that includes a "fix stale comment" sent to the caller by
the provisional 0.80 bar, exactly as in the docs2 figure it is compared with.

Beside the bars, and not counted towards them:
- the same bars on the first answer, comparable with docs2 (19 of 30 decided under the 0.80 bar);
- inline and doc comments separately;
- each part: how often it ran, and where labels allow, how often it was right (definition fetches,
  searches under the gate, list checks, stale-bar escalations, band escalations by reason, staleness
  not checked, rewrite jobs);
- agreement of each yes/no answer with Sol at 0.5, ambiguous labels left out.
usage: python3 score_round6.py
"""

from collections import Counter

import compose
import score_round4 as shared
from data_root import DATA

ROUND = DATA / "round6"
BAR_REASON = "fix stale below bar"


def key_action(case: dict, label: dict, list_label: dict | None) -> str:
    facts = case["code_facts"]
    if list_label is not None and _list_key(case, list_label).fails:
        return "fix_stale"
    return compose.readout_a(shared.sol_probabilities(label), facts)


def _list_key(case: dict, list_label: dict) -> compose.ListClaim:
    entries = {item["code"]: shared.SOL_TRUTH[answer["label"]]
               for item, answer in zip(case["items"], list_label["verdict"]["entries"], strict=True)}
    return compose.list_claim(shared.SOL_TRUTH[list_label["verdict"]["A"]["label"]], entries)


def final_result(passes: dict, keys: dict) -> dict:
    return {cid: {"a": row["action"], "escalated": "escalate" in row, "key": keys[cid]} for cid, row in passes.items()}


def part_lines(passes: dict, keys: dict) -> list[str]:
    reasons = Counter(reason.split(" ")[0] if not reason.startswith(BAR_REASON) else BAR_REASON
                      for row in passes.values() for reason in row.get("escalate", {}).get("reasons", []))
    fetched = {cid: row["definitions"] for cid, row in passes.items() if "definitions" in row}
    searched = {cid: row["search"]["outcome"] for cid, row in passes.items() if "search" in row}
    listed = {cid: row["list_claim"] for cid, row in passes.items() if "list_claim" in row}
    unchecked = [cid for cid, row in passes.items() if "stale_check" in row]
    jobs = [cid for cid, row in passes.items() if "rewrite_job" in row]
    return [
        f"escalation reasons: {dict(reasons)}",
        (f"definition fetches: {len(fetched)}, with unresolved or unknown names in "
         f"{sum(bool(d['unresolved'] or d.get('unknown')) for d in fetched.values())}: {sorted(fetched)}"),
        (f"searches under the gate: {len(searched)} {searched}; decided after the search: "
         f"{sorted(cid for cid, row in passes.items() if row['decided_by'] == 'jev+rule after find_code')}"),
        (f"list checks: {len(listed)}; failing lists {sorted(cid for cid, rec in listed.items() if rec.get('failing'))}; "
         f"key says fix_stale for {sorted(cid for cid in listed if keys[cid] == 'fix_stale')}"),
        f"staleness not checked: {len(unchecked)} {unchecked}",
        f"rewrite jobs: {len(jobs)}; of those the key says rewrite for {sum(keys[cid] == 'rewrite' for cid in jobs)}",
    ]


def split_lines(cases: dict, result: dict) -> list[str]:
    lines = []
    for name, is_doc in (("doc comments", True), ("inline and block comments", False)):
        part = {cid: r for cid, r in result.items() if cases[cid]["code_facts"]["doc_comment"] == is_doc}
        if part:
            lines.append(shared.summary(f"  {name} ({len(part)})", part))
    return lines


def main() -> None:
    cases, passes, labels = (shared.rows(ROUND / name) for name in ("cases.jsonl", "pass.jsonl", "sol-labels.jsonl"))
    list_path = ROUND / "list-sol-labels.jsonl"
    list_labels = shared.rows(list_path) if list_path.exists() else {}
    keys = {cid: key_action(cases[cid], labels[cid], list_labels.get(cid)) for cid in passes}
    final = final_result(passes, keys)
    first = shared.readouts(compose, passes, labels, {cid: case["code_facts"] for cid, case in cases.items()})
    print(shared.summary("Final row (the bars)", final))
    print(shared.bars(final))
    print("\n".join(split_lines(cases, final)))
    print(shared.summary("First answer (as docs2)", first))
    print(shared.bars(first))
    print("Actions, tool final:", dict(Counter(r["a"] for r in final.values())), "key:", dict(Counter(keys.values())))
    print("\n".join(part_lines(passes, keys)))
    print("Jev agreement with Sol at 0.5, ambiguous left out:")
    print("\n".join(shared.agreement_lines(passes, labels)))


if __name__ == "__main__":
    main()
