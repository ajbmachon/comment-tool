"""Readout A: the comment action composed in code from Noul probabilities and code-owned facts.

A failed prerequisite always decides; no weighted sum can outvote it. Values are combined with max
(any one value is enough) and a conjunction with min (both parts must hold), never a product.

A doc comment (a JSDoc, docstring, declaration comment or file header) is never removed; where the
answers lead to removal or to a rename instead, it is rewritten (Andre, 28.09.2026 04:52 CEST).
Describing what the code does is a doc's job, so `only_restates_code` is not a problem for a doc: it
is still asked and recorded, but neither the action nor escalation reads it.
"""

from dataclasses import dataclass

CUTOFF = 0.5
OTHER_VALUES = ("states_hidden_rule", "teaches_needed_knowledge", "points_to_owner")
STALE_PARTS = ("names_specific_detail", "code_shows_same_detail", "code_differs_from_comment")
REWRITTEN_NOT_REMOVED = {"remove": "rewrite", "refactor_instead": "rewrite"}
"""A comment is stale only when all three hold: it names a detail, the shown code has that detail,
and the code's version differs."""


def stale_of(p: dict) -> float:
    return min(p[q] for q in STALE_PARTS)


def decision_inputs(p: dict, facts: dict) -> dict:
    """The quantities the rule branches on, as probabilities, plus the code-found time fact."""
    explains_hard = min(p["code_is_hard_to_follow"], p["explains_how_or_why"])
    return {
        "stale": stale_of(p),
        "value": max(explains_hard, *(p[q] for q in OTHER_VALUES)),
        "is_noise": p["is_noise"],
        "name_would_replace": p["name_would_replace"],
        "problem": p["is_noise"] if facts["doc_comment"] else max(p["only_restates_code"], p["is_noise"]),
        "has_time_reference": p["has_time_reference"],
        "code_found_time": bool(facts["dates"] or facts["ticket_refs"]),
        "unowned_todo": facts["unowned_todo"],
    }


def readout_a(p: dict, facts: dict, cutoff: float = CUTOFF) -> str:
    action = _action(p, facts, cutoff)
    if facts["doc_comment"]:
        return REWRITTEN_NOT_REMOVED.get(action, action)
    return action


def _action(p: dict, facts: dict, cutoff: float) -> str:
    x = decision_inputs(p, facts)
    time_ref = x["has_time_reference"] >= cutoff or x["code_found_time"]
    problem = x["problem"] >= cutoff or time_ref or x["unowned_todo"]
    has_value = x["value"] >= cutoff
    if x["stale"] >= cutoff:
        return "fix_stale"
    if not has_value and x["is_noise"] >= cutoff:
        return "remove"
    if not has_value and x["name_would_replace"] >= cutoff:
        return "refactor_instead"
    if not has_value and problem:
        return "remove"
    if has_value and time_ref:
        return "rewrite"
    return "keep"


def rewrite_reasons(p: dict, facts: dict, cutoff: float = CUTOFF) -> list[str]:
    """In plain words, the answers and facts that sent this comment to "rewrite"; empty otherwise."""
    if readout_a(p, facts, cutoff) != "rewrite":
        return []
    x = decision_inputs(p, facts)
    no_value = x["value"] < cutoff
    reasons = []
    if no_value and x["is_noise"] >= cutoff:
        reasons.append(f"only a title or label (is_noise {x['is_noise']:.2f})")
    elif no_value and x["name_would_replace"] >= cutoff:
        reasons.append(f"a better name would say it all (name_would_replace {x['name_would_replace']:.2f})")
    if x["has_time_reference"] >= cutoff:
        reasons.append(f"tells history (has_time_reference {x['has_time_reference']:.2f})")
    if x["code_found_time"]:
        reasons.append(f"names a date or ticket ({', '.join([*facts['dates'], *facts['ticket_refs']])})")
    if no_value and x["unowned_todo"]:
        reasons.append("a TODO without an owner")
    return reasons


