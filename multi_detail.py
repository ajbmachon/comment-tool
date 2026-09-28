"""Count the round-4 comments that name more than one checkable detail, by one fixed rule.

The rule, fixed before counting: the comment body (markers removed) is split into clauses at
sentence ends, semicolons, colons and dashes used as separators. A clause is a detail when it holds
a checkable token: a digit, backticked code, a code-shaped identifier (snake_case, camelCase,
dotted or called names), an ALL-CAPS name, a number word, or an order or condition word. A comment names more than
one detail when two or more clauses are details. It is mechanical and crude, and it needs no model.
usage: python3 multi_detail.py
"""

import json
import re

from data_root import DATA
from extract_cases import comment_body, comment_prefix

CLAUSE_BREAK = re.compile(r"(?<=[.;:])\s+|\s+[—–-]{1,2}\s+")
CHECKABLE = re.compile(
    r"\d|`[^`]+`|\b[a-z]+_[a-z0-9_]+\b|\b[a-z]+[A-Z]\w*\b|\b\w+\.\w+\b|\b\w+\(\)|\b[A-Z]{2,}[A-Z0-9_]*\b"
    r"|(?i:\b(only|never|always|before|after|first|unless|even|until|when|if|instead|every|each"
    r"|once|twice|one|two|three|four|five|six|seven|eight|nine|ten)\b)"
)
"""Checkable tokens; only the order and condition words ignore case."""


def detail_clauses(comment: str, path: str) -> list[str]:
    body = " ".join(comment_body(comment.split("\n"), comment_prefix(path)))
    return [clause for clause in CLAUSE_BREAK.split(body) if clause.strip() and CHECKABLE.search(clause)]


def main() -> None:
    cases = [json.loads(line) for line in (DATA / "round4" / "cases.jsonl").read_text().splitlines()]
    counts = {c["case_id"]: len(detail_clauses(c["state"]["comment"]["text"], c["provenance"]["path"])) for c in cases}
    multi = sorted(cid for cid, n in counts.items() if n >= 2)
    print(f"comments naming two or more details: {len(multi)} of {len(counts)}")
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
