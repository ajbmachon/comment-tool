"""The comment tool's own fact rules, built from jev-navigator's general `FactRule`.

Policy lives here, not in the library: which date shapes count as a time reference, that a date
inside a file, path or ADR name does not, what a ticket reference looks like, and when a comment is
commented-out code. `facts_of` returns the dictionary rule A reads.
"""

import re

from jev_navigator.facts import FactRule, find_facts

from extract_cases import (
    DATE,
    TICKET,
    TODO,
    comment_body,
    inside_name,
    is_commented_out_code,
)


def outside_any_name(text: str, match: re.Match) -> bool:
    """A date inside a file, path or document name (`...-adr-2026-08-26.md`) is not a time reference."""
    return not inside_name(text, match)


TIME_DATE = FactRule("date", DATE, keep=outside_any_name)
TICKET_REFERENCE = FactRule("ticket_reference", TICKET)
TODO_WITHOUT_OWNER = FactRule("todo_without_owner", TODO)
COMMENT_RULES = (TIME_DATE, TICKET_REFERENCE, TODO_WITHOUT_OWNER)


def facts_of(comment_text: str, prefix: str) -> dict:
    """The facts rule A reads, found over the comment body without its markers."""
    body = comment_body(comment_text.split("\n"), prefix)
    found = find_facts("\n".join(body), COMMENT_RULES)
    return {
        "dates": [fact.text for fact in found if fact.name == "date"],
        "ticket_refs": [" ".join(fact.text.split()) for fact in found if fact.name == "ticket_reference"],
        "unowned_todo": any(fact.name == "todo_without_owner" for fact in found),
        "commented_out_code": is_commented_out_code(body, prefix),
    }
