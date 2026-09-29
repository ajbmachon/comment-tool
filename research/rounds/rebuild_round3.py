"""Rerun the 30 round-3 comments through the directive, reading every file at its case commit.

Before any Jev call it builds all 30 states and compares them with the packets the reference
labels were given (`--expect <cases.jsonl>`); one difference stops the run, because a label is
valid only for its exact packet. Every Jev exchange is journaled; the store keeps requests.

usage: uv run --project ~/Projects/jev-navigator --extra typesafe \
         python rebuild_round3.py <out_dir> <measured|unmeasured> [--expect <cases.jsonl>]
"""

import json
import sys
from pathlib import Path

from comment_tool.config import DATA
from comment_tool.core.comment_review import (
    MEASURED_CONTEXT,
    UNMEASURED_CONTEXT,
    comment_state,
    question_set,
    review_comment,
)
from comment_tool.journal.journaled_client import journaled_judge
from comment_tool.questions import path as _qpath
from research.rounds.run_round4 import case_of, index_of

sys.path.insert(0, str(DATA / "round3"))
import compose_frozen  # noqa: E402  the rule round 3 was measured with

CONTEXTS = {"measured": MEASURED_CONTEXT, "unmeasured": UNMEASURED_CONTEXT}


def differing_states(raws: list[dict], indexes: dict, context, expected: dict) -> list[str]:
    differing = []
    for raw in raws:
        case = case_of(raw)
        if comment_state(case, *context(indexes[raw["case_id"]], case)) != expected[raw["case_id"]]:
            differing.append(raw["case_id"])
    return differing


def require_expected_states(raws: list[dict], indexes: dict, context, expected_path: Path) -> None:
    expected = {c["case_id"]: c["state"] for c in map(json.loads, expected_path.read_text().splitlines())}
    differing = differing_states(raws, indexes, context, expected)
    print(f"states equal to {expected_path}: {len(raws) - len(differing)} of {len(raws)}", flush=True)
    if differing:
        sys.exit(f"refusing to ask Jev: packets differ for {differing}")


def main() -> None:
    out, context = Path(sys.argv[1]), CONTEXTS[sys.argv[2]]
    out.mkdir(parents=True, exist_ok=True)
    raws = [json.loads(line) for line in (DATA / "round3" / "cases.jsonl").read_text().splitlines()]
    indexes = {raw["case_id"]: index_of(raw) for raw in raws}
    if "--expect" in sys.argv:
        require_expected_states(raws, indexes, context, Path(sys.argv[sys.argv.index("--expect") + 1]))
    questions = question_set(json.loads((_qpath("questions.json")).read_text()))
    repositories = {raw["provenance"]["repository"] for raw in raws}
    judge = journaled_judge(out, repositories)
    with (out / "pass.jsonl").open("w") as passes:
        for raw in raws:
            row = review_comment(indexes[raw["case_id"]], judge, case_of(raw), questions, context, compose_frozen)
            passes.write(json.dumps({"case_id": raw["case_id"], "code_facts": raw["code_facts"], **row}) + "\n")
            print(raw["case_id"], row["action"], "escalate" if "escalate" in row else "", flush=True)
    print(f"Jev calls {judge.calls}, input tokens {judge.input_tokens}")


if __name__ == "__main__":
    main()
