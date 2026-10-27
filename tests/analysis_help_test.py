"""Analysis CLIs show help without retained research data or starting a job."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = sorted(path.stem for path in (ROOT / "research/analysis").glob("*.py") if path.name != "__init__.py")


@pytest.mark.parametrize("script", SCRIPTS)
def test_analysis_help_without_research_data(script, tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", f"research.analysis.{script}", "--help"],
        cwd=ROOT, env=os.environ | {"COMMENT_TOOL_DATA": str(tmp_path)},
        capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower(), result.stdout
    assert result.stderr == ""
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("compare", [False, True])
def test_sweep_totals_preserves_report_and_comparison(compare, tmp_path):
    sweep = tmp_path / "sweep"
    other = tmp_path / "other"
    sweep.mkdir()
    other.mkdir()
    rows = [{"location": "a:1", "action": "keep"}, {"location": "b:2", "action": "rewrite"}]
    (sweep / "apps-example.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    (other / "apps-example.jsonl").write_text(
        '\n'.join(json.dumps({"location": location, "action": "keep"}) for location in ("a:1", "c:3")) + "\n"
    )
    arguments = [str(sweep), *(["--compare", str(other)] if compare else [])]

    result = subprocess.run(
        [sys.executable, "-m", "research.analysis.sweep_totals", *arguments],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )

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
    assert result.stderr == ""


def test_imported_readout_helpers_keep_their_dependencies(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    answers = {
        name: {"type": "noul", "noul": 1.0 if name == "explains_hard_code" else 0.0}
        for name in (
            "explains_hard_code", "states_hidden_rule", "teaches_needed_knowledge", "points_to_owner",
            "has_time_reference", "only_restates_code", "is_noise", "contradicts_code", "name_would_replace",
        )
    }
    answers["action"] = {"type": "choice", "choice": "keep", "confidence": 1.0, "probabilities": {"keep": 1.0}}
    (run / "case.json").write_text(json.dumps({"case_id": "case", "response": {"answers": answers}}))
    (tmp_path / "pass.jsonl").write_text('{"case_id": "saved-case"}\n')
    program = """
import json
import sys
sys.argv = ['importing-caller', '--unrelated-option']
from research.analysis.compare_readouts import jev_answers, readout_a_jev
from research.analysis.escalate import score
from research.analysis.gate_replay import rows_of
answers = jev_answers()
facts = {'case': {'dates': [], 'ticket_refs': [], 'unowned_todo': False}}
sol = {'case': {'verdict': {'answers': {'action': {'choice': 'keep'}}}}}
print(readout_a_jev(answers['case'], facts['case']))
print(json.dumps(score(['case'], answers, facts, sol, 0.6), sort_keys=True))
print(json.dumps(rows_of(['pass.jsonl'])))
"""
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=ROOT,
        env=os.environ | {"COMMENT_TOOL_DATA": str(tmp_path)},
        capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "keep", '{"caught": 0, "decided": 1, "escalated": [], "hits": 1, "wrong_total": 0}',
        '[{"case_id": "saved-case"}]',
    ]
    assert result.stderr == ""


@pytest.fixture
def analysis_repository(script_repository):
    repository = script_repository

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(repository), *arguments], text=True).strip()

    git("init", "-q")
    source = repository / "src/unit/value.ts"
    source.parent.mkdir(parents=True)
    source.write_text("// The caller retries after disconnect.\nexport const value = 1;\n")
    git("add", "src")
    git("-c", "user.name=Test", "-c", "user.email=analysis@example.test", "commit", "-qm", "initial")
    source.write_text("// The caller retries after reconnect.\nexport const value = 1;\n")
    git("add", "src")
    git("-c", "user.name=Test", "-c", "user.email=analysis@example.test", "commit", "-qm", "update comment")
    return repository, git("rev-parse", "HEAD")


@pytest.mark.local
def test_discovery_snapshot_cli_and_compare(analysis_repository, tmp_path):
    repository, head = analysis_repository
    snapshot = tmp_path / "snapshot.jsonl"
    result = subprocess.run(
        [sys.executable, "-m", "research.analysis.discovery_snapshot", str(repository), head, "src", str(snapshot)],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in snapshot.read_text().splitlines()]
    assert len(rows) == 1
    assert (rows[0]["location"], rows[0]["last_line"], rows[0]["route"]) == ("src/unit/value.ts:1", 1, "jev")
    after = tmp_path / "after.jsonl"
    after.write_text(json.dumps(rows[0] | {"route": "code:keep"}) + "\n")

    comparison = subprocess.run(
        [sys.executable, "-m", "research.analysis.discovery_snapshot", "--compare", str(snapshot), str(after)],
        cwd=ROOT, capture_output=True, text=True, timeout=10,
    )

    assert comparison.returncode == 0, comparison.stderr
    assert "comments: 1 before, 1 after; 1 at the same location" in comparison.stdout
    assert "route moves at the same location: {('jev', 'code:keep'): 1}" in comparison.stdout
    assert "same start but different end line: 0; different facts: 0" in comparison.stdout


@pytest.mark.local
def test_pr_counts_uses_discovery_helpers_on_a_real_commit(analysis_repository):
    repository, head = analysis_repository
    result = subprocess.run(
        [sys.executable, "-c", (
            "import json, sys; from pathlib import Path; "
            "from research.analysis.count_pr_comments import pr_counts; "
            "print(json.dumps(pr_counts(Path(sys.argv[1]), sys.argv[2])))"
        ), str(repository), head],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "source_files": 1, "comments": 1, "decided_by_code": 0, "jev_requests": 1, "list_batches_at_most": 0,
    }
