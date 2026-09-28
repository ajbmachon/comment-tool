"""Lib packets are re-asked with their state exactly as the sweep sent it, and a request that carried
another byte order is refused."""

import pytest
from jev_navigator.judgments.journal import JournalRequest
from jev_navigator.judgments.questions import request_sha256

from gate_first_answers import SentStateMismatchError, require_sent_states, sent_states
from journaled_client import EvalsJournal

pytestmark = pytest.mark.local

SENT_STATE = {"comment": {"text": "// z first"}, "code": {"before_comment": "a", "after_comment": "b"}}
SORTED_COPY = {"code": {"after_comment": "b", "before_comment": "a"}, "comment": {"text": "// z first"}}
QUESTIONS = {"q": {"type": "noul"}}


def journal_with(tmp_path, state: dict):
    path = tmp_path / "journal.jsonl"
    request_hash = request_sha256(state, QUESTIONS)
    EvalsJournal(path, "run", {"heedvane"}).record_request(JournalRequest(request_hash, "jev-latest", state, QUESTIONS))
    return path, request_hash


def test_the_state_is_read_back_in_its_sent_order(tmp_path):
    path, request_hash = journal_with(tmp_path, SENT_STATE)

    state = sent_states(path)[request_hash]

    assert list(state) == ["comment", "code"]
    assert list(state["code"]) == ["before_comment", "after_comment"]


def test_a_request_that_carried_the_sorted_copy_is_refused(tmp_path):
    path, request_hash = journal_with(tmp_path, SORTED_COPY)
    row = {"location": "a.ts:1", "request_sha256": request_hash}

    with pytest.raises(SentStateMismatchError):
        require_sent_states(path, [row], [{"state": SENT_STATE}])


def test_a_request_that_carried_the_sent_state_passes(tmp_path):
    path, request_hash = journal_with(tmp_path, SENT_STATE)

    require_sent_states(path, [{"location": "a.ts:1", "request_sha256": request_hash}], [{"state": SENT_STATE}])


@pytest.mark.parametrize("kind, expected", [("jsdoc", "rewrite"), ("block", "remove")])
def test_gate_replay_preserves_the_sweeps_comment_kind(tmp_path, monkeypatch, kind, expected):
    import json

    import gate_first_answers
    from comment_review import question_set
    from gate_exact_compare import comment_facts, verdicts
    from run_round4 import ROUND4_QUESTIONS

    _, request_hash = journal_with(tmp_path, SENT_STATE)
    row = {
        "location": "example.ts:1", "kind": kind, "comment": "/** Obvious noise. */",
        "decided_by": "escalated", "search": {}, "request_sha256": request_hash,
    }
    (tmp_path / "apps-example.jsonl").write_text(json.dumps(row) + "\n")
    monkeypatch.setattr(gate_first_answers, "LIB", tmp_path)
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    probabilities = {check.name: 0.05 for check in questions.checks}
    probabilities["is_noise"] = 0.95

    replay_facts = comment_facts()[row["location"]]

    assert verdicts(probabilities, replay_facts)["action"] == expected
