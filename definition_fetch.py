"""Before "fix stale comment" fires: fetch the definitions behind the conditions in the shown code.

A stale verdict on a conditional line is only as good as the packet. hv-h12's comment was right: the
condition `pendingReferral.shouldClear` got its meaning (`shouldClear: raw !== undefined`) in an
imported file Jev never saw. Code reads every `if`, `elif` and `while` condition in the code the
comment describes, takes the names each condition starts from, and fetches each name's definition:
its local binding (and the function it is bound to, when it is bound to a call), its function's
signature when it is a parameter, an imported declaration, or a declaration in the same file. A name
whose definition cannot be found leaves the stale verdict untrustworthy, so the comment escalates
instead; so does a name the library calls unknown, because the file it may be defined in could not
be parsed in time (missing evidence is never absence).

Imports resolve through the library, including tsconfig path aliases read from the commit's
tsconfig files.
"""

import builtins
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path, PurePosixPath

from jev_navigator.index import tools
from jev_navigator.index.code_index import CodeIndex
from jev_navigator.index.imports import imported_names, resolve_import
from jev_navigator.index.spans import CodeSlice, Span
from jev_navigator.index.tsconfig import ScriptPaths, nearest_script_paths

UnparsedFiles = Callable[[Path, str, str], frozenset[str]] | None
"""Which files the index for (repository, commit, file) could not parse; the library's by default."""

ORIGIN = "definition_fetch"
MAX_STATEMENT_LINES = 40
SCRIPT_GLOBALS = {"Array", "Object", "Number", "String", "Boolean", "BigInt", "Symbol", "Math", "JSON", "Date",
                  "Promise", "Set", "Map", "WeakMap", "WeakSet", "Error", "RegExp", "Reflect", "Intl", "URL",
                  "globalThis", "console", "process", "window", "document", "isNaN", "isFinite", "parseInt",
                  "parseFloat", "structuredClone", "encodeURIComponent", "decodeURIComponent"}
NOT_NAMES = {
    "typescript": {"true", "false", "null", "undefined", "this", "typeof", "instanceof", "in", "new", "void", "await",
                   *SCRIPT_GLOBALS},
    "python": {"not", "and", "or", "is", "in", "self", "cls", "await", "lambda", *dir(builtins)},
}
"""Keywords, the receiver itself, and names the language provides, which have no definition to fetch."""
STRING = re.compile(r"(?:\b[rRbBuUfF]{1,2})?(?:'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)")
ROOT_NAME = re.compile(r"(?<![\w.$])[A-Za-z_$][\w$]*")
KEYWORD_ARGUMENT = re.compile(r"(?<=[(,])\s*[A-Za-z_$][\w$]*\s*=(?!=)|(?<=[(,]\s)[A-Za-z_$][\w$]*\s*=(?!=)")
SCRIPT_CONDITION = re.compile(r"\b(?:if|while)\s*\(")
PYTHON_CONDITION = re.compile(r"^\s*(?:if|elif|while)\s+(.+?):\s*(?:#.*)?$")
CALLED_BY_BINDING = re.compile(r"=\s*(?:await\s+)?(?:new\s+)?([A-Za-z_$][\w$]*)\s*\(")
SCRIPT_SUFFIXES = (".ts", ".tsx")


@dataclass(frozen=True)
class Definitions:
    """`unresolved` names have no definition in parsed code; `unknown` names may be defined in a file
    the index could not parse in time. Both leave a stale verdict untrustworthy."""

    fetched: tuple[CodeSlice, ...]
    unresolved: tuple[str, ...]
    unknown: tuple[str, ...] = ()

    def escalation_reasons(self) -> list[str]:
        return ([f"definition not found: {name}" for name in self.unresolved]
                + [f"definition unknown, file not parsed: {name}" for name in self.unknown])


def language_of(path: str) -> str:
    return "python" if path.endswith(".py") else "typescript"


def condition_names(line: str, language: str) -> tuple[str, ...]:
    """The names a condition on this line starts from, in order; members after a dot are left out."""
    condition = _condition_text(STRING.sub('""', line), language)
    return () if condition is None else root_names(condition, language)


def root_names(code: str, language: str, labels: re.Pattern | None = None) -> tuple[str, ...]:
    """The names `code` starts from, in order: no members after a dot, keywords, builtins, strings or
    keyword-argument names; `labels` matches further names that are labels, not references."""
    stripped = STRING.sub('""', code)
    not_references = [KEYWORD_ARGUMENT, *([labels] if labels else [])]
    names = (match.group(0) for match in ROOT_NAME.finditer(stripped)
             if not any(pattern.match(stripped, match.start()) for pattern in not_references))
    return tuple(dict.fromkeys(name for name in names if name not in NOT_NAMES[language]))


