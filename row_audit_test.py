"""A result row is scored only when the journal and the frozen rule give exactly that row."""

import json

import pytest

import compose
from data_root import DATA
from row_audit import RowAuditError, audit_row, journal_exchanges

pytestmark = pytest.mark.local
DOCS2 = DATA / "docs2"


def stored(name: str) -> dict:
    return {row["case_id"]: row for row in map(json.loads, (DOCS2 / name).read_text().splitlines())}


def recorded_row(case_id: str) -> tuple[dict, dict]:
    case = stored("cases.jsonl")[case_id]
    return {**stored("pass.jsonl")[case_id], "kind": case["kind"]}, case


def test_a_stored_row_matches_its_journal_and_the_rule():
    row, case = recorded_row("hv-e01")

    audit_row(row, case, journal_exchanges(DOCS2 / "journal.jsonl"), compose)


def test_an_edited_action_is_refused():
    row, case = recorded_row("hv-e01")
    edited = {**row, "action": "rewrite"}

    with pytest.raises(RowAuditError, match="action"):
        audit_row(edited, case, journal_exchanges(DOCS2 / "journal.jsonl"), compose)


def test_a_row_filed_under_another_case_is_refused():
    row, _ = recorded_row("hv-e02")
    _, other_case = recorded_row("hv-e01")

    with pytest.raises(RowAuditError, match="identity"):
        audit_row({**row, "case_id": "hv-e01"}, other_case, journal_exchanges(DOCS2 / "journal.jsonl"), compose)


def test_a_removed_escalation_is_refused():
    row, case = recorded_row("hv-e13")
    quiet = {key: value for key, value in row.items() if key != "escalate"} | {"decided_by": "jev+rule"}

    with pytest.raises(RowAuditError, match="escalation"):
        audit_row(quiet, case, journal_exchanges(DOCS2 / "journal.jsonl"), compose)
