import { Effect } from "effect";
import { AiError, DecisionModel } from "effect/ai";
import * as Discern from "@doeixd/discern";

type StoredAnswers = ReadonlyMap<string, Readonly<Record<string, number>>>;

const caseIdFromState = (state: DecisionModel.ProviderOptions["state"]): string | undefined => {
  if (typeof state !== "object" || state === null || !("caseId" in state)) return undefined;
  const caseId = state.caseId;
  return typeof caseId === "string" ? caseId : undefined;
};

const invalidRequest = (description: string) => AiError.make({
  module: "StoredAnswerDecisionModel",
  method: "decide",
  reason: new AiError.InvalidRequestError({ description }),
});

export const storedAnswerLayer = (stored: StoredAnswers) => Discern.Model.fromProvider(
  Discern.Model.provider(({ state, decisions }) => {
    const caseId = caseIdFromState(state);
    if (caseId === undefined) return Effect.fail(invalidRequest("Decision input has no caseId"));
    const probabilities = stored.get(caseId);
    if (probabilities === undefined) return Effect.fail(invalidRequest(`No stored answers for case ${caseId}`));
    const answers: Record<string, DecisionModel.ProviderAnswer> = {};
    for (const [questionId, decision] of Object.entries(decisions)) {
      if (decision._tag !== "Probability") {
        return Effect.fail(invalidRequest(`Stored replay only supports probability decision ${questionId}`));
      }
      const probability = probabilities[questionId];
      if (probability === undefined) {
        return Effect.fail(invalidRequest(`No stored probability for ${caseId}/${questionId}`));
      }
      answers[questionId] = { _tag: "Probability", probability };
    }
    return Effect.succeed({
      answers,
      usage: { inputTokens: undefined, outputTokens: undefined },
    });
  }),
);
