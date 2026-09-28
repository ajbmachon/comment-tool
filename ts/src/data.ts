import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import type { CodeFacts, CommentCase, RuleVersion } from "./types.js";

export const DEFAULT_DATA_ROOT =
  "/Users/andremachon/.claude/handoffs/effect-2026-09-25/comment-tool";

type JsonObject = Record<string, unknown>;

const isObject = (value: unknown): value is JsonObject =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const object = (value: unknown, name: string): JsonObject => {
  if (!isObject(value)) throw new Error(`${name} must be an object`);
  return value;
};

const string = (value: unknown, name: string): string => {
  if (typeof value !== "string") throw new Error(`${name} must be a string`);
  return value;
};

const number = (value: unknown, name: string): number => {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new Error(`${name} must be a finite number`);
  return value;
};

const boolean = (value: unknown, name: string): boolean => {
  if (typeof value !== "boolean") throw new Error(`${name} must be a boolean`);
  return value;
};

const strings = (value: unknown, name: string): ReadonlyArray<string> => {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`${name} must be an array of strings`);
  }
  return value;
};

const parseJson = (source: string, name: string): unknown => {
  try {
    return JSON.parse(source);
  } catch (error) {
    throw new Error(`Invalid JSON in ${name}`, { cause: error });
  }
};

const jsonLines = async (path: string): Promise<ReadonlyArray<JsonObject>> => {
  const source = await readFile(path, "utf8");
  return source.split("\n").filter(Boolean).map((line, index) =>
    object(parseJson(line, `${path}:${index + 1}`), `${path}:${index + 1}`));
};

const rowsByCase = async (path: string): Promise<ReadonlyMap<string, JsonObject>> => {
  const rows = await jsonLines(path);
  return new Map(rows.map((row) => [string(row.case_id, `${path} case_id`), row]));
};

const codeFacts = (row: JsonObject, context: string): CodeFacts => {
  const raw = object(row.code_facts, `${context}.code_facts`);
  return {
    docComment: raw.doc_comment === undefined ? false : boolean(raw.doc_comment, `${context}.doc_comment`),
    dates: strings(raw.dates, `${context}.dates`),
    ticketRefs: strings(raw.ticket_refs, `${context}.ticket_refs`),
    unownedTodo: boolean(raw.unowned_todo, `${context}.unowned_todo`),
  };
};

const probabilitiesFromAnswers = (answers: JsonObject, context: string): Readonly<Record<string, number>> => {
  const probabilities: Record<string, number> = {};
  for (const [versionedId, rawAnswer] of Object.entries(answers)) {
    const answer = object(rawAnswer, `${context}.${versionedId}`);
    if (answer.type !== "noul") continue;
    const questionId = versionedId.split("@")[0];
    if (questionId === undefined) throw new Error(`Empty question id in ${context}`);
    probabilities[questionId] = number(answer.noul, `${context}.${versionedId}.noul`);
  }
  return probabilities;
};

const answerStore = async (path: string): Promise<ReadonlyMap<string, Readonly<Record<string, number>>>> => {
  const rows = await jsonLines(path);
  return new Map(rows.map((row, index) => [
    string(row.request_sha256, `${path}:${index + 1}.request_sha256`),
    probabilitiesFromAnswers(object(row.answers, `${path}:${index + 1}.answers`), `${path}:${index + 1}.answers`),
  ]));
};

const storedAnswer = (
  store: ReadonlyMap<string, Readonly<Record<string, number>>>,
  requestSha256: string,
  context: string,
): Readonly<Record<string, number>> => {
  const found = store.get(requestSha256);
  if (found === undefined) throw new Error(`No stored answer for ${context} request ${requestSha256}`);
  return found;
};

const mergedProbabilities = (
  base: Readonly<Record<string, number>>,
  replacement: Readonly<Record<string, number>> | undefined,
): Readonly<Record<string, number>> => replacement === undefined ? base : { ...base, ...replacement };

const loadRound = async (
  dataRoot: string,
  round: string,
  folder: string,
  ruleVersion: RuleVersion,
): Promise<ReadonlyArray<CommentCase>> => {
  const base = join(dataRoot, folder);
  const cases = await rowsByCase(join(base, "cases.jsonl"));
  const passes = await rowsByCase(join(base, "pass.jsonl"));
  const answers = await answerStore(join(base, "answers.jsonl"));
  const result: Array<CommentCase> = [];
  for (const [caseId, pass] of passes) {
    const first = pass.first_answer === undefined ? pass : object(pass.first_answer, `${folder}/${caseId}.first_answer`);
    const request = string(first.request_sha256, `${folder}/${caseId}.request_sha256`);
    const caseRow = cases.get(caseId);
    if (caseRow === undefined) throw new Error(`No case facts for ${folder}/${caseId}`);
    result.push({
      round,
      caseId,
      ruleVersion,
      facts: codeFacts(caseRow, `${folder}/${caseId}`),
      probabilities: storedAnswer(answers, request, `${folder}/${caseId}`),
    });
  }
  return result;
};

