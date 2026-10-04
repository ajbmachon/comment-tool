"""The judge the tool runs on: jev-navigator's real client, pointed at any System-One service.

No hand-rolled client and no provider lock-in: the transport is jev-navigator's
`TypeSafeJevClient` (the official SDK with exact-byte capture), and *which* decision service
answers is pure environment — the SDK reads `TYPESAFE_BASE_URL`, `TYPESAFE_API_KEY` and
`TYPESAFE_DEFAULT_MODEL`, so TypeSafe's Jev, Drex by Nace.AI (`https://drex.nace.ai`,
`drex-latest`) and our own finetuned decision models (same wire shape, other base URL) are the
same code behind different variables. No client here names a provider or hardcodes a URL.

Every exchange is journaled in `<out>/journal.jsonl` with the same line schema the scored
rounds' audit parses (`request_id` = the request's sha256, base64 request and response bodies,
response status and read status), fsynced line by line: a run that dies mid-classification
still leaves every completed exchange readable. Two readers read that file and never read each
other's evidence: `submitted_bodies` gives the prepared body (the registered native intent, which
is what the round audit re-hashes and compares) and `sent_bodies` gives the measured wire body
(the bytes the transport put on the wire, which is what a gate replay compares against). They
hold different bytes, and neither one is inferred from the other.

The answer store keeps the exact request bytes (`keep_requests=True`). A request carries the
classified repository's code, so only our own repositories may be journaled.

Environment: keys and endpoints come from the process environment or a `.env` file in the
checkout root — the same convention as `jvn` and `jvr`. Real environment variables win; the
file never overrides anything already set.

usage (`.env` in the checkout root):
    TYPESAFE_BASE_URL=https://drex.nace.ai
    TYPESAFE_API_KEY=...
    TYPESAFE_DEFAULT_MODEL=drex-latest
"""

import base64
import hashlib
import json
import os
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

from jev_navigator.judgments.answers import JevResponse, response_from_raw
from jev_navigator.judgments.client import input_budget_error
from jev_navigator.judgments.journal import JournalRequest, RawResponse
from jev_navigator.judgments.judge import Judge
from jev_navigator.judgments.questions import request_body
from jev_navigator.judgments.store import JsonlAnswerStore

OWN_REPOSITORIES = frozenset({"heedvane", "analysis-engine"})
"""A request carries code, so only these repositories may be journaled."""

DEFAULT_MODEL = "jev-latest"


def load_env(root: Path | None = None) -> dict[str, str]:
    """Load `.env` from the checkout root into `os.environ`, without overriding real variables.

    Same convention in every Jev tool (`jvn`, `jvr`, this one): `.env` in the repository root,
    `KEY=value` lines, `#` comments, optional `export ` prefix, quotes stripped. Returns the
    variables the file contributed.
    """
    path = (root or Path(__file__).resolve().parents[3]) / ".env"
    if not path.exists():
        return {}
    contributed = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if not key:
            continue
        contributed[key] = value
        os.environ.setdefault(key, value)
    return contributed


class NotOwnRepositoryError(ValueError):
    """Journaling would store code from a repository that is not ours."""


def flatten_criteria(questions: Mapping) -> dict:
    """Criteria values as plain strings, deterministically — the System-One wire floor.

    Jev also accepts rich criteria values (`{"what": ..., "not_for": ..., "examples": [...]}`);
    Drex and other wire-compatible services require strings. `what` first, then `not_for` as a
    `Not:` sentence, then `examples` as a `For example:` sentence. The journal keeps the
    registered (pre-flattening) questions, and the flattening is recomputable from them, so
    provenance is preserved.
    """
    flattened = {}
    for name, question in questions.items():
        if isinstance(question, Mapping) and isinstance(question.get("criteria"), dict):
            question = {**question, "criteria": {key: _criterion(value) for key, value in question["criteria"].items()}}
        flattened[name] = question
    return flattened


def _criterion(value):
    if isinstance(value, str) or not isinstance(value, Mapping):
        return value
    parts = []
    if value.get("what"):
        parts.append(value["what"])
    if value.get("not_for"):
        not_for = value["not_for"]
        parts.append("Not: " + (", ".join(not_for) if isinstance(not_for, list) else not_for))
    if value.get("examples"):
        parts.append("For example: " + "; ".join(value["examples"]))
    return " ".join(parts)


