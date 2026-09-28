import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { pythonReference } from "./python-reference.js";
import { replayAll } from "./runner.js";
import type { ReplayRow } from "./types.js";

interface Mismatch {
  readonly round: string;
  readonly caseId: string;
  readonly typescript: ReplayRow | null;
  readonly python: ReplayRow | null;
  readonly why: ReadonlyArray<string>;
}

const here = dirname(fileURLToPath(import.meta.url));
const outputDirectory = resolve(here, "../output");

const keyOf = (row: ReplayRow): string => `${row.round}\u0000${row.caseId}`;

const mismatchesBetween = (
  actual: ReadonlyArray<ReplayRow>,
  expected: ReadonlyArray<ReplayRow>,
): ReadonlyArray<Mismatch> => {
  const actualByKey = new Map(actual.map((row) => [keyOf(row), row]));
  const expectedByKey = new Map(expected.map((row) => [keyOf(row), row]));
  const keys = new Set([...actualByKey.keys(), ...expectedByKey.keys()]);
  const mismatches: Array<Mismatch> = [];
  for (const key of [...keys].sort()) {
    const typescript = actualByKey.get(key) ?? null;
    const python = expectedByKey.get(key) ?? null;
    const why: Array<string> = [];
    if (typescript === null) why.push("missing TypeScript row");
    if (python === null) why.push("missing Python row");
    if (typescript !== null && python !== null) {
      if (typescript.action !== python.action) why.push(`action ${typescript.action} != ${python.action}`);
      if (typescript.escalated !== python.escalated) why.push(`escalated ${typescript.escalated} != ${python.escalated}`);
      if (JSON.stringify(typescript.reasons) !== JSON.stringify(python.reasons)) {
        why.push(`reasons ${JSON.stringify(typescript.reasons)} != ${JSON.stringify(python.reasons)}`);
      }
    }
    if (why.length > 0) {
      const [round, caseId] = key.split("\u0000");
      if (round === undefined || caseId === undefined) throw new Error(`Invalid comparison key ${key}`);
      mismatches.push({ round, caseId, typescript, python, why });
    }
  }
  return mismatches;
};

const summaryOf = (rows: ReadonlyArray<ReplayRow>, mismatches: ReadonlyArray<Mismatch>) => ({
  total: rows.length,
  decided: rows.filter((row) => !row.escalated).length,
  escalated: rows.filter((row) => row.escalated).length,
  mismatches: mismatches.length,
});

const typescript = await replayAll();
const python = pythonReference();
const mismatches = mismatchesBetween(typescript, python);
const summary = summaryOf(typescript, mismatches);
await mkdir(outputDirectory, { recursive: true });
await writeFile(resolve(outputDirectory, "rule-a-results.jsonl"), `${typescript.map((row) => JSON.stringify(row)).join("\n")}\n`);
await writeFile(resolve(outputDirectory, "python-reference.jsonl"), `${python.map((row) => JSON.stringify(row)).join("\n")}\n`);
await writeFile(resolve(outputDirectory, "comparison.json"), `${JSON.stringify({ summary, mismatches }, null, 2)}\n`);
console.log(JSON.stringify({ summary, mismatches }, null, 2));
if (summary.total !== 120 || summary.decided !== 93 || summary.escalated !== 27 || mismatches.length > 0) {
  process.exitCode = 1;
}
