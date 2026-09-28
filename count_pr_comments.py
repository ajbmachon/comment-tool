"""How many comments `classify.py --diff` would classify per merged pull request, and the Jev requests
that takes, with no model call.

For each pull request, the diff runs from the merge commit's first parent to the merge commit, the
comments it touches are found exactly as `classify.py` finds them, and code-decided ones are counted
apart. Each other comment costs one Jev request; a comment above a list literal it makes a claim
about may cost one more (the per-entry batch, asked only when Jev says the comment states a
condition); further re-asks and searches happen only on escalation and are not counted here. Jev's
time per request is read from the stored journals.
usage: uv run --project <jev-navigator> --extra typesafe python count_pr_comments.py <repository>=<pr>:<merge commit> ...
"""

import json
import statistics
import sys
from datetime import datetime
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex

from classify import changed_lines, is_touched
from comment_discovery import code_decision, found_comments
from data_root import DATA
from list_claims import list_claim_for

PROJECTS = Path.home() / "Projects"
INDEX_FILES = 300


def pr_counts(repository: Path, merge: str) -> dict:
    touched = changed_lines(repository, f"{merge}^1", merge)
    files = sorted(touched)
    comments = [found for start in range(0, len(files), INDEX_FILES)
                for found in _touched_in(repository, merge, files[start : start + INDEX_FILES], touched)]
    by_code = [found for found, _ in comments if code_decision(found) is not None]
    to_jev = [(found, index) for found, index in comments if code_decision(found) is None]
    lists = sum(list_claim_for(index, found.case) is not None for found, index in to_jev)
    return {"source_files": len(files), "comments": len(comments), "decided_by_code": len(by_code),
            "jev_requests": len(to_jev), "list_batches_at_most": lists}


def _touched_in(repository: Path, commit: str, files: list[str], touched: dict) -> list:
    index = CodeIndex.at_commit(repository, commit, files)
    return [(found, index) for found in found_comments(index, files) if is_touched(index, found, touched)]


def jev_seconds() -> list[float]:
    """Seconds from each stored Jev request to its response, over every journal kept here."""
    seconds = []
    for journal in DATA.rglob("journal.jsonl"):
        sent = {}
        for event in map(json.loads, journal.read_text().splitlines()):
            at = datetime.fromisoformat(event["captured_at"])
            if event["kind"] == "request":
                sent[event["exchange_id"]] = at
            elif event["exchange_id"] in sent:
                seconds.append((at - sent.pop(event["exchange_id"])).total_seconds())
    return seconds


def main() -> None:
    for argument in sys.argv[1:]:
        name, rest = argument.split("=")
        number, merge = rest.split(":")
        print(json.dumps({"repository": name, "pr": int(number), "merge": merge, **pr_counts(PROJECTS / name, merge)}))
    seconds = jev_seconds()
    print(json.dumps({"jev_requests_timed": len(seconds), "median_seconds": round(statistics.median(seconds), 1),
                      "p90_seconds": round(statistics.quantiles(seconds, n=10)[-1], 1)}))


if __name__ == "__main__":
    main()