class WireCompatClient:
    """A `JevClient` over the real TypeSafe SDK that accepts every System-One wire dialect.

    The SDK client owns configuration (env resolution, auth headers, base URL, retries); its
    own request builder prepares the request and its transport sends it with exact-byte
    capture. Two leniencies sit on top, because Drex and our finetuned models are not byte-for-
    byte Jev: criteria are flattened to strings before sending, and the response is decoded by
    jev-navigator's parser from the exact bytes instead of the SDK's strict response schemas
    (whose score `legend` model rejects Drex's echo shape). Every SDK-internal access lives in
    this adapter, including decoding typed refusals after their raw bytes are journaled.
    """

    def __init__(self) -> None:
        import httpx2
        from jev_navigator.adapters.typesafe import CapturingTransport
        from typesafe_sdk import TypeSafeClient

        self._capture = CapturingTransport(httpx2.HTTPTransport())
        self._sdk = TypeSafeClient(transport=self._capture)
        self._send_failure = threading.local()
        self.model = self._sdk._config.default_model  # noqa: SLF001 - the config is the env contract

    def ask(self, state: Mapping, questions: Mapping) -> JevResponse:
        return self.parse(self.send(state, questions))

    def _send_raw(self, state: Mapping, questions: Mapping) -> None:
        """Prepare with the SDK's own endpoint builder and send through its retry/transport.

        The lenient response type (extra-allow, no required fields) passes the SDK's response
        validation for any System-One answer shape; the captured exact bytes are the truth the
        journal and `parse` read. Returns nothing: the capture and any error carry the result.
        """
        from pydantic import ConfigDict
        from typesafe_sdk._core.endpoints import prepare_system_one
        from typesafe_sdk._core.schemas.base import Response
        from typesafe_sdk._core.transport import send as sdk_send

        class LenientResponse(Response):
            model_config = ConfigDict(extra="allow")

            @classmethod
            def _decode(cls, response):
                return cls.model_validate_json(response.content)

        request = prepare_system_one(self._sdk._config, dict(state), flatten_criteria(questions),
                                     None, None, None, None, LenientResponse)  # noqa: SLF001
        sdk_send(self._sdk._http_client, self._sdk._retry, request)  # noqa: SLF001

    def send(self, state: Mapping, questions: Mapping) -> RawResponse:
        """Send and hand back the captured raw response, whatever the provider did.

        A refusal or an undecodable body comes back as captured bytes, never as a silent
        silence: the judge journals those bytes before handing them to `parse`, which turns
        them back into the typed error (a budget refusal keeps its `max_tokens_exceeded`
        marker in the raised error) and journalling keeps that error text beside the bytes.
        With no capture there is nothing to journal as bytes, so the original error raises
        untouched.
        """
        self._send_failure.error = None
        try:
            self._send_raw(state, questions)
        except Exception as error:
            captured = self._capture.take()
            if captured is None:
                raise
            # Judge records the capture before parse re-raises this same SDK failure.
            self._send_failure.error = (captured, error)
            return captured
        captured = self._capture.take()
        if captured is None:
            raise RuntimeError("the SDK transport captured no response")
        return captured

    def parse(self, raw: RawResponse) -> JevResponse:
        """Parse through jvn, or re-raise the original SDK failure after its bytes are journaled."""
        failure = getattr(self._send_failure, "error", None)
        self._send_failure.error = None
        if failure is not None and failure[0] is raw:
            error = failure[1]
            typed = input_budget_error(error)
            if typed is not None:
                raise typed from error
            raise error
        return response_from_raw(raw.json())


