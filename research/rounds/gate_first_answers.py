"""Ask the round-4 questions on the packets of comments that escalated before the three stale questions
existed, so the search gate can be replayed on them.

Round 3 and the lib sweep asked one stale question; the gate reads the three. Round 3's packets come
from its cases file, as sent. The lib sweep's come from the sweep's journal, and only from its
measured wire bytes: where a sweep journalled the prepared body alone, as the frozen lib sweep
did, there is no sent state to replay against and the replay is refused rather than aimed at a
state nobody measured. The answer store keeps only a key-sorted copy, and Jev can answer the two
differently (the library verifier, 28.09.2026: 0.83 against 0.70 on one packet). The questions are
the round-4 set, so only the state's bytes repeat the sweep's request. Before writing any row,
every new journaled request must have carried its packet's state exactly as the journal measured it
being sent, and a request that journalled no wire is refused on the same ground.
Each packet is asked once and journaled. The output rows carry the first answer, the round-4
escalation reasons and the gate's verdict.
usage: uv run python gate_first_answers.py <out dir> <lib|round3> [first N packets, for a pilot]
"""

import glob
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import comment_tool.core.compose as compose
from comment_tool.cli.sweep import COMMENT_WORKERS
from comment_tool.config import DATA
from comment_tool.core.comment_discovery import classified_facts
from comment_tool.core.comment_review import question_set
from comment_tool.journal.journaled_client import journaled_judge, sent_bodies
from research.rounds.run_round4 import ROUND4_QUESTIONS

LIB = DATA / "pass/lib-a3bde2aa-rebuilt"


class SentStateMismatchError(ValueError):
    """A new request did not carry its packet's state exactly as the sweep sent it."""


class SentStateUnavailableError(ValueError):
    """A journal captured no wire body for a request, so what that request carried is unknowable from it."""


def sent_states(journal_path: Path) -> dict[str, dict]:
    """Native request hash to captured wire state, retaining its transmitted key order.

    Missing wire capture yields no entry; native submitted intent is not sent evidence.
    """
    return {request_id: json.loads(body)["state"] for request_id, body in sent_bodies(journal_path).items()}


def request_of(row: dict) -> str:
    """The request a row's first answer came from: a re-ask names its own request separately."""
    return row.get("first_answer", row)["request_sha256"]


def lib_escalations() -> list[dict]:
    """Lib escalations with measured states; historical intent-only journals cannot prove them."""
    states = sent_states(LIB / "journal.jsonl")
    rows = [json.loads(line) for path in sorted(glob.glob(str(LIB / "apps-*.jsonl"))) for line in Path(path).read_text().splitlines()]
    if unmeasured := sorted({row["location"] for row in rows if "search" in row and request_of(row) not in states}):
        raise SentStateUnavailableError(
            f"{len(unmeasured)} lib packets, starting with {unmeasured[0]}, captured no wire body for their "
            "request: what each sweep request carried is not knowable from that journal, and replaying a "
            "packet against a state nobody can prove was sent would ask a different request than the sweep asked")
    return [{"source": "lib sweep", "location": row["location"], "comment": row["comment"], "kind": row["kind"],
             "settled_by_search": row["decided_by"] == "jev+rule after find_code",
             "state": states[request_of(row)]}
            for row in rows if "search" in row]


def round3_escalations() -> list[dict]:
    cases = {case["case_id"]: case for case in map(json.loads, (DATA / "round3-nav-described/cases.jsonl").read_text().splitlines())}
    passes = [json.loads(line) for line in (DATA / "round3-nav-described/pass.jsonl").read_text().splitlines()]
    by_location = {f"{c['provenance']['path']}:{c['provenance']['comment_lines'][0]}": c for c in cases.values()}
    return [{"source": "round 3", "location": row["location"], "comment": row["comment"], "settled_by_search": False,
             "state": by_location[row["location"]]["state"]} for row in passes if "escalate" in row]


SOURCES = {"lib": lib_escalations, "round3": round3_escalations}


def require_sent_states(journal_path: Path, rows: list[dict], packets: list[dict]) -> None:
    """Require captured wire state equal to the packet, independent of JSON serialization spacing."""
    states = sent_states(journal_path)
    for row, packet in zip(rows, packets, strict=True):
        if (state := states.get(row["request_sha256"])) is None:
            raise SentStateUnavailableError(f"{row['location']}: the journal captured no wire state for its request")
        if state != packet["state"]:
            raise SentStateMismatchError(f"{row['location']}: the request did not carry the state as sent")


def packet_facts(stored: dict) -> dict:
    """Preserve lib classifications; round-3 packets predate doc-comment discovery."""
    path = stored["location"].rsplit(":", 1)[0]
    return classified_facts(stored["comment"], path, stored.get("kind"))


def gated(judge, questions, stored: dict) -> dict:
    answers = judge.ask_all(stored["state"], checks=questions.checks, picks=questions.picks, scores=questions.scores)
    p = {name: result.probability for name, result in answers.checks.items()}
    facts = packet_facts(stored)
    return {key: stored[key] for key in ("source", "location", "settled_by_search")} | {
        "request_sha256": answers.request_sha256, "probabilities": p,
        "escalation_reasons": compose.escalation_reasons(p, facts), "searched_under_gate": compose.search_could_settle(p)}


def main() -> None:
    out, source = Path(sys.argv[1]), sys.argv[2]
    packets = SOURCES[source]()[: int(sys.argv[3]) if len(sys.argv) > 3 else None]
    out.mkdir(parents=True, exist_ok=True)
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    judge = journaled_judge(out, {"heedvane", "analysis-engine"})
    with ThreadPoolExecutor(COMMENT_WORKERS) as pool:
        rows = list(pool.map(lambda s: gated(judge, questions, s), packets))
    require_sent_states(out / "journal.jsonl", rows, packets)
    (out / "gated.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(f"asked {len(rows)}; Jev calls {judge.calls}; every request carried its state as sent")


if __name__ == "__main__":
    main()
