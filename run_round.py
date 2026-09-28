"""Run the tool, as `classify.py` runs it, on one registered round.

Before any Jev call, `frozen_round.verify` checks the round against its registration: the repository's
sources, the exact question file, the cases and every case record rebuilt in full from git objects, the
library commit, the Python version and the secret-scan receipt; one difference stops the run. Each comment
then goes through `sweep.review_found`: the first answer, the definition fetch before "fix stale comment",
the search only where the gate allows it, and the rewrite job of a decided rewrite. Every exchange is
journaled. The rows are written to `pass.jsonl.partial` and renamed to `pass.jsonl` only when all
registered comments are done, so a partial run never looks complete.
usage: uv run python run_round.py <round name>      (the round folder under data_root.DATA)
"""

import json
import os
import sys

from comment_discovery import FoundComment
from comment_review import question_set
from data_root import DATA
from frozen_round import rows_exactly, verify
from journaled_client import journaled_judge
from run_round4 import case_of, index_of
from sweep import review_found


def main() -> None:
    round_dir = DATA / sys.argv[1]
    manifest = verify(round_dir)
    raws = rows_exactly(round_dir / "cases.jsonl", manifest.case_ids)
    questions = question_set(manifest.questions())
    judge = journaled_judge(round_dir, {raw["provenance"]["repository"] for raw in raws.values()})
    partial = round_dir / "pass.jsonl.partial"
    with partial.open("w") as passes:
        for case_id in manifest.case_ids:
            raw = raws[case_id]
            row = review_found(index_of(raw), judge, FoundComment(case_of(raw), raw["kind"]), questions)
            passes.write(json.dumps({"case_id": case_id, **row}) + "\n")
            print(case_id, row["action"], row["decided_by"], flush=True)
    os.replace(partial, round_dir / "pass.jsonl")
    print(f"Jev comment requests {judge.calls}")


if __name__ == "__main__":
    main()
