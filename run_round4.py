"""Run the frozen round-4 tool on the 30 round-4 comments, the same way the sweep judges a comment.

Before any Jev call every packet is rebuilt from git objects and compared with `round4/cases.jsonl`,
the packet the Sol labels are given; one difference stops the run. Every exchange is journaled.
usage: uv run python run_round4.py
"""

import json
import sys
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex

from comment_review import MEASURED_CONTEXT, CommentCase, comment_state, question_set
from data_root import DATA
from journaled_client import journaled_judge
from sample_round4 import REPOSITORIES
from sweep import judged

HERE = Path(__file__).resolve().parent
ROUND = DATA / "round4"
ROUND4_QUESTIONS = HERE / "questions.round4.json"
"""The questions round 4, the first doc round, the gate replay and the rewrite pilot were asked."""


def case_of(raw: dict) -> CommentCase:
    """Cases sampled before doc comments were reviewed carry no `doc_comment` fact; rounds 3 and 4
    took only comments code did not keep, so none of them is a doc comment."""
    first, last = raw["provenance"]["comment_lines"]
    return CommentCase(raw["provenance"]["path"], first, last, raw["state"]["comment"]["text"],
                       raw["state"]["code"]["language"], {"doc_comment": False, **raw["code_facts"]})


def index_of(raw: dict) -> CodeIndex:
    provenance = raw["provenance"]
    return CodeIndex.at_commit(REPOSITORIES[provenance["repository"]][0], provenance["commit"], [provenance["path"]])


def main() -> None:
    raws = [json.loads(line) for line in (ROUND / "cases.jsonl").read_text().splitlines()]
    indexes = {raw["case_id"]: index_of(raw) for raw in raws}
    differing = [raw["case_id"] for raw in raws
                 if comment_state(case_of(raw), *MEASURED_CONTEXT(indexes[raw["case_id"]], case_of(raw))) != raw["state"]]
    print(f"packets equal to the labelled ones: {len(raws) - len(differing)} of {len(raws)}", flush=True)
    if differing:
        sys.exit(f"refusing to ask Jev: packets differ for {differing}")
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    judge = journaled_judge(ROUND, {raw["provenance"]["repository"] for raw in raws})
    with (ROUND / "pass.jsonl").open("w") as passes:
        for raw in raws:
            row = judged(indexes[raw["case_id"]], judge, case_of(raw), questions)
            row.pop("state", None)
            passes.write(json.dumps({"case_id": raw["case_id"], **row}) + "\n")
            print(raw["case_id"], row["action"], row["decided_by"], flush=True)
    print(f"Jev comment requests {judge.calls}")


if __name__ == "__main__":
    main()
