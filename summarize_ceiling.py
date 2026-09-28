"""Summarise the replayed history curves: where the stop question's answer stops changing.

For each replayed search: the stop probability at each history size, the token size, whether the
search itself judged an opened place to be the target, and the first size at which the stop
question says yes (0.8 or more, the library's yes bar). Nothing here is labelled, so the curve shows
where more history stops changing the answer, not whether the answer is right.
usage: python3 summarize_ceiling.py
"""

import json
from pathlib import Path

from ceiling_lib_sweep import searched_more_than_once

HERE = Path(__file__).resolve().parent
YES_AT = 0.8


def curves() -> list[dict]:
    """The replayed curves, without comments searched at two locations, whose places were merged."""
    ambiguous = searched_more_than_once()
    rows = [json.loads(line) for line in (HERE / "ceiling" / "curves.jsonl").read_text().splitlines()]
    return [row for row in rows if row["comment"] not in ambiguous]


def first_yes(points: list[dict]) -> int | None:
    return next((point["steps"] for point in points if point["probability"] >= YES_AT), None)


def moves_after(curves_: list[dict], size: int) -> list[float]:
    """How far the stop probability moved when a history of `size` steps grew by one."""
    return [abs(c["points"][size]["probability"] - c["points"][size - 1]["probability"])
            for c in curves_ if len(c["points"]) > size]


def main() -> None:
    all_curves = curves()
    print(f"{len(all_curves)} searches replayed, {sum(len(c['points']) for c in all_curves)} history sizes asked")
    for c in all_curves:
        path = " ".join(f"{p['probability']:.2f}" for p in c["points"])
        tokens = c["points"][-1]["tokens"]
        found_steps = [n + 1 for n, decision in enumerate(c["found_at_step"]) if decision == "found"]
        print(f"  steps {len(c['points'])}, tokens up to {tokens}, search found at {found_steps or 'none'}, "
              f"stop yes first at {first_yes(c['points'])}: {path}  | {c['comment'][:60]!r}")
    for size in range(1, max(len(c["points"]) for c in all_curves)):
        moves = moves_after(all_curves, size)
        if moves:
            print(f"growing from {size} to {size + 1} steps: {len(moves)} searches, mean move {sum(moves) / len(moves):.2f}, largest {max(moves):.2f}")


if __name__ == "__main__":
    main()
