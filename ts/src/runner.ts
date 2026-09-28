import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Effect } from "effect";
import { loadCases } from "./data.js";
import { evaluateCase } from "./policy.js";
import type { ReplayRow } from "./types.js";

const here = dirname(fileURLToPath(import.meta.url));
export const DEFAULT_RESULTS_PATH = resolve(here, "../output/rule-a-results.jsonl");

export const replayAll = async (): Promise<ReadonlyArray<ReplayRow>> => {
  const cases = await loadCases();
  const rows: Array<ReplayRow> = [];
  for (const entry of cases) {
    const result = await Effect.runPromise(evaluateCase({
      caseId: entry.caseId,
      ruleVersion: entry.ruleVersion,
      facts: entry.facts,
    }, entry.probabilities));
    rows.push({ round: entry.round, caseId: entry.caseId, ...result });
  }
  return rows;
};

export const writeReplay = async (path = DEFAULT_RESULTS_PATH): Promise<ReadonlyArray<ReplayRow>> => {
  const rows = await replayAll();
  await mkdir(dirname(path), { recursive: true });
  await writeFile(path, `${rows.map((row) => JSON.stringify(row)).join("\n")}\n`);
  return rows;
};

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const path = process.argv[2] === undefined ? DEFAULT_RESULTS_PATH : resolve(process.argv[2]);
  const rows = await writeReplay(path);
  const decided = rows.filter((row) => !row.escalated).length;
  console.log(`wrote ${rows.length} rows to ${path}: ${decided} decided, ${rows.length - decided} escalated`);
}
