"""Every call journals exactly one exchange over the real SDK transport: refusals and malformed
bodies keep their measured wire bytes (never silenced, never journalled twice), and the fresh
journal still replays the registered questions and every sent state.
"""

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from comment_tool.cli.sweep import QUESTIONS
from comment_tool.core.comment_review import question_set
from comment_tool.journal.journaled_client import journaled_judge, sent_bodies
from research.rounds import row_audit
from research.rounds.gate_first_answers import sent_states

pytestmark = pytest.mark.local

STATE = {"comment": {"text": "// z first"}, "code": {"before_comment": "a", "after_comment": "b"}}
MARKERS = ("clean", "refuse", "budget", "garbage")
BUDGET_BODY = json.dumps({"detail": {"error_type": "max_tokens_exceeded"}}).encode()


class DecisionEndpoint(BaseHTTPRequestHandler):
    """Answer each marker with the exact bytes a silent client would have had to lose."""

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        request = json.loads(body)
        marker = request["state"]["marker"]
        if marker == "refuse":
            code, content_type, payload = 429, "text/plain", b"Too Many Requests"
        elif marker == "budget":
            code, content_type, payload = 400, "application/json", BUDGET_BODY
        elif marker == "garbage":
            code, content_type, payload = 200, "application/json", b"not json"
        else:
            answers = {}
            for name, question in request["questions"].items():
                if question["type"] == "noul":
                    answers[name] = {"type": "noul", "noul": 0.1}
                elif question["type"] == "choice":
                    labels = list(question["criteria"])
                    answers[name] = {"type": "choice", "choice": labels[0], "confidence": 1.0,
                                     "probabilities": {label: float(i == 0) for i, label in enumerate(labels)}}
                else:
                    answers[name] = {"type": "score", "score": 0.0, "confidence": 1.0,
                                     "legend": question["criteria"], "probabilities": {}}
            code, content_type = 200, "application/json"
            payload = json.dumps({"model": request["model"], "answers": answers}).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        """Keep the endpoint silent; the exchanges it served are journalled."""


@pytest.fixture
def run(tmp_path, monkeypatch):
    """One journal for one clean answer, one raw 429 refusal, one budget refusal, one malformed answer."""
    endpoint = ThreadingHTTPServer(("127.0.0.1", 0), DecisionEndpoint)
    thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TYPESAFE_BASE_URL", f"http://127.0.0.1:{endpoint.server_port}")
    monkeypatch.setenv("TYPESAFE_API_KEY", "local-protocol-test")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    monkeypatch.setenv("SYSTEM_ONE_ROUTES", "")
    try:
        out = tmp_path / "journal"
        out.mkdir()
        judge = journaled_judge(out, {"heedvane"})
        questions = question_set(json.loads(QUESTIONS.read_text()))
        answered, raised, states = {}, {}, {}
        for marker in MARKERS:
            state = {**STATE, "marker": marker}
            states[marker] = state
            try:
                answered[marker] = judge.ask_all(state, checks=questions.checks, picks=questions.picks,
                                                 scores=questions.scores)
            except Exception as error:
                raised[marker] = error
        yield {"journal": out / "journal.jsonl", "questions": questions, "answered": answered,
               "raised": raised, "states": states}
    finally:
        endpoint.shutdown()
        endpoint.server_close()
        thread.join()


def rows(journal):
    return [json.loads(line) for line in journal.read_text().splitlines()]


def test_a_refusal_or_malformed_answer_journals_its_exchange_exactly_once(run):
    journal = run["journal"]
    lines = rows(journal)

    assert "clean" in run["answered"] and set(run["raised"]) == {"refuse", "budget", "garbage"}
    assert len(lines) == 2 * len(MARKERS)  # no call is silenced and none journals twice
    by_exchange = {}
    for line in lines:
        by_exchange.setdefault(line["exchange_id"], []).append(line)
    for exchange in by_exchange.values():
        [request_row] = [row for row in exchange if row["kind"] == "request"]
        [response_row] = [row for row in exchange if row["kind"] == "response"]
        assert len(response_row["request_id"]) == 64  # every response binds the request's own hash
        measured = base64.b64decode(response_row["sent_body_base64"])
        assert response_row["provider_request_sha256"] == hashlib.sha256(measured).hexdigest()
        assert measured != base64.b64decode(request_row["request_body_base64"])
        # the journalled request hash names the measured wire bytes, never the planned body

    def response_holding(payload: bytes) -> dict:
        [row] = [row for row in lines if row["kind"] == "response"
                 and base64.b64decode(row["response_body_base64"]) == payload]
        return row

    refused = response_holding(b"Too Many Requests")
    assert (refused["response_status"], refused["response_read_status"]) == (429, "failed")
    budget = response_holding(BUDGET_BODY)
    assert (budget["response_status"], budget["response_read_status"]) == (400, "failed")
    assert "max_tokens_exceeded" in str(run["raised"]["budget"])  # the typed refusal still reaches the sweep
    malformed = response_holding(b"not json")
    assert (malformed["response_status"], malformed["response_read_status"]) == (200, "failed")
    clean = next(row for row in lines if row["kind"] == "response"
                 and row["exchange_id"] == f"ex-{run['answered']['clean'].request_sha256[:16]}")
    assert (clean["response_status"], clean["response_read_status"]) == (200, "complete")


def test_the_fresh_journal_replays_the_registered_questions_and_every_sent_state(run):
    journal, questions = run["journal"], run["questions"]

    sets = row_audit.registered_question_sets(questions)
    row_audit.audit_journal(journal, sets)  # a fresh run's own journal must survive the audit unchanged

    exchanges = row_audit.journal_exchanges(journal)
    assert len(exchanges) == 1  # refusals and malformed bytes stay failures, never fake answers
    assert next(iter(exchanges.values()))["questions"] == sets.first
    assert len(sent_states(journal)) == len(MARKERS)
    for state in run["states"].values():
        assert any(json.dumps(state).encode() in body for body in sent_bodies(journal).values())
