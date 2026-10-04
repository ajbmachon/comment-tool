"""Which comments the tool reviews, and which code decides alone, built on `find_comments`.

`find_comments` is called without a drop rule, so every comment found becomes one case and the
sweep's denominator counts them all. Code keeps tool directives and removes commented-out code;
everything else goes to Jev, doc comments included (Andre, 28.09.2026 04:49 CEST: "those comments
can be bad too"). A doc comment carries the `doc_comment` fact, which rule A reads to rewrite it
instead of removing it. A `/** */` block is a doc comment wherever it sits.
"""

from dataclasses import dataclass

from jev_navigator.comments import CommentBlock, CommentKind, find_comments
from jev_navigator.index.code_index import CodeIndex

from comment_tool.core.comment_facts import facts_of
from comment_tool.core.comment_review import CommentCase
from comment_tool.core.definition_fetch import language_of
from comment_tool.core.extract_cases import comment_prefix

KEPT_BY_CODE = {CommentKind.TOOL_DIRECTIVE}
DOC_KINDS = {CommentKind.DOCSTRING, CommentKind.JSDOC, CommentKind.HEADER, CommentKind.DECLARATION}


@dataclass(frozen=True)
class FoundComment:
    case: CommentCase
    kind: str


def found_comments(index: CodeIndex, files: list[str]) -> list[FoundComment]:
    return [FoundComment(_case(block), str(block.kind)) for block in find_comments(index, files).kept]


def _case(block: CommentBlock) -> CommentCase:
    text = comment_text(block)
    file = block.span.file
    facts = classified_facts(text, file, block.kind)
    return CommentCase(file, block.span.start, block.span.end, text, language_of(file), facts)


def classified_facts(text: str, file: str, kind: str | None) -> dict:
    """Facts for a discovered or replayed comment, preserving its parser classification."""
    return {**facts_of(text, comment_prefix(file)), "doc_comment": kind in DOC_KINDS}


def comment_text(block: CommentBlock) -> str:
    """The comment itself; for a comment trailing code, only the part after the marker."""
    if block.kind != CommentKind.INLINE:
        return block.text
    for marker in (" //", " #"):
        if marker in block.text:
            return marker.strip() + block.text.split(marker, 1)[1]
    return block.text


def code_decision(found: FoundComment) -> dict | None:
    """Keep for tool directives, remove for commented-out code; None sends it to Jev."""
    if found.kind in KEPT_BY_CODE:
        return {"action": "keep", "decided_by": "code", "reason": found.kind}
    if found.case.facts["commented_out_code"] and not found.case.facts["doc_comment"]:
        return {"action": "remove", "decided_by": "code", "reason": "commented_out_code"}
    return None
