"""A result row is scored only when the journal and the frozen rule give exactly that row."""

import json
from pathlib import Path

import pytest
from jev_navigator.judgments.questions import request_sha256

import compose
from comment_review import question_set
from data_root import DATA
from row_audit import RowAuditError, audit_journal, audit_row, journal_exchanges, registered_question_sets

pytestmark = pytest.mark.local
DOCS2 = DATA / "docs2"
ROUND5_QUESTIONS = Path(__file__).resolve().parent / "questions.round5.json"


def stored(name: str) -> dict:
    return {row["case_id"]: row for row in map(json.loads, (DOCS2 / name).read_text().splitlines())}


def recorded_row(case_id: str) -> tuple[dict, dict]:
    case = stored("cases.jsonl")[case_id]
    return {**stored("pass.jsonl")[case_id], "kind": case["kind"]}, case


def audited(row: dict, case: dict, exchanges: dict | None = None) -> None:
    sets = registered_question_sets(question_set(json.loads(ROUND5_QUESTIONS.read_text())))
    audit_row(row, case, exchanges or journal_exchanges(DOCS2 / "journal.jsonl"), compose, sets)


def test_a_stored_round_matches_its_journal_and_the_rule():
    sets = registered_question_sets(question_set(json.loads(ROUND5_QUESTIONS.read_text())))

    audit_journal(DOCS2 / "journal.jsonl", sets)
    audited(*recorded_row("hv-e01"))


def test_an_edited_action_is_refused():
    row, case = recorded_row("hv-e01")

    with pytest.raises(RowAuditError, match="action"):
        audited({**row, "action": "rewrite"}, case)


def test_a_row_filed_under_another_case_is_refused():
    row, _ = recorded_row("hv-e02")
    _, other_case = recorded_row("hv-e01")

    with pytest.raises(RowAuditError, match="identity"):
        audited({**row, "case_id": "hv-e01"}, other_case)


def test_a_removed_escalation_is_refused():
    row, case = recorded_row("hv-e13")
    quiet = {key: value for key, value in row.items() if key != "escalate"} | {"decided_by": "jev+rule"}

    with pytest.raises(RowAuditError, match="escalation"):
        audited(quiet, case)


def test_a_re_ask_with_an_unregistered_question_set_is_refused():
    row, case = recorded_row("hv-e01")
    exchanges = journal_exchanges(DOCS2 / "journal.jsonl")
    first = exchanges[row["request_sha256"]]
    state = {**case["state"], "code": {**case["state"]["code"], "elsewhere": [{"code": "x = 1"}]}}
    nouls = {**first["nouls"], "has_time_reference": 0.95}
    reask_hash = request_sha256(state, first["questions"])
    exchanges[reask_hash] = {"state": state, "questions": first["questions"], "nouls": nouls}
    rewritten = {**row, "request_sha256": reask_hash, "probabilities": nouls,
                 "first_answer": {key: row[key] for key in ("probabilities", "request_sha256")},
                 "action": compose.readout_a(nouls, case["code_facts"]), "decision_path": compose.decision_path(nouls, case["code_facts"])}
    assert rewritten["action"] == "rewrite"

    with pytest.raises(RowAuditError, match="question set"):
        audited(rewritten, case, exchanges)
