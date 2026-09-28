import { Schema } from "effect";
import { Decision } from "effect/ai";
import * as Discern from "@doeixd/discern";

export const PolicyInputSchema = Schema.Struct({
  caseId: Schema.String,
  ruleVersion: Schema.Literals(["legacy-round3", "current"]),
  facts: Schema.Struct({
    docComment: Schema.Boolean,
    dates: Schema.Array(Schema.String),
    ticketRefs: Schema.Array(Schema.String),
    unownedTodo: Schema.Boolean,
  }),
});

const OnComment = Discern.on(PolicyInputSchema);

const probability = (
  id: string,
  instructions: string,
  trueCriterion: string,
  falseCriterion: string,
) => OnComment.probability({
  id,
  instructions,
  criteria: { true: trueCriterion, false: falseCriterion },
});

export const questions = {
  codeIsHardToFollow: probability(
    "code_is_hard_to_follow",
    "Is the adjacent code hard to follow for a developer reading it without any comment?",
    "The code's behavior or shape is non-obvious without explanation.",
    "The code's names and statements make its behavior plain.",
  ),
  explainsHowOrWhy: probability(
    "explains_how_or_why",
    "Does the comment explain how the adjacent code works, or why it is written this way?",
    "The comment describes mechanism or rationale beyond a title.",
    "The comment does not describe mechanism or rationale.",
  ),
  statesHiddenRule: probability(
    "states_hidden_rule",
    "Does the comment state a rule or warning that the adjacent code does not show?",
    "The comment names a constraint, required order, consequence, or external behavior not visible in code.",
    "The comment states no rule beyond what the code visibly enforces.",
  ),
  teachesNeededKnowledge: probability(
    "teaches_needed_knowledge",
    "Does the comment teach domain or platform knowledge needed to change the adjacent code safely?",
    "The comment supplies relevant domain, protocol, library, format, or platform knowledge.",
    "The comment supplies no relevant knowledge beyond the code.",
  ),
  pointsToOwner: probability(
    "points_to_owner",
    "Does the comment point to the place that owns a rule instead of copying the rule's full text?",
    "The comment names an owning document, path, link, or module without copying the full rule.",
    "The comment names no owner, or copies the full rule.",
  ),
  onlyRestatesCode: probability(
    "only_restates_code",
    "Does the comment only repeat what the adjacent code already says?",
    "Every statement in the comment can be read directly from the adjacent code.",
    "At least one statement adds a reason, constraint, or fact not visible in the code.",
  ),
  hasTimeReference: probability(
    "has_time_reference",
    "Does the comment tell history instead of describing the code as it is now?",
    "The comment retells earlier behavior, an incident, or a decision credited to a person, chat, or meeting.",
    "The comment describes only current behavior and rationale.",
  ),
  isNoise: probability(
    "is_noise",
    "Is the comment only a title or group label naming the code that follows?",
    "Apart from divider characters, the comment is only a heading or label.",
    "The comment contains at least one statement beyond naming the following code.",
  ),
  nameWouldReplace: probability(
    "name_would_replace",
    "Would a better name or a small extracted function say everything the comment says?",
    "A clearer name or extraction would carry all of the comment's meaning.",
    "The current names already carry the meaning, or some meaning cannot fit in a name.",
  ),
  contradictsCode: probability(
    "contradicts_code",
    "Does the comment state a detail that the shown code visibly does differently?",
    "The comment and shown code describe the same detail differently.",
    "No comment statement is refuted by the same thing in the shown code.",
  ),
  namesSpecificDetail: probability(
    "names_specific_detail",
    "Does the comment state a specific value, name, order, or condition checkable against code?",
    "The comment names a concrete, checkable detail.",
    "The comment gives only purpose, rationale, a label, or a pointer.",
  ),
  codeShowsSameDetail: probability(
    "code_shows_same_detail",
    "Does the shown code contain a line about the same detail the comment states?",
    "A shown line handles the same value, name, order, or condition.",
    "No shown line handles that detail, or the comment states no detail.",
  ),
  codeDiffersFromComment: probability(
    "code_differs_from_comment",
    "Where comment and code share a detail, is the code's version different from the comment's?",
    "The shared detail differs in value, name, order, or condition.",
    "The shared detail matches, or no detail is shared.",
  ),
};

/** One Effect definition over the case schema. Discern selects the needed subset per policy branch. */
export const RuleADecisions = Decision.make({
  input: PolicyInputSchema,
  decisions: {
    code_is_hard_to_follow: questions.codeIsHardToFollow.decision,
    explains_how_or_why: questions.explainsHowOrWhy.decision,
    states_hidden_rule: questions.statesHiddenRule.decision,
    teaches_needed_knowledge: questions.teachesNeededKnowledge.decision,
    points_to_owner: questions.pointsToOwner.decision,
    only_restates_code: questions.onlyRestatesCode.decision,
    has_time_reference: questions.hasTimeReference.decision,
    is_noise: questions.isNoise.decision,
    name_would_replace: questions.nameWouldReplace.decision,
    contradicts_code: questions.contradictsCode.decision,
    names_specific_detail: questions.namesSpecificDetail.decision,
    code_shows_same_detail: questions.codeShowsSameDetail.decision,
    code_differs_from_comment: questions.codeDiffersFromComment.decision,
  },
});
