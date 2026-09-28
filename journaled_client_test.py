"""The Evals journal adapter keeps the exact response bytes the library hands it, and the client reports
the exact request bytes it sent."""

import base64
import json

import pytest
from jev_navigator.judgments.journal import JournalRequest, RawResponse

from journaled_client import EvalsJournal, JevHttpClient, NotOwnRepositoryError

pytestmark = pytest.mark.local

BODY = b'{"answers": {"q": {"noul": 0.9}}}'


def request() -> JournalRequest:
    return JournalRequest(request_sha256="a" * 64, requested_model="jev-latest", state={"s": 1}, questions={"q": {}})


class RecordingProviders:
    """The Evals POST helper at the network boundary: it records the posted bytes and answers once."""

    JEV_URL = "https://jev.invalid/v1"

    def __init__(self) -> None:
        self.posted: list[bytes] = []

    def credential(self, name, key_file) -> str:
        return "key"

    def post_json(self, http, timeout, response_observer) -> None:
        self.posted.append(http.data)
        response_observer({"body": BODY, "status": 200, "content_type": "application/json"})


def response_rows(path) -> list[dict]:
    return [row for row in map(json.loads, path.read_text().splitlines()) if row["kind"] == "response"]


def test_a_response_is_journaled_with_its_exact_bytes_and_status(tmp_path):
    journal = EvalsJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_response(request_id, RawResponse(BODY, 200, "application/json"))

    [row] = response_rows(tmp_path / "journal.jsonl")
    assert base64.b64decode(row["response_body_base64"]) == BODY
    assert (row["response_status"], row["response_read_status"]) == (200, "complete")


def test_a_failure_with_a_response_keeps_its_bytes(tmp_path):
    journal = EvalsJournal(tmp_path / "journal.jsonl", "run", {"heedvane"})
    request_id = journal.record_request(request())

    journal.record_failure(request_id, "ValueError: bad json", RawResponse(b"not json", 502, "text/plain"))

    [row] = response_rows(tmp_path / "journal.jsonl")
    assert base64.b64decode(row["response_body_base64"]) == b"not json"
    assert (row["response_status"], row["response_read_status"]) == (502, "failed")


def test_code_from_another_repository_is_never_journaled(tmp_path):
    with pytest.raises(NotOwnRepositoryError):
        EvalsJournal(tmp_path / "journal.jsonl", "run", {"heedvane", "customer-repo"})


def test_the_client_reports_the_exact_bytes_it_sent():
    providers = RecordingProviders()
    client = JevHttpClient(providers=providers)

    raw = client.send({"z": 1, "a": 2}, {"q": {}})

    assert raw.sent_body == providers.posted[0]
    assert raw.sent_body.index(b'"z"') < raw.sent_body.index(b'"a"')
