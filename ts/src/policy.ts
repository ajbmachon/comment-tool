import { Effect } from "effect";
import * as Discern from "@doeixd/discern";
import { PolicyInputSchema, questions } from "./questions.js";
import { storedAnswerLayer } from "./replay-model.js";
import type { Action, CodeFacts, PolicyInput, RuleVersion } from "./types.js";

export const CUTOFF = 0.5;
export const ESCALATION_LOW = 0.4;
export const ESCALATION_HIGH = 0.6;
export const STALE_DECIDES_AT = 0.8;

type Bounds = "exact" | "escalating";

const isLegacy = Discern.deterministic<PolicyInput>(
  (input) => input.ruleVersion === "legacy-round3",
  { id: "legacy-round3", description: "The case uses the frozen round-3 rule" },
);

const isCurrent = Discern.not(isLegacy);
const hasCodeFoundTime = Discern.deterministic<PolicyInput>(
  (input) => input.facts.dates.length > 0 || input.facts.ticketRefs.length > 0,
  { id: "code-found-time", description: "Code extraction found a date or ticket" },
);
const hasUnownedTodo = Discern.deterministic<PolicyInput>(
  (input) => input.facts.unownedTodo,
  { id: "unowned-todo", description: "Code extraction found a TODO without an owner" },
);
const currentNonDoc = Discern.deterministic<PolicyInput>(
  (input) => input.ruleVersion === "current" && !input.facts.docComment,
  { id: "current-non-doc", description: "The current rule may treat restatement as a problem" },
);

const threshold = (bounds: Bounds, question: typeof questions.codeIsHardToFollow) =>
  bounds === "exact"
    ? question.atLeast(CUTOFF)
    : question.band({ match: ESCALATION_HIGH, miss: ESCALATION_LOW });

const patterns = (bounds: Bounds) => {
  const hard = threshold(bounds, questions.codeIsHardToFollow);
  const explains = threshold(bounds, questions.explainsHowOrWhy);
  const hiddenRule = threshold(bounds, questions.statesHiddenRule);
  const knowledge = threshold(bounds, questions.teachesNeededKnowledge);
  const owner = threshold(bounds, questions.pointsToOwner);
  const noise = threshold(bounds, questions.isNoise);
  const nameWouldReplace = threshold(bounds, questions.nameWouldReplace);
  const restates = threshold(bounds, questions.onlyRestatesCode);
  const timeAnswer = threshold(bounds, questions.hasTimeReference);
  const value = Discern.or(Discern.and(hard, explains), hiddenRule, knowledge, owner);
  const legacyStale = Discern.and(isLegacy, threshold(bounds, questions.contradictsCode));
  const currentStaleParts = Discern.and(
    threshold(bounds, questions.namesSpecificDetail),
    threshold(bounds, questions.codeShowsSameDetail),
    threshold(bounds, questions.codeDiffersFromComment),
  );
  const differsClearsStaleBar = bounds === "exact"
    ? Discern.deterministic<PolicyInput>(() => true, { id: "no-stale-bar-for-exact-action" })
    : questions.codeDiffersFromComment.whereResult(
      ({ probability }) => probability >= STALE_DECIDES_AT
        ? Discern.matched(`p=${probability.toFixed(3)}`)
        : Discern.uncertain(`fix stale below bar: code_differs_from_comment ${probability.toFixed(2)}`),
      { id: "stale-decides-at-0.80", description: "A current stale result below 0.80 escalates" },
    );
  const stale = Discern.or(
    legacyStale,
    Discern.and(isCurrent, currentStaleParts, differsClearsStaleBar),
  );
  const noValue = Discern.not(value);
  const noNoise = Discern.not(noise);
  const noNameReplacement = Discern.not(nameWouldReplace);
  const timeReference = Discern.or(hasCodeFoundTime, timeAnswer);
  const restatementCounts = Discern.or(isLegacy, currentNonDoc);
  const pathProblem = Discern.and(restatementCounts, Discern.or(restates, noise));
  const problem = Discern.or(pathProblem, timeReference, hasUnownedTodo);
  return {
    stale,
    value,
    noValue,
    noise,
    noNoise,
    nameWouldReplace,
    noNameReplacement,
    timeAnswer,
    timeReference,
    pathProblem,
    problem,
  };
};

const mapDocAction = (action: Action) => (input: PolicyInput): Action =>
  input.facts.docComment && (action === "remove" || action === "refactor_instead") ? "rewrite" : action;

const makePolicy = (bounds: Bounds) => {
  const p = patterns(bounds);
  return Discern.type(PolicyInputSchema).pipe(
    Discern.when(p.stale, mapDocAction("fix_stale"), { id: "fix-stale" }),
    Discern.when(Discern.and(p.noValue, p.noise), mapDocAction("remove"), { id: "remove-noise" }),
    Discern.when(
      Discern.and(p.noValue, p.noNoise, p.nameWouldReplace),
      mapDocAction("refactor_instead"),
      { id: "refactor-instead" },
    ),
    Discern.when(
      Discern.and(p.noValue, p.noNoise, p.noNameReplacement, p.problem),
      mapDocAction("remove"),
      { id: "remove-problem" },
    ),
    Discern.when(Discern.and(p.value, p.timeReference), mapDocAction("rewrite"), { id: "rewrite-history" }),
    Discern.orElse(mapDocAction("keep")),
  );
};

