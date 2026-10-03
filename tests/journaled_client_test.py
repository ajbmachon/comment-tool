"""The journal keeps the exact request and response bytes the round audit parses, `.env` loading never
overrides the real environment, and a foreign repository is refused.

Measured truth only: a response row names the hash of the bytes actually sent, or `null` when no
request bytes were captured — a planned body is never recorded as a sent one.
"""

import base64
import hashlib
import json
import os

import pytest
from jev_navigator.judgments.journal import JournalRequest, RawResponse
from jev_navigator.judgments.questions import request_body

from comment_tool.journal.journaled_client import (
    ExchangeJournal,
    NotOwnRepositoryError,
    load_env,
    sent_bodies,
)

pytestmark = pytest.mark.local

BODY = b'{"answers": {"q": {"noul": 0.9}}}'
WIRE_BODY = b'{"state":{"s":1},"model":"jev-latest","questions":{"q":{}}}'


def request() -> JournalRequest:
    return JournalRequest(request_sha256="a" * 64, requested_model="drex-latest", state={"s": 1}, questions={"q": {}})


def response_rows(path) -> list[dict]:
    return [row for row in map(json.loads, path.read_text().splitlines()) if row["kind"] == "response"]


def test_a_response_is_journaled_under_its_request_hash_with_exact_bytes(tmp_path):
    journal = ExchangeJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_response(request_id, RawResponse(BODY, 200, "application/json"))

    [row] = response_rows(tmp_path / "journal.jsonl")
    assert row["request_id"] == "a" * 64
    assert base64.b64decode(row["response_body_base64"]) == BODY
    assert (row["response_status"], row["response_read_status"]) == (200, "complete")
    assert row["model"] == "drex-latest"
    assert row["provider_request_sha256"] is None  # with no captured request bytes, nothing is inferred
    # The audit reads the request bytes back by hash.
    assert sent_bodies(tmp_path / "journal.jsonl")["a" * 64]


def test_a_response_binds_the_measured_wire_bytes_never_the_planned_body(tmp_path):
    journal = ExchangeJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_response(request_id, RawResponse(BODY, 200, "application/json", sent_body=WIRE_BODY))

    [row] = response_rows(tmp_path / "journal.jsonl")
    assert base64.b64decode(row["sent_body_base64"]) == WIRE_BODY
    assert row["provider_request_sha256"] == hashlib.sha256(WIRE_BODY).hexdigest()
    assert row["provider_request_sha256"] != hashlib.sha256(request_body({"s": 1}, {"q": {}})).hexdigest()


def test_a_failure_with_a_response_keeps_its_bytes(tmp_path):
    journal = ExchangeJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_failure(request_id, "ValueError: bad json", RawResponse(b"not json", 502, "text/plain"))

    [row] = response_rows(tmp_path / "journal.jsonl")
    assert base64.b64decode(row["response_body_base64"]) == b"not json"
    assert (row["response_status"], row["response_read_status"]) == (502, "failed")


def test_a_failure_without_a_response_keeps_its_error_and_closes_the_exchange(tmp_path):
    journal = ExchangeJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_failure(request_id, "ConnectTimeout: no route")

    assert response_rows(tmp_path / "journal.jsonl") == []  # an uncaptured exchange invents no response bytes
    lines = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    [failure] = [row for row in lines if row["kind"] == "failure"]
    assert failure["error"] == "ConnectTimeout: no route"
    assert failure["request_id"] == "a" * 64  # the error still names the exchange it refused
    assert "response_body_base64" not in failure and "sent_body_base64" not in failure
    assert sent_bodies(tmp_path / "journal.jsonl")["a" * 64]  # the replay slot of the exchange stays intact


def test_a_refused_exchange_is_journaled_once_even_when_its_error_is_journaled_too(tmp_path):
    journal = ExchangeJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_response(request_id, RawResponse(b"not json", 502, "text/plain", sent_body=WIRE_BODY))
    journal.record_failure(request_id, "ValueError: bad json", RawResponse(b"not json", 502, "text/plain",
                                                                           sent_body=WIRE_BODY))

    assert len(response_rows(tmp_path / "journal.jsonl")) == 1  # the exchange's bytes are kept exactly once


def test_code_from_another_repository_is_never_journaled(tmp_path):
    with pytest.raises(NotOwnRepositoryError):
        ExchangeJournal(tmp_path / "journal.jsonl", "run", {"heedvane", "customer-repo"})


def test_env_file_contributes_but_never_overrides_the_real_environment(tmp_path):
    (tmp_path / ".env").write_text(
        "# tool config\n"
        "TYPESAFE_BASE_URL=https://drex.nace.ai\n"
        'TYPESAFE_DEFAULT_MODEL="drex-latest"\n'
        "export TYPESAFE_API_KEY=from-file\n"
        "broken line without equals\n"
    )
    os.environ["TYPESAFE_API_KEY"] = "from-shell"

    contributed = load_env(tmp_path)

    try:
        assert contributed["TYPESAFE_API_KEY"] == "from-file"  # what the file holds...
        assert os.environ["TYPESAFE_API_KEY"] == "from-shell"  # ...but the shell keeps winning
        assert os.environ["TYPESAFE_BASE_URL"] == "https://drex.nace.ai"
        assert os.environ["TYPESAFE_DEFAULT_MODEL"] == "drex-latest"
    finally:
        for key in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_DEFAULT_MODEL"):
            os.environ.pop(key, None)
