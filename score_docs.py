"""Pre-registered scoring for doc-comment review, frozen before any Jev or Sol call on the 30 docs.

Answer key: the current rule (`compose`, doc comments never removed and "only restates the code"
not read for them) applied to Sol's blind yes/no labels on the exact packet (true 1, false 0,
ambiguous 0.5). Bars, on the first answer: at least 70 of 100 decided on their own, and at least 90
of 100 of those matching the key.

Beside the bars, and not counted towards them:
- the tool's final decision (after the definition fetch and any gated search) against the key;
- the actions proposed, for Jev and for the key;
- how often the never-remove rule turned a removal into a rewrite, for Jev and for the key;
- agreement of each yes/no answer with Sol at 0.5, ambiguous labels left out, to show which
  questions' anchors misfire on docs;
- how many comments name a detail the shown code lacks, so their staleness was not checked.
usage: python3 score_docs.py <round dir>
"""

from collections import Counter
from pathlib import Path

import sys

import compose
import score_round4 as shared

NOT_A_DOC = {"doc_comment": False}


def final_line(passes: dict, result: dict) -> str:
    decided = [cid for cid, row in passes.items() if "escalate" not in row]
    hits = [cid for cid in decided if passes[cid]["action"] == result[cid]["key"]]
    return (f"Tool final (after definition fetch and gated search): decided {len(decided)} of {len(passes)}; "
            f"of those {len(hits)} of {len(decided)} match; mistakes {sorted(set(decided) - set(hits))}")


def rewritten_not_removed(probabilities: dict, facts: dict) -> bool:
    as_doc = compose.readout_a(probabilities, facts)
    return as_doc == "rewrite" and compose.readout_a(probabilities, {**facts, **NOT_A_DOC}) in compose.REWRITTEN_NOT_REMOVED


def main() -> None:
    round_dir = Path(sys.argv[1])
    passes, labels = shared.rows(round_dir / "pass.jsonl"), shared.rows(round_dir / "sol-labels.jsonl")
    facts = {cid: case["code_facts"] for cid, case in shared.rows(round_dir / "cases.jsonl").items()}
    result = shared.readouts(compose, passes, labels, facts)
    print(shared.summary("Doc comments, first answer", result))
    print(shared.bars(result))
    print(final_line(passes, result))
    print("Actions, Jev first answer:", dict(Counter(r["a"] for r in result.values())))
    print("Actions, key:", dict(Counter(r["key"] for r in result.values())))
    jev_turned = [cid for cid in passes if rewritten_not_removed(shared.first_answer(passes[cid])["probabilities"], facts[cid])]
    key_turned = [cid for cid in passes if rewritten_not_removed(shared.sol_probabilities(labels[cid]), facts[cid])]
    print(f"Removal turned into rewrite: Jev {len(jev_turned)} {jev_turned}; key {len(key_turned)} {key_turned}")
    print("Jev agreement with Sol at 0.5, ambiguous left out:")
    print("\n".join(shared.agreement_lines(passes, labels)))
    unchecked = [cid for cid, row in passes.items() if compose.stale_check(shared.first_answer(row)["probabilities"])]
    print(f"Staleness not checked (a named detail the shown code lacks): {len(unchecked)} of {len(passes)} {unchecked}")
    print(shared.after_search_line(passes))


if __name__ == "__main__":
    main()
