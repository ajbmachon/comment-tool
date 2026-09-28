"""Find real doc comments the rules send to "rewrite", for the rewrite-packet pilot. Jev only, no Sol.

In the validation sample's hash order, skipping every file an earlier round used, each file's first
doc comment goes through `sweep.judged` until each repository has given `PER_REPOSITORY` decided
rewrites or `MAX_DOCS` doc comments. Heedvane is read in `apps/web/src/lib` at the lib-sweep commit,
the engine at the round-3 commit. Every exchange is journaled.
usage: uv run python rewrite_candidates.py
"""

import json
import re

from jev_navigator.index.code_index import CodeIndex

from comment_review import question_set
from data_root import DATA
from journaled_client import journaled_judge
from run_round4 import ROUND4_QUESTIONS, case_of
from sample_docs import case_paths, doc_comment, rank, round4_paths
from sample_round4 import REPOSITORIES, candidate_files, packet, used_paths
from sweep import judged

OUT = DATA / "docs-rewrite"
PER_REPOSITORY, MAX_DOCS = 5, 250
SOURCES = {
    "heedvane": (REPOSITORIES["heedvane"][0], "a3bde2aa8", re.compile(r"^apps/web/src/lib/.*\.(ts|tsx)$"),
                 re.compile(r"\.test\.|\.spec\.|test-support|generated|\.d\.ts$|__tests__|/e2e/")),
    "analysis-engine": (REPOSITORIES["analysis-engine"][0], REPOSITORIES["analysis-engine"][1],
                        REPOSITORIES["analysis-engine"][3], REPOSITORIES["analysis-engine"][4]),
}
PREFIXES = {"heedvane": "hv-r", "analysis-engine": "en-r"}


def validation_paths() -> set[str]:
    return case_paths(DATA / "docs" / "cases.jsonl")


def candidates(name: str, used: set[str]):
    repository, commit, include, exclude = SOURCES[name]
    for path in sorted(candidate_files(repository, commit, include, exclude), key=lambda p: rank(name, p)):
        if path not in used:
            index = CodeIndex.at_commit(repository, commit, [path])
            found = doc_comment(index, name, path)
            if found is not None:
                yield index, found


def main() -> None:
    OUT.mkdir(exist_ok=True)
    used = used_paths() | round4_paths() | validation_paths()
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    judge = journaled_judge(OUT, set(SOURCES))
    with (OUT / "cases.jsonl").open("w") as cases, (OUT / "pass.jsonl").open("w") as passes:
        for name in SOURCES:
            rewrites = 0
            for number, (index, found) in enumerate(candidates(name, used), start=1):
                case = {**packet(name, index.commit, f"{PREFIXES[name]}{number:03d}", index, found), "kind": found.kind}
                row = judged(index, judge, case_of(case), questions)
                row.pop("state", None)
                cases.write(json.dumps(case) + "\n")
                passes.write(json.dumps({"case_id": case["case_id"], **row}) + "\n")
                rewrites += row["action"] == "rewrite" and "escalate" not in row
                if rewrites == PER_REPOSITORY or number == MAX_DOCS:
                    print(f"{name}: {rewrites} decided rewrites in {number} doc comments", flush=True)
                    break
    print(f"Jev comment requests {judge.calls}")


if __name__ == "__main__":
    main()
