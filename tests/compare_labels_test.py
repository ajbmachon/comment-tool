"""The label compare readout finds its retained datasets through DATA, whatever directory it is launched in.

Both original faults are replayed against the real retained files: from an unrelated directory the
label files were looked for relative to the launching directory (FileNotFoundError), and from the
data folder itself `DATA / "file".read_text()` raised AttributeError on the string before the
parentheses were fixed. Identical stdout from both launches proves the readout is directory-free
and scores the same records it always meant to."""

import subprocess
import sys
from pathlib import Path

import pytest

from comment_tool.config import DATA

SCRIPT = Path(__file__).resolve().parents[1] / "research" / "analysis" / "compare_labels.py"

pytestmark = pytest.mark.local


def run_from(cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT)], cwd=cwd, capture_output=True, text=True, check=False)


def test_the_readout_runs_from_an_unrelated_directory(tmp_path):
    from_elsewhere = run_from(tmp_path)

    assert from_elsewhere.returncode == 0, from_elsewhere.stderr
    assert "Draft vs Sol action" in from_elsewhere.stdout
    assert "agree 27 of 32" in from_elsewhere.stdout
    assert "agree 28 of 32" in from_elsewhere.stdout


def test_the_readout_scores_the_same_records_from_the_data_folder(tmp_path):
    """Launch point must not decide which files are compared or what the readout says."""
    from_elsewhere = run_from(tmp_path)
    from_data = run_from(DATA)

    assert from_data.returncode == 0, from_data.stderr
    assert from_data.stdout == from_elsewhere.stdout
