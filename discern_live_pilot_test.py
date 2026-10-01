"""The frozen-request pilot boundary: identity verification, byte-exact journaling, honest failures.

These tests run the real adapter, the real journaled Judge and a local HTTP substitute for the
licensed provider. The substitute is only the provider: the journal, the store and the parser stay
the owners they are in production, so a lost response body or a fabricated probability fails here.
"""

import base64
import hashlib
import json
import os
import select
import signal
import subprocess
import sys
import threading
from http.client import IncompleteRead
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from jev_navigator.judgments.thresholds import Thresholds

import journaled_client
from discern_live_pilot import live, load_request_row, prepare, verified_request
from journaled_client import journaled_judge, request_body

pytestmark = pytest.mark.local

FROZEN_JOURNAL = Path("/Users/andremachon/.claude/handoffs/effect-2026-09-25/comment-tool/docs/journal.jsonl")
FROZEN_REQUEST_ID = "d64f8f8787f5cf5cba55297b67213f6776941a7f9905e4f7b5441485046ff8cf"
FROZEN_WIRE = "94853929762756f6eb0f8efbd9acf37a2400bcb4c2836e25f0df7725498fd3e5"
SERVED_MODEL = "pilot-substitute-1"


@pytest.fixture(autouse=True)
def substitute_credential(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "pilot-local-dummy")


class SubstituteProvider:
    """A local stand-in for the licensed provider: real HTTP, real status codes, no mock layer."""

    def __init__(self, respond, *, declared_size_offset: int = 0) -> None:
        self.respond = respond
        self.declared_size_offset = declared_size_offset
        self.received = []

    def __enter__(self) -> str:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.received.append(body)
                status, content_type, reply = outer.respond(body)
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(reply) + outer.declared_size_offset))
                self.end_headers()
                self.wfile.write(reply)

            def log_message(self, *args) -> None:
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *args) -> None:
        self.server.shutdown()
        self.server.server_close()


def frozen_body() -> bytes:
    """The exact wire bytes of the frozen request, read from the real journal row."""
    row = json.loads(next(line for line in FROZEN_JOURNAL.open() if FROZEN_REQUEST_ID in line))
    return base64.b64decode(row["request_body_base64"])


def frozen_row(tmp_path: Path) -> Path:
    """The real frozen request row, copied into a journal the test owns."""
    journal = tmp_path / "frozen" / "journal.jsonl"
    journal.parent.mkdir(parents=True)
    journal.write_text(next(line for line in FROZEN_JOURNAL.open() if FROZEN_REQUEST_ID in line))
    return journal


def substitute_answers(body: bytes, *, omit: str | None = None) -> bytes:
    """The recorded provider response shape, with controlled Nouls for this transport proof."""
    questions = json.loads(body)["questions"]
    request = load_request_row(FROZEN_JOURNAL, FROZEN_REQUEST_ID)
    response = next(row for row in map(json.loads, FROZEN_JOURNAL.open())
                    if row.get("kind") == "response" and row.get("exchange_id") == request["exchange_id"]
                    and row.get("response_status") == 200)
    answers = json.loads(base64.b64decode(response["response_body_base64"]))["answers"]
    for question_id, question in questions.items():
        if question.get("type") == "noul":
            answers[question_id] = {"type": "noul", "noul": 0.5}
    if omit is not None:
        del answers[omit]
    return json.dumps({"model": SERVED_MODEL, "usage": {"input_tokens": 1234}, "answers": answers}).encode()


def response_rows(path: Path) -> list[dict]:
    return [row for row in map(json.loads, path.open()) if row.get("kind") == "response"]


def failure_rows(path: Path) -> list[dict]:
    return [row for row in response_rows(path) if row.get("response_read_status") == "failed"]


def judge_against(tmp_path: Path, monkeypatch, endpoint: str):
    """The production judge, with its client pointed at the substitute through the evals URL it reads."""
    monkeypatch.setenv("TYPESAFE_API_KEY", "pilot-local-dummy")
    monkeypatch.setattr(journaled_client._providers(), "JEV_URL", endpoint)
    return journaled_judge(tmp_path / "live", {"heedvane"})


def test_prepare_reports_the_frozen_identity_without_credentials_or_provider(tmp_path, monkeypatch):
    def refuse(*args):
        raise AssertionError("prepare must not touch the provider helpers")

    monkeypatch.setattr(journaled_client, "_providers", refuse)
    observation = prepare(frozen_row(tmp_path), FROZEN_REQUEST_ID)

    assert observation["mode"] == "prepare"
    assert observation["request"]["request_sha256"] == FROZEN_REQUEST_ID
    assert observation["request"]["provider_request_sha256"] == FROZEN_WIRE
    assert observation["request"]["requested_model"] == "jev-latest"
    assert len(observation["request"]["question_ids"]) == 18
    assert len(observation["request"]["noul_question_ids"]) == 14


def test_prepare_refuses_a_tampered_wire_or_canonical_hash(tmp_path):
    journal = tmp_path / "frozen" / "journal.jsonl"
    journal.parent.mkdir(parents=True)
    row = json.loads(next(line for line in FROZEN_JOURNAL.open() if FROZEN_REQUEST_ID in line))

    journal.write_text(json.dumps({**row, "provider_request_sha256": "0" * 64}))
    with pytest.raises(ValueError, match="wire hash mismatch"):
        prepare(journal, FROZEN_REQUEST_ID)

    # Same wire identity, but a body whose canonical hash no longer matches the row's request id.
    body = json.loads(base64.b64decode(row["request_body_base64"]))
    body["state"]["comment"]["text"] += " tampered"
    reencoded = request_body(body["model"], body["state"], body["questions"])
    journal.write_text(json.dumps({**row, "request_body_base64": base64.b64encode(reencoded).decode("ascii"),
                                   "provider_request_sha256": hashlib.sha256(reencoded).hexdigest()}))
    with pytest.raises(ValueError, match="canonical hash mismatch"):
        prepare(journal, FROZEN_REQUEST_ID)


