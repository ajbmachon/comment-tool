"""The real SDK sends to a loopback endpoint that independently retains request and reply bytes."""

import base64
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from jev_navigator.judgments.client import InputBudgetExceededError
from jev_navigator.judgments.questions import request_sha256
from pydantic import ValidationError
from typesafe_sdk._core.errors import TypeSafeAPIConnectionError, TypeSafeRateLimitError

from comment_tool.cli.sweep import QUESTIONS
from comment_tool.core.comment_review import question_set
from comment_tool.journal.journaled_client import journaled_judge, sent_bodies, submitted_bodies
from research.rounds import row_audit
from research.rounds.gate_first_answers import require_sent_states, sent_states

pytestmark = pytest.mark.local

STATE = {"comment": {"text": "// z first"}, "code": {"before_comment": "a", "after_comment": "b"}}
MARKERS = ("clean", "refuse", "budget", "garbage", "invalid", "disconnect", "clean_after")
BUDGET_BODY = json.dumps({"detail": {"error_type": "max_tokens_exceeded"}}).encode()


class DecisionEndpoint(BaseHTTPRequestHandler):
    """Keep the exact received body independently of the client and journal."""

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        request = json.loads(body)
        marker = request["state"]["marker"]
        if marker == "disconnect":
            self.server.received.setdefault(marker, []).append((body, None))
            self.close_connection = True
            return  # the endpoint observed a request, but the capture owner received no response
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
                    answers[name] = {"type": "noul", "noul": "not a probability" if marker == "invalid" else 0.1}
                elif question["type"] == "choice":
                    labels = list(question["criteria"])
                    answers[name] = {"type": "choice", "choice": labels[0], "confidence": 1.0,
                                     "probabilities": {label: float(i == 0) for i, label in enumerate(labels)}}
                else:
                    answers[name] = {"type": "score", "score": 0.0, "confidence": 1.0,
                                     "legend": question["criteria"], "probabilities": {}}
            code, content_type = 200, "application/json"
            payload = json.dumps({"model": request["model"], "answers": answers}).encode()
        self.server.received.setdefault(marker, []).append((body, payload))
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        """The endpoint's retained bytes provide the evidence."""


@pytest.fixture
def run(tmp_path, monkeypatch):
    endpoint = ThreadingHTTPServer(("127.0.0.1", 0), DecisionEndpoint)
    endpoint.received = {}
    thread = threading.Thread(target=endpoint.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("TYPESAFE_BASE_URL", f"http://127.0.0.1:{endpoint.server_port}")
    monkeypatch.setenv("TYPESAFE_API_KEY", "local-protocol-test")
    monkeypatch.setenv("TYPESAFE_DEFAULT_MODEL", "jev-latest")
    monkeypatch.setenv("SYSTEM_ONE_ROUTES", "")
    try:
        judge = journaled_judge(tmp_path, {"heedvane"})
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
        yield {"journal": tmp_path / "journal.jsonl", "questions": questions, "answered": answered,
               "raised": raised, "states": states, "received": endpoint.received}
    finally:
        endpoint.shutdown()
        endpoint.server_close()
        thread.join()


def test_measured_wire_errors_and_replay_follow_the_actual_http_exchange(run):
    journal = run["journal"]
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    measured, submitted = sent_bodies(journal), submitted_bodies(journal)
    assert set(run["answered"]) == {"clean", "clean_after"}  # a prior SDK failure cannot poison the next send
    assert set(run["raised"]) == {"refuse", "budget", "garbage", "invalid", "disconnect"}
    assert isinstance(run["raised"]["refuse"], TypeSafeRateLimitError)
    assert run["raised"]["refuse"].body == "Too Many Requests"
    assert isinstance(run["raised"]["budget"], InputBudgetExceededError)
    assert "max_tokens_exceeded" in str(run["raised"]["budget"])
    assert run["raised"]["budget"].__cause__.body == json.loads(BUDGET_BODY)
    assert isinstance(run["raised"]["garbage"], ValidationError)
    assert isinstance(run["raised"]["invalid"], ValueError)
    assert isinstance(run["raised"]["disconnect"], TypeSafeAPIConnectionError)

    native_ids = {}
    for marker in MARKERS:
        [request] = [row for row in rows if row["kind"] == "request"
                     and json.loads(base64.b64decode(row["request_body_base64"]))["state"]["marker"] == marker]
        request_id = request["request_id"]
        native_ids[marker] = request_id
        native = json.loads(submitted[request_id])
        assert request_sha256(native["state"], native["questions"]) == request_id
        responses = [row for row in rows if row["kind"] == "response" and row["request_id"] == request_id]
        failures = [row for row in rows if row["kind"] == "failure" and row["request_id"] == request_id]
        if marker == "disconnect":
            assert responses == []
            assert request_id not in measured
            [failure] = failures
            error = run["raised"][marker]
            assert failure["error"] == f"{type(error).__name__}: {error}"
            assert "response_body_base64" not in failure and "sent_body_base64" not in failure
            continue
        [response] = responses
        received_body, reply_body = run["received"][marker][-1]  # the SDK may retry a refusal
        assert measured[request_id] == received_body
        assert base64.b64decode(response["sent_body_base64"]) == received_body
        assert response["provider_request_sha256"] == hashlib.sha256(received_body).hexdigest()
        assert response["provider_request_sha256"] != hashlib.sha256(submitted[request_id]).hexdigest()
        wire = json.loads(received_body)
        assert wire["state"] == run["states"][marker]
        assert wire["model"] == "jev-latest"
        assert wire["questions"] != native["questions"]  # rich native criteria were flattened by the adapter
        assert base64.b64decode(response["response_body_base64"]) == reply_body
        assert response["response_sha256"] == hashlib.sha256(reply_body).hexdigest()
        if marker in run["raised"]:
            error = run["raised"][marker]
            [failure] = failures
            assert failure["error"] == f"{type(error).__name__}: {error}"
            assert "response_body_base64" not in failure
            assert response["response_read_status"] == "failed"
        else:
            assert failures == []
            assert response["response_read_status"] == "complete"

    assert set(submitted) == set(native_ids.values())
    assert set(measured) == set(native_ids.values()) - {native_ids["disconnect"]}
    sets = row_audit.registered_question_sets(run["questions"])
    row_audit.audit_journal(journal, sets)  # registration is checked against native intent
    exchanges = row_audit.journal_exchanges(journal)
    assert set(exchanges) == {native_ids["clean"], native_ids["clean_after"]}
    assert exchanges[native_ids["clean"]]["questions"] == sets.first
    assert exchanges[native_ids["clean"]]["state"] == run["states"]["clean"]
    assert exchanges[native_ids["clean"]]["nouls"] == {check.name: 0.1 for check in run["questions"].checks}
    states = sent_states(journal)
    assert states == {native_ids[marker]: state for marker, state in run["states"].items() if marker != "disconnect"}
    captured_markers = [marker for marker in MARKERS if marker != "disconnect"]
    require_sent_states(journal, [{"location": marker, "request_sha256": native_ids[marker]} for marker in captured_markers],
                        [{"state": run["states"][marker]} for marker in captured_markers])