const loadRound3 = async (dataRoot: string): Promise<ReadonlyArray<CommentCase>> => {
  const folder = join(dataRoot, "round3-nav-described");
  const caseRows = await jsonLines(join(dataRoot, "round3", "cases.jsonl"));
  const passRows = await jsonLines(join(folder, "pass.jsonl"));
  if (caseRows.length !== passRows.length) throw new Error("Round3 cases and pass rows have different lengths");
  const cases = new Map<string, JsonObject>();
  const passes = new Map<string, JsonObject>();
  for (const [index, caseRow] of caseRows.entries()) {
    const pass = passRows[index];
    if (pass === undefined) throw new Error(`Missing round3 pass row ${index + 1}`);
    const caseId = string(caseRow.case_id, `round3 case ${index + 1}.case_id`);
    const provenance = object(caseRow.provenance, `round3/${caseId}.provenance`);
    const commentLines = provenance.comment_lines;
    if (!Array.isArray(commentLines) || typeof commentLines[0] !== "number") {
      throw new Error(`round3/${caseId}.comment_lines must start with a number`);
    }
    const expectedLocation = `${string(provenance.path, `round3/${caseId}.path`)}:${commentLines[0]}`;
    if (string(pass.location, `round3/${caseId}.location`) !== expectedLocation) {
      throw new Error(`Round3 pass order differs at ${caseId}`);
    }
    cases.set(caseId, caseRow);
    passes.set(caseId, pass);
  }
  const answers = await answerStore(join(folder, "answers.jsonl"));
  const runFiles = (await readdir(join(folder, "run"))).filter((name) => name.endsWith(".json")).sort();
  const runCaseIds = new Set<string>();
  for (const file of runFiles) {
    const run = object(parseJson(await readFile(join(folder, "run", file), "utf8"), file), file);
    runCaseIds.add(string(run.case_id, `${file}.case_id`));
  }
  const result: Array<CommentCase> = [];
  for (const caseId of [...runCaseIds].sort()) {
    const pass = passes.get(caseId);
    const caseRow = cases.get(caseId);
    if (pass === undefined || caseRow === undefined) throw new Error(`Incomplete round3 case ${caseId}`);
    const request = string(pass.request_sha256, `round3/${caseId}.request_sha256`);
    result.push({
      round: "round 3",
      caseId,
      ruleVersion: "legacy-round3",
      facts: codeFacts(caseRow, `round3/${caseId}`),
      probabilities: storedAnswer(answers, request, `round3/${caseId}`),
    });
  }
  return result;
};

const applyRound4Reasks = async (
  dataRoot: string,
  cases: ReadonlyArray<CommentCase>,
): Promise<ReadonlyArray<CommentCase>> => {
  const folder = join(dataRoot, "round4-definitions-elsewhere");
  const rows = await rowsByCase(join(folder, "rows.jsonl"));
  const answers = await answerStore(join(folder, "answers.jsonl"));
  return cases.map((entry) => {
    const row = rows.get(entry.caseId);
    if (row === undefined || row.stale_reask === undefined) return entry;
    const staleReask = object(row.stale_reask, `round4 reask/${entry.caseId}`);
    const request = string(staleReask.request_sha256, `round4 reask/${entry.caseId}.request_sha256`);
    return {
      ...entry,
      probabilities: mergedProbabilities(
        entry.probabilities,
        storedAnswer(answers, request, `round4 reask/${entry.caseId}`),
      ),
    };
  });
};

export const loadCases = async (
  dataRoot = process.env.COMMENT_TOOL_DATA ?? DEFAULT_DATA_ROOT,
): Promise<ReadonlyArray<CommentCase>> => {
  const round3 = await loadRound3(dataRoot);
  const round4 = await applyRound4Reasks(
    dataRoot,
    await loadRound(dataRoot, "round 4", "round4", "current"),
  );
  const docs = await loadRound(dataRoot, "docs 1", "docs", "current");
  const docs2 = await loadRound(dataRoot, "docs 2", "docs2", "current");
  return [...round3, ...round4, ...docs, ...docs2];
};
