"""The installed console commands validate arguments before repository or judgment work."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(command: str, arguments: list[str], directory: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ | {
        "TYPESAFE_API_KEY": "cli-test-unused",
        "TYPESAFE_BASE_URL": "http://127.0.0.1:1",
        "TYPESAFE_DEFAULT_MODEL": "jev-latest",
    }
    return subprocess.run([str(Path(sys.executable).with_name(command)), *arguments], cwd=directory,
                          env=environment, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("command", ["comment-sweep", "comment-tool"])
def test_help_prints_usage_without_required_arguments(command, tmp_path):
    result = run_cli(command, ["--help"], tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert f"usage: {command}" in result.stdout
    assert "repository" in result.stdout and "commit" in result.stdout
    options = ["--only"] if command == "comment-sweep" else ["--files", "--diff"]
    assert all(option in result.stdout for option in options)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(("command", "arguments"), [
    ("comment-sweep", []),
    ("comment-sweep", ["repository", "HEAD", "src"]),
    ("comment-sweep", ["repository", "HEAD", "src", "out", "--only"]),
    ("comment-sweep", ["repository", "HEAD", "src", "out", "--unknown"]),
    ("comment-tool", []),
    ("comment-tool", ["repository", "HEAD", "journal"]),
    ("comment-tool", ["repository", "HEAD", "journal", "--files"]),
    ("comment-tool", ["repository", "HEAD", "journal", "--diff"]),
    ("comment-tool", ["repository", "HEAD", "journal", "--files", "src/a.py", "--diff", "base"]),
    ("comment-tool", ["repository", "HEAD", "journal", "--diff", "base", "--unknown"]),
])
def test_invalid_invocation_reports_usage_before_creating_output(command, arguments, tmp_path):
    result = run_cli(command, arguments, tmp_path)

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert f"usage: {command}" in result.stderr and "error:" in result.stderr
    assert "Traceback" not in result.stderr
    assert not list(tmp_path.iterdir())


@pytest.fixture
def source_repository(tmp_path):
    repository = tmp_path / "heedvane"
    repository.mkdir()

    def git(*arguments: str) -> str:
        return subprocess.check_output(["git", "-C", str(repository), *arguments], text=True).strip()

    git("init", "-q")
    for name in ("one", "two"):
        source = repository / "src" / name / "value.py"
        source.parent.mkdir(parents=True)
        source.write_text("VALUE = 1\n")
    git("add", "src")
    git("-c", "user.name=Test", "-c", "user.email=cli@example.test", "commit", "-qm", "initial")
    base = git("rev-parse", "HEAD")
    (repository / "src/one/value.py").write_text("VALUE = 2\n")
    git("add", "src")
    git("-c", "user.name=Test", "-c", "user.email=cli@example.test", "commit", "-qm", "change one file")
    return repository, base, git("rev-parse", "HEAD")


@pytest.mark.parametrize("mode", ["files", "diff"])
def test_classify_filters_reach_the_real_git_scope_without_model_calls(mode, source_repository, tmp_path):
    repository, base, head = source_repository
    journal = tmp_path / "journal"
    selection = ["--files", "src/one/value.py", "src/two/value.py"] if mode == "files" else ["--diff", base]

    result = run_cli("comment-tool", [str(repository), head, str(journal), *selection], tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    count = 2 if mode == "files" else 1
    assert f"0 comments in {count} files at {head[:12]}" in result.stderr
    assert "Jev requests 0" in result.stderr
    assert (journal / "journal.jsonl").read_bytes() == b""


@pytest.mark.parametrize("only", [False, True])
def test_sweep_filters_real_units_without_model_calls(only, source_repository, tmp_path):
    repository, _, head = source_repository
    out = tmp_path / "out"
    selection = ["--only", "src/two"] if only else []

    result = run_cli("comment-sweep", [str(repository), head, "src", str(out), *selection], tmp_path)

    assert result.returncode == 0, result.stderr
    assert "src/two 1 files {}" in result.stdout
    assert ("src/one 1 files {}" in result.stdout) is not only
    expected = {"src-two.jsonl"} if only else {"src-one.jsonl", "src-two.jsonl"}
    assert {path.name for path in out.glob("src-*.jsonl")} == expected
    assert all(path.read_bytes() == b"" for path in out.glob("src-*.jsonl"))
    assert "Jev calls (comment requests) 0" in result.stdout
    assert (out / "journal.jsonl").read_bytes() == b""
