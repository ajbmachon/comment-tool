"""Comment review as a thin directive on jev-navigator.

The library supplies the code index, the code a comment describes, masking, the pre-send secret
scan, the answer store and the Jev call. This directive builds the comment's state, asks every
frozen question in one `ask_all` request (Nouls, the action Choices and the change-risk Score),
applies rule A and its escalation band, and returns one row that names every piece of evidence by
file, lines and commit. The code shown around the comment is injected (`Context`), so a different
cut is a separate, named arm.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace

from jev_navigator.comments import code_above_comment
from jev_navigator.index.code_index import CodeIndex
from jev_navigator.index.spans import CodeSlice, Span
from jev_navigator.judgments.judge import AllAnswers, Judge
from jev_navigator.judgments.questions import Check, Criterion, Pick, Rate
from jev_navigator.operations import code_described_by_comment

import compose

BEFORE_COMMENT_LINES = 8
ACTION = "action"
CHANGE_RISK = "change_risk_without_comment"


@dataclass(frozen=True)
class CommentCase:
    file: str
    first_line: int
    last_line: int
    text: str
    language: str
    facts: Mapping


@dataclass(frozen=True)
class QuestionSet:
    checks: tuple[Check, ...]
    picks: tuple[tuple[Pick, Mapping[str, str]], ...]
    scores: tuple[Rate, ...]


Context = Callable[[CodeIndex, CommentCase], tuple[CodeSlice | None, CodeSlice]]


def question_set(questions: Mapping) -> QuestionSet:
    """The frozen `questions.json`, as library question types with unchanged wording."""
    checks = tuple(_check(name, q) for name, q in questions.items() if q["type"] == "noul")
    picks = tuple((Pick(name, q["instructions"]), dict(q["criteria"])) for name, q in questions.items() if q["type"] == "choice")
    scores = tuple(Rate(name, q["instructions"], tuple(q["criteria"])) for name, q in questions.items() if q["type"] == "score")
    return QuestionSet(checks, picks, scores)


def _check(name: str, question: Mapping) -> Check:
    return Check(name, question["instructions"], _criterion(question["criteria"]["true"]),
                 _criterion(question["criteria"]["false"]))


def _criterion(described: Mapping) -> Criterion:
    return Criterion(described["what"], described.get("not_for", ""), tuple(described.get("examples", ())))


def lines_above(index: CodeIndex, case: CommentCase) -> CodeSlice | None:
    """Up to BEFORE_COMMENT_LINES lines directly above the comment, blank lines included."""
    if case.first_line == 1:
        return None
    span = Span(case.file, max(1, case.first_line - BEFORE_COMMENT_LINES), case.first_line - 1)
    return index.read_slice(span, origin="lines_above")


def library_code_above(index: CodeIndex, case: CommentCase) -> CodeSlice | None:
    return code_above_comment(index, case.file, case.first_line).code


def described_after(index: CodeIndex, case: CommentCase) -> CodeSlice:
    """The code the comment is about. A docstring sits inside its function or class, so for those
    it is the rest of the owner; otherwise it is `code_described_by_comment`."""
    owner = _docstring_owner(index, case) if _is_docstring(case) else None
    if owner is None or owner.end <= case.last_line:
        return code_described_by_comment(index, case.file, case.last_line)
    return index.read_slice(Span(case.file, case.last_line + 1, owner.end, owner.name), origin="docstring_owner")


def _docstring_owner(index: CodeIndex, case: CommentCase) -> Span | None:
    owners = [symbol for symbol in index.symbols_in(case.file) if symbol.contains(case.first_line)]
    return min(owners, key=Span.size, default=None)


def _is_docstring(case: CommentCase) -> bool:
    return case.language == "python" and case.text.lstrip().lstrip("rRuU").startswith(('"""', "'''"))


def context_of(before: Callable, after: Callable = described_after) -> Context:
    return lambda index, case: (before(index, case), after(index, case))


MEASURED_CONTEXT = context_of(lines_above)
"""The cut the fresh round-3 Sol labels were given."""
UNMEASURED_CONTEXT = context_of(library_code_above)
"""The library's code-above cut; no reference labels exist for it yet."""


def comment_state(case: CommentCase, before: CodeSlice | None, after: CodeSlice, elsewhere: tuple[CodeSlice, ...] = ()) -> dict:
    """The packet. Code fetched from other places (a definition, a search) goes in `code.elsewhere`
    with its source, never into `code.after_comment`."""
    code = {"language": case.language, "before_comment": before.text if before else "", "after_comment": after.text}
    if elsewhere:
        code["elsewhere"] = [{**piece.source(), "code": piece.text} for piece in elsewhere]
    return {"comment": {"text": case.text}, "code": code}


STALE_FIELDS = "`code.before_comment` or `code.after_comment`"
STALE_FIELDS_WITH_ELSEWHERE = "`code.before_comment`, `code.after_comment` or `code.elsewhere`"


def stale_reask_checks(questions: QuestionSet) -> tuple[Check, ...]:
    """The stale questions for a packet with `code.elsewhere`: the same questions, with that field
    added wherever they name the shown code."""
    stale = [check for check in questions.checks if check.name in compose.STALE_PARTS]
    return tuple(replace(check, instructions=check.instructions.replace(STALE_FIELDS, STALE_FIELDS_WITH_ELSEWHERE))
                 for check in stale)


def review_comment(index: CodeIndex, judge: Judge, case: CommentCase, questions: QuestionSet, context: Context,
                   rule=compose) -> dict:
    """``rule`` is the composition module (readout_a, decision_path, escalation_reasons) the round froze."""
    before, after = context(index, case)
    state = comment_state(case, before, after)
    answers = judge.ask_all(state, checks=questions.checks, picks=questions.picks, scores=questions.scores)
    probabilities = {name: result.probability for name, result in answers.checks.items()}
    row = {
        "location": f"{case.file}:{case.first_line}",
        "commit": index.commit,
        "comment": case.text,
        "evidence": {"before_comment": before.source() if before else None, "after_comment": after.source()},
        **_suggestions(answers),
        "request_sha256": answers.request_sha256,
        "state": state,
    }
    return recomposed(row, probabilities, case, rule)


def recomposed(row: dict, probabilities: dict, case: CommentCase, rule=compose) -> dict:
    """The row's probabilities, decision path, action and escalation, composed from `probabilities`."""
    decided = {key: value for key, value in row.items() if key != "escalate"}
    decided.update(probabilities=probabilities, decision_path=rule.decision_path(probabilities, case.facts),
                   action=rule.readout_a(probabilities, case.facts))
    return with_escalation(decided, rule.escalation_reasons(probabilities, case.facts))


def with_escalation(row: dict, reasons: list[str]) -> dict:
    """The row handed to the calling agent (then a human) for `reasons`, added to any it already has."""
    if not reasons:
        return row
    earlier = row.get("escalate", {}).get("reasons", [])
    return {**row, "escalate": {"route": "calling_llm", "fallback": "human", "reasons": [*earlier, *reasons]}}


def _suggestions(answers: AllAnswers) -> dict:
    """B's action pick and its arguments only suggest the phrasing; the Score only orders the queue."""
    picks = {name: {"choice": pick.choice, "confidence": pick.confidence, "probabilities": dict(pick.probabilities)}
             for name, pick in answers.picks.items()}
    risk = answers.scores[CHANGE_RISK]
    return {"suggestion": picks.pop(ACTION), "argument_suggestions": picks,
            "change_risk": {"score": risk.score, "confidence": risk.confidence, "probabilities": dict(risk.probabilities)}}
