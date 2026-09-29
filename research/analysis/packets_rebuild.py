"""Check, with no model call, that the current library rebuilds every Sol-labelled packet byte for byte.

A Sol label is valid only for its exact packet, so each re-pin must rebuild the labelled
packets from git objects and compare their JSON bytes with the stored ones.
usage: uv run python packets_rebuild.py
"""

import json
import sys
from pathlib import Path

from comment_tool.config import DATA
from comment_tool.core.comment_review import MEASURED_CONTEXT, comment_state
from research.rounds.run_round4 import case_of, index_of

LABELLED = tuple(DATA / name / "cases.jsonl" for name in ("round3-nav-described", "round4", "docs", "docs2", "round6"))
"""The packets the current Sol labels were given: round 3's fresh labels, round 4's, both doc rounds' and round 6's."""


def packet_bytes(state: dict) -> bytes:
    return json.dumps(state).encode()


def rebuilt(raw: dict) -> dict:
    case = case_of(raw)
    return comment_state(case, *MEASURED_CONTEXT(index_of(raw), case))


def differing(path: Path) -> tuple[int, list[str]]:
    raws = [json.loads(line) for line in path.read_text().splitlines()]
    return len(raws), [raw["case_id"] for raw in raws if packet_bytes(rebuilt(raw)) != packet_bytes(raw["state"])]


def main() -> None:
    failed = False
    for path in LABELLED:
        total, different = differing(path)
        print(f"{path.parent.name}: {total - len(different)} of {total} packets byte-identical; different: {different}")
        failed = failed or bool(different)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
