"""Pre-registered scoring for round 6, frozen before any Jev or Sol call on its 30 comments.

What round 6 measures: whether the tool, run as an agent calls it (`classify.py --diff`), reproduces Sol's
judgments through rule A on 30 fresh model-reviewable comments that recent pull requests touched (23 doc
comments and 7 block comments, as drawn). Rule A itself was approved separately; the round does not test
whether rule A is the right policy. List claims are not part of this round.

Before scoring, `frozen_round.verify` checks the registration again (the manifest bound by its hash in
`FROZEN.txt`, and agreeing with the code registration in `registered_rounds.py`, which also fixes the
question file), and the rows must be exactly the 30 registered ids in the cases, the result and the Sol
labels, with no duplicate, gap or extra. A run with a leftover `pass.jsonl.partial`, or without
`pass.jsonl`, is not complete and is refused; a partial run is never a smaller round. Every journaled
request must have asked the registered first question set or the stale-only re-ask set (or only the
gated search's own questions), and each result row is proven from the journal by `row_audit.audit_row`
(first request state and question set, request hashes, answers, and the action, decision path,
escalation and `decided_by` recomputed with the frozen rule). Each Sol label must name the hash of the exact packet and
questions it was given. A list claim anywhere fails the scoring.

Answer key: the frozen rule (`round6/compose_frozen.py`, hash-pinned) applied to Sol's labels on the exact
first packet (true 1, false 0, ambiguous 0.5), with the case's code facts.

Bars, on the tool's final row (after the definition fetch, the gated search and the stale bar): at least
70 of 100 decided, and at least 90 of 100 of those matching the key. An escalated row is not decided,
whatever its reason, including a "fix stale comment" sent to the caller by the provisional 0.80 bar, as in
the docs2 figure it is compared with.

Beside the bars, and not counted towards them: the same on the first answer (comparable with docs2), doc
and block comments separately, each part's count (definition fetches, searches, stale-bar and band
escalations by reason, staleness not checked, rewrite jobs), and each question's agreement with Sol.
usage: uv run python score_round6.py      (from a checkout at the round's registered repository commit)
"""

from collections import Counter

import research.rounds.score_round4 as shared
from comment_tool.config import DATA
from comment_tool.core.comment_review import question_set
from research.labels.sol_labels import request_sha256 as sol_request_sha256
from research.rounds.frozen_round import FrozenRoundError, Manifest, completed_rows, frozen_rule, rows_exactly, verify
from research.rounds.row_audit import audit_journal, audit_row, journal_exchanges, registered_question_sets

ROUND = DATA / "round6"
BAR_REASON = "fix stale below bar"


def verified_inputs(manifest: Manifest, rule) -> tuple[dict, dict, dict]:
    cases = rows_exactly(ROUND / "cases.jsonl", manifest.case_ids)
    passes, labels = (completed_rows(ROUND, name, manifest.case_ids) for name in ("pass.jsonl", "sol-labels.jsonl"))
    if any("items" in case for case in cases.values()) or any("list_claim" in row for row in passes.values()):
        raise FrozenRoundError("a list claim is in round 6; list claims are not part of this round")
    questions = manifest.questions()
    sets = registered_question_sets(question_set(questions))
    audit_journal(ROUND / "journal.jsonl", sets)
    exchanges = journal_exchanges(ROUND / "journal.jsonl")
    for case_id, row in passes.items():
        audit_row(row, cases[case_id], exchanges, rule, sets)
    for case_id, label in labels.items():
        if "verdict" not in label or label["request_sha256"] != sol_request_sha256(cases[case_id]["state"], questions):
            raise FrozenRoundError(f"{case_id}: Sol label missing, failed or given another packet")
    return cases, passes, labels


def part_lines(passes: dict, keys: dict) -> list[str]:
    reasons = Counter(BAR_REASON if reason.startswith(BAR_REASON) else reason.split(" ")[0]
                      for row in passes.values() for reason in row.get("escalate", {}).get("reasons", []))
    fetched = {cid: row["definitions"] for cid, row in passes.items() if "definitions" in row}
    searched = {cid: row["search"]["outcome"] for cid, row in passes.items() if "search" in row}
    jobs = [cid for cid, row in passes.items() if "rewrite_job" in row]
    return [
        f"escalation reasons: {dict(reasons)}",
        (f"definition fetches: {len(fetched)}, with unresolved or unknown names in "
         f"{sum(bool(d['unresolved'] or d.get('unknown')) for d in fetched.values())}: {sorted(fetched)}"),
        (f"searches under the gate: {len(searched)} {searched}; decided after the search: "
         f"{sorted(cid for cid, row in passes.items() if row['decided_by'] == 'jev+rule after find_code')}"),
        f"staleness not checked: {sum('stale_check' in row for row in passes.values())}",
        f"rewrite jobs: {len(jobs)}; of those the key says rewrite for {sum(keys[cid] == 'rewrite' for cid in jobs)}",
    ]


def split_lines(cases: dict, result: dict) -> list[str]:
    lines = []
    for name, is_doc in (("doc comments", True), ("block and inline comments", False)):
        part = {cid: r for cid, r in result.items() if cases[cid]["code_facts"]["doc_comment"] == is_doc}
        if part:
            lines.append(shared.summary(f"  {name} ({len(part)})", part))
    return lines


def main() -> None:
    manifest = verify(ROUND)
    rule = frozen_rule(manifest)
    cases, passes, labels = verified_inputs(manifest, rule)
    facts = {cid: case["code_facts"] for cid, case in cases.items()}
    keys = {cid: rule.readout_a(shared.sol_probabilities(labels[cid]), facts[cid]) for cid in manifest.case_ids}
    final = {cid: {"a": row["action"], "escalated": "escalate" in row, "key": keys[cid]} for cid, row in passes.items()}
    first = shared.readouts(rule, passes, labels, facts)
    print("Measures: the tool reproduces Sol's judgments through rule A (rule A approved separately)")
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
