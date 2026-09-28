"""Pick the round-4 comments and build their packets, with no model call.

15 Heedvane comments from outside `apps/web/src/lib` (the lib sweep) and 15 analysis-engine
comments, at the round-3 commits, one per file, in a fixed hash order, from files no earlier round
used. A comment qualifies when it is a whole-line comment code does not decide (the population the
reference labels cover). Packets use the measured cut: the lines above and `code_described_by_comment`.
usage: run-slot -- uv run --project <jev-navigator> python sample_round4.py > round4/cases.jsonl
"""

import hashlib
import json
import re
import sys
from pathlib import Path

from jev_navigator.index import tools
from jev_navigator.index.code_index import CodeIndex

from comment_discovery import code_decision, found_comments
from comment_review import MEASURED_CONTEXT, comment_state
from data_root import DATA

SALT = "comment-fresh-v4"
PER_REPOSITORY = 15
REPOSITORIES = {
    "heedvane": (Path.home() / "Projects/heedvane", "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590", "hv-h",
                 re.compile(r"^apps/.*\.(ts|tsx)$"),
                 re.compile(r"^apps/web/src/lib/|\.test\.|\.spec\.|test-support|generated|\.d\.ts$|__tests__|/e2e/")),
    "analysis-engine": (Path.home() / "Projects/analysis-engine", "65ce1972665975d20bb09f3638a6155f6fb3f9b9", "en-h",
                        re.compile(r"^enginepy/.*\.py$"), re.compile(r"_test\.py$|/tests?/|generated|conftest\.py$")),
}
USED_SEEDS = (DATA / "round3" / "used-seeds.tsv", DATA / "round3" / "seeds.tsv")
REVIEWED_KIND = "block"


def rank(*parts) -> str:
    return hashlib.sha256(":".join([SALT, *map(str, parts)]).encode()).hexdigest()


def used_paths() -> set[str]:
    return {row.split("\t")[3] for path in USED_SEEDS for row in path.read_text().splitlines()[1:] if row.strip()}


def candidate_files(repository: Path, commit: str, include: re.Pattern, exclude: re.Pattern) -> list[str]:
    listed = tools.git(["ls-tree", "-r", "--name-only", commit], repository).splitlines()
    return [path for path in listed if include.match(path) and not exclude.search(path)]


def reviewable_comment(index: CodeIndex, name: str, path: str):
    """The first comment in hash order that goes to Jev, or None when the file has none."""
    eligible = [found for found in found_comments(index, [path]) if found.kind == REVIEWED_KIND and code_decision(found) is None]
    return min(eligible, key=lambda found: rank(name, path, found.case.first_line), default=None)


def packet(name: str, commit: str, case_id: str, index: CodeIndex, found) -> dict:
    case = found.case
    before, after = MEASURED_CONTEXT(index, case)
    return {
        "case_id": case_id, "deterministic_keep": None, "deterministic_proposal": None, "code_facts": case.facts,
        "provenance": {"repository": name, "commit": commit, "path": case.file, "comment_lines": [case.first_line, case.last_line],
                       "code_before_lines": before.source()["lines"] if before else None, "code_after_lines": after.source()["lines"]},
        "state": comment_state(case, before, after),
    }


def main() -> None:
    used = used_paths()
    for name, (repository, commit, prefix, include, exclude) in REPOSITORIES.items():
        picked = 0
        for path in sorted(candidate_files(repository, commit, include, exclude), key=lambda p: rank(name, p)):
            if path in used:
                continue
            index = CodeIndex.at_commit(repository, commit, [path])
            found = reviewable_comment(index, name, path)
            if found is None:
                continue
            picked += 1
            print(json.dumps(packet(name, commit, f"{prefix}{picked:02d}", index, found)), flush=True)
            if picked == PER_REPOSITORY:
                break
        print(f"{name}: {picked} picked", file=sys.stderr)


if __name__ == "__main__":
    main()
