import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Effect, Schema } from "effect";
import { evaluateCase } from "./policy.js";
import type { CodeFacts } from "./types.js";

const here = dirname(fileURLToPath(import.meta.url));
export const REPO_ROOT = resolve(here, "../..");

/** The observation the Python adapter prints: the served answer, bound to the frozen request. */
export const ObservationSchema = Schema.Struct({
  mode: Schema.Literals(["live"]),
  journal: Schema.String,
  request: Schema.Struct({
    request_sha256: Schema.String,
    provider_request_sha256: Schema.String,
    exchange_id: Schema.String,
    requested_model: Schema.String,
    question_ids: Schema.Array(Schema.String),
    noul_question_ids: Schema.Array(Schema.String),
  }),
  artifacts: Schema.Struct({ journal: Schema.String, answers: Schema.String }),
  response: Schema.Struct({
    served_model: Schema.String,
    input_tokens: Schema.Number,
    request_sha256: Schema.String,
  }),
  probabilities: Schema.Record(Schema.String, Schema.Number),
});
export type Observation = Schema.Schema.Type<typeof ObservationSchema>;

/** The code-owned facts come from the frozen case row, never from the model. */
const CaseRowSchema = Schema.Struct({
  case_id: Schema.String,
  provenance: Schema.Struct({
    repository: Schema.String,
    commit: Schema.String,
  }),
  code_facts: Schema.Struct({
    doc_comment: Schema.Boolean,
    dates: Schema.Array(Schema.String),
    ticket_refs: Schema.Array(Schema.String),
    unowned_todo: Schema.Boolean,
  }),
});

const decodeObservation = Schema.decodeUnknownSync(ObservationSchema);
const decodeCaseRow = Schema.decodeUnknownSync(CaseRowSchema);

export const loadCaseFacts = async (
  casesPath: string,
  caseId: string,
): Promise<{ facts: CodeFacts; sourceRef: string }> => {
  const rows = (await readFile(casesPath, "utf8")).split("\n").filter(Boolean);
  for (const [index, line] of rows.entries()) {
    const row = decodeCaseRow(JSON.parse(line) as unknown);
    if (row.case_id !== caseId) continue;
    return {
      facts: {
        docComment: row.code_facts.doc_comment,
        dates: row.code_facts.dates,
        ticketRefs: row.code_facts.ticket_refs,
        unownedTodo: row.code_facts.unowned_todo,
      },
      sourceRef: `${row.provenance.repository}@${row.provenance.commit}`,
    };
  }
  throw new Error(`no case ${caseId} in ${casesPath} (${rows.length} rows read)`);
};

export interface AdapterOptions {
  readonly journal: string;
  readonly requestId: string;
  readonly out: string;
  readonly endpoint?: string;
}

/** Runs the adapter executable in this repository; live mode is explicit on its command line. */
export const runAdapter = (options: AdapterOptions): { observation: Observation; adapterMs: number } => {
  const args = [
    "run", "--no-sync", "python", resolve(REPO_ROOT, "discern_live_pilot.py"),
    "live", "--journal", options.journal, "--request-id", options.requestId, "--out", options.out,
  ];
  if (options.endpoint !== undefined) args.push("--endpoint", options.endpoint);
  const started = Date.now();
  const result = spawnSync("uv", args, { cwd: REPO_ROOT, encoding: "utf8", env: process.env });
  const adapterMs = Date.now() - started;
  if (result.error !== undefined) throw result.error;
  if (result.status !== 0) {
    throw new Error(`the adapter failed with status ${result.status}: ${result.stderr.trim()}`);
  }
  return { observation: decodeObservation(JSON.parse(result.stdout) as unknown), adapterMs };
};

export interface PilotOptions extends AdapterOptions {
  readonly caseId: string;
  readonly casesPath: string;
  readonly receipt: string;
}

export interface PilotReceipt {
  readonly pilot: string;
  readonly written_at: string;
  readonly source: {
    readonly spike: string;
    readonly case_id: string;
    readonly source_ref: string;
    readonly evaluator: string;
  };
  readonly original_request: {
    readonly request_sha256: string;
    readonly provider_request_sha256: string;
    readonly exchange_id: string;
    readonly requested_model: string;
    readonly original_journal: string;
    readonly question_ids: ReadonlyArray<string>;
  };
  readonly artifacts: {
    readonly live_journal: Awaited<ReturnType<typeof hashedFile>>;
    readonly live_answers: Awaited<ReturnType<typeof hashedFile>>;
  };
  readonly served_model: string;
  readonly usage: { readonly input_tokens: number };
  readonly probabilities: Readonly<Record<string, number>>;
  readonly outcome: { readonly action: string; readonly escalated: boolean; readonly reasons: ReadonlyArray<string> };
  readonly timings: { readonly adapter_ms: number; readonly evaluate_ms: number };
}

const hashedFile = async (path: string): Promise<{ path: string; sha256: string }> => ({
  path,
  sha256: createHash("sha256").update(await readFile(path)).digest("hex"),
});

/** One frozen request, asked live once through the journal, reduced by the original evaluator. */
export const runPilot = async (options: PilotOptions): Promise<PilotReceipt> => {
  const { facts, sourceRef } = await loadCaseFacts(options.casesPath, options.caseId);
  const { observation, adapterMs } = runAdapter(options);
  const evaluateStarted = Date.now();
  const outcome = await Effect.runPromise(evaluateCase(
    { caseId: options.caseId, ruleVersion: "current", facts },
    observation.probabilities,
  ));
  const evaluateMs = Date.now() - evaluateStarted;
  const receipt: PilotReceipt = {
    pilot: "discern-live-rule-a",
    written_at: new Date().toISOString(),
    source: {
      spike: "b38b2c88b25f33f4d93f387d01ca29a66b63765a",
      case_id: options.caseId,
      source_ref: sourceRef,
      evaluator: "ts/src/policy.ts evaluateCase",
    },
    original_request: {
      request_sha256: observation.request.request_sha256,
      provider_request_sha256: observation.request.provider_request_sha256,
      exchange_id: observation.request.exchange_id,
      requested_model: observation.request.requested_model,
      original_journal: observation.journal,
      question_ids: observation.request.question_ids,
    },
    artifacts: {
      live_journal: await hashedFile(observation.artifacts.journal),
      live_answers: await hashedFile(observation.artifacts.answers),
    },
    served_model: observation.response.served_model,
    usage: { input_tokens: observation.response.input_tokens },
    probabilities: observation.probabilities,
    outcome,
    timings: { adapter_ms: adapterMs, evaluate_ms: evaluateMs },
  };
  await mkdir(dirname(options.receipt), { recursive: true });
  await writeFile(options.receipt, `${JSON.stringify(receipt, null, 2)}\n`);
  return receipt;
};

const flag = (argv: ReadonlyArray<string>, name: string): string => {
  const index = argv.indexOf(name);
  if (index < 0 || index + 1 >= argv.length) throw new Error(`missing ${name} <value>`);
  return argv[index + 1]!;
};

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2);
  const options = {
    journal: flag(argv, "--journal"),
    requestId: flag(argv, "--request-id"),
    out: flag(argv, "--out"),
    caseId: flag(argv, "--case-id"),
    casesPath: flag(argv, "--cases"),
    receipt: flag(argv, "--receipt"),
  };
  const receipt = await runPilot(argv.includes("--endpoint")
    ? { ...options, endpoint: flag(argv, "--endpoint") }
    : options);
  console.log(`receipt ${receipt.artifacts.live_journal.path}: ${receipt.outcome.action}, `
    + `escalated ${receipt.outcome.escalated}`);
}
