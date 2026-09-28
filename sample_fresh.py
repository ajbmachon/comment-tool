"""Pick fresh comment seeds by hash order, one per file, from files no earlier seed came from.

Production source only (no tests, generated code or type declarations). A seed is kept only when
code alone does not decide it, so every seed goes to Jev.
usage: python3 sample_fresh.py seeds.tsv 15 > round2/seeds.tsv
"""

import hashlib
import re
import subprocess
import sys

from extract_cases import block_span, build_case, comment_prefix, is_comment

REPOS = {
    "heedvane": ("/Users/andremachon/Projects/heedvane", "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590",
                 re.compile(r"^apps/.*\.(ts|tsx)$"), re.compile(r"\.test\.|\.spec\.|test-support|generated|\.d\.ts$|__tests__|/e2e/")),
    "analysis-engine": ("/Users/andremachon/Projects/analysis-engine", "65ce1972665975d20bb09f3638a6155f6fb3f9b9",
                        re.compile(r"^enginepy/.*\.py$"), re.compile(r"_test\.py$|/tests?/|generated|conftest\.py$")),
}
SALT = "comment-fresh-v1"


def files(repo: str, commit: str, include: re.Pattern, exclude: re.Pattern) -> list[str]:
    listed = subprocess.check_output(["git", "-C", repo, "ls-tree", "-r", "--name-only", commit], text=True).splitlines()
    return [path for path in listed if include.match(path) and not exclude.search(path)]


def block_starts(repo: str, commit: str, path: str) -> list[int]:
    text = subprocess.check_output(["git", "-C", repo, "show", f"{commit}:{path}"], text=True)
    lines = text.split("\n")
    prefix = comment_prefix(path)
    starts, index = [], 0
    while index < len(lines):
        if is_comment(lines[index], prefix):
            start, end = block_span(lines, index, prefix)
            starts.append(start + 1)
            index = end + 1
        else:
            index += 1
    return starts


def rank(*parts) -> str:
    return hashlib.sha256(":".join([SALT, *map(str, parts)]).encode()).hexdigest()


def main() -> None:
    used = {row.split("\t")[3] for row in open(sys.argv[1]) if row.strip()}
    per_repo = int(sys.argv[2])
    for name, (repo, commit, include, exclude) in REPOS.items():
        picked = 0
        for path in sorted(files(repo, commit, include, exclude), key=lambda p: rank(name, p)):
            if path in used:
                continue
            for line in sorted(block_starts(repo, commit, path), key=lambda l: rank(name, path, l)):
                case = build_case("probe", repo, commit, path, line)
                if case["deterministic_keep"] or case["deterministic_proposal"]:
                    continue
                picked += 1
                print(f"{'hv' if name == 'heedvane' else 'en'}-f{picked:02d}\t{repo}\t{commit}\t{path}\t{line}")
                break
            if picked == per_repo:
                break


if __name__ == "__main__":
    main()
