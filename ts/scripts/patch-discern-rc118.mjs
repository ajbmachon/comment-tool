import { readFile, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const packageRoot = fileURLToPath(new URL("../node_modules/@doeixd/discern/dist/", import.meta.url));

const patches = new Map([
  ["index.js", [
    ['import * as AiError from "effect/unstable/ai/AiError";\nimport * as Decision from "effect/unstable/ai/Decision";\nimport * as DecisionModel from "effect/unstable/ai/DecisionModel";', 'import { AiError, Decision, DecisionModel } from "effect/ai";'],
    ['evaluate: (input, answers) => andResult(patterns.map((pattern) => pattern.evaluate(input, answers))),', 'evaluate: (input, answers) => andResult(patterns.map((pattern) => pattern.preview(input).resolved ?? pattern.evaluate(input, answers))),'],
    ['evaluate: (input, answers) => orResult(patterns.map((pattern) => pattern.evaluate(input, answers))),', 'evaluate: (input, answers) => orResult(patterns.map((pattern) => pattern.preview(input).resolved ?? pattern.evaluate(input, answers))),'],
  ]],
  ["model.js", [
    ['import * as AiError from "effect/unstable/ai/AiError";\nimport * as Decision from "effect/unstable/ai/Decision";\nimport * as DecisionModel from "effect/unstable/ai/DecisionModel";', 'import { AiError, Decision, DecisionModel } from "effect/ai";'],
  ]],
  ["index.d.ts", [
    ['import * as AiError from "effect/unstable/ai/AiError";\nimport * as Decision from "effect/unstable/ai/Decision";\nimport * as DecisionModel from "effect/unstable/ai/DecisionModel";', 'import { AiError, Decision, DecisionModel } from "effect/ai";'],
  ]],
  ["model.d.ts", [
    ['import * as AiError from "effect/unstable/ai/AiError";\nimport * as DecisionModel from "effect/unstable/ai/DecisionModel";', 'import { AiError, DecisionModel } from "effect/ai";'],
  ]],
  ["procedure.d.ts", [
    ['import type * as AiError from "effect/unstable/ai/AiError";\nimport type * as DecisionModel from "effect/unstable/ai/DecisionModel";', 'import type { AiError, DecisionModel } from "effect/ai";'],
  ]],
  ["internal/hash.d.ts", [
    ['import type * as Decision from "effect/unstable/ai/Decision";', 'import type { Decision } from "effect/ai";'],
  ]],
]);

for (const [relativePath, replacements] of patches) {
  const path = `${packageRoot}${relativePath}`;
  let source = await readFile(path, "utf8");
  for (const [before, after] of replacements) {
    if (source.includes(before)) {
      source = source.replace(before, after);
    } else if (!source.includes(after)) {
      throw new Error(`Discern compatibility patch no longer applies to ${relativePath}`);
    }
  }
  await writeFile(path, source);
}
