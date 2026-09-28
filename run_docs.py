"""Run the tool, as `classify.py` runs it, on one round of sampled comments.

Before any Jev call every packet is rebuilt from git objects and compared with `<round dir>/cases.jsonl`,
the packet the Sol labels are given; one difference stops the run. Each comment goes through
`sweep.review_found`: the first answer (with the list-claim question when the list check fires), the
definition fetch before "fix stale comment", the list entries, the search only where the gate allows
it, and the rewrite job of a decided rewrite. Every exchange is journaled.
usage: run-slot -- uv run --project <jev-navigator> --extra typesafe python run_docs.py <round dir> <questions.json>
"""

import json
import sys
from pathlib import Path

from comment_discovery import FoundComment
from comment_review import MEASURED_CONTEXT, comment_state, question_set
from journaled_client import journaled_judge
from run_round4 import case_of, index_of
from sweep import review_found


def main() -> None:
    round_dir, questions_path = Path(sys.argv[1]), Path(sys.argv[2])
    raws = [json.loads(line) for line in (round_dir / "cases.jsonl").read_text().splitlines()]
    indexes = {raw["case_id"]: index_of(raw) for raw in raws}
    differing = [raw["case_id"] for raw in raws
                 if comment_state(case_of(raw), *MEASURED_CONTEXT(indexes[raw["case_id"]], case_of(raw))) != raw["state"]]
    print(f"packets equal to the labelled ones: {len(raws) - len(differing)} of {len(raws)}", flush=True)
    if differing:
        sys.exit(f"refusing to ask Jev: packets differ for {differing}")
    questions = question_set(json.loads(questions_path.read_text()))
    judge = journaled_judge(round_dir, {raw["provenance"]["repository"] for raw in raws})
    with (round_dir / "pass.jsonl").open("w") as passes:
        for raw in raws:
            row = review_found(indexes[raw["case_id"]], judge, FoundComment(case_of(raw), raw["kind"]), questions)
            passes.write(json.dumps({"case_id": raw["case_id"], **row}) + "\n")
            print(raw["case_id"], row["action"], row["decided_by"], flush=True)
    print(f"Jev comment requests {judge.calls}")


if __name__ == "__main__":
    main()
