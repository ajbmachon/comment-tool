"""Pick round 6: 30 comments that recent merged pull requests touched, and build their packets, with no model call.

The population is what an agent calling `classify.py --diff` sees: comments whose own lines or
described code changed in a pull request. The six pull requests are the ones from `count_pr_comments.py`
that change source (5 most recent merged into develop per repository, 28.09.2026). From each, 5 comments
in a fixed hash order, so no single large pull request dominates: 15 per repository, inline and doc
comments mixed as they come. Comments code decides (tool directives, commented-out code) make no Jev call
and are counted apart, not sampled. A comment an earlier round already labelled (same file and text) is
skipped. When the list check fires, the packet carries the list and its entries, as the list round's do,
so Sol labels them from the same frozen file.
usage: uv run --project <jev-navigator> --extra typesafe python sample_round6.py > round6/cases.jsonl
"""

import hashlib
import json
import sys
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex

from classify import changed_lines, is_touched
from comment_discovery import code_decision, found_comments
from list_claims import entry_items, list_claim_for
from sample_round4 import REPOSITORIES, packet

HERE = Path(__file__).resolve().parent
SALT = "round6-v1"
PER_PULL_REQUEST = 5
PULL_REQUESTS = (
    ("heedvane", 2862, "1ac2ce22c26e57e7f42993a73178bceb2795f511"),
    ("heedvane", 2858, "7fe48e61a25aea0f553929e76b11f73d4abe7f3e"),
    ("heedvane", 2857, "eec275da221b2d9991f4c1cc1c25fa0c4dd47cf2"),
    ("analysis-engine", 1311, "d40c3f5a0c524abb7a4edb938a743923e206a341"),
    ("analysis-engine", 1303, "b22367e737ff15944a307cdd79efeca488105149"),
    ("analysis-engine", 1294, "e9895ace2dd15772eb0dc719ca6f7f7422e88e31"),
)
CASE_PREFIXES = {"heedvane": "hv-k", "analysis-engine": "en-k"}
"""Round 6 ids; earlier rounds used the letters d to h and r."""


def rank(*parts) -> str:
    return hashlib.sha256(":".join([SALT, *map(str, parts)]).encode()).hexdigest()


def labelled_before() -> set[tuple[str, str]]:
    """(file, comment text) of every comment an earlier round's packet holds."""
    return {(case["provenance"]["path"], case["state"]["comment"]["text"])
            for cases in HERE.glob("*/cases.jsonl") if cases.parent.name != "round6"
            for case in map(json.loads, cases.read_text().splitlines()) if "provenance" in case}


def touched_comments(repository: Path, merge: str) -> tuple[CodeIndex, list, int]:
    """The index, the touched comments Jev would review, and how many code decided."""
    touched = changed_lines(repository, f"{merge}^1", merge)
    index = CodeIndex.at_commit(repository, merge, sorted(touched))
    found = [f for f in found_comments(index, sorted(touched)) if is_touched(index, f, touched)]
    return index, [f for f in found if code_decision(f) is None], sum(code_decision(f) is not None for f in found)


def round_packet(name: str, number: int, case_id: str, merge: str, picked) -> dict:
    """The packet as the runner rebuilds it: from an index of the comment's own file."""
    index = CodeIndex.at_commit(REPOSITORIES[name][0], merge, [picked.case.file])
    found = next(f for f in found_comments(index, [picked.case.file]) if f.case.first_line == picked.case.first_line)
    base = {**packet(name, index.commit, case_id, index, found), "kind": found.kind, "pull_request": number}
    literal = list_claim_for(index, found.case)
    if literal is None:
        return base
    return {**base, "list": literal.name, "items": list(entry_items(index, found.case.file, literal).items)}


def main() -> None:
    seen = labelled_before()
    numbers = dict.fromkeys(CASE_PREFIXES, 0)
    for name, pull_request, merge in PULL_REQUESTS:
        _, reviewable, by_code = touched_comments(REPOSITORIES[name][0], merge)
        fresh = [f for f in reviewable if (f.case.file, f.case.text) not in seen]
        picked = sorted(fresh, key=lambda f: rank(name, pull_request, f.case.file, f.case.first_line))[:PER_PULL_REQUEST]
        print(f"{name} #{pull_request}: {len(reviewable)} for Jev, {by_code} decided by code, "
              f"{len(reviewable) - len(fresh)} labelled before, picked {len(picked)}", file=sys.stderr)
        for found in picked:
            numbers[name] += 1
            print(json.dumps(round_packet(name, pull_request, f"{CASE_PREFIXES[name]}{numbers[name]:02d}", merge, found)))


if __name__ == "__main__":
    main()
