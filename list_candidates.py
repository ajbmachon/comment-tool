"""Find real comments the list-claim trigger fires on, with no model call, to pick the first labelled run.

For each repository at its round-3 commit, every file whose comments use a quantifier word is read,
and every comment on which `list_claims.list_claim_for` finds a list is printed with its entries and
whether any entry is, or holds, a name.
usage: uv run python list_candidates.py > <out.jsonl>
"""

import json
import sys

from jev_navigator.index import tools
from jev_navigator.index.code_index import CodeIndex

from comment_discovery import found_comments
from definition_fetch import language_of
from list_claims import _entry_names, claims_every_entry, list_claim_for
from sample_round4 import REPOSITORIES, candidate_files

QUANTIFIED_COMMENT = r"(#|//|\*).*(only|every|all|each|always|never|none)"
CHUNK = 300


def quantified_files(repository, commit: str, include, exclude) -> list[str]:
    listed = tools.git(["grep", "-l", "-i", "-E", QUANTIFIED_COMMENT, commit, "--"], repository).splitlines()
    wanted = set(candidate_files(repository, commit, include, exclude))
    return sorted(path.split(":", 1)[1] for path in listed if path.split(":", 1)[1] in wanted)


def main() -> None:
    for name, (repository, commit, _, include, exclude) in REPOSITORIES.items():
        files = quantified_files(repository, commit, include, exclude)
        for start in range(0, len(files), CHUNK):
            chunk = files[start : start + CHUNK]
            index = CodeIndex.at_commit(repository, commit, chunk)
            for found in found_comments(index, chunk):
                literal = list_claim_for(index, found.case) if claims_every_entry(found.case.text) else None
                if literal is not None:
                    path = found.case.file
                    named = [entry for entry in literal.entries if _entry_names(entry, path)]
                    print(json.dumps({"repository": name, "commit": commit, "location": f"{path}:{found.case.first_line}",
                                      "comment": found.case.text, "list": literal.name, "entries": len(literal.entries),
                                      "named_entries": len(named), "language": language_of(path)}), flush=True)


if __name__ == "__main__":
    sys.exit(main())
