"""Pick round 6: 30 fresh model-reviewable comments that recent merged pull requests touched, and build
their packets, with no model call.

The population is what an agent calling `classify.py --diff` sees: comments whose own lines or described
code changed in a pull request, in files that still exist after it (a comment in a deleted file needs no
action and is out of scope). The six pull requests are the ones from `count_pr_comments.py` that change
source (5 most recent merged into develop per repository, 28.09.2026). From each, 5 comments in a fixed
hash order, so no single large pull request dominates: 15 per repository, comment kinds as they come.
Comments code decides (tool directives, commented-out code) make no Jev call and are not sampled; list
claims are not part of round 6 (they have their own round), so a sampled comment the list check fires on
stops the sampling. A comment any earlier labelled round holds (same file and text), as listed in the
hashed prior-label manifest, is skipped. The population's strata go to stderr, so the omitted ones are
reported beside the round.
usage: uv run python sample_round6.py prior-labels     (writes round6/prior-labels.json)
       uv run python sample_round6.py > <data>/round6/cases.jsonl 2> <data>/round6/sample.log
"""

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from jev_navigator.index.code_index import CodeIndex

from comment_tool.claims.list_claims import list_claim_for
from comment_tool.cli.classify import changed_lines, is_touched
from comment_tool.config import DATA
from comment_tool.core.comment_discovery import code_decision, found_comments
from research.rounds.registered_rounds import ROUNDS
from research.rounds.sample_round4 import REPOSITORIES, packet

ROUND = DATA / "round6"
SALT = "round6-v1"
PER_PULL_REQUEST = 5
PULL_REQUESTS = (
    ("heedvane", 2862, "1ac2ce22c26e57e7f42993a73178bceb2795f511"),
    ("heedvane", 2858, "7fe48e61a25aea0f553929e76b11f73d4abe7f3e"),
    ("heedvane", 2857, "eec275da221b2d9991f4c1cc1c25fa0c4dd47cf2"),
    ("analysis-engine", 1311, "d40c3f5a0c524abb7a4edb938a743923e206a341"),
    ("analysis-engine", 1303, "b22367e737ff15944a307cdd79efeca488105149"),
    ("analysis-engine", 1294, "e9895ace2dd15772eb0dc719ca6f7f7422e88e31"),
)
CASE_PREFIXES = {"heedvane": "hv-k", "analysis-engine": "en-k"}
"""Round 6 ids; earlier rounds used the letters d to h and r."""
PRIOR_LABELLED = (
    ("cases.jsonl", "sol-labels.jsonl"), ("round2/cases.jsonl", "round2/sol-labels.jsonl"),
    ("round3/cases.jsonl", "round3/sol-labels.jsonl"),
    ("round3-nav-described/cases.jsonl", "round3-nav-described/sol-labels.fresh.jsonl"),
    ("round3-nav-frozen/cases.jsonl", "round3-nav-frozen/sol-labels.jsonl"),
    ("round3-nav-window/cases.jsonl", "round3-nav-window/sol-labels.jsonl"),
    ("round4/cases.jsonl", "round4/sol-labels.jsonl"), ("docs/cases.jsonl", "docs/sol-labels.jsonl"),
    ("docs2/cases.jsonl", "docs2/sol-labels.jsonl"), ("list-round/cases.jsonl", "list-round/sol-labels.jsonl"),
    ("stop-labels/packets.jsonl", "stop-labels/labels.jsonl"),
)
"""Every earlier round with Sol labels: its packets and its labels, relative to the data folder."""


class SampleError(RuntimeError):
    """The draw does not have the registered shape."""


def rank(*parts) -> str:
    return hashlib.sha256(":".join([SALT, *map(str, parts)]).encode()).hexdigest()


def write_prior_labels() -> None:
    sets = [{"cases": cases, "labels": labels, "cases_sha256": _sha256(DATA / cases), "labels_sha256": _sha256(DATA / labels)}
            for cases, labels in PRIOR_LABELLED]
    (ROUND / "prior-labels.json").write_text(json.dumps({"sets": sets}, indent=1) + "\n")


