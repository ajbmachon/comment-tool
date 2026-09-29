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
still leaves every completed exchange readable. The answer store keeps the exact request bytes
(`keep_requests=True`). A request carries the classified repository's code, so only our own
repositories may be journaled.

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
    `_send_raw`, so an SDK version bump is a one-function fix.
    """

    def __init__(self) -> None:
        import httpx2
        from jev_navigator.adapters.typesafe import CapturingTransport
        from typesafe_sdk import TypeSafeClient

        self._capture = CapturingTransport(httpx2.HTTPTransport())
        self._sdk = TypeSafeClient(transport=self._capture)
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
        self._send_raw(state, questions)
        captured = self._capture.take()
        if captured is None:
            raise RuntimeError("the SDK transport captured no response")
        return captured

    def parse(self, raw: RawResponse) -> JevResponse:
        # jev-navigator's parser, not the SDK's strict response schemas: the SDK builds and
        # sends the request, but Drex and the finetuned models echo score legends in shapes
        # the SDK's models reject and the library accepts.
        return response_from_raw(raw.json())


class ExchangeJournal:
    """jev-navigator's `Journal` protocol, writing the round-audit's line schema durably.

    One fsynced line per event. `request_id` is the request's sha256 — what result rows and
    `row_audit` cite — and `provider_request_sha256` binds each response to the exact request
    bytes that produced it. A failure keeps the response bytes when one arrived but did not
    parse.
    """

    def __init__(self, path: Path, run_id: str, repositories: set[str]) -> None:
        foreign = repositories - OWN_REPOSITORIES
        if foreign:
            raise NotOwnRepositoryError(f"{sorted(foreign)} are not own repositories; their code must not be stored")
        self.path = Path(path)
        self.run_id = run_id
        self._lock = threading.Lock()
        self._touch()
        self._open: dict[str, dict] = {}

    def _touch(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("ab") as stream:
            stream.flush()
            os.fsync(stream.fileno())

    def record_request(self, request: JournalRequest) -> str:
        body = request.body or request_body(request.state, request.questions)
        exchange_id = f"ex-{request.request_sha256[:16]}"
        self._open[exchange_id] = {"model": request.requested_model, "request_sha256": request.request_sha256,
                                   "body_sha256": _sha256(body)}
        self._append({
            "run_id": self.run_id, "exchange_id": exchange_id, "request_id": request.request_sha256,
            "operation": "comment_review", "provider": "system-one", "model": request.requested_model,
            "attempt": 1, "captured_at": _now(), "submitted_request_sha256": request.request_sha256,
            "kind": "request", "endpoint": None, "request_content_type": "application/json",
            "provider_request_sha256": _sha256(body), "request_body_base64": base64.b64encode(body).decode(),
        })
        return exchange_id

    def record_response(self, request_id: str, response: RawResponse) -> None:
        row = self._response_row(request_id, response, "complete", None)
        self._open.pop(request_id, None)
        self._append(row)

    def record_failure(self, request_id: str, error: str, response: RawResponse | None = None) -> None:
        if response is None:
            self._open.pop(request_id, None)
            return
        row = self._response_row(request_id, response, "failed", error)
        self._open.pop(request_id, None)
        self._append(row)

    def _response_row(self, request_id: str, response: RawResponse, read_status: str, read_error: str | None) -> dict:
        exchange = self._open.get(request_id, {})
        return {
            "run_id": self.run_id, "exchange_id": request_id,
            "request_id": exchange.get("request_sha256", request_id),
            "operation": "comment_review", "provider": "system-one", "model": exchange.get("model"),
            "attempt": 1, "captured_at": _now(),
            "submitted_request_sha256": exchange.get("request_sha256", request_id),
            "kind": "response", "provider_request_sha256": exchange.get("body_sha256"),
            "response_status": response.status, "response_content_type": response.content_type,
            "response_read_status": read_status, "response_read_error": read_error,
            "response_sha256": _sha256(response.body), "response_body_base64": base64.b64encode(response.body).decode(),
        }

    def _append(self, row: dict) -> None:
        encoded = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        with self._lock, self.path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())


def sent_bodies(path: Path) -> dict[str, bytes]:
    """Request id (the request's hash) to the exact body bytes sent, for every request in a journal."""
    return {event["request_id"]: base64.b64decode(event["request_body_base64"])
            for event in map(json.loads, path.read_text().splitlines()) if event["kind"] == "request"}


def journaled_judge(out: Path, repositories: set[str]) -> Judge:
    """A Judge whose every exchange is journaled in `out/journal.jsonl` and whose store keeps requests.

    The client is jev-navigator's `TypeSafeJevClient` under `WireCompatClient`, configured
    entirely by the environment: `TYPESAFE_DEFAULT_MODEL` names the decision model
    (`jev-latest`, `drex-latest`, or one of our finetuned checkpoints) and `TYPESAFE_BASE_URL`
    the service that answers.
    """

    load_env()
    return Judge(WireCompatClient(),
                 journal=ExchangeJournal(out / "journal.jsonl", out.name, repositories),
                 store=JsonlAnswerStore(out / "answers.jsonl", keep_requests=True))


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
