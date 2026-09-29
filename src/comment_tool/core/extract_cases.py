"""Build comment-value case packets from exact Git blobs.

For each (repo, file, line) seed the comment block containing that line is expanded, classified by
the deterministic keep rule (tool directive, file header, or a doc block attached to a
declaration), and paired with the code directly above and below it. Provenance stays outside
the model-visible request.

usage: python3 extract_cases.py seeds.tsv > cases.jsonl
seeds.tsv columns: case_id, repo_dir, commit, path, line
"""

import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

MAX_ANNOTATED_LINES = 25
MAX_PRECEDING_LINES = 8
DATE = re.compile(
    r"\b20\d\d-\d\d-\d\d\b|\b\d{1,2}\.\d{1,2}\.20\d\d\b|"
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2},?\s+)?20\d\d\b"
)
TICKET = re.compile(r"(?<![\w&/])#\d+\b(?!;)|\bPR\s*#?\d+\b|\b(issue|ticket|task)\s+#?\d+\b", re.IGNORECASE)
TODO = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b(?!\s*\()")
DIVIDER = re.compile(r"^[\s#/*\-=_~\u2500-\u257f]+$")
TS_CODE = re.compile(
    r"[;{}]\s*$"
    r"|^\s*(if|for|while|switch)\s*\("
    r"|^\s*(const|let|var)\s+[\w$\[{][^=]*="
    r"|^\s*(import|export)\b.*\bfrom\s+['\"]"
    r"|^\s*(await\s+)?[\w.$]+\(.*\)\s*;?$"
)
"""A line that reads as TypeScript: it ends a statement or block, opens a condition or loop, declares
a variable, imports or re-exports, or is a call. A keyword alone is not enough: prose starts with
"for", "if" or "return" too."""
UNIT_START = {
    "#": re.compile(r"^\s*(async\s+def|def|class|@)\b"),
    "//": re.compile(r"^\s*(export\s+)?(default\s+)?(async\s+)?(abstract\s+)?(function|class|interface)\b"),
}
DECLARATION = {
    "#": re.compile(r"^\s*(async\s+def|def|class|@)\b"),
    "//": re.compile(r"^\s*(/\*\*|(export\s+)?(default\s+)?(declare\s+)?(async\s+)?(abstract\s+)?(function|class|interface|enum|type\s+\w+)\b)"),
}
DIRECTIVE = re.compile(
    r"(eslint-(disable|enable)|@ts-(expect-error|ignore|nocheck)|noqa|type:\s*ignore|pragma|"
    r"squawk-ignore|biome-ignore|prettier-ignore|istanbul ignore|c8 ignore|pyright:|SPDX-License|^#!)"
)


def git_blob(repo: str, commit: str, path: str) -> tuple[str, str]:
    """Return the file text and blob id of `path` at `commit`."""
    blob = subprocess.check_output(["git", "-C", repo, "rev-parse", f"{commit}:{path}"], text=True).strip()
    text = subprocess.check_output(["git", "-C", repo, "cat-file", "-p", blob], text=True)
    return text, blob


def comment_prefix(path: str) -> str:
    return "#" if path.endswith(".py") else "//"


def is_comment(line: str, prefix: str) -> bool:
    return line.lstrip().startswith(prefix)


def block_span(lines: list[str], index: int, prefix: str) -> tuple[int, int]:
    """Expand from a seed line to the contiguous run of comment lines around it."""
    start = index
    while start > 0 and is_comment(lines[start - 1], prefix):
        start -= 1
    end = index
    while end + 1 < len(lines) and is_comment(lines[end + 1], prefix):
        end += 1
    return start, end


def annotated_span(lines: list[str], block_end: int, prefix: str) -> tuple[int, int]:
    """The code the comment governs: following lines, past blank lines, until the next comment,
    the next function or class, or a dedent out of the comment's block, capped."""
    start = block_end + 1
    while start < len(lines) and not lines[start].strip():
        start += 1
    indent = indentation(lines[block_end])
    end = start
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if index - start + 1 > MAX_ANNOTATED_LINES:
            break
        if not line.strip():
            continue
        if is_comment(line, prefix) or UNIT_START[prefix].match(line) or indentation(line) < indent:
            break
        end = index
    return start, end


def indentation(line: str) -> int:
    return len(line) - len(line.lstrip())


def preceding_span(lines: list[str], block_start: int, prefix: str) -> tuple[int, int]:
    """The code directly above the comment, which a trailing comment in a block annotates."""
    end = block_start - 1
    start = end + 1
    while start - 1 >= 0 and code_line_continues(lines[start - 1], prefix) and end - start + 1 < MAX_PRECEDING_LINES:
        start -= 1
    return start, end


def code_line_continues(line: str, prefix: str) -> bool:
    """The annotated run ends at a blank line or at the next comment block."""
    return bool(line.strip()) and not is_comment(line, prefix)


def is_file_header(lines: list[str], block_start: int, prefix: str) -> bool:
    """True when nothing but blank lines, shebangs or other comments precede the block."""
    return all(not line.strip() or is_comment(line, prefix) or line.startswith("#!") for line in lines[:block_start])


def opens_declaration(lines: list[str], block_end: int, prefix: str) -> bool:
    """True when the line right after the block starts a function, class, type or doc comment."""
    following = block_end + 1
    return following < len(lines) and bool(DECLARATION[prefix].match(lines[following]))


def deterministic_keep(lines: list[str], start: int, end: int, prefix: str) -> str | None:
    """Name the code-owned reason a comment is kept without a model call, or None."""
    block = "\n".join(lines[start : end + 1])
    if DIRECTIVE.search(block):
        return "tool_directive"
    if is_file_header(lines, start, prefix):
        return "file_header"
    if opens_declaration(lines, end, prefix):
        return "declaration_doc"
    return None


def deterministic_proposal(facts: dict) -> str | None:
    """Name the removal proposal code makes without a model call, or None."""
    if facts["commented_out_code"]:
        return "remove_commented_out_code"
    return None


def inside_name(text: str, match: re.Match) -> bool:
    """True when a date is part of a file, path or document name such as `...-adr-2026-08-26.md`."""
    before = text[: match.start()]
    token_start = max(before.rfind(" "), before.rfind("\n"), before.rfind("("), before.rfind("`")) + 1
    token = text[token_start : match.end() + 4]
    return "/" in token or text[match.start() - 1 : match.start()] in ("-", "_") or ".md" in token


def comment_body(block_lines: list[str], prefix: str) -> list[str]:
    """The comment lines without their markers, blank lines dropped."""
    bodies = [line.lstrip()[len(prefix):].strip() for line in block_lines]
    return [body for body in bodies if body]


def is_commented_out_code(body: list[str], prefix: str) -> bool:
    """True when every non-blank comment line parses (Python) or reads (TypeScript) as code."""
    content = [line for line in body if not DIVIDER.match(line)]
    if not content:
        return False
    if prefix == "#":
        try:
            tree = ast.parse("\n".join(content))
        except SyntaxError:
            return False
        return not all(isinstance(node, ast.Expr) and isinstance(node.value, ast.Name) for node in tree.body)
    return all(TS_CODE.search(line) for line in content)


def code_facts(block_lines: list[str], prefix: str) -> dict:
    """Facts about a comment that code owns, so no model is asked for them."""
    body = comment_body(block_lines, prefix)
    text = "\n".join(body)
    return {
        "dates": [match.group(0) for match in DATE.finditer(text) if not inside_name(text, match)],
        "ticket_refs": [" ".join(match.group(0).split()) for match in TICKET.finditer(text)],
        "unowned_todo": bool(TODO.search(text)),
        "divider_lines": sum(1 for line in body if DIVIDER.match(line)),
        "commented_out_code": is_commented_out_code(body, prefix),
    }


def build_case(case_id: str, repo: str, commit: str, path: str, line: int) -> dict:
    text, blob = git_blob(repo, commit, path)
    lines = text.split("\n")
    prefix = comment_prefix(path)
    if not is_comment(lines[line - 1], prefix):
        raise SystemExit(f"{case_id}: {path}:{line} is not a {prefix} comment")
    start, end = block_span(lines, line - 1, prefix)
    before_start, before_end = preceding_span(lines, start, prefix)
    code_start, code_end = annotated_span(lines, end, prefix)
    comment_text = "\n".join(lines[start : end + 1])
    before_text = "\n".join(lines[before_start : before_end + 1])
    code_text = "\n".join(lines[code_start : code_end + 1])
    facts = code_facts(lines[start : end + 1], prefix)
    return {
        "case_id": case_id,
        "deterministic_keep": deterministic_keep(lines, start, end, prefix),
        "deterministic_proposal": deterministic_proposal(facts),
        "code_facts": facts,
        "provenance": {
            "repository": repo.rstrip("/").split("/")[-1],
            "commit": commit,
            "path": path,
            "blob": blob,
            "comment_lines": [start + 1, end + 1],
            "code_before_lines": [before_start + 1, before_end + 1],
            "code_after_lines": [code_start + 1, code_end + 1],
            "comment_sha256": hashlib.sha256(comment_text.encode()).hexdigest(),
        },
        "state": {
            "comment": {"text": comment_text},
            "code": {
                "language": "python" if path.endswith(".py") else "typescript",
                "before_comment": before_text,
                "after_comment": code_text,
            },
        },
    }


def main() -> None:
    for row in Path(sys.argv[1]).read_text().splitlines(keepends=True):
        if not row.strip() or row.startswith("case_id"):
            continue
        case_id, repo, commit, path, line = row.rstrip("\n").split("\t")
        print(json.dumps(build_case(case_id, repo, commit, path, int(line))))


if __name__ == "__main__":
    main()