class ExchangeJournal:
    """jev-navigator's `Journal` protocol, writing the round-audit's line schema durably.

    One fsynced line per event. `request_id` is the request's sha256 — what result rows and
    `row_audit` cite — and `provider_request_sha256` on a response row is the hash of the
    measured SENT bytes, or null when no request bytes were captured (never the planned body:
    the wire body is flattened and compact, so it differs from the prepared body, and the
    replay slot `sent_bodies` reads stays the measured one). A call that ended in a refusal or
    a malformed reply keeps its bytes in exactly one response row, `failed`, and keeps the error
    that was actually raised in a `failure` event beside those bytes rather than dropping it.
    A call with no captured bytes keeps only that `failure` event, with the wire slots absent.
    """

    def __init__(self, path: Path, run_id: str, repositories: set[str]) -> None:
        foreign = repositories - OWN_REPOSITORIES
        if foreign:
            raise NotOwnRepositoryError(f"{sorted(foreign)} are not own repositories; their code must not be stored")
        self.path = Path(path)
        self.run_id = run_id
        self._lock = threading.Lock()
        self._touch()
        self._exchanges: dict[str, dict] = {}
        # Exchange id to the request that opened it, kept for the whole run: every later event of an
        # exchange has to name the same native request id and model, and `answered` has to keep
        # refusing to replay an answer the provider never returned.
        self._answered: set[str] = set()

    def _touch(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.flush()
            os.fsync(stream.fileno())

    def record_request(self, request: JournalRequest) -> str:
        body = request.body or request_body(request.state, request.questions)
        exchange_id = f"ex-{request.request_sha256[:16]}"
        self._exchanges[exchange_id] = {"model": request.requested_model, "request_sha256": request.request_sha256}
        self._append({
            "run_id": self.run_id, "exchange_id": exchange_id, "request_id": request.request_sha256,
            "operation": "comment_review", "provider": "system-one", "model": request.requested_model,
            "attempt": 1, "captured_at": _now(), "submitted_request_sha256": request.request_sha256,
            "kind": "request", "endpoint": None, "request_content_type": "application/json",
            "request_body_base64": base64.b64encode(body).decode(),
        })
        return exchange_id

    def record_response(self, exchange_id: str, response: RawResponse) -> None:
        """Journal the exchange's one response row: `complete` only when the bytes replay.

        `response_read_status` describes whether the body can be replayed and audited, not
        merely whether bytes arrived: a refusal or an undecodable body is journaled as
        `failed`, which the audit consumers skip without choking on it, and it still binds
        the measured request bytes.
        """
        read_error = _unreadable(response)
        row = self._response_row(exchange_id, response, "failed" if read_error else "complete", read_error)
        self._answered.add(exchange_id)
        self._append(row)

    def record_failure(self, exchange_id: str, error: str, response: RawResponse | None = None) -> None:
        """Keep the refusal that an exchange actually produced, without duplicating its bytes.

        Where `record_response` already wrote the exchange's response row, those bytes are
        already kept once, so this adds a `failure` event with the error text the client
        raised and no second copy of the bytes; silence would hide a refusal that did happen.
        Where nothing was captured, no bytes are invented: the error-only row keeps the error
        text and leaves the measured slots absent, because an uncaptured exchange has no
        measured truth.
        """
        if response is not None:
            if exchange_id in self._answered:
                self._append(self._failure_row(exchange_id, error))
                return
            row = self._response_row(exchange_id, response, "failed", error)
        else:
            row = self._failure_row(exchange_id, error)
        self._append(row)

    def _response_row(self, exchange_id: str, response: RawResponse, read_status: str,
                      read_error: str | None) -> dict:
        exchange = self._exchanges.get(exchange_id, {})
        row = {
            "run_id": self.run_id, "exchange_id": exchange_id,
            "request_id": exchange.get("request_sha256", exchange_id),
            "operation": "comment_review", "provider": "system-one", "model": exchange.get("model"),
            "attempt": 1, "captured_at": _now(),
            "submitted_request_sha256": exchange.get("request_sha256", exchange_id),
            "kind": "response",
            "provider_request_sha256": _sha256(response.sent_body) if response.sent_body is not None else None,
            "response_status": response.status, "response_content_type": response.content_type,
            "response_read_status": read_status, "response_read_error": read_error,
            "response_sha256": _sha256(response.body), "response_body_base64": base64.b64encode(response.body).decode(),
        }
        if response.sent_body is not None:
            row["sent_body_base64"] = base64.b64encode(response.sent_body).decode()
        return row

    def _failure_row(self, exchange_id: str, error: str) -> dict:
        """A refusal or timeout that produced no capturable response still keeps one row.

        The response slots stay absent: with no captured bytes there is nothing to bind and
        nothing to replay, so `sent_bodies` finds no measured wire for this exchange and the
        audit consumers have nothing to trust rather than something to mistrust.
        """
        exchange = self._exchanges.get(exchange_id, {})
        return {
            "run_id": self.run_id, "exchange_id": exchange_id,
            "request_id": exchange.get("request_sha256", exchange_id),
            "operation": "comment_review", "provider": "system-one", "model": exchange.get("model"),
            "attempt": 1, "captured_at": _now(),
            "submitted_request_sha256": exchange.get("request_sha256", exchange_id),
            "kind": "failure", "error": error, "response_read_status": "failed", "response_read_error": error,
        }

    def _append(self, row: dict) -> None:
        encoded = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        with self._lock, self.path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())


