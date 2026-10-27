"""Analysis entry points provide help before loading research data or doing work."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(path.stem for path in (ROOT / "research/analysis").glob("*.py") if path.name != "__init__.py")


@pytest.mark.parametrize("script", SCRIPTS)
@pytest.mark.parametrize("empty_data", [False, True], ids=["default-data", "empty-data"])
def test_analysis_help(script, empty_data, tmp_path):
    environment = os.environ.copy()
    if empty_data:
        environment["COMMENT_TOOL_DATA"] = str(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", f"research.analysis.{script}", "--help"],
        cwd=ROOT, env=environment, capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()
    assert result.stderr == ""
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("compare", [False, True], ids=["ordinary", "compare"])
def test_sweep_totals_preserves_output(compare, tmp_path):
    for name, rows in [
        ("sweep", [
            {"location": "a:1", "action": "keep"},
            {"location": "b:2", "action": "remove"},
            {"location": "c:3", "escalate": {}, "decided_by": "escalated", "search": {"outcome": "found"}},
        ]),
        ("other", [{"location": "a:1", "action": "rewrite"}, {"location": "d:4", "action": "keep"}]),
    ]:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "apps-web-src-lib-demo.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    arguments = [str(tmp_path / "sweep")]
    if compare:
        arguments += ["--compare", str(tmp_path / "other")]
    result = subprocess.run(
        [sys.executable, "-m", "research.analysis.sweep_totals", *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )

    expected = (
        "| Unit | Comments | keep | rewrite | remove | refactor_instead | fix_stale | escalate |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| demo | 3 | 1 | 0 | 1 | 0 | 0 | 1 |\n"
        "| **total** | 3 | 1 | 0 | 1 | 0 | 0 | 1 |\n"
        "\nSearches: {'found': 1}\n"
    )
    if compare:
        expected += "\nLocations: 1 in both, 2 only here, 1 only in the other\n"
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == expected