export const ruleA = makePolicy("exact");

const confidenceMatcher = (() => {
  const p = patterns("escalating");
  const uncertaintyOnly = (pattern: Discern.Pattern<PolicyInput>) => Discern.and(pattern, Discern.not(pattern));
  const gates = Discern.type(PolicyInputSchema).pipe(
    Discern.when(uncertaintyOnly(p.stale), () => false, { id: "stale-uncertainty" }),
    Discern.when(uncertaintyOnly(p.value), () => false, { id: "value-uncertainty" }),
    Discern.when(Discern.and(p.noValue, uncertaintyOnly(p.noise)), () => false, { id: "noise-uncertainty" }),
    Discern.when(
      Discern.and(p.noValue, p.noNoise, uncertaintyOnly(p.nameWouldReplace)),
      () => false,
      { id: "name-uncertainty" },
    ),
    Discern.when(
      Discern.and(p.noValue, p.noNoise, uncertaintyOnly(p.pathProblem)),
      () => false,
      { id: "problem-uncertainty" },
    ),
    Discern.when(
      Discern.and(Discern.not(hasCodeFoundTime), uncertaintyOnly(p.timeAnswer)),
      () => false,
      { id: "history-uncertainty" },
    ),
  );
  return gates.pipe(
    Discern.onUncertain(() => true),
    Discern.orElse(() => false),
  );
})();

export const escalationPolicy = confidenceMatcher;

const staleValue = (p: Readonly<Record<string, number>>, version: RuleVersion): number =>
  version === "legacy-round3"
    ? requiredProbability(p, "contradicts_code")
    : Math.min(
      requiredProbability(p, "names_specific_detail"),
      requiredProbability(p, "code_shows_same_detail"),
      requiredProbability(p, "code_differs_from_comment"),
    );

const valueValue = (p: Readonly<Record<string, number>>): number => Math.max(
  Math.min(requiredProbability(p, "code_is_hard_to_follow"), requiredProbability(p, "explains_how_or_why")),
  requiredProbability(p, "states_hidden_rule"),
  requiredProbability(p, "teaches_needed_knowledge"),
  requiredProbability(p, "points_to_owner"),
);

const requiredProbability = (p: Readonly<Record<string, number>>, questionId: string): number => {
  const value = p[questionId];
  if (value === undefined) throw new Error(`Missing stored probability ${questionId}`);
  return value;
};

const decisionPath = (
  p: Readonly<Record<string, number>>,
  facts: CodeFacts,
  version: RuleVersion,
): ReadonlyArray<readonly [string, number]> => {
  const value = valueValue(p);
  const path: Array<readonly [string, number]> = [[version === "legacy-round3" ? "contradicts_code" : "stale", staleValue(p, version)], ["value", value]];
  const noise = requiredProbability(p, "is_noise");
  if (value < CUTOFF) {
    path.push(["is_noise", noise]);
    if (noise < CUTOFF) {
      path.push(["name_would_replace", requiredProbability(p, "name_would_replace")]);
      if (version === "legacy-round3" || !facts.docComment) {
        path.push(["problem", Math.max(requiredProbability(p, "only_restates_code"), noise)]);
      }
    }
  }
  if (facts.dates.length === 0 && facts.ticketRefs.length === 0) {
    path.push(["has_time_reference", requiredProbability(p, "has_time_reference")]);
  }
  return path;
};

export const escalationReasons = (
  action: Action,
  p: Readonly<Record<string, number>>,
  facts: CodeFacts,
  version: RuleVersion,
): ReadonlyArray<string> => {
  const reasons = decisionPath(p, facts, version)
    .filter(([, value]) => ESCALATION_LOW < value && value < ESCALATION_HIGH)
    .map(([name, value]) => `${name} ${value.toFixed(2)}`);
  if (version === "current" && action === "fix_stale") {
    const differs = requiredProbability(p, "code_differs_from_comment");
    if (differs < STALE_DECIDES_AT) {
      reasons.push(`fix stale below bar: code_differs_from_comment ${differs.toFixed(2)}`);
    }
  }
  return reasons;
};

export const evaluateCase = (
  input: PolicyInput,
  probabilities: Readonly<Record<string, number>>,
) => {
  const layer = storedAnswerLayer(new Map([[input.caseId, probabilities]]));
  return Effect.gen(function* () {
    const action = yield* ruleA(input);
    const escalated = yield* escalationPolicy(input);
    const reasons = escalationReasons(action, probabilities, input.facts, input.ruleVersion);
    if (escalated !== (reasons.length > 0)) {
      return yield* Effect.die(`Discern uncertainty and reason calculation disagree for ${input.caseId}`);
    }
    return { action, escalated, reasons };
  }).pipe(Effect.provide(layer));
};
