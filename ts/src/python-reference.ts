import { execFileSync } from "node:child_process";
import type { ReplayRow } from "./types.js";

const COMMENT_TOOL = "/Users/andremachon/Projects/comment-tool";

const PYTHON_REFERENCE = String.raw`
import json
import per_band
import compose

def facts(folder, case_id, doc=False):
    row = per_band.rows(per_band.DATA / folder / "cases.jsonl")[case_id]
    return {"doc_comment": doc, **row["code_facts"]}

rounds = [
    ("round 3", per_band.round3(), per_band.compose_frozen, lambda cid: facts("round3", cid)),
    ("round 4", per_band.round4(), compose, lambda cid: facts("round4", cid)),
    ("docs 1", per_band.doc_round("docs 1", "docs"), compose, lambda cid: facts("docs", cid)),
    ("docs 2", per_band.doc_round("docs 2", "docs2"), compose, lambda cid: facts("docs2", cid)),
]
for round_name, entries, rule, facts_of in rounds:
    for entry in entries:
        case_facts = facts_of(entry["case"])
        reasons = rule.escalation_reasons(entry["p"], case_facts)
        print(json.dumps({
            "round": round_name,
            "caseId": entry["case"],
            "action": entry["action"],
            "escalated": bool(reasons),
            "reasons": reasons,
        }, separators=(",", ":")))
`;

const isReplayRow = (value: unknown): value is ReplayRow => {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const row = value instanceof Object ? value : undefined;
  if (row === undefined) return false;
  const values = Object.entries(row);
  const fields = new Map(values);
  return typeof fields.get("round") === "string"
    && typeof fields.get("caseId") === "string"
    && typeof fields.get("action") === "string"
    && typeof fields.get("escalated") === "boolean"
    && Array.isArray(fields.get("reasons"))
    && fields.get("reasons")?.every((reason: unknown) => typeof reason === "string") === true;
};

export const pythonReference = (): ReadonlyArray<ReplayRow> => {
  const output = execFileSync("uv", ["run", "--no-sync", "python", "-c", PYTHON_REFERENCE], {
    cwd: COMMENT_TOOL,
    encoding: "utf8",
    env: process.env,
  });
  return output.split("\n").filter(Boolean).map((line, index) => {
    const value: unknown = JSON.parse(line);
    if (!isReplayRow(value)) throw new Error(`Invalid Python reference row ${index + 1}`);
    return value;
  });
};