def decision_path(p: dict, facts: dict) -> dict:
    """The probabilities readout A actually reads for this case, in branch order."""
    x = decision_inputs(p, facts)
    read = {"stale": x["stale"], "value": x["value"]}
    if x["value"] < CUTOFF:
        read["is_noise"] = x["is_noise"]
        if x["is_noise"] < CUTOFF:
            read["name_would_replace"] = x["name_would_replace"]
            if not facts["doc_comment"]:
                read["problem"] = x["problem"]
    if not x["code_found_time"]:
        read["has_time_reference"] = x["has_time_reference"]
    return read


ESCALATION_BAND = (0.4, 0.6)
STALE_DECIDES_AT = 0.80
"""Provisional (lead, 28.09.2026): "fix stale comment" decides alone only when the code's version
differs at this value or above; below it, the calling agent decides. Fitted on 3 stored verdicts, of
which 2 were wrong; refit once a fresh labelled round has more stale cases."""


def escalation_reasons(p: dict, facts: dict) -> list[str]:
    """The band reasons, and a stale verdict below `STALE_DECIDES_AT`; empty when A decides alone."""
    return band_reasons(p, facts) + _stale_below_bar(p, facts)


def band_reasons(p: dict, facts: dict) -> list[str]:
    """The decision-path quantities inside the escalation band."""
    low, high = ESCALATION_BAND
    return [f"{name} {value:.2f}" for name, value in decision_path(p, facts).items() if low < value < high]


def _stale_below_bar(p: dict, facts: dict) -> list[str]:
    differs = p["code_differs_from_comment"]
    if readout_a(p, facts) != "fix_stale" or differs >= STALE_DECIDES_AT:
        return []
    return [f"fix stale below bar: code_differs_from_comment {differs:.2f}"]


def search_could_settle(p: dict) -> bool:
    """A code search can settle only a doubt about staleness (stale inside the escalation band), and
    only when the comment names a detail the shown code does not surely hold (below the band's top).
    Every other doubt is about the comment's own words, and a surely shown detail needs no search."""
    low, high = ESCALATION_BAND
    detail_not_surely_shown = p["names_specific_detail"] >= CUTOFF and p["code_shows_same_detail"] < high
    return low < stale_of(p) < high and detail_not_surely_shown


NOT_CHECKABLE = "not_checkable_detail_not_shown"


def stale_check(p: dict) -> str | None:
    """`NOT_CHECKABLE` when the comment names a detail the shown code does not hold: its low stale
    value is missing evidence, not a finding that the comment is current."""
    return NOT_CHECKABLE if p["names_specific_detail"] >= CUTOFF and p["code_shows_same_detail"] < CUTOFF else None


@dataclass(frozen=True)
class ListClaim:
    """A comment's claim about every entry of a list: `fails` with the `failing` entries, or
    escalation `reasons`; all empty when the claim holds or none is made."""

    fails: bool = False
    failing: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


ENTRY_NO_BAR = 0.20
"""Only an entry at Jev's no bar or lower may decide: one noisy answer among many entries must not."""


def list_claim(claim: float, entries: dict[str, float]) -> ListClaim:
    """`claim` is P(the comment states a condition every entry must meet); `entries` maps each entry
    to P(it meets that condition). An entry at `ENTRY_NO_BAR` or lower makes the comment stale; an
    entry above it and below the band's top escalates, named."""
    low, high = ESCALATION_BAND
    if low < claim < high:
        return ListClaim(reasons=(f"list claim {claim:.2f}",))
    if claim < CUTOFF or not entries:
        return ListClaim()
    failing = tuple(entry for entry, p in entries.items() if p <= ENTRY_NO_BAR)
    if failing:
        return ListClaim(fails=True, failing=failing)
    return ListClaim(reasons=tuple(f"entry {entry} {p:.2f}" for entry, p in entries.items() if p < high))