def labelled_before() -> set[tuple[str, str]]:
    """(file, comment text) of every comment in the prior-label manifest, after checking its hashes."""
    seen = set()
    for entry in json.loads((ROUND / "prior-labels.json").read_text())["sets"]:
        for kind in ("cases", "labels"):
            if _sha256(DATA / entry[kind]) != entry[f"{kind}_sha256"]:
                raise SampleError(f"{entry[kind]} changed since the prior-label manifest was written")
        seen |= {_labelled_comment(row) for row in map(json.loads, (DATA / entry["cases"]).read_text().splitlines())}
    return seen


def _labelled_comment(row: dict) -> tuple[str, str]:
    if "search_id" in row:
        return row["search_id"].rsplit(":", 1)[0], row["comment"]
    return row["provenance"]["path"], row["state"]["comment"]["text"]


def touched_comments(repository: Path, merge: str) -> list:
    touched = changed_lines(repository, f"{merge}^1", merge)
    index = CodeIndex.at_commit(repository, merge, sorted(touched))
    return [f for f in found_comments(index, sorted(touched)) if is_touched(index, f, touched)]


def round_packet(name: str, pull_request: int, case_id: str, merge: str, file: str, first_line: int) -> dict:
    """The packet, built from an index of the comment's own file, as the runner rebuilds it."""
    index = CodeIndex.at_commit(REPOSITORIES[name][0], merge, [file])
    found = next(f for f in found_comments(index, [file]) if f.case.first_line == first_line)
    if list_claim_for(index, found.case) is not None:
        raise SampleError(f"{case_id} carries a list claim; list claims are not part of round 6")
    return {**packet(name, index.commit, case_id, index, found), "kind": found.kind, "pull_request": pull_request}


def rebuilt_case(raw: dict) -> dict:
    """The full case record rebuilt from git objects, for `frozen_round.verify`."""
    provenance = raw["provenance"]
    return round_packet(provenance["repository"], raw["pull_request"], raw["case_id"], provenance["commit"],
                        provenance["path"], provenance["comment_lines"][0])


def strata(name: str, pull_request: int, found: list) -> str:
    by_code = [f for f in found if code_decision(f) is not None]
    facts = Counter(fact for f in found for fact in ("dates", "ticket_refs", "unowned_todo") if f.case.facts[fact])
    return (f"{name} #{pull_request}: {len(found)} touched; kinds {dict(Counter(f.kind for f in found))}; "
            f"decided by code {len(by_code)}; date, ticket or TODO facts {dict(facts)}")


def draw() -> list[dict]:
    seen, cases, numbers = labelled_before(), [], dict.fromkeys(CASE_PREFIXES, 0)
    for name, pull_request, merge in PULL_REQUESTS:
        found = touched_comments(REPOSITORIES[name][0], merge)
        print(strata(name, pull_request, found), file=sys.stderr)
        fresh = [f for f in found if code_decision(f) is None and (f.case.file, f.case.text) not in seen]
        picked = sorted(fresh, key=lambda f: rank(name, pull_request, f.case.file, f.case.first_line))[:PER_PULL_REQUEST]
        for f in picked:
            numbers[name] += 1
            case_id = f"{CASE_PREFIXES[name]}{numbers[name]:02d}"
            cases.append(round_packet(name, pull_request, case_id, merge, f.case.file, f.case.first_line))
    require_registered_draw(cases)
    return cases


def require_registered_draw(cases: list[dict]) -> None:
    """Exactly 5 fresh comments from each registered pull request, in its registered repository and merge
    commit, under exactly the registered case ids, with no comment twice."""
    drawn = Counter((c["provenance"]["repository"], c["pull_request"], c["provenance"]["commit"]) for c in cases)
    comments = {(c["provenance"]["commit"], c["provenance"]["path"], c["provenance"]["comment_lines"][0]) for c in cases}
    registered = dict.fromkeys(PULL_REQUESTS, PER_PULL_REQUEST)
    if dict(drawn) != registered or [c["case_id"] for c in cases] != list(ROUNDS["round6"].case_ids) or len(comments) != len(cases):
        raise SampleError(f"the draw is not the registered 6 pull requests x 5 fresh comments: {dict(drawn)}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    if sys.argv[1:] == ["prior-labels"]:
        write_prior_labels()
        return
    for case in draw():
        print(json.dumps(case))


if __name__ == "__main__":
    main()