def _condition_text(line: str, language: str) -> str | None:
    if language == "python":
        match = PYTHON_CONDITION.match(line)
        return match.group(1) if match else None
    match = SCRIPT_CONDITION.search(line)
    return _inside_parentheses(line, match.end()) if match else None


def _inside_parentheses(text: str, start: int) -> str:
    depth = 1
    for position in range(start, len(text)):
        depth += {"(": 1, ")": -1}.get(text[position], 0)
        if depth == 0:
            return text[start:position]
    return text[start:]


def local_binding(lines: Sequence[str], name: str, before_line: int, language: str) -> tuple[int, int] | None:
    """The first and last line of the nearest statement above `before_line` that binds `name`."""
    binds = _binding_pattern(name, language)
    for number in range(before_line - 1, 0, -1):
        if binds.search(lines[number - 1]):
            return number, _statement_end(lines, number, language)
    return None


def _binding_pattern(name: str, language: str) -> re.Pattern:
    word = re.escape(name)
    if language == "python":
        return re.compile(rf"^\s*{word}\s*(?::[^=]+)?=(?!=)|\bfor\s+{word}\s+in\b|\bas\s+{word}\b")
    return re.compile(rf"\b(?:const|let|var)\s+(?:{word}\b|[{{\[][^}}\]]*\b{word}\b)")


def _statement_end(lines: Sequence[str], start: int, language: str) -> int:
    """A TypeScript statement ends with `;` outside brackets; a Python one at the first line that
    closes its brackets without a trailing backslash."""
    depth = 0
    last = min(len(lines), start + MAX_STATEMENT_LINES - 1)
    for number in range(start, last + 1):
        text = STRING.sub('""', lines[number - 1]).rstrip()
        depth += sum(text.count(c) for c in "([{") - sum(text.count(c) for c in ")]}")
        ended = text.endswith(";") if language == "typescript" else not text.endswith("\\")
        if depth <= 0 and ended:
            return number
    return last


def fetch_definitions(repository: Path, commit: str, shown: Span) -> Definitions:
    """Every definition behind the conditions in `shown`; names without one are listed as unresolved."""
    lines = _file_lines(repository, commit, shown.file)
    named = [(name, number) for number in range(shown.start, shown.end + 1)
             for name in condition_names(lines[number - 1], language_of(shown.file))]
    return definitions_of(repository, commit, shown, named)


def definitions_of(repository: Path, commit: str, shown: Span, named: Sequence[tuple[str, int]],
                   unparsed_files: UnparsedFiles = None) -> Definitions:
    """The definitions of each (name, line where it is used), skipping names `shown` itself defines.
    A name without one is unknown when a file it may be defined in was not parsed, else unresolved."""
    unparsed_files = unparsed_files or _unparsed_files
    pieces: dict[tuple[str, int, int], None] = {}
    unresolved: list[str] = []
    unknown: list[str] = []
    for name, line in named:
        found = _definition_pieces(repository, commit, shown, name, line)
        if found is None:
            homes = _homes(repository, commit, shown.file, name)
            missing = unknown if any(home in unparsed_files(repository, commit, home) for home in homes) else unresolved
            missing.append(name)
        pieces.update(dict.fromkeys(found or ()))
    fetched = tuple(_slice(repository, commit, *piece) for piece in pieces)
    return Definitions(fetched, tuple(dict.fromkeys(unresolved)), tuple(dict.fromkeys(unknown)))


def _homes(repository: Path, commit: str, file: str, name: str) -> list[str]:
    """The files a definition of `name` was looked for in: `file`, and the file it imports `name` from."""
    specifier = imported_names("\n".join(_file_lines(repository, commit, file)), file).get(name)
    imported = _resolved(repository, commit, file, specifier) if specifier else None
    return [file, *([imported] if imported else [])]


def _unparsed_files(repository: Path, commit: str, file: str) -> frozenset[str]:
    return _index(repository, commit, file).unparsed_files


def imported_from_outside(repository: Path, commit: str, file: str, name: str) -> bool:
    """`name` is bound by an import from a package or module outside the repository."""
    source = "\n".join(_file_lines(repository, commit, file))
    specifier = imported_names(source, file).get(name) or _module_import(source, file, name)
    return specifier is not None and _resolved(repository, commit, file, specifier) is None and not specifier.startswith(".")


