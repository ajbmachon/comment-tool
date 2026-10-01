# comment-tool

Classifies code comments for a calling agent: keep, remove, refactor instead, rewrite, or fix stale, with
an escalation when it is unsure. Code finds the comments and the code they describe, Jev answers closed
questions about each one, and code composes the action (`comment_tool.core.compose`). The tool only
classifies; the caller acts on the rows.

- **Run it:** [Commands and help](#running). `comment-tool` prints one JSON row per comment;
  `comment-sweep` writes rows by directory unit. Only our own
  repositories (Heedvane and analysis-engine, see `comment_tool.repos`) may be classified, because every
  Jev exchange is journaled.
- **Read the rows:** [docs/CONTRACT.md](docs/CONTRACT.md).
- **Measurements:** [docs/REPORT.md](docs/REPORT.md), under the rules in [docs/RIGOR.md](docs/RIGOR.md).
  The round data it cites (packets, answers, journals, Sol labels, frozen records) stays in
  `~/.claude/handoffs/effect-2026-09-25/comment-tool`; `comment_tool.config` points there, and
  `COMMENT_TOOL_DATA` overrides it.
- **Rewriting a comment:** [docs/rewrite/PROMPT-DRAFT.md](docs/rewrite/PROMPT-DRAFT.md) is guidance for
  the caller.

## Running

```text
uv run comment-tool --help
uv run comment-tool <repository> <commit> <journal dir> --files <path> ...
uv run comment-tool <repository> <commit> <journal dir> --diff <base>

uv run comment-sweep --help
uv run comment-sweep <repository> <commit> <parent dir> <out dir> [--only <unit> ...]
```

`--files` takes one or more repository-relative paths; `--diff` takes one base revision. Choose
exactly one. `comment-tool` prints classification rows to stdout and a summary to stderr.

For `comment-sweep`, `<parent dir>` is repository-relative. Each child directory is a unit;
the parent's own files form numbered units such as `src#1`. `--only` takes one or more unit
names, such as `src/services`; omit it to sweep every unit. Rows and the exchange journal go
to `<out dir>`, and unit summaries go to stdout.

Both commands accept `-h` or `--help` without positional arguments and exit successfully.
Missing arguments, unknown options or conflicting file/diff selections print usage and exit
with status 2 before repository reads or journal creation.

## Layout

```
src/comment_tool/    the tool
  cli/               entry points: classify, sweep
  core/              review, discovery, facts, escalation, compose, definition fetch, case extraction
  claims/            list claims, rewrite packets, the TypeScript parser bridge
  journal/           the journaled Jev client
  config.py          where the round data lives
  questions/         the frozen question files, packaged with the tool
  repos.py           the repositories the tool may read
research/            the rounds behind docs/REPORT.md; not part of the shipped tool
  rounds/            frozen registrations, samplers, runners, scorers, row audit
  labels/            blind Sol reference labels
  analysis/          comparisons, band tables, trace exports, totals
tests/               the suite; `local`-marked tests need the local checkouts and round data
```

Replay scripts retain the sweep's parsed comment kind and use the same fact classifier as live discovery.
Doc comments therefore remain eligible for rewrite or keep, never removal; historical round-3 packets
contain only the non-doc comments selected for that round.

## Tests

`uv run pytest` runs everything; it needs the local heedvane and analysis-engine checkouts, the round
data and the heedvane-evals checkout. Hosted CI runs `uv run pytest -m "not local"`: the tests that need
none of those. The library, [jev-navigator](https://github.com/ajbmachon/jev-navigator), is pinned to its
verified repair commit `cc90bfc6`; a scored round records the exact library commit it ran on in its frozen record.

## Scored rounds, before and after the restructure

Round data is verified against a frozen manifest that hashes every source file of the checkout it ran
from. Rounds scored before the package restructure stay verifiable from the
[`pre-restructure-20260929`](../../tree/pre-restructure-20260929) checkout; new rounds register against
the current layout.
