"""Gate replay reads measured states, compares decoded content and refuses unavailable capture."""

import json
from pathlib import Path

import pytest
from jev_navigator.judgments.journal import JournalRequest, RawResponse
from jev_navigator.judgments.questions import request_sha256

from comment_tool.journal.journaled_client import ExchangeJournal
from research.rounds import gate_first_answers
from research.rounds.gate_first_answers import (
    SentStateMismatchError,
    SentStateUnavailableError,
    lib_escalations,
    require_sent_states,
    sent_states,
)

pytestmark = pytest.mark.local

DATA = Path.home() / ".claude/handoffs/effect-2026-09-25/comment-tool"
LIB = DATA / "pass" / "lib-a3bde2aa-rebuilt"

SENT_STATE = {"comment": {"text": "// z first"}, "code": {"before_comment": "a", "after_comment": "b"}}
SORTED_COPY = {"comment": {"text": "// z first"}, "code": {"after_comment": "b", "before_comment": "a"}}
CODE_ELSEWHERE = {"comment": {"text": "// z first"}, "code": {"before_comment": "a", "after_comment": "b",
                                                             "elsewhere": []}}
QUESTIONS = {"q": {"type": "noul", "criteria": {"x": "x"}}}


def journal_with(tmp_path: Path, state: dict, *, capture: bool = True) -> tuple[Path, str]:
    """A real journal with compact captured JSON, or native intent alone."""
    path = tmp_path / "journal.jsonl"
    request_hash = request_sha256(state, QUESTIONS)
    journal = ExchangeJournal(path, "run", {"heedvane"})
    exchange_id = journal.record_request(JournalRequest(request_hash, "jev-latest", state, QUESTIONS))
    if capture:
        wire = json.dumps({"state": state, "questions": QUESTIONS}, separators=(",", ":")).encode()
        journal.record_response(exchange_id, RawResponse(
            b'{"model":"jev-latest","answers":{"q":{"type":"noul","noul":0.1}}}',
            200, "application/json", sent_body=wire))
    return path, request_hash


def test_the_sent_state_is_read_back_in_its_sent_order(tmp_path):
    path, sent_hash = journal_with(tmp_path, SENT_STATE)

    state = sent_states(path)[sent_hash]

    assert list(state) == ["comment", "code"] and list(state["code"]) == ["before_comment", "after_comment"]
    # Re-ordering the keys of a state changes neither its content nor its hash, so the hash on its
    # own can never be the check that a replay was asked the same question. What has to survive is
    # the state itself, in the order it went out.
    assert request_sha256(SORTED_COPY, QUESTIONS) == request_sha256(SENT_STATE, QUESTIONS)


def test_a_request_that_carried_a_different_state_is_refused(tmp_path):
    path, sent_hash = journal_with(tmp_path, SENT_STATE)
    row = {"location": "a.ts:1", "request_sha256": sent_hash}

    require_sent_states(path, [row], [{"state": SENT_STATE}])  # the state that went out, as it went out
    require_sent_states(path, [row], [{"state": SORTED_COPY}])  # the same content, keys in another order

    with pytest.raises(SentStateMismatchError):
        require_sent_states(path, [row], [{"state": CODE_ELSEWHERE}])  # a code region that never went out


@pytest.mark.parametrize("capture", [False, True])
def test_missing_measured_state_is_unavailable_even_when_native_intent_exists(tmp_path, capture):
    path, request_id = journal_with(tmp_path, SENT_STATE, capture=capture)
    row = {"location": "a.ts:1", "request_sha256": "b" * 64 if capture else request_id}
    with pytest.raises(SentStateUnavailableError):
        require_sent_states(path, [row], [{"state": SENT_STATE}])


def test_historical_lib_intent_cannot_prove_a_measured_state(monkeypatch):
    monkeypatch.setattr(gate_first_answers, "LIB", LIB)
    assert sent_states(LIB / "journal.jsonl") == {}
    with pytest.raises(SentStateUnavailableError):
        lib_escalations()


@pytest.mark.parametrize("kind, expected", [("jsdoc", "rewrite"), ("block", "remove")])
def test_gate_replay_preserves_the_sweeps_comment_kind(tmp_path, monkeypatch, kind, expected):
    import research.rounds.gate_first_answers as gate_first_answers_module
    from comment_tool.core.comment_review import question_set
    from research.analysis.gate_exact_compare import comment_facts, verdicts
    from research.rounds.run_round4 import ROUND4_QUESTIONS

    _, request_hash = journal_with(tmp_path, SENT_STATE)
    row = {
        "location": "example.ts:1", "kind": kind, "comment": "/** Obvious noise. */",
        "decided_by": "escalated", "search": {}, "request_sha256": request_hash,
    }
    (tmp_path / "apps-example.jsonl").write_text(json.dumps(row) + "\n")
    monkeypatch.setattr(gate_first_answers_module, "LIB", tmp_path)
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    probabilities = {check.name: 0.05 for check in questions.checks}
    probabilities["is_noise"] = 0.95

    replay_facts = comment_facts()[row["location"]]

    assert verdicts(probabilities, replay_facts)["action"] == expected
