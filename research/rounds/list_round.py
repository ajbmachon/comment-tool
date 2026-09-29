"""The first labelled run of the list-claim check: build the packets, then run the tool on them.

Six real comments the trigger fires on, from `list-round/candidates.jsonl` (found with no model by
`list_candidates.py`): en-h11, the case the questions were written for; the verifier's two controls,
a list where every entry meets the comment's condition (`COST_KEY_TO_CREDITS_KEY`) and a list made of
names (`CATALOG_REFUSALS`); and three more in a fixed hash order. Each packet holds the first request's
state and B's entries with their definitions, exactly as the tool builds them.
usage: uv run python list_round.py sample > list-round/cases.jsonl
       uv run python list_round.py run
"""

import hashlib
import json
import sys

from jev_navigator.index.code_index import CodeIndex

from comment_tool.claims.list_claims import entry_items, list_claim_for
from comment_tool.cli.sweep import QUESTIONS, judged
from comment_tool.config import DATA
from comment_tool.core.comment_discovery import found_comments
from comment_tool.core.comment_review import question_set
from comment_tool.journal.journaled_client import journaled_judge
from research.rounds.run_round4 import case_of, index_of
from research.rounds.sample_round4 import REPOSITORIES, packet

ROUND = DATA / "list-round"
SALT = "list-round-v1"
CHOSEN = {
    "enginepy/workflows/document_analysis/standards_scout.py:318": "target en-h11",
    "apps/api/src/credit-conversion.ts:176": "control: every entry meets the condition",
    "apps/api/src/run-attempts/postgres-run-attempt-catalog.ts:1799": "control: entries are names",
}
RANDOM_PICKS = 3


def rank(location: str) -> str:
    return hashlib.sha256(f"{SALT}:{location}".encode()).hexdigest()


def chosen_candidates() -> list[tuple[dict, str]]:
    candidates = [json.loads(line) for line in (ROUND / "candidates.jsonl").read_text().splitlines()]
    fixed = [(c, CHOSEN[c["location"]]) for c in candidates if c["location"] in CHOSEN]
    others = sorted((c for c in candidates if c["location"] not in CHOSEN), key=lambda c: rank(c["location"]))
    return fixed + [(c, "hash order") for c in others[:RANDOM_PICKS]]


def list_packet(number: int, candidate: dict, role: str) -> dict:
    path, line = candidate["location"].rsplit(":", 1)
    repository = REPOSITORIES[candidate["repository"]][0]
    index = CodeIndex.at_commit(repository, candidate["commit"], [path])
    found = next(f for f in found_comments(index, [path]) if f.case.first_line == int(line))
    literal = list_claim_for(index, found.case)
    items = entry_items(index, path, literal).items
    base = packet(candidate["repository"], index.commit, f"lr-{number:02d}", index, found)
    return {**base, "role": role, "list": literal.name, "items": list(items)}


def sample() -> None:
    for number, (candidate, role) in enumerate(chosen_candidates(), start=1):
        print(json.dumps(list_packet(number, candidate, role)), flush=True)


def run() -> None:
    raws = [json.loads(line) for line in (ROUND / "cases.jsonl").read_text().splitlines()]
    questions = question_set(json.loads(QUESTIONS.read_text()))
    judge = journaled_judge(ROUND, {raw["provenance"]["repository"] for raw in raws})
    with (ROUND / "pass.jsonl").open("w") as passes:
        for raw in raws:
            row = judged(index_of(raw), judge, case_of(raw), questions)
            row.pop("state", None)
            passes.write(json.dumps({"case_id": raw["case_id"], **row}) + "\n")
            print(raw["case_id"], row["action"], row.get("escalate", {}).get("reasons", []), flush=True)
    print(f"Jev requests {judge.calls}")


if __name__ == "__main__":
    {"sample": sample, "run": run}[sys.argv[1]]()
