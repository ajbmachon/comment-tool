"""After a definition fetch, only the stale questions are asked again, on the extra code in its own field."""

import json
from pathlib import Path

import pytest
from jev_navigator.directives.find_code import Outcome
from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge
from jev_navigator.testing import ScriptedJevClient

import comment_tool.core.compose as compose
from comment_tool.cli.sweep import QUESTIONS, THREE_OUTCOMES, judged, review_found
from comment_tool.config import DATA
from comment_tool.core.comment_discovery import FoundComment
from comment_tool.core.comment_review import question_set
from research.rounds.run_round4 import case_of

pytestmark = pytest.mark.local

HEEDVANE = Path.home() / "Projects/heedvane"
FIRST_ANSWERS = {"states_hidden_rule": 0.9, "code_is_hard_to_follow": 0.38, **dict.fromkeys(compose.STALE_PARTS, 0.9)}


def hv_h12() -> dict:
    return next(case for case in map(json.loads, (DATA / "round4/cases.jsonl").read_text().splitlines())
                if case["case_id"] == "hv-h12")


def stale_after_the_definition(question_id: str, _question: dict, state: dict) -> float:
    """The stale parts hold on the first packet; with the definition in view the code no longer differs."""
    name = question_id.split("@")[0]
    if "elsewhere" in state["code"]:
        return 0.1 if name == "code_differs_from_comment" else 0.9
    return FIRST_ANSWERS.get(name, 0.05)


def test_the_definition_fetch_reasks_only_the_stale_questions_on_code_elsewhere():
    raw = hv_h12()
    index = CodeIndex.at_commit(HEEDVANE, raw["provenance"]["commit"], [raw["provenance"]["path"]])
    client = ScriptedJevClient(nouls=stale_after_the_definition)

    row = judged(index, Judge(client), case_of(raw), question_set(json.loads(QUESTIONS.read_text())))

    (first_state, _), (reask_state, reask_questions) = client.requests
    assert {question_id.split("@")[0] for question_id in reask_questions} == set(compose.STALE_PARTS)
    assert reask_state["code"]["after_comment"] == first_state["code"]["after_comment"]
    assert [piece["file"] for piece in reask_state["code"]["elsewhere"]] == [
        raw["provenance"]["path"], "apps/web/src/lib/billing/referral-cookie.ts"]
    assert "code.elsewhere" in next(iter(q for qid, q in reask_questions.items() if qid.startswith("code_differs")))["instructions"]
    assert (row["action"], row["probabilities"]["code_is_hard_to_follow"]) == ("keep", 0.38)
    assert row["decided_by"] == "jev+rule after definition_fetch"


def test_a_kept_comment_whose_detail_is_not_shown_says_its_staleness_was_not_checked():
    raw = hv_h12()
    index = CodeIndex.at_commit(HEEDVANE, raw["provenance"]["commit"], [raw["provenance"]["path"]])
    not_shown = {"states_hidden_rule": 0.9, "names_specific_detail": 0.8, "code_shows_same_detail": 0.11}
    client = ScriptedJevClient(nouls=lambda question_id, _q, _s: not_shown.get(question_id.split("@")[0], 0.05))

    row = judged(index, Judge(client), case_of(raw), question_set(json.loads(QUESTIONS.read_text())))

    assert (row["action"], row["stale_check"]) == ("keep", compose.NOT_CHECKABLE)


def stored(folder: str, name: str, case_id: str) -> dict:
    return next(row for row in map(json.loads, (DATA / folder / name).read_text().splitlines()) if row["case_id"] == case_id)


def test_a_decided_rewrite_carries_its_rewrite_job_for_the_caller():
    raw = stored("docs-rewrite", "cases.jsonl", "hv-r015")
    index = CodeIndex.at_commit(HEEDVANE, raw["provenance"]["commit"], [raw["provenance"]["path"]])
    client = ScriptedJevClient(nouls=lambda question_id, _q, _s: 0.9 if question_id.startswith("states_hidden_rule") else 0.05)

    row = review_found(index, Judge(client), FoundComment(case_of(raw), raw["kind"]), question_set(json.loads(QUESTIONS.read_text())))

    packet = stored("docs-rewrite", "rewrite-packets.jsonl", "hv-r015")
    assert row["action"] == "rewrite"
    assert row["rewrite_job"] == {key: packet[key] for key in packet if key not in ("case_id", "location", "commit")}


def test_every_search_outcome_has_a_label_and_an_incomplete_scope_is_not_absence():
    assert set(THREE_OUTCOMES) == set(Outcome)
    assert THREE_OUTCOMES[Outcome.SCOPE_INCOMPLETE] == "not_yet_inspected"
