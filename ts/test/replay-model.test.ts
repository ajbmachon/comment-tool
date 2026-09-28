import assert from "node:assert/strict";
import { test } from "node:test";
import { Effect } from "effect";
import * as Discern from "@doeixd/discern";
import { questions } from "../src/questions.js";
import { storedAnswerLayer } from "../src/replay-model.js";
import type { PolicyInput } from "../src/types.js";

test("stored replay preserves the exact JavaScript number by case id and question id", async () => {
  const stored = 0.47000000000000003;
  const input: PolicyInput = {
    caseId: "case-with-long-float",
    ruleVersion: "current",
    facts: { docComment: false, dates: [], ticketRefs: [], unownedTodo: false },
  };
  const layer = storedAnswerLayer(new Map([[input.caseId, { states_hidden_rule: stored }]]));
  const answer = await Effect.runPromise(
    Discern.ask(questions.statesHiddenRule, input).pipe(Effect.provide(layer)),
  );
  assert.equal(Object.is(answer.probability, stored), true);
});
