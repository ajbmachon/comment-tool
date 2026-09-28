"""A comment's claim about every entry of a list: the trigger, the entries, the combination and the wiring."""

import json
import subprocess
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge
from jev_navigator.testing import ScriptedJevClient

import compose
from comment_review import question_set
from list_claims import (
    CALLER_DECIDES,
    ENTRY_CHECK,
    LIST_CLAIM,
    claims_every_entry,
    entry_items,
    list_literal,
)
from rewrite_packet import git_source
from run_round4 import case_of
from sweep import QUESTIONS, judged
from ts_parse import typescript_of

HERE = Path(__file__).resolve().parent
ENGINE = Path.home() / "Projects/analysis-engine"
TYPESCRIPT_COMPILER = typescript_of(Path.home() / "Projects/heedvane")
TYPESCRIPT = """export const SAFE_METHODS = ["GET", "HEAD"] as const;
export enum Tier { Free = "free", Pro = "pro" }
export type Level = "low" | "high";
export const LIMIT = 3;
"""


def en_h11() -> dict:
    return next(case for case in map(json.loads, (HERE / "round4/cases.jsonl").read_text().splitlines())
                if case["case_id"] == "en-h11")


def scripted_list_answers(question_id: str, _question: dict, state: dict) -> float:
    """The list claim holds a condition, only the workflow entry fails it, and every other answer is no."""
    if question_id.startswith(LIST_CLAIM):
        return 0.95
    if question_id.startswith(ENTRY_CHECK.name):
        entry = state["items"][int(question_id.rsplit("#", 1)[1])]["code"]
        return 0.1 if "workflows" in entry else 0.9
    return 0.05


def test_only_every_all_each_always_never_and_none_trigger_a_list_claim():
    assert claims_every_entry("# This list only holds files whose purpose is clear.")
    assert claims_every_entry("// Every entry is lower case.")
    assert not claims_every_entry("# Checked in this order; the first match wins.")


def test_python_list_entries_come_from_the_parser():
    case = en_h11()["provenance"]
    source = git_source(ENGINE, case["commit"], case["path"])

    literal = list_literal(source, case["path"], case["code_after_lines"][0], TYPESCRIPT_COMPILER)

    assert literal.name == "_ENFORCEMENT_FILENAME_PATTERNS"
    assert len(literal.entries) == 11
    assert literal.entries[-1] == 're.compile(r"(^|/)\\.github/workflows/[^/]+\\.ya?ml$")'


def test_typescript_arrays_enums_and_unions_are_lists_and_a_constant_is_not():
    entries = [list_literal(TYPESCRIPT, "lists.ts", line, TYPESCRIPT_COMPILER) for line in (1, 2, 3, 4)]

    assert [(e.name, e.entries) if e else None for e in entries] == [
        ("SAFE_METHODS", ('"GET"', '"HEAD"')), ("Tier", ('Free = "free"', 'Pro = "pro"')),
        ("Level", ('"low"', '"high"')), None]


def test_only_an_entry_at_the_no_bar_or_lower_makes_the_comment_stale():
    claim = compose.list_claim(0.9, {"a": 0.9, "b": 0.2, "c": 0.35})

    assert (claim.fails, claim.failing, claim.reasons) == (True, ("b",), ())
    assert compose.list_claim(0.9, {"a": 0.9, "b": 0.3}) == compose.ListClaim(reasons=("entry b 0.30",))


def test_a_doubtful_claim_or_entry_escalates_and_a_held_claim_changes_nothing():
    assert compose.list_claim(0.5, {"a": 0.1}).reasons == ("list claim 0.50",)
    assert compose.list_claim(0.9, {"a": 0.9, "b": 0.45}).reasons == ("entry b 0.45",)
    assert compose.list_claim(0.9, {"a": 0.9, "b": 0.7}) == compose.list_claim(0.1, {"a": 0.1})


def test_en_h11_asks_the_list_claim_in_its_first_request_and_one_question_per_entry():
    raw = en_h11()
    case = case_of(raw)
    index = CodeIndex.at_commit(ENGINE, raw["provenance"]["commit"], [case.file])
    client = ScriptedJevClient(nouls=scripted_list_answers)

    row = judged(index, Judge(client), case, question_set(json.loads(QUESTIONS.read_text())))

    first_request_questions, entry_state = client.requests[0][1], client.requests[-1][0]
    assert any(LIST_CLAIM in question_id for question_id in first_request_questions)
    assert set(entry_state) == {"comment", "items"}
    assert row["action"] == "fix_stale"
    assert row["list_claim"]["failing"] == ['re.compile(r"(^|/)\\.github/workflows/[^/]+\\.ya?ml$")']
    assert row["list_claim"]["caller_decides"] == CALLER_DECIDES


NAMED_ENTRIES = """import re
from pkg_outside import EXTERNAL
READ_ONLY = ("GET", "HEAD")


def make(x):
    return x


ROUTES = (READ_ONLY, re.compile(r"x"), make("y"), UNKNOWN, *EXTERNAL)
"""


def committed(repository: Path, name: str, text: str) -> str:
    (repository / name).write_text(text)
    for command in (["init", "-q"], ["add", name], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t"]):
        subprocess.run(["git", *command], cwd=repository, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True, text=True, check=True).stdout.strip()


def test_named_entries_carry_their_definitions_and_only_repository_names_without_one_are_unresolved(tmp_path):
    commit = committed(tmp_path, "routes.py", NAMED_ENTRIES)
    literal = list_literal(NAMED_ENTRIES, "routes.py", 10, TYPESCRIPT_COMPILER)

    prepared = entry_items(CodeIndex.at_commit(tmp_path, commit, ["routes.py"]), "routes.py", literal)

    assert [[d["lines"] for d in item["definitions"]] for item in prepared.items] == [[[3, 3]], [], [[6, 7]], [], []]
    assert prepared.unresolved == ("UNKNOWN",)
