import assert from "node:assert/strict";
import { test } from "node:test";
import { Effect } from "effect";
import { evaluateCase } from "../src/policy.js";
import type { CodeFacts } from "../src/types.js";

const noFacts: CodeFacts = {
  docComment: false,
  dates: [],
  ticketRefs: [],
  unownedTodo: false,
};

const probabilities = (overrides: Readonly<Record<string, number>> = {}): Readonly<Record<string, number>> => ({
  code_is_hard_to_follow: 0.1,
  explains_how_or_why: 0.1,
  states_hidden_rule: 0.1,
  teaches_needed_knowledge: 0.1,
  points_to_owner: 0.1,
  only_restates_code: 0.1,
  has_time_reference: 0.1,
  is_noise: 0.1,
  name_would_replace: 0.1,
  contradicts_code: 0.1,
  names_specific_detail: 0.1,
  code_shows_same_detail: 0.1,
  code_differs_from_comment: 0.1,
  ...overrides,
});

const run = (p: Readonly<Record<string, number>>, facts = noFacts) => Effect.runPromise(evaluateCase({
  caseId: "edge-case",
  ruleVersion: "current",
  facts,
}, p));

test("0.40 is outside the open escalation band", async () => {
  const result = await run(probabilities({ states_hidden_rule: 0.4 }));
  assert.equal(result.escalated, false);
});

test("0.4000001 is inside the open escalation band", async () => {
  const result = await run(probabilities({ states_hidden_rule: 0.4000001 }));
  assert.equal(result.escalated, true);
  assert.deepEqual(result.reasons, ["value 0.40"]);
});

test("0.60 is outside the open escalation band", async () => {
  const result = await run(probabilities({ states_hidden_rule: 0.6 }));
  assert.equal(result.escalated, false);
  assert.equal(result.action, "keep");
});

test("stale at the 0.80 bar decides", async () => {
  const result = await run(probabilities({
    names_specific_detail: 0.9,
    code_shows_same_detail: 0.9,
    code_differs_from_comment: 0.8,
  }));
  assert.equal(result.action, "fix_stale");
  assert.equal(result.escalated, false);
});

test("a doc comment that would be removed is rewritten", async () => {
  const result = await run(probabilities({ is_noise: 0.9 }), { ...noFacts, docComment: true });
  assert.equal(result.action, "rewrite");
  assert.equal(result.escalated, false);
});
