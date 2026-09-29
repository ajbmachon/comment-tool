"""Jev over HTTP with a durable journal: jev-navigator's `Journal` protocol, fitted to the Evals
`ProviderResponseJournal` by a thin adapter.

The client splits sending from parsing. `send` returns the library's `RawResponse` (exact body
bytes, HTTP status, content type), so the judge journals those bytes before `parse` reads them. The adapter writes the
request body the client sends, built by the same function, byte for byte. Only our own
repositories may be journaled, because a request carries their code.
"""

import base64
import json
import sys
import urllib.request
from collections.abc import Mapping
from functools import cache
from pathlib import Path

from jev_navigator.judgments.answers import JevResponse, response_from_raw
from jev_navigator.judgments.client import LATEST_JEV
from jev_navigator.judgments.journal import JournalRequest, RawResponse
from jev_navigator.judgments.judge import Judge
from jev_navigator.judgments.store import JsonlAnswerStore

EVALS_CHECKOUT = Path.home() / "Projects/heedvane-evals-clm-quality"

OWN_REPOSITORIES = frozenset({"heedvane", "analysis-engine"})
KEY_FILE = Path.home() / ".config/jgrep/env"
TIMEOUT_SECONDS = 120
FIRST_ATTEMPT = 1


@cache
def _providers():
    """The Evals provider helpers (credential, endpoint, POST); loaded on first use, so the tool and its
    offline tests import without the heedvane-evals checkout."""
    sys.path.insert(0, str(EVALS_CHECKOUT))
    from experiments import compare_decision_providers
    return compare_decision_providers


@cache
def _response_journal_class():
    sys.path.insert(0, str(EVALS_CHECKOUT))
    from experiments.provider_response_journal import ProviderResponseJournal
    return ProviderResponseJournal


class NotOwnRepositoryError(ValueError):
    """Journaling would store code from a repository that is not ours."""


def request_body(model: str, state: Mapping, questions: Mapping) -> bytes:
    return json.dumps({"model": model, "state": state, "questions": questions}).encode()


class JevHttpClient:
    """`providers` is the Evals helper module (credential, endpoint, POST); loaded from the checkout by default."""

    def __init__(self, model: str = LATEST_JEV, providers=None) -> None:
        self.model = model
        self._providers = providers or _providers()
        self._key = self._providers.credential("TYPESAFE_API_KEY", KEY_FILE)

    def ask(self, state: Mapping, questions: Mapping) -> JevResponse:
        return self.parse(self.send(state, questions))

    def send(self, state: Mapping, questions: Mapping) -> RawResponse:
        """The exact response body bytes, with HTTP status and content type, and the exact request bytes
        sent, so the answer store keeps the request as sent; nothing is parsed here."""
        body = request_body(self.model, state, questions)
        http = urllib.request.Request(self._providers.JEV_URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self._key})
        received = {}
        self._providers.post_json(http, TIMEOUT_SECONDS, response_observer=received.update)
        return RawResponse(received["body"], received["status"], received["content_type"], sent_body=body)

    def parse(self, raw: RawResponse) -> JevResponse:
        return response_from_raw(raw.json())


class EvalsJournal:
    """jev-navigator's Journal protocol over `ProviderResponseJournal`."""

    def __init__(self, path: Path, run_id: str, repositories: set[str]) -> None:
        foreign = repositories - OWN_REPOSITORIES
        if foreign:
            raise NotOwnRepositoryError(f"{sorted(foreign)} are not own repositories; their code must not be stored")
        self._journal = _response_journal_class()(path, run_id)
        self._exchanges = {}

    def record_request(self, request: JournalRequest) -> str:
        exchange = self._journal.exchange(request.request_sha256, "jev", model=request.requested_model,
                                          operation="comment_review", submitted_request_sha256=request.request_sha256)
        self._exchanges[exchange.exchange_id] = exchange
        exchange({"kind": "request", "attempt": FIRST_ATTEMPT, "endpoint": _providers().JEV_URL, "content_type": "application/json",
                  "body": request_body(request.requested_model, request.state, request.questions)})
        return exchange.exchange_id

    def record_response(self, request_id: str, response: RawResponse) -> None:
        self._exchanges.pop(request_id)(_response_event(response))

    def record_failure(self, request_id: str, error: str, response: RawResponse | None = None) -> None:
        """A failure keeps the response bytes when one arrived but did not parse."""
        received = _response_event(response) if response is not None else {"kind": "response", "attempt": FIRST_ATTEMPT,
                                                                            "status": None, "body": b""}
        self._exchanges.pop(request_id)({**received, "read_status": "failed", "read_error": error})


def sent_bodies(path: Path) -> dict[str, bytes]:
    """Request id (the request's hash) to the exact body bytes sent, for every request in a journal."""
    return {event["request_id"]: base64.b64decode(event["request_body_base64"])
            for event in map(json.loads, path.read_text().splitlines()) if event["kind"] == "request"}


def _response_event(response: RawResponse) -> dict:
    return {"kind": "response", "attempt": FIRST_ATTEMPT, "status": response.status,
            "content_type": response.content_type, "body": response.body}


def journaled_judge(out: Path, repositories: set[str]) -> Judge:
    """A Judge whose every exchange is journaled in `out/journal.jsonl` and whose store keeps requests."""
    return Judge(JevHttpClient(), journal=EvalsJournal(out / "journal.jsonl", out.name, repositories),
                 store=JsonlAnswerStore(out / "answers.jsonl", keep_requests=True))
