"""How much evidence may ride in one provider request, and what to do when it will not fit.

A packet is built from units: one comment (with its before/after code), one list literal entry
(with the definitions its names need), or one code place (one definition, or one place the
cross-file search opened). A comment's questions keep riding together in one request - that is the
shape the measured rounds were labelled on, and one place does not answer another place's
question. What may not ride together, once there is more than one, is *independent* units that one
request cannot carry: `code.before_comment` and `code.after_comment` are singular for that reason,
and `code.elsewhere` is the one field that ever held more than one place.

`route_limit` reads the ceilings from the client's route table when the installed jev-navigator
publishes one, and from the reference route table when it does not: `drex`, `drex-quick` and
`drex-turbo` answer HTTP 422 `max_tokens_exceeded` above 8,192 request tokens, and `jev` and the
Gemini deciders answer HTTP 400 `max_tokens_exceeded` above 32,000 (`docs/reference/
RUNTIME-CONTRACTS.md` and `enginepy/host/system_one.py`'s `ROUTE_LIMITS`, both read 29.09.2026). A
model name that table does not list is held to `drex`'s ceiling, its smallest. `SYSTEM_ONE_ROUTES`
and `SYSTEM_ONE_ROUTE_LIMITS=name=tokens,...` are how an operator names the routes and their
ceilings - the same names `JevClient` and `GatewayClient` are configured by - so a run's route
table and this measurement come from one place, and no call here is capped by a number counted in
some other way.

Counting is in tokens, never characters, because a character is not a token and a `b64:` block of
base64 was refused for its token count, not its length. One token is about three characters, and
`token_size` mirrors `jev_navigator.history.estimate_tokens` (`len(text) // 3 + 1`), so a packet
measured here stays comparable with a history measured there.
"""

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

TOKENS_PER_CHAR = 3
"""Characters per token, as `jev_navigator.history.estimate_tokens` counts them (3.10.2026)."""

QUESTION_RESERVE_TOKENS = 2_000
"""Tokens a search keeps free for its questions, beside the code it ships with them (the reserve
`SearchBudget.budget_tokens` and `SearchBudget.excerpt_budget_tokens` both hold back)."""

DEFAULT_ROUTE_LIMITS = {"drex": 8_192, "drex-quick": 8_192, "drex-turbo": 8_192, "jev": 32_000,
                        "gemini-flash": 1_048_576, "gemini-flash-latest": 1_048_576, "gemini-pro": 1_048_576}
"""Request-token ceilings of the routes this tool can be pointed at (`RUNTIME-CONTRACTS.md`)."""

DEFAULT_EXCERPT_LIMITS = {"drex": 1_024, "jev": 4_096}
"""What those routes read of one place's code, beside the request that carries it."""

SEARCH_ROUNDS = 8
"""Rounds of places one search may open: 8 rounds x a 3-wide beam = the 24 places a search that
stays inside its route's input limit can read, and a round is a packet, not a hard stop."""


@dataclass(frozen=True)
class PacketBudget:
    """What one request of this run may carry: the request itself, and one place's code inside it."""

    request_tokens: int
    excerpt_tokens: int

    @property
    def evidence_tokens(self) -> int:
        """The part of the request left for code once the questions have kept their reserve."""
        return self.request_tokens - QUESTION_RESERVE_TOKENS


def token_size(text: str) -> int:
    """Tokens in a piece of text, counted the way the library's history budget counts them."""
    return len(text) // TOKENS_PER_CHAR + 1


def state_token_size(state: dict) -> int:
    """Tokens in the state as the client would be sent it: one JSON document, no padding."""
    return token_size(json.dumps(state, ensure_ascii=False, separators=(",", ":")))


def route_names(judge, environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """The routes this judge's client may answer from, first choice first."""
    named = tuple(getattr(getattr(judge, "client", None), "route_names", ()) or ())
    if named:
        return named
    environment = os.environ if environment is None else environment
    return tuple(name.strip() for name in environment.get("SYSTEM_ONE_ROUTES", "").split(",") if name.strip())


def route_limit(judge, environment: Mapping[str, str] | None = None) -> PacketBudget | None:
    """The tightest (request, one place's code) ceilings of the routes this judge may use.

    None when it names no route at all, which is the one case where no size is known here: the
    packet then goes as it always did, and the service answers it with `max_tokens_exceeded`.
    """
    client = getattr(judge, "client", None)
    limits = getattr(client, "route_limits", None)
    if limits:
        return PacketBudget(min(limit.max_request_tokens for limit in limits.values()),
                            min(limit.max_excerpts_tokens for limit in limits.values()))
    environment = os.environ if environment is None else environment
    names = route_names(judge, environment)
    if not names:
        return None
    requests = dict(DEFAULT_ROUTE_LIMITS)
    excerpts = dict(DEFAULT_EXCERPT_LIMITS)
    for entry in environment.get("SYSTEM_ONE_ROUTE_LIMITS", "").split(","):
        if "=" in entry:
            name, _, tokens = entry.partition("=")
            requests[name.strip()] = int(tokens)
            excerpts.setdefault(name.strip(), DEFAULT_EXCERPT_LIMITS["drex"])
    return PacketBudget(min(requests.get(name, requests["drex"]) for name in names),
                        min(excerpts.get(name, excerpts["drex"]) for name in names))


def packet_fits(judge, state: dict) -> bool:
    """False only when a route table is known and this state leaves no room for its questions.

    A state is measured in tokens, in the exact JSON the client would be sent, against the route's
    request ceiling minus `QUESTION_RESERVE_TOKENS` - the reserve `SearchBudget` keeps for the
    questions themselves beside the code it ships with them.
    """
    budget = route_limit(judge, None)
    return budget is None or state_token_size(state) <= budget.evidence_tokens


def packets_fitting(judge, units: list[list], fits: Callable[[list], bool]) -> list[list] | None:
    """Put independently answerable units of evidence into as few packets as the routes will read.

    A unit is one place's code, kept whole: places that answer one question together ride together,
    and a unit larger on its own than one request may be makes this return None, which the caller
    reports as unanswerable instead of cutting the evidence down or sending a request that no route
    of this run was ever going to read.
    """
    if not units:
        return []
    if route_limit(judge, None) is None:
        return [[piece for unit in units for piece in unit]]
    packets: list[list] = [[units[0]]]
    for unit in units[1:]:
        if fits([*packets[-1], *unit]):
            packets[-1] = [*packets[-1], *unit]
        elif fits(list(unit)):
            packets.append(list(unit))
        else:
            return None
    return packets


def lowest_answers(first: Mapping[str, float], *later: Mapping[str, float]) -> dict[str, float]:
    """Merge one question's answers across packets: the lowest probability decides.

    `stale_of` is the lowest of its three probabilities, and a place that shows the detail
    contradicts a place that hides it, so the lowest answer is the one that settles the question.
    """
    merged = dict(first)
    for answers in later:
        for name, probability in answers.items():
            merged[name] = min(probability, merged[name]) if name in merged else probability
    return merged
