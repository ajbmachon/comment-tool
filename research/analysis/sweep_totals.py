"""Totals of a sweep directory per unit and action, the search outcomes of its escalations, and
which comments two sweeps of the same commit share.

usage: python3 sweep_totals.py <sweep dir> [--compare <other sweep dir>]
"""

import argparse
import json
from collections import Counter
from pathlib import Path

ACTIONS = ("keep", "rewrite", "remove", "refactor_instead", "fix_stale", "escalate")
REVIEWED_KINDS = ("block",)
"""Whole-line comments not attached to a declaration: the population the reference labels cover."""


def unit_rows(sweep: Path) -> dict[str, list[dict]]:
    return {path.stem: [json.loads(line) for line in path.read_text().splitlines()]
            for path in sorted(sweep.glob("apps-*.jsonl"))}


def outcome(row: dict) -> str:
    return "escalate" if "escalate" in row else row["action"]


def table(units: dict[str, list[dict]], keep_row=lambda row: True) -> str:
    lines = ["| Unit | Comments | " + " | ".join(ACTIONS) + " |", "|---" * (len(ACTIONS) + 2) + "|"]
    total = Counter()
    for unit, rows in units.items():
        counts = Counter(outcome(row) for row in rows if keep_row(row))
        total.update(counts)
        lines.append(f"| {unit.removeprefix('apps-web-src-lib-')} | {sum(counts.values())} | " + " | ".join(str(counts[a]) for a in ACTIONS) + " |")
    lines.append(f"| **total** | {sum(total.values())} | " + " | ".join(str(total[a]) for a in ACTIONS) + " |")
    return "\n".join(lines)


def search_summary(rows: list[dict]) -> Counter:
    return Counter((row.get("search") or {}).get("outcome", row.get("searched", "no search"))
                   for row in rows if row.get("decided_by", "").startswith(("escalated", "jev+rule after")))


def main() -> None:
    parser = argparse.ArgumentParser(description="Read sweep JSONL files and print action totals and search outcomes to stdout.")
    parser.add_argument("sweep", type=Path, help="sweep directory containing apps-*.jsonl files")
    parser.add_argument("--compare", type=Path, metavar="OTHER", help="compare comment locations with another sweep directory")
    args = parser.parse_args()
    sweep = args.sweep
    units = unit_rows(sweep)
    rows = [row for unit in units.values() for row in unit]
    print(table(units))
    if "kind" in rows[0]:
        print("\nKinds:", dict(Counter((row["kind"], row["decided_by"]) for row in rows)))
        print("\nWhole-line comments only (the labelled population):")
        print(table(units, lambda row: row["kind"] in REVIEWED_KINDS))
    print("\nSearches:", dict(search_summary(rows)))
    if args.compare is not None:
        other = [row for unit in unit_rows(args.compare).values() for row in unit]
        mine, theirs = {row["location"] for row in rows}, {row["location"] for row in other}
        print(f"\nLocations: {len(mine & theirs)} in both, {len(mine - theirs)} only here, {len(theirs - mine)} only in the other")


if __name__ == "__main__":
    main()