def sent_bodies(path: Path) -> dict[str, bytes]:
    """Request id (the request's hash) to the request bytes MEASURED on the wire for that exchange.

    Read from `sent_body_base64`, the captured wire body, and only where the transport captured
    one. A journal that recorded no wire for an exchange simply has no entry for it, and nothing
    here rebuilds one from the prepared body: the wire body was compact and had its criteria
    flattened, so a prepared body is never proof of what the wire carried.
    """
    return {event["request_id"]: base64.b64decode(event["sent_body_base64"])
            for event in map(json.loads, path.read_text().splitlines()) if event.get("sent_body_base64") is not None}


def submitted_bodies(path: Path) -> dict[str, bytes]:
    """Request id (the request's hash) to the native intent the judge prepared for that request.

    The prepared body holds the registered questions with their rich criteria and the state in
    its sent order, which is the only body that can prove what the judge meant to ask — so the
    round audit compares and re-hashes this one. It says nothing about what the wire carried,
    which `sent_bodies` keeps separately.
    """
    return {event["request_id"]: base64.b64decode(event["request_body_base64"])
            for event in map(json.loads, path.read_text().splitlines()) if event["kind"] == "request"}


def journaled_judge(out: Path, repositories: set[str]) -> Judge:
    """A Judge whose every exchange is journaled in `out/journal.jsonl` and whose store keeps requests.

    The client is configured entirely by the environment: with `SYSTEM_ONE_ROUTES` set,
    jev-navigator's route table answers — the first named route (Drex, Jev, a finetuned
    checkpoint) is primary and each later one is the automatic fallback. Routed responses reach Judge decoded, so
    their measured wire bytes are unavailable in this journal. Without routes, the single service named by `TYPESAFE_BASE_URL` /
    `TYPESAFE_DEFAULT_MODEL` answers under `WireCompatClient`'s wire dialect handling.
    """

    load_env()
    from jev_navigator.adapters.routes import RoutedJevClient, routes_from_env

    routes = routes_from_env()
    client: WireCompatClient | _RouteDialect = WireCompatClient()
    if routes:
        client = _RouteDialect(RoutedJevClient(routes))
    return Judge(client,
                 journal=ExchangeJournal(out / "journal.jsonl", out.name, repositories),
                 store=JsonlAnswerStore(out / "answers.jsonl", keep_requests=True))


class _RouteDialect:
    """The route table's failover under `WireCompatClient`'s dialect: criteria flattened to
    strings before every route sees them (Drex requires it). The routed client returns decoded
    responses; its adapter exposes no measured wire bytes to this journal."""

    def __init__(self, routed) -> None:
        self._routed = routed
        self.model = routed.model

    def ask(self, state, questions):
        return self._routed.ask(state, flatten_criteria(questions))


def _unreadable(response: RawResponse) -> str | None:
    """Why the captured body replays no answer set, or None when it replays one.

    Decoded through jev-navigator's parser, which is the read a replay makes: no bytes, a
    refused status and a body the parser rejects are all unreadable, so `complete` never comes
    to mean merely that bytes arrived.
    """
    if not response.body:
        return "no response bytes were captured"
    if response.status not in (None, 200):
        return f"the provider refused the request with {response.status}"
    try:
        response_from_raw(response.json())
    except (ValueError, TypeError, AttributeError, KeyError) as error:
        return f"the captured response replays no answer: {error}"
    return None


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
