import assert from "node:assert/strict";
import { execFile, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { createServer, type IncomingMessage, type Server, type ServerResponse } from "node:http";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { test } from "node:test";
import { REPO_ROOT } from "../src/live-pilot.js";

const FROZEN_JOURNAL = "/Users/andremachon/.claude/handoffs/effect-2026-09-25/comment-tool/docs/journal.jsonl";
const FROZEN_CASES = "/Users/andremachon/.claude/handoffs/effect-2026-09-25/comment-tool/docs/cases.jsonl";
const FROZEN_REQUEST_ID = "d64f8f8787f5cf5cba55297b67213f6776941a7f9905e4f7b5441485046ff8cf";
const RUNNER = resolve(REPO_ROOT, "ts/src/live-pilot.ts");
const PILOT_ENV = { ...process.env, TYPESAFE_API_KEY: "pilot-local-dummy" };

/** The boundary proof needs the local machine's real environment; elsewhere it is skipped, not faked. */
const environmentReady = existsSync(resolve(REPO_ROOT, ".venv"))
  && existsSync("/Users/andremachon/Projects/heedvane-evals-clm-quality/experiments/provider_response_journal.py")
  && existsSync(FROZEN_JOURNAL)
  && spawnUvWorks();

function spawnUvWorks(): boolean {
  try {
    return execFileSync("uv", ["--version"], { encoding: "utf8" }).startsWith("uv");
  } catch {
    return false;
  }
}

/** The first noul question of the frozen request, by its versioned id, for the omission test. */
const firstNoulId = (): string => {
  const rowLine = readFileSync(FROZEN_JOURNAL, "utf8").split("\n")
    .find((line) => line.includes(FROZEN_REQUEST_ID));
  if (rowLine === undefined) throw new Error(`no frozen row for ${FROZEN_REQUEST_ID}`);
  const body = JSON.parse(Buffer.from(JSON.parse(rowLine).request_body_base64, "base64").toString()) as {
    questions: Record<string, { type: string }>;
  };
  const ids = Object.keys(body.questions).filter((id) => body.questions[id]?.type === "noul").sort();
  const first = ids[0];
  if (first === undefined) throw new Error("the frozen request has no noul question");
  return first;
};

type Behavior = "valid" | "missing" | "malformed";

const recordedAnswers = (): Record<string, { type: string; noul?: number }> => {
  const rows = readFileSync(FROZEN_JOURNAL, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
  const original = rows.find((row) => row.kind === "request" && row.request_id === FROZEN_REQUEST_ID);
  const response = rows.find((row) => row.kind === "response" && row.exchange_id === original.exchange_id && row.response_status === 200);
  return JSON.parse(Buffer.from(response.response_body_base64, "base64").toString("utf8")).answers;
};

/** A local substitute for the licensed provider: real HTTP over the socket, nothing else mocked. */
const startSubstitute = async (behavior: Behavior, omitId?: string):
Promise<{ url: string; received: string[]; close: () => Promise<void> }> => {
  const received: string[] = [];
  const respond = (request: IncomingMessage, response: ServerResponse): void => {
    let body = "";
    request.on("data", (chunk: Buffer) => {
      body += chunk.toString("utf8");
    });
    request.on("end", () => {
      received.push(body);
      if (behavior === "malformed") {
        response.writeHead(200, { "Content-Type": "text/html" });
        response.end("<html>not json at all</html>");
        return;
      }
      const answers: Record<string, unknown> = recordedAnswers();
      for (const [id, question] of Object.entries(JSON.parse(body).questions as Record<string, { type: string }>)) {
        if (question.type === "noul" && id !== omitId) {
          answers[id] = { type: "noul", noul: id.startsWith("states_hidden_rule") ? 0.5 : 0.1 };
        }
      }
      if (omitId !== undefined) delete answers[omitId];
      response.writeHead(200, { "Content-Type": "application/json" });
      response.end(JSON.stringify({ model: "pilot-substitute-1", usage: { input_tokens: 1234 }, answers }));
    });
  };
  const server: Server = createServer(respond);
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const address = server.address();
  if (address === null || typeof address === "string") throw new Error("no substitute port");
  return { url: `http://127.0.0.1:${address.port}`, received, close: () => new Promise((done) => server.close(() => done())) };
};

interface RunResult {
  status: number;
  stdout: string;
  stderr: string;
}

/** The real runner CLI, pointed at the substitute; a nonzero status comes back as a result, not a throw. */
const runPilotCli = (out: string, receipt: string, url: string): Promise<RunResult> => {
  const argv = [
    "--import", "tsx", RUNNER,
    "--journal", FROZEN_JOURNAL, "--request-id", FROZEN_REQUEST_ID,
    "--out", out, "--receipt", receipt, "--cases", FROZEN_CASES,
    "--case-id", "hv-d01", "--endpoint", url,
  ];
  return new Promise((done) => {
    execFile(process.execPath, argv, {
      cwd: resolve(REPO_ROOT, "ts"), encoding: "utf8", env: PILOT_ENV,
    }, (error, stdout, stderr) => {
      done({ status: error === null ? 0 : typeof error.code === "number" ? error.code : -1, stdout, stderr });
    });
  });
};

const sha256Of = async (path: string): Promise<string> =>
  createHash("sha256").update(await readFile(path)).digest("hex");

test("the frozen request runs live through the substitute and reduces to the served outcome", { skip: !environmentReady }, async (t) => {
  const out = join(tmpdir(), `pilot-live-${Date.now()}`);
  const receiptPath = join(out, "receipt.json");
  const substitute = await startSubstitute("valid");
  t.after(() => substitute.close());

  const run = await runPilotCli(`${out}/live`, receiptPath, substitute.url);
  assert.equal(run.status, 0, run.stderr);

  const receipt = JSON.parse(await readFile(receiptPath, "utf8")) as {
    served_model: string;
    original_request: { request_sha256: string };
    artifacts: { live_journal: { path: string; sha256: string }; live_answers: { path: string; sha256: string } };
    probabilities: Record<string, number>;
    outcome: { action: string; escalated: boolean; reasons: string[] };
  };
  assert.equal(receipt.served_model, "pilot-substitute-1");
  assert.equal(receipt.original_request.request_sha256, FROZEN_REQUEST_ID);
  assert.equal(Object.keys(receipt.probabilities).length, 14);
  assert.equal(substitute.received.length, 1);
  assert.equal(createHash("sha256").update(substitute.received[0]!).digest("hex"),
    "94853929762756f6eb0f8efbd9acf37a2400bcb4c2836e25f0df7725498fd3e5");
  const [stored] = (await readFile(receipt.artifacts.live_answers.path, "utf8")).trim().split("\n").map((line) => JSON.parse(line));
  assert.equal(Object.keys(stored.answers).length, 18);
  assert.equal(stored.model, "pilot-substitute-1");
  // The evaluator consumed the served answers: 0.5 sits in the open escalation band, 0.1s do not.
  assert.deepEqual(receipt.outcome, { action: "keep", escalated: true, reasons: ["value 0.50"] });
  // The receipt binds the exact artifacts it names.
  assert.equal(await sha256Of(receipt.artifacts.live_journal.path), receipt.artifacts.live_journal.sha256);
  assert.equal(await sha256Of(receipt.artifacts.live_answers.path), receipt.artifacts.live_answers.sha256);
});

test("a served response missing a probability is refused at the boundary, naming the question", { skip: !environmentReady }, async (t) => {
  const out = join(tmpdir(), `pilot-missing-${Date.now()}`);
  const unanswered = firstNoulId();
  const substitute = await startSubstitute("missing", unanswered);
  t.after(() => substitute.close());

  const run = await runPilotCli(`${out}/live`, `${out}/receipt.json`, substitute.url);
  assert.notEqual(run.status, 0);
  assert.match(run.stderr, new RegExp(`answers no probability for ${unanswered}`));
  assert.equal(existsSync(`${out}/receipt.json`), false);
});

test("a malformed response keeps its exact bytes in the journal the pilot wrote", { skip: !environmentReady }, async (t) => {
  const out = join(tmpdir(), `pilot-malformed-${Date.now()}`);
  const substitute = await startSubstitute("malformed");
  t.after(() => substitute.close());

  const run = await runPilotCli(`${out}/live`, `${out}/receipt.json`, substitute.url);
  assert.notEqual(run.status, 0);
  assert.match(run.stderr, /Expecting value/);

  const rows = (await readFile(`${out}/live/journal.jsonl`, "utf8")).split("\n").filter(Boolean)
    .map((line) => JSON.parse(line) as { kind: string; response_body_base64?: string; response_status?: number });
  const responses = rows.filter((row) => row.kind === "response");
  assert.ok(responses.length >= 1);
  for (const row of responses) {
    assert.equal(Buffer.from(row.response_body_base64 ?? "", "base64").toString(), "<html>not json at all</html>");
    assert.equal(row.response_status, 200);
  }
});
