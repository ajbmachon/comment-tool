"""Replay one frozen Jev request live, once, journaled: the Discern Rule A pilot's Python side.

The adapter loads the original provider request by its request id from the frozen docs-round
journal, verifies both identities before any dispatch - the canonical request hash (the library's
``request_sha256`` over state and questions) and the exact wire bytes the original run sent - and
only then asks the unchanged questions through the existing Judge: its masking, final secret
refusal, the Evals journal and the answer store with ``keep_requests=True``. The observation JSON
it prints feeds the TypeScript reducer in ``ts/src/live-pilot.ts``; nothing here duplicates Rule A.

prepare mode is free: it prints the request identity without initializing credentials or touching
any provider. live mode is explicit and asks the provider exactly once into a fresh output
directory; it refuses a response that fails to parse or that leaves a probability unanswered, and
the journal keeps the exact bytes of any such response.

usage:
    uv run python discern_live_pilot.py prepare --journal <original journal> --request-id <sha256>
    uv run python discern_live_pilot.py live --journal <original journal> --request-id <sha256> \
        --out <fresh dir> [--endpoint <url>]
"""

import argparse
import base64
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from jev_navigator.judgments.answers import JevResponse
from jev_navigator.judgments.questions import request_sha256
from jev_navigator.judgments.thresholds import Thresholds

from journaled_client import journaled_judge, request_body

REPOSITORIES = frozenset({"heedvane"})


def load_request_row(journal: Path, request_id: str) -> dict:
    """The single frozen request row for this request id; absent or ambiguous means stop."""
    rows = [json.loads(line) for line in journal.read_text().splitlines() if line.strip()]
    found = [row for row in rows if row.get("kind") == "request" and row.get("request_id") == request_id]
    if len(found) != 1:
        raise ValueError(f"{journal}: expected exactly one request row for {request_id}, found {len(found)}")
    return found[0]


def verified_request(row: dict) -> tuple[Mapping, str]:
    """The parsed request and the wire hash, with every identity checked before dispatch.

    The wire hash is sha256 over the exact recorded bytes; byte identity rebuilds the body the way
    the client builds it; the canonical hash is the library's request_sha256 over state+questions.
    """
    body = base64.b64decode(row["request_body_base64"])
    wire = hashlib.sha256(body).hexdigest()
    if wire != row["provider_request_sha256"]:
        raise ValueError(f"wire hash mismatch: journal says {row['provider_request_sha256']}, bytes hash to {wire}")
    parsed = json.loads(body)
    rebuilt = request_body(parsed["model"], parsed["state"], parsed["questions"])
    if rebuilt != body:
        raise ValueError("the recorded body is not byte-identical to the request the client would build")
    canonical = request_sha256(parsed["state"], parsed["questions"])
    if canonical != row["request_id"] or canonical != row.get("submitted_request_sha256"):
        raise ValueError(f"canonical hash mismatch: request_id {row['request_id']}, computed {canonical}")
    return parsed, wire


def identity(row: dict, parsed: Mapping, wire: str) -> dict:
    """The request identity as the pilot receipt binds it."""
    questions = parsed["questions"]
    return {
        "request_sha256": row["request_id"],
        "provider_request_sha256": wire,
        "exchange_id": row.get("exchange_id"),
        "requested_model": parsed["model"],
        "question_ids": sorted(questions),
        "noul_question_ids": sorted(q for q, question in questions.items() if question.get("type") == "noul"),
        "captured_at": row.get("captured_at"),
    }


def prepare(journal: Path, request_id: str) -> dict:
    """Free: the request identity. No credential is read and no provider is contacted."""
    row = load_request_row(journal, request_id)
    parsed, wire = verified_request(row)
    return {"mode": "prepare", "journal": str(journal), "request": identity(row, parsed, wire)}


