"""A comment's claim about every entry of a list, checked one entry at a time (approved by Andre,
28.09.2026, about 08:00 CEST).

Code triggers it: the comment uses one of the words in `QUANTIFIER`, and the code it describes is a
single list-like literal with at least two entries, read with the language's parser (a Python tuple,
list, set or dict; a TypeScript array, object, enum or union type). Question A (`LIST_CLAIM`) joins
the comment's first request. When A is yes, question B (`ENTRY_CHECK`) is asked once per entry
through the library's `check_each`, and `compose.list_claim` combines the answers: one entry that
surely fails the condition makes the comment stale. An entry that is, or holds, a name (a constant, a
spread, a call's argument, a first-party callee) carries the definitions `definition_fetch` finds for
those names; a name without one escalates (also one the library calls unknown because its file was
not parsed), as does a list longer than `MAX_ENTRIES`. A name imported
from a package outside the repository, a function (`re.compile`) or a value (an icon), passes as it
is and needs no definition (lead, 28.09.2026). A failing list is only proposed: the entries disagree
with the comment, but either side may be wrong, so the row says the caller decides (Andre, 28.09.2026:
"Only propose").
"""

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex
from jev_navigator.index.spans import Span
from jev_navigator.judgments.judge import Judge

import comment_tool.core.compose as compose
from comment_tool.claims.ts_parse import ts_parse, typescript_of
from comment_tool.core.comment_review import (
    CommentCase,
    QuestionSet,
    described_after,
    question_set,
    with_escalation,
)
from comment_tool.core.definition_fetch import (
    Definitions,
    definitions_of,
    imported_from_outside,
    language_of,
    root_names,
)
from comment_tool.questions import path as _qpath

QUANTIFIER = re.compile(r"\b(only|every|all|each|always|never|none)\b", re.IGNORECASE)
SCRIPT_ENTRY_LABEL = re.compile(r"[A-Za-z_$][\w$]*\s*[:=](?![:=])")
"""A TypeScript object key or enum member name (`key:` or `Name =`): a label, not a reference."""
MIN_ENTRIES, MAX_ENTRIES = 2, 60
CALLER_DECIDES = "comment or list may be wrong, caller decides"
LIST_CLAIM = "states_condition_for_every_entry"
_CHECKS = {check.name: check for check in
           question_set(json.loads((_qpath("questions.list-claims.json")).read_text())).checks}
CLAIM_CHECK, ENTRY_CHECK = _CHECKS[LIST_CLAIM], _CHECKS["entry_meets_stated_condition"]


@dataclass(frozen=True)
class ListLiteral:
    name: str
    entries: tuple[str, ...]
    line: int


@dataclass(frozen=True)
class EntryItems:
    items: tuple[dict, ...]
    fetched: tuple[dict, ...]
    unresolved: tuple[str, ...]
    unknown: tuple[str, ...] = ()

    def escalation_reasons(self) -> list[str]:
        return Definitions((), self.unresolved, self.unknown).escalation_reasons()


def claims_every_entry(comment: str) -> bool:
    return QUANTIFIER.search(comment) is not None


def list_literal(source: str, path: str, line: int, typescript: Path) -> ListLiteral | None:
    """The list-like literal declared on `line`, when it has at least `MIN_ENTRIES` entries."""
    found = _python_list(source, line) if path.endswith(".py") else _typescript_list(source, path, line, typescript)
    return found if found is not None and len(found.entries) >= MIN_ENTRIES else None


def _python_list(source: str, line: int) -> ListLiteral | None:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign | ast.AnnAssign) and node.lineno == line:
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            entries = _python_entries(source, node.value)
            return ListLiteral(ast.unparse(target), entries, line) if entries is not None else None
    return None


