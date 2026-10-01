"""Jev over HTTP with a durable journal: jev-navigator's `Journal` protocol, fitted to the Evals
`ProviderResponseJournal` by a thin adapter.

The client splits sending from parsing. `send` returns the library's `RawResponse` (exact body
bytes, HTTP status, content type), so the judge journals those bytes before `parse` reads them. The adapter writes the
request body the client sends, built by the same function, byte for byte. Only our own
repositories may be journaled, because a request carries their code.
"""

import json
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from functools import cache
from http.client import HTTPResponse, IncompleteRead
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


@dataclass(frozen=True, kw_only=True)
class _FailedResponse(RawResponse):
    """Captured bytes whose original transport failure is raised after the judge journals them."""

    error: Exception
    read_error: str | None = None


def request_body(model: str, state: Mapping, questions: Mapping) -> bytes:
    return json.dumps({"model": model, "state": state, "questions": questions}).encode()


class JevHttpClient:
    def __init__(self, model: str = LATEST_JEV, endpoint: str | None = None) -> None:
        self.model = model
        self.endpoint = endpoint
        self._key = _providers().credential("TYPESAFE_API_KEY", KEY_FILE)

    def ask(self, state: Mapping, questions: Mapping) -> JevResponse:
        return self.parse(self.send(state, questions))

    def send(self, state: Mapping, questions: Mapping) -> RawResponse:
        """The exact response body bytes, with HTTP status and content type; nothing is parsed here.

        HTTP and read failures travel with their captured bytes. The judge persists those bytes
        before ``parse`` raises the original cause. The JSON-returning provider helper is not a
        raw transport: it would decode before the judge could make the response durable.
        """
        http = urllib.request.Request(self._endpoint(), data=request_body(self.model, state, questions), headers={
            "Content-Type": "application/json", "Authorization": "Bearer " + self._key})
        try:
            with urllib.request.urlopen(http, timeout=TIMEOUT_SECONDS) as response:
                return _read_response(response, http.data)
        except urllib.error.HTTPError as error:
            with error:
                raw = _read_response(error, http.data)
            read_error = f"{type(raw.error).__name__}: {raw.error}" if isinstance(raw, _FailedResponse) else None
            failure = _providers().ProviderHTTPError(error, raw.body, read_error)
            failure.__cause__ = error
            return _FailedResponse(raw.body, raw.status, raw.content_type, sent_body=http.data, error=failure, read_error=read_error)

    def _endpoint(self) -> str:
        return self.endpoint or _providers().JEV_URL

    def parse(self, raw: RawResponse) -> JevResponse:
        if isinstance(raw, _FailedResponse):
            raise raw.error
        return response_from_raw(raw.json())


def _read_response(response: HTTPResponse | urllib.error.HTTPError, sent_body: bytes) -> RawResponse:
    content_type = response.headers.get("Content-Type", "")
    try:
        body = response.read()
    except IncompleteRead as error:
        return _FailedResponse(error.partial, response.status, content_type, sent_body=sent_body, error=error,
                               read_error=f"{type(error).__name__}: {error}")
    return RawResponse(body, response.status, content_type, sent_body=sent_body)


class EvalsJournal:
    """jev-navigator's Journal protocol over `ProviderResponseJournal`."""

    def __init__(self, path: Path, run_id: str, repositories: set[str], *, endpoint: str | None = None) -> None:
        foreign = repositories - OWN_REPOSITORIES
        if foreign:
            raise NotOwnRepositoryError(f"{sorted(foreign)} are not own repositories; their code must not be stored")
        self._journal = _response_journal_class()(path, run_id)
        self._endpoint = endpoint
        self._exchanges = {}

    def record_request(self, request: JournalRequest) -> str:
        exchange = self._journal.exchange(request.request_sha256, "jev", model=request.requested_model,
                                          operation="comment_review", submitted_request_sha256=request.request_sha256)
        self._exchanges[exchange.exchange_id] = exchange
        exchange({"kind": "request", "attempt": FIRST_ATTEMPT, "endpoint": self._endpoint or _providers().JEV_URL,
                  "content_type": "application/json",
                  "body": request_body(request.requested_model, request.state, request.questions)})
        return exchange.exchange_id

    def record_response(self, request_id: str, response: RawResponse) -> None:
        self._exchanges[request_id](_response_event(response))

    def record_failure(self, request_id: str, error: str, response: RawResponse | None = None) -> None:
        """A failure keeps the response bytes when one arrived but did not parse.

        The judge records the raw response first and then the parse failure for the same exchange,
        so a failure may arrive after the response was already recorded; it still binds to that
        exchange and keeps the exact bytes and the original cause.
        """
        exchange = self._exchanges.pop(request_id)
        received = _response_event(response) if response is not None else {"kind": "response", "attempt": FIRST_ATTEMPT,
                                                                            "status": None, "body": b""}
        exchange({**received, "read_status": "failed", "read_error": error})


def _response_event(response: RawResponse) -> dict:
    event = {"kind": "response", "attempt": FIRST_ATTEMPT, "status": response.status,
             "content_type": response.content_type, "body": response.body}
    if isinstance(response, _FailedResponse) and response.read_error is not None:
        event.update(read_status="failed", read_error=response.read_error)
    return event


def journaled_judge(out: Path, repositories: set[str], *, model: str = LATEST_JEV, endpoint: str | None = None) -> Judge:
    """A Judge whose every exchange is journaled in `out/journal.jsonl` and whose store keeps requests.

    ``endpoint`` points the client at a substitute provider (the pilot's boundary proof); without it
    the client uses the evals helpers' own Jev URL.
    """
    return Judge(JevHttpClient(model=model, endpoint=endpoint),
                 journal=EvalsJournal(out / "journal.jsonl", out.name, repositories, endpoint=endpoint),
                 store=JsonlAnswerStore(out / "answers.jsonl", keep_requests=True))
