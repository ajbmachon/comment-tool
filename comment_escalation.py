"""The comment review's escalation as a jev-navigator LlmStep: an escalated pass row goes to the
calling agent with the comment, its code, Jev's probabilities, both readouts and the one unclear
question, and comes back as one listed action. Built here, not called by the sweep yet.
"""

from collections.abc import Mapping

from jev_navigator.llm_step import Connector, LlmGuard, LlmStep, PickFromOptions

ACTIONS = {
    "keep": "The comment stays as it is.",
    "rewrite": "Keep its rule, drop history, dates, people and ticket numbers.",
    "remove": "The comment has no value for a reader of this code.",
    "refactor_instead": "A better name or a small extracted function would say what the comment says.",
    "fix_stale": "The comment contradicts the code it describes.",
}
INSTRUCTIONS = (
    "Decide what happens to this code comment. Automated checks could not settle one question, named "
    "in `unclear_question`. Read the comment against the code shown, answer that question for "
    "yourself, then pick the action. Comments earn their place by explaining hard code, stating a "
    "rule or warning the code does not show, teaching knowledge needed to change the code safely, or "
    "pointing to the owner of a rule."
)


def escalation_context(row: Mapping, code: str) -> dict:
    nouls = {qid: round(answer["noul"], 2) for qid, answer in row["answers"].items() if answer["type"] == "noul"}
    return {
        "location": row["location"],
        "comment": row["comment"],
        "code": code,
        "probabilities": nouls,
        "rule_readout": row["action"],
        "jev_action_suggestion": row["suggestion"]["choice"],
        "unclear_question": row["escalate"]["unclear_question"],
        "options": ACTIONS,
    }


def comment_escalation_step(connector: Connector, guard: LlmGuard, code_for) -> LlmStep:
    """`code_for(row)` returns the code the comment describes; the step runs only on escalated rows."""
    return LlmStep(
        name="comment_escalation",
        when=lambda row: "escalate" in row,
        context=lambda row: escalation_context(row, code_for(row)),
        answer=PickFromOptions(INSTRUCTIONS, answer_field="action"),
        connector=connector,
        guard=guard,
    )
