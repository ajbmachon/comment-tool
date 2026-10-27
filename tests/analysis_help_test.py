"""CLI help stays available without research data or running an analysis."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ANALYSIS = Path(__file__).resolve().parents[1] / "research" / "analysis"
SCRIPTS = sorted(path for path in ANALYSIS.glob("*.py") if path.name != "__init__.py")
assert len(SCRIPTS) == 19


def assert_help(command: list[str], empty_data: Path) -> None:
    result = subprocess.run(
        [*command, "--help"],
        env={**os.environ, "COMMENT_TOOL_DATA": str(empty_data)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower(), result.stdout


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda script: script.stem)
def test_help_without_research_data(script: Path, tmp_path: Path) -> None:
    assert_help([sys.executable, "-m", f"research.analysis.{script.stem}"], tmp_path)


@pytest.mark.parametrize("compare", [False, True], ids=["ordinary", "compare"])
def test_sweep_totals_output(compare: bool, tmp_path: Path) -> None:
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "apps-example.jsonl").write_text(
        '{"action": "keep", "location": "one"}\n'
        '{"action": "rewrite", "location": "two"}\n'
    )
    (second / "apps-example.jsonl").write_text(
        '{"action": "keep", "location": "one"}\n'
        '{"action": "remove", "location": "three"}\n'
    )
    command = [sys.executable, str(ANALYSIS / "sweep_totals.py"), str(first)]
    if compare:
        command += ["--compare", str(second)]
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    expected = (
        "| Unit | Comments | keep | rewrite | remove | refactor_instead | fix_stale | escalate |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| apps-example | 2 | 1 | 1 | 0 | 0 | 0 | 0 |\n"
        "| **total** | 2 | 1 | 1 | 0 | 0 | 0 | 0 |\n"
        "\nSearches: {}\n"
    )
    if compare:
        expected += "\nLocations: 1 in both, 1 only here, 1 only in the other\n"
    assert result.returncode == 0, result.stderr
    assert result.stdout == expected
