"""Classify the comments of a file list, or the comments a diff touches: one JSON row per comment.

The entry point for a calling agent. The tool only classifies; the caller acts on the rows (see
`CONTRACT.md` for the row fields). Each comment is reviewed as in `sweep.py`: code settles tool
directives and commented-out code, Jev answers the rest, and rule A composes the action. With
`--diff <base>`, a comment is in scope when its own lines or the code it describes hold a line the
diff changed between the merge base and `<commit>`; a pure deletion counts as changing the lines on
both sides of it. Comments in a file the diff deletes are out of scope: a deleted comment needs no
action. Only source files are read (`sweep.source_files`: Python and TypeScript, no tests
or generated code). Rows go to stdout, one per line; a summary goes to stderr. Every Jev exchange is
journaled in `<journal dir>`, so only our own repositories can be classified.
usage: uv run comment-tool \
         <repository> <commit> <journal dir> (--files <path> ... | --diff <base>)
"""

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from jev_navigator.index import tools
from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge

from comment_tool.cli.sweep import (
    COMMENT_WORKERS,
    NOT_SOURCE,
    QUESTIONS,
    SOURCE,
    outcome_of,
    review_found,
)
from comment_tool.core.comment_discovery import FoundComment, found_comments
from comment_tool.core.comment_review import QuestionSet, described_after, question_set
from comment_tool.journal.journaled_client import journaled_judge

HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.MULTILINE)
Touched = Mapping[str, frozenset[int]] | None
"""Changed lines per file; None classifies every comment of the files."""


def changed_lines(repository: Path, base: str, commit: str) -> dict[str, frozenset[int]]:
    """The lines of `commit` that the diff from the merge base of `base` and `commit` changed, per source file."""
    diff = tools.git(["diff", "-U0", "--no-color", "--no-ext-diff", f"{base}...{commit}"], repository)
    touched: dict[str, frozenset[int]] = {}
    for file, hunks in _file_sections(diff):
        if SOURCE.search(file) and not NOT_SOURCE.search(file):
            touched[file] = frozenset(line for match in HUNK.finditer(hunks) for line in _hunk_lines(match))
    return touched


def _file_sections(diff: str) -> list[tuple[str, str]]:
    """(new path, its hunks) for each file the diff adds or changes; deleted files are left out."""
    sections = []
    for section in diff.split("\ndiff --git "):
        new_path = re.search(r"^\+\+\+ b/(.+)$", section, re.MULTILINE)
        if new_path:
            sections.append((new_path.group(1), section))
    return sections


def _hunk_lines(match: re.Match) -> range:
    start, count = int(match.group(1)), int(match.group(2) or 1)
    return range(start, start + 2) if count == 0 else range(start, start + count)


def classify(index: CodeIndex, judge: Judge, questions: QuestionSet, touched: Touched) -> list[dict]:
    """One row per comment in the index's files, or per comment a diff touches."""
    found = [f for f in found_comments(index, list(index.files)) if touched is None or is_touched(index, f, touched)]
    with ThreadPoolExecutor(COMMENT_WORKERS) as pool:
        return list(pool.map(lambda comment: review_found(index, judge, comment, questions), found))


def is_touched(index: CodeIndex, found: FoundComment, touched: Mapping[str, frozenset[int]]) -> bool:
    changed = touched.get(found.case.file, frozenset())
    described = described_after(index, found.case).span
    own = range(found.case.first_line, found.case.last_line + 1)
    return any(line in changed for line in (*own, *range(described.start, described.end + 1)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify source comments in files or a Git diff.", allow_abbrev=False)
    parser.add_argument("repository", type=Path, help="path to the repository")
    parser.add_argument("commit", help="Git commit or revision to read")
    parser.add_argument("journal", type=Path, help="directory for the exchange journal")
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--files", nargs="+", metavar="PATH", help="repository-relative source files to classify")
    selection.add_argument("--diff", metavar="BASE", help="classify comments touched by the diff from this merge base")
    arguments = parser.parse_args()
    repository, commit, journal = arguments.repository, arguments.commit, arguments.journal
    files, base = arguments.files, arguments.diff
    commit = tools.git(["rev-parse", "--verify", f"{commit}^{{commit}}"], repository).strip()
    touched = changed_lines(repository, base, commit) if base is not None else None
    scope = sorted(touched) if touched is not None else files
    journal.mkdir(parents=True, exist_ok=True)
    judge = journaled_judge(journal, {repository.name})
    rows = classify(CodeIndex.at_commit(repository, commit, scope), judge,
                    question_set(json.loads(QUESTIONS.read_text())), touched) if scope else []
    for row in rows:
        print(json.dumps(row), flush=True)
    print(f"{len(rows)} comments in {len(scope)} files at {commit[:12]}: {dict(Counter(map(outcome_of, rows)))}; "
          f"Jev requests {judge.calls}", file=sys.stderr)


if __name__ == "__main__":
    main()
