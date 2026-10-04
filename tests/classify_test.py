"""The agent entry point: comments of a file list, or only the ones a diff touches, one row each."""

import json
import subprocess
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge
from jev_navigator.testing import ScriptedJevClient

from comment_tool.cli.classify import changed_lines, classify
from comment_tool.cli.sweep import QUESTIONS, source_files
from comment_tool.core.comment_discovery import found_comments
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


# One authored file per suffix the pinned library parses (jev-navigator `LANGUAGE_BY_SUFFIX`), each
# carrying a trailing comment; plus the declaration, test-support and generated shapes that stay out.
SOURCES = {
    "pkg/values.py": "ROWS = 1  # measured limit\n",
    "pkg/values.ts": "export const rows = 1; // measured limit\n",
    "pkg/values.tsx": "export const view = 1; // measured limit\n",
    "pkg/values.mts": "export const rows = 1; // measured limit\n",
    "pkg/values.cts": "export const rows = 1; // measured limit\n",
    "pkg/values.js": "export const rows = 1; // measured limit\n",
    "pkg/values.jsx": "export const view = 1; // measured limit\n",
    "pkg/values.mjs": "export const rows = 1; // measured limit\n",
    "pkg/values.cjs": "const rows = 1; // measured limit\n",
    "pkg/values.d.ts": "export type Row = number;\n",
    "pkg/values.d.mts": "export type Row = number;\n",
    "pkg/values.d.cts": "export type Row = number;\n",
    "pkg/values.test.mts": "import test from 'node:test';\n",
    "pkg/values.spec.mjs": "import test from 'node:test';\n",
    "pkg/values_test.py": "ROWS = 1\n",
    "pkg/generated/values.ts": "export const rows = [];\n",
    "pkg/tests/helper.py": "ROWS = 1\n",
}
IN_SCOPE = ["pkg/values.cjs", "pkg/values.cts", "pkg/values.js", "pkg/values.jsx", "pkg/values.mjs",
            "pkg/values.mts", "pkg/values.py", "pkg/values.ts", "pkg/values.tsx"]


def committed_files(repository: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    git(repository, "add", "pkg")
    git(repository, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", message)
    return git(repository, "rev-parse", "HEAD").strip()


def test_source_scope_covers_the_whole_script_family_and_keeps_the_exclusions(tmp_path):
    git(tmp_path, "init", "-q")
    base = committed_files(tmp_path, SOURCES, "initial")

    assert source_files(tmp_path, base, "pkg") == IN_SCOPE

    head = committed_files(tmp_path, {"pkg/values.mts": "export const rows = 2; // measured limit\n",
                                      "pkg/values.mjs": "export const rows = 2; // measured limit\n"},
                           "touch the native modules")
    touched = changed_lines(tmp_path, base, head)

    assert set(touched) == {"pkg/values.mts", "pkg/values.mjs"}

    index = CodeIndex.at_commit(tmp_path, head, sorted(touched))
    found = {found.case.file: found for found in found_comments(index, sorted(touched))}
    assert set(found) == {"pkg/values.mts", "pkg/values.mjs"}
    assert "measured limit" in found["pkg/values.mts"].case.text
    assert found["pkg/values.mts"].case.language == "typescript"
    assert found["pkg/values.mjs"].case.language == "javascript"

    client = ScriptedJevClient(default_noul=0.05)
    rows = classify(index, Judge(client), question_set(json.loads(QUESTIONS.read_text())), touched)

    assert {row["location"] for row in rows} == {"pkg/values.mts:1", "pkg/values.mjs:1"}
    assert {state["code"]["language"] for state, _ in client.requests} == {"typescript", "javascript"}
