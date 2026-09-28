"""Jev over HTTP with a durable journal: jev-navigator's `Journal` protocol, fitted to the Evals
`ProviderResponseJournal` by a thin adapter.

The client splits sending from parsing. `send` returns the library's `RawResponse` (exact body
bytes, HTTP status, content type), so the judge journals those bytes before `parse` reads them. The adapter writes the
request body the client sends, built by the same function, byte for byte. Only our own
repositories may be journaled, because a request carries their code.
"""

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
    def __init__(self, model: str = LATEST_JEV) -> None:
        self.model = model
        self._key = _providers().credential("TYPESAFE_API_KEY", KEY_FILE)

    def ask(self, state: Mapping, questions: Mapping) -> JevResponse:
        return self.parse(self.send(state, questions))

    def send(self, state: Mapping, questions: Mapping) -> RawResponse:
        """The exact response body bytes, with HTTP status and content type; nothing is parsed here."""
        http = urllib.request.Request(_providers().JEV_URL, data=request_body(self.model, state, questions), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self._key})
        received = {}
        _providers().post_json(http, TIMEOUT_SECONDS, response_observer=received.update)
        return RawResponse(received["body"], received["status"], received["content_type"])

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


def _response_event(response: RawResponse) -> dict:
    return {"kind": "response", "attempt": FIRST_ATTEMPT, "status": response.status,
            "content_type": response.content_type, "body": response.body}


def journaled_judge(out: Path, repositories: set[str]) -> Judge:
    """A Judge whose every exchange is journaled in `out/journal.jsonl` and whose store keeps requests."""
    return Judge(JevHttpClient(), journal=EvalsJournal(out / "journal.jsonl", out.name, repositories),
                 store=JsonlAnswerStore(out / "answers.jsonl", keep_requests=True))
