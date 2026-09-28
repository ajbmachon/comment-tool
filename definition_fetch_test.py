"""Definitions behind the conditions a stale verdict reads, fetched by code before "fix stale comment" fires."""

import subprocess
from pathlib import Path

import pytest
from jev_navigator.index.spans import Span

from definition_fetch import (
    Definitions,
    condition_names,
    definitions_of,
    fetch_definitions,
    local_binding,
    root_names,
)

HEEDVANE = Path.home() / "Projects/heedvane"
HV_H12_COMMIT = "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590"
HV_H12_FILE = "apps/web/src/app/api/github/attach/route.ts"


def test_a_typescript_condition_is_read_from_its_root_names():
    line = "    if (pendingReferral.shouldClear && !isExpired(at)) response.cookies.delete(REFERRAL_COOKIE_NAME);"

    assert condition_names(line, "typescript") == ("pendingReferral", "isExpired", "at")


def test_a_python_condition_leaves_out_keywords_self_and_strings():
    line = '    elif not self.cache and limit > MAX_ITEMS or kind == "full":'

    assert condition_names(line, "python") == ("limit", "MAX_ITEMS", "kind")


def test_a_line_without_a_condition_has_no_names():
    assert condition_names("    return response;", "typescript") == ()


def test_a_local_binding_is_found_with_its_whole_statement():
    lines = ("function f(items) {", "  const limit = items", "    .length;", "  if (limit > 3) return;", "}")

    assert local_binding(lines, "limit", before_line=4, language="typescript") == (2, 3)


def test_a_parameter_has_no_local_binding():
    lines = ("function f(items) {", "  if (items.length > 3) return;", "}")

    assert local_binding(lines, "items", before_line=2, language="typescript") is None


@pytest.mark.local
def test_hv_h12_fetches_the_function_that_sets_should_clear():
    shown = Span(HV_H12_FILE, 85, 86)

    found = fetch_definitions(HEEDVANE, HV_H12_COMMIT, shown)

    assert found.unresolved == ()
    assert any("shouldClear: raw !== undefined" in piece.text for piece in found.fetched)
    assert [piece.span.file for piece in found.fetched] == [HV_H12_FILE, "apps/web/src/lib/billing/referral-cookie.ts"]


ENGINE = Path.home() / "Projects/analysis-engine"
EN_D09_COMMIT = "65ce1972665975d20bb09f3638a6155f6fb3f9b9"
EN_D09_FILE = "enginepy/hub/event_counts.py"


def test_builtins_and_language_globals_need_no_definition():
    assert condition_names("    if not isinstance(ret, dict) or len(ret) > MAX:", "python") == ("ret", "MAX")
    assert condition_names("  if (Array.isArray(rows) && Number.isFinite(limit)) {", "typescript") == ("rows", "limit")


@pytest.mark.local
def test_a_parameter_resolves_to_its_function_signature():
    shown = Span(EN_D09_FILE, 15, 21)

    found = fetch_definitions(ENGINE, EN_D09_COMMIT, shown)

    assert found.unresolved == ()
    assert [(piece.span.start, piece.span.end) for piece in found.fetched] == [(13, 13)]


def test_string_prefixes_are_part_of_the_string():
    assert root_names('re.compile(r"(^|/)x$", flags=F"{mode}")', "python") == ("re",)


UNDEFINED_NAME = """def check(x):
    if x and MISSING:
        return 1
"""


def committed_file(repository: Path, name: str, text: str) -> str:
    (repository / name).write_text(text)
    for command in (["init", "-q"], ["add", name], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "t"]):
        subprocess.run(["git", *command], cwd=repository, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repository, capture_output=True, text=True, check=True).stdout.strip()


def test_a_name_whose_file_could_not_be_parsed_is_unknown_not_unresolved(tmp_path):
    commit = committed_file(tmp_path, "check.py", UNDEFINED_NAME)
    shown, named = Span("check.py", 2, 3), [("MISSING", 2)]

    parsed = definitions_of(tmp_path, commit, shown, named)
    timed_out = definitions_of(tmp_path, commit, shown, named, unparsed_files=lambda _repository, _commit, file: frozenset({file}))

    assert (parsed.unresolved, parsed.unknown) == (("MISSING",), ())
    assert (timed_out.unresolved, timed_out.unknown) == ((), ("MISSING",))


def test_unknown_and_unresolved_names_both_escalate():
    assert Definitions((), ("a",), ("b",)).escalation_reasons() == ["definition not found: a", "definition unknown, file not parsed: b"]
