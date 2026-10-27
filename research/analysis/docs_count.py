"""Count, with no model call, the doc comments a directory sends to Jev now that they get review.

For every doc comment `find_comments` keeps (`comment_discovery.DOC_KINDS`): its kind, whether it
sits on a named function or class, and whether it names a checkable detail by the fixed mechanical
rule in `multi_detail.py` (a stand-in for question 1, which is a Jev answer).
usage: uv run python docs_count.py <repository> <commit> <parent dir>
"""

import argparse
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jev_navigator.comments import CommentBlock

def row_of(block: "CommentBlock") -> tuple[str, str, str]:
    from research.analysis.multi_detail import detail_clauses
    named = block.attached is not None and bool(block.attached.name)
    group = "on a named function or class" if named else "on other code or none"
    detail = "names a checkable detail" if detail_clauses(block.text, block.span.file) else "no checkable detail"
    return group, str(block.kind), detail


def main() -> None:
    parser = argparse.ArgumentParser(description="Read repository files at a commit and print doc-comment counts by kind, attachment, and detail as text.")
    parser.add_argument("repository", type=Path, help="repository to inspect")
    parser.add_argument("commit", help="commit whose files to inspect")
    parser.add_argument("parent_dir", help="directory under which to count comments")
    args = parser.parse_args()
    from jev_navigator.comments import find_comments
    from jev_navigator.index.code_index import CodeIndex

    from comment_tool.cli.sweep import source_files, sweep_units
    from comment_tool.core.comment_discovery import DOC_KINDS
    repository, commit, parent = args.repository, args.commit, args.parent_dir
    counts = Counter()
    for _, files in sweep_units(source_files(repository, commit, parent), parent):
        index = CodeIndex.at_commit(repository, commit, files)
        counts.update(row_of(block) for block in find_comments(index, files).kept if block.kind in DOC_KINDS)
    for key, count in sorted(counts.items()):
        print(count, " | ".join(key))
    print(sum(counts.values()), "doc comments in all")


if __name__ == "__main__":
    main()
