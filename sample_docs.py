"""Pick 30 doc comments that validate doc review, and build their packets, with no model call.

15 Heedvane doc comments from outside `apps/web/src/lib` and 15 analysis-engine ones, at the round-3
commits, one per file, in a fixed hash order, from files no earlier round used: rounds 3 and 4, and
every file in the case files named on the command line. A doc comment is any
kind in `comment_discovery.DOC_KINDS` (JSDoc, docstring, declaration comment, file header).
Packets use the tool's cut: the lines above, and the code the comment is about (for a function's
docstring, the rest of the function).
usage: run-slot -- uv run --project <jev-navigator> python sample_docs.py <id letter> [used cases.jsonl ...] > <round>/cases.jsonl
       (the first doc round: `sample_docs.py d`; the second: `sample_docs.py e docs/cases.jsonl docs-rewrite/cases.jsonl`)
"""

import hashlib
import json
import sys
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex

from comment_discovery import DOC_KINDS, found_comments
from sample_round4 import PER_REPOSITORY, REPOSITORIES, candidate_files, packet, used_paths

HERE = Path(__file__).resolve().parent
SALT = "comment-docs-v1"
CASE_PREFIXES = {"heedvane": "hv-", "analysis-engine": "en-"}


def rank(*parts) -> str:
    return hashlib.sha256(":".join([SALT, *map(str, parts)]).encode()).hexdigest()


def round4_paths() -> set[str]:
    return case_paths(HERE / "round4" / "cases.jsonl")


def case_paths(cases: Path) -> set[str]:
    return {json.loads(line)["provenance"]["path"] for line in cases.read_text().splitlines()}


def doc_comment(index: CodeIndex, name: str, path: str):
    """The first doc comment in hash order, or None when the file has none."""
    docs = [found for found in found_comments(index, [path]) if found.kind in DOC_KINDS]
    return min(docs, key=lambda found: rank(name, path, found.case.first_line), default=None)


def main() -> None:
    letter = sys.argv[1]
    used = used_paths() | round4_paths() | {path for cases in sys.argv[2:] for path in case_paths(Path(cases))}
    for name, (repository, commit, _, include, exclude) in REPOSITORIES.items():
        picked = 0
        for path in sorted(candidate_files(repository, commit, include, exclude), key=lambda p: rank(name, p)):
            if path in used:
                continue
            index = CodeIndex.at_commit(repository, commit, [path])
            found = doc_comment(index, name, path)
            if found is None:
                continue
            picked += 1
            row = packet(name, commit, f"{CASE_PREFIXES[name]}{letter}{picked:02d}", index, found)
            print(json.dumps({**row, "kind": found.kind}), flush=True)
            if picked == PER_REPOSITORY:
                break
        print(f"{name}: {picked} picked", file=sys.stderr)


if __name__ == "__main__":
    main()