def live(journal: Path, request_id: str, out: Path, endpoint: str | None = None) -> dict:
    """Explicit: one live ask through the journaled Judge, into a fresh output directory.

    ``endpoint`` points the client at a substitute provider (the pilot's boundary proof); without
    it the client uses the evals helpers' own Jev URL.
    """
    row = load_request_row(journal, request_id)
    parsed, wire = verified_request(row)
    _refuse_existing(out)
    judge = journaled_judge(out, set(REPOSITORIES), model=parsed["model"], endpoint=endpoint)
    response = judge.ask(parsed["state"], parsed["questions"], thresholds=Thresholds())
    if judge.calls != 1:
        raise RuntimeError(f"expected exactly one live call, the judge made {judge.calls}")
    _verify_resent_body(out, wire)
    probabilities = _noul_probabilities(parsed["questions"], response)
    missing = sorted(parsed["questions"].keys() - response.answers.keys())
    if missing:
        raise ValueError(f"the served response leaves requested answers missing: {', '.join(missing)}")
    return {
        "mode": "live",
        "journal": str(journal),
        "request": identity(row, parsed, wire),
        "artifacts": {"journal": str(out / "journal.jsonl"), "answers": str(out / "answers.jsonl")},
        "response": {
            "served_model": response.model,
            "input_tokens": response.input_tokens,
            "request_sha256": response.request_sha256,
        },
        "probabilities": probabilities,
    }


def _refuse_existing(out: Path) -> None:
    for name in ("journal.jsonl", "answers.jsonl"):
        if (out / name).exists():
            raise FileExistsError(f"{out / name} already exists; the pilot writes a fresh output directory only")


def _verify_resent_body(out: Path, wire_sha256: str) -> None:
    """The journal's recorded request bytes must be the frozen wire bytes, byte for byte."""
    rows = [json.loads(line) for line in (out / "journal.jsonl").read_text().splitlines() if line.strip()]
    requests = [row for row in rows if row.get("kind") == "request"]
    if len(requests) != 1:
        raise RuntimeError(f"expected exactly one journaled request, found {len(requests)}")
    resent = hashlib.sha256(base64.b64decode(requests[0]["request_body_base64"])).hexdigest()
    if resent != wire_sha256:
        raise RuntimeError(f"the resent request bytes differ from the frozen wire bytes ({resent} != {wire_sha256})")


def _noul_probabilities(questions: Mapping, response: JevResponse) -> dict[str, float]:
    """The served P(yes) per question, keyed by question id without its wording hash.

    A probability the response fails to answer is a failure, never a fallback.
    """
    probabilities: dict[str, float] = {}
    for question_id, question in questions.items():
        if question.get("type") != "noul":
            continue
        base = question_id.split("@", 1)[0]
        if base in probabilities:
            raise ValueError(f"two questions share the id {base}; refusing to pick one")
        try:
            answer = response.noul(question_id)
        except KeyError:
            raise ValueError(f"the served response answers no probability for {question_id}") from None
        probabilities[base] = answer.probability
    return probabilities


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="replay one frozen Jev request live, once, journaled")
    commands = parser.add_subparsers(dest="mode", required=True)
    prepare_command = commands.add_parser("prepare", help="free: the request identity, no credentials, no provider")
    prepare_command.add_argument("--journal", type=Path, required=True)
    prepare_command.add_argument("--request-id", required=True)
    live_command = commands.add_parser("live", help="explicit: one live ask through the journaled Judge")
    live_command.add_argument("--journal", type=Path, required=True)
    live_command.add_argument("--request-id", required=True)
    live_command.add_argument("--out", type=Path, required=True)
    live_command.add_argument("--endpoint", default=None, help="substitute provider URL; default is the real one")
    args = parser.parse_args(argv)
    if args.mode == "prepare":
        result = prepare(args.journal, args.request_id)
    else:
        result = live(args.journal, args.request_id, args.out, args.endpoint)
    json.dump(result, sys.stdout, sort_keys=True)
    print()


if __name__ == "__main__":
    main()