def _module_import(source: str, path: str, name: str) -> str | None:
    """The module a whole-module import binds `name` to (`import re`, `import * as fs from "node:fs"`)."""
    word = re.escape(name)
    pattern = (rf"^\s*import\s+([\w.]+)(?:\s+as\s+{word})?\s*$" if path.endswith(".py")
               else rf"^\s*import\s+\*\s+as\s+{word}\s+from\s+['\"]([^'\"]+)['\"]")
    for match in re.finditer(pattern, source, re.MULTILINE):
        bound = match.group(0).split(" as ")[-1].strip() if " as " in match.group(0) else match.group(1).split(".")[0]
        if bound == name or not path.endswith(".py"):
            return match.group(1)
    return None


def _definition_pieces(repository: Path, commit: str, shown: Span, name: str, line: int) -> list | None:
    """The spans that define `name`; empty when the shown code defines it; None when nothing does."""
    lines = _file_lines(repository, commit, shown.file)
    binding = local_binding(lines, name, line, language_of(shown.file)) or _parameter_of(repository, commit, shown.file, name, line)
    if binding is not None:
        if binding[0] >= shown.start:
            return []
        return _binding_pieces(repository, commit, shown.file, binding, lines)
    declared = _declaration(repository, commit, shown.file, name)
    return [declared] if declared is not None else None


def _parameter_of(repository: Path, commit: str, file: str, name: str, line: int) -> tuple[int, int] | None:
    """The signature lines of the function around `line`, when it declares `name` as a parameter."""
    function = _index(repository, commit, file).enclosing_symbol(file, line)
    if function is None:
        return None
    lines = _file_lines(repository, commit, file)
    end = _parameter_list_end(lines, function.start)
    signature = STRING.sub('""', "\n".join(lines[function.start - 1 : end]))
    return (function.start, end) if re.search(rf"(?<![\w.$]){re.escape(name)}\b", signature) else None


def _parameter_list_end(lines: Sequence[str], start: int) -> int:
    depth, opened = 0, False
    for number in range(start, min(len(lines), start + MAX_STATEMENT_LINES - 1) + 1):
        text = STRING.sub('""', lines[number - 1])
        opened = opened or "(" in text
        depth += text.count("(") - text.count(")")
        if opened and depth <= 0:
            return number
    return start


def _binding_pieces(repository: Path, commit: str, file: str, binding: tuple[int, int], lines) -> list | None:
    statement = "\n".join(lines[binding[0] - 1 : binding[1]])
    pieces = [(file, *binding)]
    called = CALLED_BY_BINDING.search(statement)
    if called is None:
        return pieces
    declared = _declaration(repository, commit, file, called.group(1))
    return pieces + [declared] if declared is not None else None


def _declaration(repository: Path, commit: str, file: str, name: str) -> tuple[str, int, int] | None:
    """`name` declared in `file`, or declared in the file `file` imports it from."""
    source = "\n".join(_file_lines(repository, commit, file))
    specifier = imported_names(source, file).get(name)
    home = file if specifier is None else _resolved(repository, commit, file, specifier)
    if home is None:
        return None
    spans = [span for span in _index(repository, commit, home).find_definition(name) if span.file == home]
    return (home, spans[0].start, spans[0].end) if spans else None


def _resolved(repository: Path, commit: str, importer: str, specifier: str) -> str | None:
    """The repository file `specifier` names; script files resolve aliases through their nearest tsconfig."""
    return resolve_import(specifier, importer, _all_files(repository, commit), _script_paths(repository, commit, importer))


def _script_paths(repository: Path, commit: str, importer: str) -> ScriptPaths | None:
    if importer.endswith(".py"):
        return None
    return nearest_script_paths(_index(repository, commit, importer).root, str(PurePosixPath(importer).parent))


def _slice(repository: Path, commit: str, file: str, start: int, end: int) -> CodeSlice:
    text = "\n".join(_file_lines(repository, commit, file)[start - 1 : end])
    return CodeSlice(Span(file, start, end), text, ORIGIN, commit)


@cache
def _all_files(repository: Path, commit: str) -> frozenset[str]:
    return frozenset(tools.git(["ls-tree", "-r", "--name-only", commit], repository).splitlines())


@cache
def _file_text(repository: Path, commit: str, file: str) -> str:
    return tools.git(["show", f"{commit}:{file}"], repository)


def _file_lines(repository: Path, commit: str, file: str) -> tuple[str, ...]:
    return tuple(_file_text(repository, commit, file).split("\n"))


@cache
def _index(repository: Path, commit: str, file: str) -> CodeIndex:
    return CodeIndex.at_commit(repository, commit, [file])
