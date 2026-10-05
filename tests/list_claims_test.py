"""A comment's claim about every entry of a list: the trigger, the entries, the combination and the wiring."""

import json
import subprocess
from pathlib import Path

import pytest
from jev_navigator.index.code_index import CodeIndex
from jev_navigator.judgments.judge import Judge
from jev_navigator.testing import ScriptedJevClient

import comment_tool.core.compose as compose
from comment_tool.claims.list_claims import (
    CALLER_DECIDES,
    ENTRY_CHECK,
    LIST_CLAIM,
    claims_every_entry,
    entry_items,
    list_literal,
)
from comment_tool.claims.rewrite_packet import git_source
from comment_tool.claims.ts_parse import typescript_of
from comment_tool.cli.sweep import QUESTIONS, judged
from comment_tool.config import DATA
from comment_tool.core.comment_review import question_set
from research.rounds.run_round4 import case_of

ENGINE = Path.home() / "Projects/analysis-engine"
TYPESCRIPT_COMPILER = typescript_of(Path.home() / "Projects/heedvane")
TYPESCRIPT = """export const SAFE_METHODS = ["GET", "HEAD"] as const;
export enum Tier { Free = "free", Pro = "pro" }
export type Level = "low" | "high";
export const LIMIT = 3;
"""


def en_h11() -> dict:
    return next(case for case in map(json.loads, (DATA / "round4/cases.jsonl").read_text().splitlines())
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


@pytest.mark.local
def test_python_list_entries_come_from_the_parser():
    case = en_h11()["provenance"]
    source = git_source(ENGINE, case["commit"], case["path"])

    literal = list_literal(source, case["path"], case["code_after_lines"][0], TYPESCRIPT_COMPILER)

    assert literal.name == "_ENFORCEMENT_FILENAME_PATTERNS"
    assert len(literal.entries) == 11
    assert literal.entries[-1] == 're.compile(r"(^|/)\\.github/workflows/[^/]+\\.ya?ml$")'


@pytest.mark.local
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


@pytest.mark.local
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
    (repository / name).parent.mkdir(parents=True, exist_ok=True)
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


VIEWS_COMMIT = "f0b4171f8dfcd6683d669e0fcff723ba2206647b"
VIEWS_FILE = "runtime/agent-runtimes/pi/secret-mask.mjs"


@pytest.mark.local
@pytest.mark.parametrize("missing_helper", [False, True])
def test_real_views_packet_fetches_helpers_without_arrow_bindings_or_regex_tokens(script_repository, missing_helper):
    source = git_source(ENGINE, VIEWS_COMMIT, VIEWS_FILE)
    repository, commit = ENGINE, VIEWS_COMMIT
    if missing_helper:
        source = source.replace("function hexForms(bytes)", "function renamedHexForms(bytes)", 1)
        repository, commit = script_repository, committed(script_repository, VIEWS_FILE, source)
    literal = list_literal(source, VIEWS_FILE, 412, TYPESCRIPT_COMPILER)

    prepared = entry_items(CodeIndex.at_commit(repository, commit, [VIEWS_FILE]), VIEWS_FILE, literal)

    assert prepared.unresolved == (("hexForms",) if missing_helper else ())
    assert prepared.unknown == ()
    assert bool(prepared.escalation_reasons()) == missing_helper
    assert [[definition["lines"] for definition in item["definitions"]] for item in prepared.items] == [
        [[380, 382]], [[380, 382]], [] if missing_helper else [[399, 402]],
        [[404, 407]], [[385, 387]], [[394, 397]],
    ]
    assert all(definition["commit"] == commit and definition["file"] == VIEWS_FILE
               for item in prepared.items for definition in item["definitions"])
    assert tuple(item["code"] for item in prepared.items) == literal.entries


SCRIPT_ENTRIES = """import { EXTERNAL } from "outside";
const outer = 3;
const key = 4;
function helper(value) { return value; }
const ENTRIES = [
  ({outer}) => outer,
  {outer},
  { [key]: helper(EXTERNAL) },
  () => { const outer = 1; return outer + MISSING; },
];
"""


@pytest.mark.local
def test_script_entry_packets_preserve_shorthand_and_computed_references_but_exclude_shadowed_bindings(script_repository):
    commit = committed(script_repository, "entries.ts", SCRIPT_ENTRIES)
    literal = list_literal(SCRIPT_ENTRIES, "entries.ts", 5, TYPESCRIPT_COMPILER)

    prepared = entry_items(CodeIndex.at_commit(script_repository, commit, ["entries.ts"]), "entries.ts", literal)

    assert [[definition["lines"] for definition in item["definitions"]] for item in prepared.items] == [
        [], [[2, 2]], [[3, 3], [4, 4]], [],
    ]
    assert prepared.unresolved == ("MISSING",)
    assert prepared.unknown == ()

    changed_source = SCRIPT_ENTRIES.replace("() => { const outer", "(MISSING) => { const outer")
    changed_commit = committed(script_repository, "entries.ts", changed_source)
    changed_literal = list_literal(changed_source, "entries.ts", 5, TYPESCRIPT_COMPILER)

    changed = entry_items(CodeIndex.at_commit(script_repository, changed_commit, ["entries.ts"]), "entries.ts", changed_literal)

    assert changed.unresolved == ()
    assert changed.unknown == ()
    assert all(definition["commit"] == changed_commit for item in changed.items for definition in item["definitions"])