def _python_entries(source: str, value: ast.expr | None) -> tuple[str, ...] | None:
    if isinstance(value, ast.Tuple | ast.List | ast.Set):
        return tuple(ast.get_source_segment(source, element) for element in value.elts)
    if isinstance(value, ast.Dict):
        return tuple(f"{ast.get_source_segment(source, key)}: {ast.get_source_segment(source, item)}" if key else
                     f"**{ast.get_source_segment(source, item)}" for key, item in zip(value.keys, value.values, strict=True))
    return None


def _typescript_list(source: str, path: str, line: int, typescript: Path) -> ListLiteral | None:
    parsed = ts_parse(typescript, path, source, line, "entries")
    return ListLiteral(parsed["name"], tuple(parsed["entries"]), line) if parsed["kind"] == "list" else None


def list_claim_for(index: CodeIndex, case: CommentCase) -> ListLiteral | None:
    """The list a comment makes a claim about, when code's trigger fires; None otherwise."""
    if not claims_every_entry(case.text):
        return None
    source = "\n".join(index.lines(case.file))
    return list_literal(source, case.file, described_after(index, case).span.start, typescript_of(index.git_root))


def with_list_claim_question(questions: QuestionSet) -> QuestionSet:
    return QuestionSet((*questions.checks, CLAIM_CHECK), questions.picks, questions.scores)


def entry_items(index: CodeIndex, file: str, literal: ListLiteral) -> EntryItems:
    """Each entry as B's item, with the definitions of the names it needs, and the names without one."""
    items, fetched, unresolved, unknown = [], [], [], []
    for entry in literal.entries:
        found = definitions_of(index.git_root, index.commit, Span(file, literal.line, literal.line),
                               [(name, literal.line) for name in _entry_names(entry, file)])
        definitions = [{**piece.source(), "code": piece.text} for piece in found.fetched]
        items.append({"code": entry, "definitions": definitions})
        fetched += [piece.source() for piece in found.fetched]
        unresolved += [name for name in found.unresolved
                       if not imported_from_outside(index.git_root, index.commit, file, name)]
        unknown += found.unknown
    return EntryItems(tuple(items), tuple(fetched), tuple(dict.fromkeys(unresolved)), tuple(dict.fromkeys(unknown)))


def _entry_names(entry: str, file: str) -> tuple[str, ...]:
    language = language_of(file)
    return root_names(entry, language, None if language == "python" else SCRIPT_ENTRY_LABEL)


def checked_list_claim(index: CodeIndex, judge: Judge, case: CommentCase, literal: ListLiteral, row: dict) -> dict:
    """Asks B for each entry when A is yes, and applies `compose.list_claim` to the row."""
    if len(literal.entries) > MAX_ENTRIES:
        return with_escalation(row, [f"list too long ({len(literal.entries)} entries)"])
    claim_probability = row["probabilities"][LIST_CLAIM]
    if claim_probability < compose.CUTOFF:
        return with_escalation(row, list(compose.list_claim(claim_probability, {}).reasons))
    prepared = entry_items(index, case.file, literal)
    record = {"list": literal.name, "definitions": list(prepared.fetched), "unresolved": list(prepared.unresolved),
              "unknown": list(prepared.unknown)}
    if prepared.escalation_reasons():
        return with_escalation({**row, "list_claim": record}, prepared.escalation_reasons())
    entries = _entry_probabilities(judge, case, literal, prepared.items)
    claim = compose.list_claim(claim_probability, entries)
    record |= {"entries": entries, "failing": list(claim.failing), **({"caller_decides": CALLER_DECIDES} if claim.fails else {})}
    checked = {**row, "list_claim": record, **({"action": "fix_stale"} if claim.fails else {})}
    return with_escalation(checked, list(claim.reasons))


def _entry_probabilities(judge: Judge, case: CommentCase, literal: ListLiteral, items: tuple[dict, ...]) -> dict[str, float]:
    results = judge.check_each(ENTRY_CHECK, list(items), {"comment": {"text": case.text}})
    return {entry: result.probability for entry, result in zip(literal.entries, results, strict=True)}
