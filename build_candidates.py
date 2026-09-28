"""Write one Meta Builder candidate per model-bound comment case.

Cases code decides alone (file headers, tool directives, declaration docs, commented-out code) are skipped: they never reach Jev.
usage: python3 build_candidates.py cases.jsonl questions.json candidates/
"""

import json
import pathlib
import sys

VALUE_USE = "One of four value answers; their maximum is the comment's usefulness score."
HARD_USE = "Together with the other half, as their minimum, the explains-hard-code value; never used alone."
INTENDED_USES = {
    "code_is_hard_to_follow": HARD_USE,
    "explains_how_or_why": HARD_USE,
    "states_hidden_rule": VALUE_USE,
    "teaches_needed_knowledge": VALUE_USE,
    "points_to_owner": VALUE_USE,
    "only_restates_code": "Problem answer; with no value it makes the comment a removal proposal.",
    "has_time_reference": "Time answer, joined in code with detected dates and ticket numbers; with value it makes a rewrite proposal, without value a removal proposal.",
    "is_noise": "Problem answer; with no value it makes the comment a removal proposal.",
    "contradicts_code": "When it holds, the comment is proposed for a stale-comment fix before any other outcome.",
    "name_would_replace": "With no value and no title or label, it turns a removal into a rename-or-extract proposal.",
    "addressed_to_agent": "Recorded only; no decision reads it until its answers have been reviewed.",
    "change_risk_without_comment": "Orders the review queue only; it never decides an outcome.",
    "action": "Readout B: the dispatched function; compared with readout A (the composed Nouls) against Sol labels.",
    "refactor_instead.kind": "Argument read only when action is refactor_instead.",
    "link_owner.kind": "Argument read only when action is link_owner.",
}
WORKFLOW = {
    "purpose": "Decide per non-doc code comment whether it stays, is rewritten without time references, is replaced by a clearer name, is fixed as stale, or is proposed for removal.",
    "consumer_code": (
        "explains_hard = min(answers['code_is_hard_to_follow'].noul, answers['explains_how_or_why'].noul)\n"
        "value = max(explains_hard, answers['states_hidden_rule'].noul, answers['teaches_needed_knowledge'].noul, answers['points_to_owner'].noul)\n"
        "time_ref = answers['has_time_reference'].noul >= cutoff or bool(facts['dates'] or facts['ticket_refs'])\n"
        "problem = max(answers['only_restates_code'].noul, answers['is_noise'].noul) >= cutoff or time_ref or facts['unowned_todo']\n"
        "if answers['contradicts_code'].noul >= cutoff: propose_stale_fix(comment)\n"
        "elif value < cutoff and answers['is_noise'].noul >= cutoff: propose_removal(comment)\n"
        "elif value < cutoff and answers['name_would_replace'].noul >= cutoff: propose_rename_or_extract(comment)\n"
        "elif value < cutoff and problem: propose_removal(comment)\n"
        "elif value >= cutoff and time_ref: propose_rewrite(comment)\n"
        "else: keep(comment)\n"
        "record(answers['addressed_to_agent'].noul)\n"
        "queue_rank = answers['change_risk_without_comment'].score\n"
        "call = answers['action'].choice\n"
        "call_confidence = answers['action'].confidence\n"
        "kind = None\n"
        "if call == 'refactor_instead':\n"
        "    kind = answers['refactor_instead.kind'].choice\n"
        "    call_confidence = min(call_confidence, answers['refactor_instead.kind'].confidence)\n"
        "if call == 'link_owner':\n"
        "    kind = answers['link_owner.kind'].choice\n"
        "    call_confidence = min(call_confidence, answers['link_owner.kind'].confidence)\n"
        "dispatch(call, kind, call_confidence)"
    ),
}
HEEDVANE = "heedvane 39d8a3dc"
CONSTRUCTED = "constructed matched control"


def pair(pair_id, a, b, outputs, case_ref, anchor, a_truth, b_truth):
    """One source-backed atomicity pair: two propositions, their consumers, and a case where they differ."""
    return {
        "pair_id": pair_id,
        "proposition_a": {"id": a[0], "text": a[1], "source_anchor": a[2]},
        "proposition_b": {"id": b[0], "text": b[1], "source_anchor": b[2]},
        "consumer_outputs": {"a": outputs[0], "b": outputs[1]},
        "independence_evidence": {"case_ref": case_ref, "source_anchor": anchor, "a_truth": a_truth, "b_truth": b_truth},
    }


