"""Re-score round 4 with the definition fetch before "fix stale comment", on the stored first answers.

Only comments whose stored first answer says "fix stale comment" change: code fetches the definitions
behind the described code's conditions, and the three stale questions are asked once more with them
in `code.elsewhere` (journaled in <out dir>). The answer key stays the round-4 rule on Sol's labels
for the exact packet. The first run (`round4-definitions/`) pasted the definitions into the described
code and re-asked every question; the current tool asks only the stale questions.
usage: run-slot -- uv run --project <jev-navigator> --extra typesafe python rescore_definitions.py <out dir>
"""

import json
import sys
from pathlib import Path

import score_round4 as frozen
from comment_review import question_set
from journaled_client import journaled_judge
from run_round4 import ROUND4_QUESTIONS, case_of, index_of
from sweep import checked_stale


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(exist_ok=True)
    raws = frozen.rows(frozen.ROUND / "cases.jsonl")
    passes, labels = frozen.rows(frozen.ROUND / "pass.jsonl"), frozen.rows(frozen.ROUND / "sol-labels.jsonl")
    before = frozen.readouts(frozen.compose, passes, labels, {cid: case_of(raw).facts for cid, raw in raws.items()})
    questions = question_set(json.loads(ROUND4_QUESTIONS.read_text()))
    judge = journaled_judge(out, {"heedvane", "analysis-engine"})
    after, rows = dict(before), []
    for cid, raw in raws.items():
        first = frozen.first_answer(passes[cid])
        if first["action"] != "fix_stale":
            continue
        row = checked_stale(index_of(raw), judge, case_of(raw), questions, first)
        rows.append({"case_id": cid, **{k: v for k, v in row.items() if k != "state"}})
        after[cid] = {**before[cid], "a": row["action"], "escalated": "escalate" in row}
        print(cid, "before:", before[cid]["a"], "escalated" if before[cid]["escalated"] else "decided",
              "| after:", row["action"], "escalated" if "escalate" in row else "decided", row.get("escalate", {}).get("reasons", []),
              "| key:", before[cid]["key"], "| fetched:", [f"{p['file']}:{p['lines'][0]}-{p['lines'][1]}" for p in row["definitions"]["fetched"]],
              "| unresolved:", row["definitions"]["unresolved"])
    (out / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    print(frozen.summary("Round 4, frozen rule", before))
    print(frozen.summary("Round 4, definition fetch before fix stale", after))
    print(frozen.bars(after))
    print(f"Jev calls {judge.calls}")


if __name__ == "__main__":
    main()