@pytest.mark.parametrize(("malformed", "failure_type"), [(b"<html>not json at all</html>", json.JSONDecodeError), (b"[]", TypeError)])
def test_a_malformed_response_keeps_its_exact_bytes_and_original_cause(tmp_path, monkeypatch, malformed, failure_type):
    with SubstituteProvider(lambda body: (200, "text/html", malformed)) as endpoint:
        judge = judge_against(tmp_path, monkeypatch, endpoint)
        row = load_request_row(frozen_row(tmp_path), FROZEN_REQUEST_ID)
        parsed, _wire = verified_request(row)
        with pytest.raises(failure_type) as caught:
            judge.ask(parsed["state"], parsed["questions"], thresholds=Thresholds())

    [failure] = failure_rows(tmp_path / "live" / "journal.jsonl")
    assert base64.b64decode(failure["response_body_base64"]) == malformed
    assert failure["response_status"] == 200
    assert failure["response_read_error"] == f"{type(caught.value).__name__}: {caught.value}"


@pytest.mark.parametrize(("status", "valid_json", "size_offset"), [(502, False, 0), (502, True, 0), (200, True, 1)])
def test_transport_failures_keep_bytes_and_cause_without_accepting_answers(tmp_path, monkeypatch, status, valid_json, size_offset):
    refused = substitute_answers(frozen_body()) if valid_json else b"upstream unavailable"
    failure_type = IncompleteRead if size_offset else journaled_client._providers().ProviderHTTPError
    provider = SubstituteProvider(lambda body: (status, "application/json", refused), declared_size_offset=size_offset)
    with provider as endpoint:
        judge = judge_against(tmp_path, monkeypatch, endpoint)
        row = load_request_row(frozen_row(tmp_path), FROZEN_REQUEST_ID)
        parsed, _wire = verified_request(row)
        with pytest.raises(failure_type) as caught:
            judge.ask(parsed["state"], parsed["questions"], thresholds=Thresholds())

    rows = response_rows(tmp_path / "live" / "journal.jsonl")
    captured, failure = rows
    assert base64.b64decode(captured["response_body_base64"]) == refused
    assert captured["response_status"] == status
    assert captured["response_read_status"] == ("failed" if size_offset else "complete")
    assert base64.b64decode(failure["response_body_base64"]) == refused
    assert failure["response_read_error"] == f"{type(caught.value).__name__}: {caught.value}"
    assert len(provider.received) == 1
    if not size_offset:
        assert caught.value.code == status


@pytest.mark.parametrize("missing_type", ["noul", "choice"])
def test_live_refuses_a_response_that_leaves_an_answer_unanswered(tmp_path, missing_type):
    unanswered = next(question_id for question_id, question in json.loads(frozen_body())["questions"].items()
                      if question["type"] == missing_type)

    with (SubstituteProvider(lambda body: (200, "application/json", substitute_answers(body, omit=unanswered))) as endpoint,
          pytest.raises(ValueError, match=unanswered)):
        live(frozen_row(tmp_path), FROZEN_REQUEST_ID, tmp_path / "live", endpoint)


def test_raw_response_survives_process_interruption_before_the_first_response_parse(tmp_path):
    """Stop the real child at its first response decode, kill it, then reopen its durable journal."""
    child_code = r'''
import json, os, signal, sys
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
import journaled_client
from pathlib import Path
from discern_live_pilot import load_request_row, verified_request
from jev_navigator.judgments.thresholds import Thresholds
row = load_request_row(Path(sys.argv[2]), sys.argv[3])
request, _ = verified_request(row)
journaled_client._providers().JEV_URL = sys.argv[5]
judge = journaled_client.journaled_judge(Path(sys.argv[4]), {"heedvane"})
def before_decode(frame, event, result):
    if event == "call" and frame.f_code is json.loads.__code__ and frame.f_locals.get("s") == b"[]":
        print("response_parse_start", flush=True)
        os.kill(os.getpid(), signal.SIGSTOP)
sys.setprofile(before_decode)
judge.ask(request["state"], request["questions"], thresholds=Thresholds())
'''
    out = tmp_path / "interrupted"
    with SubstituteProvider(lambda body: (200, "application/json", b"[]")) as endpoint:
        child = subprocess.Popen([sys.executable, "-c", child_code, str(Path(journaled_client.__file__).parent),
                                  str(FROZEN_JOURNAL), FROZEN_REQUEST_ID, str(out), endpoint],
                                 cwd=Path(__file__).parent, env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            ready, _, _ = select.select([child.stdout], [], [], 10)
            marker = child.stdout.readline() if ready else b""
        finally:
            if child.poll() is None:
                child.kill()
            _, stderr = child.communicate(timeout=5)
    assert marker == b"response_parse_start\n", stderr.decode()
    assert child.returncode == -signal.SIGKILL
    [stored] = response_rows(out / "journal.jsonl")
    assert stored["response_status"] == 200
    assert base64.b64decode(stored["response_body_base64"]) == b"[]"