COMMENT = "request.state.comment.text"
CODE = "request.state.code"
RULE_AND_KNOWLEDGE = pair(
    "hidden_rule_and_domain_knowledge",
    ("hidden_rule", "`comment.text` states a constraint, order or consequence the adjacent code does not show.", COMMENT),
    ("domain_knowledge", "`comment.text` teaches how a domain, library, protocol or platform works.", COMMENT),
    ("Value: hidden rule.", "Value: needed knowledge."),
    "hv-20", f"{HEEDVANE} apps/web/src/lib/spend-governance/budget-policy-store.ts:28", True, False,
)
RESTATES_AND_LABEL = pair(
    "restates_code_and_title_label",
    ("restates_code", "Every statement in `comment.text` can be read from the adjacent code.", COMMENT),
    ("title_label", "`comment.text` is only a heading or label naming the code that follows.", COMMENT),
    ("Problem: restating.", "Problem: noise."),
    "constructed: '# Increment the counter' above 'count += 1'", CONSTRUCTED, True, False,
)
HARD_AND_EXPLAINED = pair(
    "code_is_hard_and_comment_explains",
    ("code_is_hard", "The code in `code.before_comment` and `code.after_comment` is hard to follow on its own.", CODE),
    ("comment_explains_code", "`comment.text` explains how the adjacent code works or why it is written this way.", COMMENT),
    ("First half of the explains-hard-code value.", "Second half of the explains-hard-code value."),
    "constructed: a dense bit-mask expression under a comment that only reads '# helpers'", CONSTRUCTED, True, False,
)
ATOMICITY_PAIRS = {
    "code_is_hard_to_follow": HARD_AND_EXPLAINED,
    "explains_how_or_why": HARD_AND_EXPLAINED,
    "states_hidden_rule": RULE_AND_KNOWLEDGE,
    "teaches_needed_knowledge": RULE_AND_KNOWLEDGE,
    "points_to_owner": pair(
        "names_owner_and_copies_rule",
        ("names_owner", "`comment.text` names a document, path or module that owns a rule.", COMMENT),
        ("copies_rule", "`comment.text` restates that rule in full.", COMMENT),
        ("Value: owner pointer.", "Not consumed; a copied rule is judged by states_hidden_rule."),
        "constructed: '# Retention follows docs/policies/data-retention.md; change it there first.'", CONSTRUCTED, True, False,
    ),
    "only_restates_code": RESTATES_AND_LABEL,
    "is_noise": RESTATES_AND_LABEL,
    "has_time_reference": pair(
        "retells_history_and_states_present_rule",
        ("retells_history", "`comment.text` retells an earlier version, an incident, or who decided.", COMMENT),
        ("present_rule", "`comment.text` states how or why the code behaves as it does now.", COMMENT),
        ("Time: rewrite or removal.", "Value: kept content."),
        "hv-26", f"{HEEDVANE} apps/api/src/views/findings-row-projection.ts:106", True, False,
    ),
    "contradicts_code": pair(
        "contradicts_shown_code_and_mentions_unshown_code",
        ("contradicts_shown", "A statement in `comment.text` disagrees with the shown code.", COMMENT),
        ("mentions_unshown", "`comment.text` makes claims about code that is not shown.", COMMENT),
        ("Stale-comment fix.", "Not consumed; such claims cannot be checked here."),
        "constructed: '# Retry five times' above 'for attempt in range(3):'", CONSTRUCTED, True, False,
    ),
    "name_would_replace": pair(
        "name_carries_meaning_and_comment_gives_reason",
        ("name_carries_meaning", "A clearer name or extracted function could say what `comment.text` says.", COMMENT),
        ("gives_reason", "`comment.text` gives a reason no name can hold.", COMMENT),
        ("Rename-or-extract proposal.", "Value: kept content."),
        "constructed: '# seconds until the session expires' above 't = 900'", CONSTRUCTED, True, False,
    ),
    "addressed_to_agent": pair(
        "addresses_agent_and_warns_reader",
        ("addresses_agent", "`comment.text` addresses an AI agent directly.", COMMENT),
        ("warns_reader", "`comment.text` warns any reader about a change that would break something.", COMMENT),
        ("Recorded for review.", "Value: hidden rule."),
        "constructed: '# Do not reorder: the second call reads what the first one writes.'", CONSTRUCTED, False, True,
    ),
}


def candidate(case: dict, questions: dict) -> dict:
    return {
        "case_id": case["case_id"],
        "group_id": "comment-value-v5",
        "revision_id": "r5",
        "request": {"model": "jev-latest", "state": case["state"], "questions": questions},
        "intended_uses": INTENDED_USES,
        "workflow": WORKFLOW,
        "review_context": {
            "questions": {qid: {"atomicity_pairs": [atomicity]} for qid, atomicity in ATOMICITY_PAIRS.items()}
        },
    }


def main() -> None:
    cases_path, questions_path, out_dir = sys.argv[1:4]
    questions = json.loads(pathlib.Path(questions_path).read_text())
    out = pathlib.Path(out_dir)
    out.mkdir(exist_ok=True)
    for line in pathlib.Path(cases_path).read_text().splitlines():
        case = json.loads(line)
        if case["deterministic_keep"] or case["deterministic_proposal"]:
            continue
        (out / f"{case['case_id']}.json").write_text(json.dumps(candidate(case, questions), indent=2) + "\n")


if __name__ == "__main__":
    main()
