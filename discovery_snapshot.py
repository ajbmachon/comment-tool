"""Record, with no model call, how the tool sorts every comment of a directory at one commit: its
location, kind, the route code gives it (kept, removed, or sent to Jev) and its facts. Two
snapshots taken under different library versions show exactly which comments moved.

usage: uv run python discovery_snapshot.py <repository> <commit> <parent dir> <out.jsonl>
       python3 discovery_snapshot.py --compare <before.jsonl> <after.jsonl>
"""

import json
import sys
from collections import Counter
from pathlib import Path


def route_of(found) -> str:
    from comment_discovery import code_decision

    decided = code_decision(found)
    return "jev" if decided is None else f"code:{decided['action']}"


def snapshot(repository: Path, commit: str, parent: str, out: Path) -> None:
    from jev_navigator.index.code_index import CodeIndex

    from comment_discovery import found_comments
    from sweep import source_files, sweep_units

    with out.open("w") as rows:
        for _, files in sweep_units(source_files(repository, commit, parent), parent):
            index = CodeIndex.at_commit(repository, commit, files)
            for found in found_comments(index, files):
                case = found.case
                rows.write(json.dumps({"location": f"{case.file}:{case.first_line}", "last_line": case.last_line,
                                       "kind": found.kind, "route": route_of(found), "facts": case.facts}) + "\n")


def compare(before_path: Path, after_path: Path) -> None:
    before = {row["location"]: row for row in map(json.loads, before_path.read_text().splitlines())}
    after = {row["location"]: row for row in map(json.loads, after_path.read_text().splitlines())}
    shared = before.keys() & after.keys()
    print(f"comments: {len(before)} before, {len(after)} after; {len(shared)} at the same location")
    print(f"only before: {len(before.keys() - after.keys())}; only after: {len(after.keys() - before.keys())}")
    print("routes before:", dict(Counter(row["route"] for row in before.values())))
    print("routes after: ", dict(Counter(row["route"] for row in after.values())))
    moved = Counter((before[loc]["route"], after[loc]["route"]) for loc in shared if before[loc]["route"] != after[loc]["route"])
    print("route moves at the same location:", dict(moved))
    kinds = Counter((before[loc]["kind"], after[loc]["kind"]) for loc in shared if before[loc]["kind"] != after[loc]["kind"])
    print("kind changes at the same location:", dict(kinds))
    spans = sum(before[loc]["last_line"] != after[loc]["last_line"] for loc in shared)
    facts = sum(before[loc]["facts"] != after[loc]["facts"] for loc in shared)
    print(f"same start but different end line: {spans}; different facts: {facts}")


if __name__ == "__main__":
    if sys.argv[1] == "--compare":
        compare(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        snapshot(Path(sys.argv[1]), sys.argv[2], sys.argv[3], Path(sys.argv[4]))
