# comment-tool

Classifies code comments for a calling agent: keep, remove, refactor instead, rewrite, or fix stale, with
an escalation when it is unsure. Code finds the comments and the code they describe, Jev answers closed
questions about each one, and code composes the action (`compose.py`). The tool only classifies; the
caller acts on the rows.

- **Run it:** `uv run python classify.py <repository> <commit> <journal dir> (--files <path> ... | --diff <base>)`
  prints one JSON row per comment. Only our own repositories (Heedvane and analysis-engine) may be
  classified, because every Jev exchange is journaled.
- **Read the rows:** [CONTRACT.md](CONTRACT.md).
- **Measurements:** [REPORT.md](REPORT.md), under the rules in [RIGOR.md](RIGOR.md). The round data it
  cites (packets, answers, journals, Sol labels, frozen records) stays in
  `~/.claude/handoffs/effect-2026-09-25/comment-tool`; `data_root.py` points there, and
  `COMMENT_TOOL_DATA` overrides it.
- **Rewriting a comment:** [rewrite/PROMPT-DRAFT.md](rewrite/PROMPT-DRAFT.md) is guidance for the caller.

Replay scripts retain the sweep’s parsed comment kind and use the same fact classifier as live discovery.
Doc comments therefore remain eligible for rewrite or keep, never removal; historical round-3 packets
contain only the non-doc comments selected for that round.

## Tests

`uv run pytest` runs everything; it needs the local heedvane and analysis-engine checkouts, the round
data and the heedvane-evals checkout. Hosted CI runs `uv run pytest -m "not local"`: the tests that need
none of those. The library, [jev-navigator](https://github.com/ajbmachon/jev-navigator), comes from its
main branch; a scored round records the exact library commit it ran on in its frozen record.
