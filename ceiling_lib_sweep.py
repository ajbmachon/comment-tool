"""Replay the stored lib-sweep searches with a growing History and ask the stop question at each size.

Each search's opened places come from the stored requests, in the order they were answered, with
the exact code Jev saw. `ceiling_curve` asks the sweep's stop question over the first 1, 2, ... of
them, so the curve shows where more history stops changing the answer. Only searches that opened
at least two places can show that. The stop question is asked live; nothing else is recomputed.
usage: uv run python ceiling_lib_sweep.py
"""

import json
from collections import defaultdict

from jev_navigator.history import FetchedSpan, HistoryStep, ceiling_curve

from data_root import DATA
from journaled_client import journaled_judge
from sweep import HOLDS_WHAT_COMMENT_IS_ABOUT, STOP_SECTIONS

SWEEP = DATA / "pass" / "lib-a3bde2aa-rebuilt"
OUT = DATA / "ceiling"
SEARCH_PREFIX = "the code this comment describes: "
FOUND_AT = 0.8
MIN_OPENED = 2


def searched_more_than_once() -> set[str]:
    """Comment texts searched at two locations: their stored requests cannot be told apart by text."""
    texts = [json.loads(line)["comment"] for path in SWEEP.glob("apps-*.jsonl")
             for line in path.read_text().splitlines() if "search" in json.loads(line)]
    return {text for text in texts if texts.count(text) > 1}


def stored_searches() -> dict[str, list[dict]]:
    ambiguous = searched_more_than_once()
    by_comment = defaultdict(list)
    for record in map(json.loads, (SWEEP / "answers.jsonl").read_text().splitlines()):
        target = record["request"]["state"].get("target")
        if target and target["description"].removeprefix(SEARCH_PREFIX) not in ambiguous:
            by_comment[target["description"].removeprefix(SEARCH_PREFIX)].append(record)
    return {text: sorted(records, key=lambda r: r["recorded_at"]) for text, records in by_comment.items() if len(records) >= MIN_OPENED}


def history_step(record: dict, commit: str) -> HistoryStep:
    opened = record["request"]["state"]["slice"]
    first, last = opened["lines"].split("-")
    source = {"file": opened["file"], "lines": [int(first), int(last)], "commit": commit}
    found = next(a["noul"] for qid, a in record["answers"].items() if qid.startswith("contains_target"))
    return HistoryStep("open", {"place": f"{opened['file']}:{opened['lines']}"}, (FetchedSpan(source, opened["code"]),),
                       decision="found" if found >= FOUND_AT else "opened")


def main() -> None:
    commit = json.loads(next(SWEEP.glob("apps-*.jsonl")).read_text().splitlines()[0])["commit"]
    judge = journaled_judge(OUT, {"heedvane"})
    with (OUT / "curves.jsonl").open("w") as curves:
        for comment, records in stored_searches().items():
            steps = [history_step(record, commit) for record in records]
            points = ceiling_curve(judge, steps, HOLDS_WHAT_COMMENT_IS_ABOUT, {"comment": {"text": comment}}, sections=STOP_SECTIONS)
            curves.write(json.dumps({"comment": comment, "found_at_step": [s.decision for s in steps],
                                     "points": [vars(point) for point in points]}) + "\n")
    print(f"stop questions asked {judge.calls}")


if __name__ == "__main__":
    main()
