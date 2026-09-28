"""Compare the lib packets' first answers asked from the store's key-sorted copy (`gate-replay`) with the
same packets asked with their state exactly as sent (`gate-replay-exact`), under the current rule.

Both runs asked the round-4 questions, and each pair has the same request hash, so the only difference in
what Jev read is the key order of the state. Jev's spread on identical bytes comes from the packets the
exact run asked twice (the journal holds both exchanges); a difference beyond that spread is key order.
usage: uv run python gate_exact_compare.py
"""

import base64
import json
from collections import Counter, defaultdict

import compose
from data_root import DATA
from gate_first_answers import lib_escalations, packet_facts

MOVED = 0.10


def rows(name: str) -> dict[str, dict]:
    lines = (DATA / name / "gated.jsonl").read_text().splitlines()
    return {row["location"]: row for row in map(json.loads, lines) if row["source"] == "lib sweep"}


def comment_facts() -> dict[str, dict]:
    """Location to the comment's code facts, as the gate replay computed them."""
    return {packet["location"]: packet_facts(packet) for packet in lib_escalations()}


def verdicts(p: dict, facts: dict) -> dict:
    return {"escalates": bool(compose.escalation_reasons(p, facts)), "gate": compose.search_could_settle(p),
            "action": compose.readout_a(p, facts), "stale_check": compose.stale_check(p)}


def repeated_answers(journal_name: str) -> list[tuple[dict, dict]]:
    """The two noul answer sets of every request sent twice with identical bytes."""
    bodies, answers = defaultdict(list), defaultdict(list)
    for event in map(json.loads, (DATA / journal_name / "journal.jsonl").read_text().splitlines()):
        if event["kind"] == "request":
            bodies[event["request_id"]].append(event["request_body_base64"])
        elif event["kind"] == "response":
            raw = json.loads(base64.b64decode(event["response_body_base64"]))["answers"]
            answers[event["request_id"]].append({q.split("@")[0]: a["noul"] for q, a in raw.items() if a.get("type") == "noul"})
    return [tuple(answers[rid]) for rid, sent in bodies.items() if len(sent) == 2 and sent[0] == sent[1]]


def spread_line(pairs: list[tuple[dict, dict]]) -> str:
    gaps = [abs(first[q] - second[q]) for first, second in pairs for q in first]
    return (f"same bytes asked twice: {len(pairs)} packets, {len(gaps)} answers; largest gap {max(gaps):.2f}; "
            f"moved by {MOVED} or more: {sum(gap >= MOVED for gap in gaps)}")


def main() -> None:
    sorted_copy, exact = rows("gate-replay"), rows("gate-replay-exact")
    facts = comment_facts()
    changed, moved, totals, answered = Counter(), Counter(), Counter(), 0
    for location, new in exact.items():
        old = sorted_copy[location]
        assert old["request_sha256"] == new["request_sha256"], location
        before, after = verdicts(old["probabilities"], facts[location]), verdicts(new["probabilities"], facts[location])
        changed.update(key for key in before if before[key] != after[key])
        totals.update({"escalate, sorted copy": before["escalates"], "escalate, exact": after["escalates"],
                       "gate, sorted copy": before["gate"], "gate, exact": after["gate"]})
        moved.update(q for q, v in new["probabilities"].items() if abs(v - old["probabilities"][q]) >= MOVED)
        answered += len(new["probabilities"])
    print(f"packets {len(exact)}; verdicts that changed: {dict(changed)}")
    print(f"totals: {dict(totals)}")
    print(f"answers moved by {MOVED} or more: {sum(moved.values())} of {answered}; per question: {dict(moved.most_common())}")
    print(spread_line(repeated_answers("gate-replay-exact")))


if __name__ == "__main__":
    main()
