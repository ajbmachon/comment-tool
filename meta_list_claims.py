"""Export the list-claim requests for en-h11 for question review, with no Jev call.

The tool runs once on en-h11 against a scripted client (A yes, so B is asked too), and both exact
requests are written as review candidates: the first request with A added, and the batch of B.
Intended uses for the other questions are taken, by question name, from the round-4 candidate.
usage: run-slot -- uv run --project <jev-navigator> python meta_list_claims.py <out dir>
"""

import json
import sys
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge
from jev_navigator.judgments.review import export_for_review
from jev_navigator.testing import ScriptedJevClient

from comment_review import question_set
from data_root import DATA
from list_claims import ENTRY_CHECK, LIST_CLAIM
from run_round4 import case_of
from sweep import QUESTIONS, judged

ENGINE = Path.home() / "Projects/analysis-engine"
CLAIM_USE = ("compose.list_claim reads this probability at cut-off 0.5: strictly between 0.40 and 0.60 escalates; "
             "at 0.5 or more, B is asked once per entry. Only asked when code finds a quantifier word and a list literal.")
ENTRY_USE = ("compose.list_claim reads every entry: any entry at 0.20 or less makes the comment 'fix stale comment' "
             "naming those entries; otherwise any entry below 0.60 escalates, named. Before B is asked, a name in an "
             "entry that is defined in the repository but cannot be resolved escalates the comment; a name imported "
             "from a package passes as it is.")


def main() -> None:
    out = Path(sys.argv[1])
    raw = next(c for c in map(json.loads, (DATA / "round4/cases.jsonl").read_text().splitlines()) if c["case_id"] == "en-h11")
    client = ScriptedJevClient(nouls={LIST_CLAIM: 0.95}, default_noul=0.05)
    index = CodeIndex.at_commit(ENGINE, raw["provenance"]["commit"], [raw["provenance"]["path"]])
    judged(index, Judge(client), case_of(raw), question_set(json.loads(QUESTIONS.read_text())))
    earlier_uses = {qid.split("@")[0]: use for qid, use in
                    json.loads((DATA / "meta-round4/candidate.json").read_text())["intended_uses"].items()}
    for number, (state, questions) in enumerate(client.requests):
        uses = {qid: CLAIM_USE if qid.startswith(LIST_CLAIM) else ENTRY_USE if qid.startswith(ENTRY_CHECK.name)
                else earlier_uses[qid.split("@")[0]] for qid in questions}
        export_for_review(state, questions, uses, out / f"candidate-{number}.json", case_id="en-h11",
                          group_id="list-claims", revision_id="approved-2026-09-28")
    print(f"{len(client.requests)} requests exported")


if __name__ == "__main__":
    main()
