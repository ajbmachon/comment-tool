"""Prove a round's result rows from the journal instead of trusting them.

A row in `pass.jsonl` is only a record. Before it is scored, `audit_row` checks it against the journal the
run wrote: its first request holds exactly the case's registered state and the registered first question
set, a re-ask holds exactly the registered stale-only question set, every request hash matches its
journaled body, the row's answers are the journaled answers (a re-ask overrides only its own questions),
and the row's action, decision path, escalation reasons and `decided_by` are exactly what the frozen rule
gives for those answers. `audit_journal` checks that every journaled request asked a registered question
set, or only the code search's own questions. Any difference raises; nothing is repaired.
"""

import base64
import json
from dataclasses import dataclass
from pathlib import Path

from jev_navigator.judgments.judge import Judge
from jev_navigator.judgments.questions import request_sha256
from jev_navigator.testing import ScriptedJevClient

from comment_review import QuestionSet, stale_reask_checks
from definition_fetch import Definitions
from journaled_client import sent_bodies
from sweep import HOLDS_WHAT_COMMENT_IS_ABOUT

SEARCH_QUESTIONS = frozenset({"contains_target", "could_contain_target", "open_first", HOLDS_WHAT_COMMENT_IS_ABOUT.name})
"""The questions a gated code search asks; a journaled request may ask only these instead of a registered set."""


class RowAuditError(RuntimeError):
    """A result row differs from the journaled exchange or from the frozen rule."""


@dataclass(frozen=True)
class QuestionSets:
    """The exact `questions` payloads a round may send: the first request's and the stale-only re-ask's."""

    first: dict
    reask: dict


def registered_question_sets(questions: QuestionSet) -> QuestionSets:
    """The payloads the library builds for the registered questions, captured with no model call."""
    client = ScriptedJevClient(default_noul=0.5)
    judge = Judge(client)
    judge.ask_all({}, checks=questions.checks, picks=questions.picks, scores=questions.scores)
    judge.ask_all({}, checks=stale_reask_checks(questions))
    (_, first), (_, reask) = client.requests
    return QuestionSets(dict(first), dict(reask))


def audit_journal(path: Path, sets: QuestionSets) -> None:
    """Raises unless every journaled request asked a registered question set or only search questions."""
    for request_id, body in sent_bodies(path).items():
        questions = json.loads(body)["questions"]
        names = {qid.split("@")[0].split("#")[0] for qid in questions}
        if questions not in (sets.first, sets.reask) and not names <= SEARCH_QUESTIONS:
            raise RowAuditError(f"journaled request {request_id[:12]} asked an unregistered question set")


def journal_exchanges(path: Path) -> dict[str, dict]:
    """Request hash to its journaled state, questions and noul answers, for every complete 200 response."""
    requests, exchanges = sent_bodies(path), {}
    for event in map(json.loads, path.read_text().splitlines()):
        if event.get("response_status") == 200 and event.get("response_read_status") == "complete":
            body = json.loads(requests[event["request_id"]])
            answers = json.loads(base64.b64decode(event["response_body_base64"]))["answers"]
            exchanges[event["request_id"]] = {"state": body["state"], "questions": body["questions"], "nouls": _nouls(answers)}
    return exchanges


def _nouls(answers: dict) -> dict[str, float]:
    return {qid.split("@")[0]: answer["noul"] for qid, answer in answers.items() if answer.get("type") == "noul"}


def audit_row(row: dict, case: dict, exchanges: dict[str, dict], rule, sets: QuestionSets) -> None:
    """Raises `RowAuditError` unless `row` is exactly what the journal and the frozen rule give for `case`."""
    _same(row, "identity", _identity(row), _case_identity(case))
    first = row.get("first_answer", row)
    first_exchange = _exchange(row, exchanges, first["request_sha256"])
    _same(row, "first request state", first_exchange["state"], case["state"])
    _same(row, "first question set", first_exchange["questions"], sets.first)
    _same(row, "first answers", first["probabilities"], first_exchange["nouls"])
    expected = dict(first_exchange["nouls"])
    if row["request_sha256"] != first["request_sha256"]:
        reask = _exchange(row, exchanges, row["request_sha256"])
        _same(row, "re-ask question set", reask["questions"], sets.reask)
        _same(row, "re-asked state", _without_elsewhere(reask["state"]), case["state"])
        expected |= reask["nouls"]
    _same(row, "final answers", row["probabilities"], expected)
    _same_composition(row, case["code_facts"], rule)


def _same_composition(row: dict, facts: dict, rule) -> None:
    probabilities = row["probabilities"]
    _same(row, "action", row["action"], rule.readout_a(probabilities, facts))
    _same(row, "decision path", row["decision_path"], rule.decision_path(probabilities, facts))
    fetched = row.get("definitions", {})
    missing = Definitions((), tuple(fetched.get("unresolved", ())), tuple(fetched.get("unknown", ()))).escalation_reasons()
    expected = set(rule.escalation_reasons(probabilities, facts)) | set(missing)
    _same(row, "escalation reasons", set(row.get("escalate", {}).get("reasons", [])), expected)
    _same(row, "decided_by", row["decided_by"] == "escalated", bool(expected))


def _exchange(row: dict, exchanges: dict[str, dict], request_hash: str) -> dict:
    exchange = exchanges.get(request_hash)
    if exchange is None:
        raise RowAuditError(f"{row['case_id']}: request {request_hash[:12]} has no complete journaled response")
    _same(row, "request hash", request_sha256(exchange["state"], exchange["questions"]), request_hash)
    return exchange


def _identity(row: dict) -> tuple:
    return row["location"], row["commit"], row["kind"], row["comment"]


def _case_identity(case: dict) -> tuple:
    provenance = case["provenance"]
    return (f"{provenance['path']}:{provenance['comment_lines'][0]}", provenance["commit"], case["kind"],
            case["state"]["comment"]["text"])


def _without_elsewhere(state: dict) -> dict:
    return {**state, "code": {key: value for key, value in state["code"].items() if key != "elsewhere"}}


def _same(row: dict, what: str, found, expected) -> None:
    if found != expected:
        raise RowAuditError(f"{row['case_id']}: {what} differs from the journal or the frozen rule")
