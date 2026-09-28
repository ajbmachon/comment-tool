"""Score the search's per-place check and the history stop question against blind Sol place labels.

Per place: does the search's own check (`contains_target`, yes at 0.8 or more, no at 0.2 or less)
agree with Sol's label? Per history size k: the stop question should say yes exactly when one of
the first k fetched places holds what the comment is about. Every place also records whether Sol
found the target already in the code shown with the comment, and whether the place overlaps the
shown code's lines, to see whether an eager yes comes from code the comment was already shown with.
usage: python3 score_stop.py
"""

import json
from collections import Counter
from pathlib import Path

from data_root import DATA

LABELS = DATA / "stop-labels"
YES_AT, NO_AT = 0.8, 0.2
SEARCH_PREFIX = "the code this comment describes: "
STORES = {"lib": DATA / "pass" / "lib-a3bde2aa-rebuilt", "round4": DATA / "round4"}


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def band(probability: float) -> str:
    return "yes" if probability >= YES_AT else "no" if probability <= NO_AT else "unsure"


def place_checks(store: list[dict], comment: str) -> list[float]:
    opened = sorted((r for r in store if r["request"]["state"].get("target", {}).get("description") == SEARCH_PREFIX + comment),
                    key=lambda r: r["recorded_at"])
    return [next(a["noul"] for qid, a in r["answers"].items() if qid.startswith("contains_target")) for r in opened]


def shown_lines(search_id: str) -> tuple[str, int, int] | None:
    """The file and lines of the code shown after the comment, from the row that escalated."""
    if search_id.startswith("round4/"):
        case = next(c for c in records(DATA / "round4" / "cases.jsonl") if c["case_id"] == search_id.split("/")[1])
        first, last = case["provenance"]["code_after_lines"]
        return case["provenance"]["path"], first, last
    for path in (STORES["lib"]).glob("apps-*.jsonl"):
        for row in records(path):
            if row["location"] == search_id:
                source = row.get("first_answer", row)["evidence"]["after_comment"]
                return source["file"], *source["lines"]
    return None


def overlaps(place_at: str, shown: tuple[str, int, int] | None) -> bool:
    file, lines = place_at.rsplit(":", 1)
    first, last = map(int, lines.split("-"))
    return shown is not None and file == shown[0] and first <= shown[2] and shown[1] <= last


def stop_curve(search_id: str, comment: str) -> list[float]:
    if search_id.startswith("round4/"):
        row = next(r for r in records(DATA / "round4" / "pass.jsonl") if r["case_id"] == search_id.split("/")[1])
        return [row["search"]["stop_question"]["probability"]]
    curve = next(c for c in records(DATA / "ceiling" / "curves.jsonl") if c["comment"] == comment)
    return [point["probability"] for point in curve["points"]]


def main() -> None:
    packets = {p["search_id"]: p for p in records(LABELS / "packets.jsonl")}
    labels = {r["search_id"]: r["verdict"] for r in records(LABELS / "labels.jsonl") if "verdict" in r}
    place_rows, stop_rows = [], []
    for search_id, packet in packets.items():
        verdict = labels[search_id]
        store = records((STORES["round4"] if search_id.startswith("round4/") else STORES["lib"]) / "answers.jsonl")
        checks = place_checks(store, packet["comment"])
        shown = shown_lines(search_id)
        shown_label = verdict["shown"]["label"]
        sol = [verdict["places"][place["id"]]["label"] for place in packet["places"]]
        for place, check, label in zip(packet["places"], checks, sol, strict=True):
            place_rows.append({"search": search_id, "place": place["at"], "check": check, "band": band(check), "sol": label,
                               "overlaps_shown": overlaps(place["at"], shown), "shown_has_target": shown_label})
        for size, probability in enumerate(stop_curve(search_id, packet["comment"]), 1):
            truth = "true" if "true" in sol[:size] else "ambiguous" if "ambiguous" in sol[:size] else "false"
            stop_rows.append({"search": search_id, "size": size, "stop": probability, "band": band(probability),
                              "truth": truth, "shown_has_target": shown_label})
    (LABELS / "scored-places.jsonl").write_text("".join(json.dumps(r) + "\n" for r in place_rows))
    (LABELS / "scored-stops.jsonl").write_text("".join(json.dumps(r) + "\n" for r in stop_rows))
    print(f"{len(packets)} searches, {len(place_rows)} places, {len(stop_rows)} stop answers")
    print("Sol place labels:", dict(Counter(r["sol"] for r in place_rows)),
          "; shown code already holds the target:", dict(Counter(labels[s]["shown"]["label"] for s in packets)))
    print("Per-place check band against Sol:", dict(Counter((r["band"], r["sol"]) for r in place_rows)))
    print("Stop question band against 'a fetched place so far holds it':", dict(Counter((r["band"], r["truth"]) for r in stop_rows)))
    wrong_yes = [r for r in stop_rows if r["band"] == "yes" and r["truth"] == "false"]
    print(f"Stop yes while no fetched place holds it: {len(wrong_yes)}; of those, Sol says the shown code already holds it:",
          dict(Counter(r["shown_has_target"] for r in wrong_yes)))
    first_places = [r for r in place_rows if r["place"] == packets[r["search"]]["places"][0]["at"]]
    print("First opened place overlaps the shown code:", dict(Counter(r["overlaps_shown"] for r in first_places)),
          "; its Sol label:", dict(Counter(r["sol"] for r in first_places)))


if __name__ == "__main__":
    main()
