"""The agent entry point: comments of a file list, or only the ones a diff touches, one row each."""

import json
import subprocess
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge
from jev_navigator.testing import ScriptedJevClient

from comment_tool.cli.classify import changed_lines, classify
from comment_tool.cli.sweep import QUESTIONS
from comment_tool.core.comment_review import question_set

BEFORE = '''# Limits for the importer.
MAX_ROWS = 10


def load(rows):
    # Stop at the limit so one huge upload cannot stall the queue.
    return rows[:MAX_ROWS]


def unrelated():
    # Kept apart from the importer on purpose.
    return None
'''
AFTER = BEFORE.replace("return rows[:MAX_ROWS]", "return rows[: MAX_ROWS * 2]").replace("# Limits for the importer.\n", "")


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(["git", *arguments], cwd=repository, capture_output=True, text=True, check=True).stdout


def committed(repository: Path, text: str) -> str:
    (repository / "importer.py").write_text(text)
    git(repository, "add", "importer.py")
    git(repository, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t")
    return git(repository, "rev-parse", "HEAD").strip()


def two_commits(repository: Path) -> tuple[str, str]:
    git(repository, "init", "-q")
    return committed(repository, BEFORE), committed(repository, AFTER)


def rows_for(repository: Path, commit: str, touched: dict | None) -> list[dict]:
    index = CodeIndex.at_commit(repository, commit, ["importer.py"])
    judge = Judge(ScriptedJevClient(default_noul=0.05))
    return classify(index, judge, question_set(json.loads(QUESTIONS.read_text())), touched)


def test_a_diff_marks_changed_lines_and_both_sides_of_a_deletion(tmp_path):
    base, head = two_commits(tmp_path)

    assert changed_lines(tmp_path, base, head) == {"importer.py": frozenset({0, 1, 6})}


def test_a_file_list_classifies_every_comment(tmp_path):
    _, head = two_commits(tmp_path)

    rows = rows_for(tmp_path, head, touched=None)

    assert [row["location"] for row in rows] == ["importer.py:5", "importer.py:10"]
    assert {row["action"] for row in rows} == {"keep"}


def test_a_diff_classifies_only_comments_on_or_above_changed_code(tmp_path):
    base, head = two_commits(tmp_path)

    rows = rows_for(tmp_path, head, touched=changed_lines(tmp_path, base, head))

    assert [row["location"] for row in rows] == ["importer.py:5"]
