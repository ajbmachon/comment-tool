# Rigor rules for the comment review tool

These rules apply to every run, every report line and every edit proposal. Each rule names the
check that proves it was followed.

## 1. Measured claims only, each with its denominator

Every number says what was counted and out of how many ("23 of 25 decided comments matched the
answer key"), and which run and which commit it came from. There are no estimates in place of
measurements and no percentages without the count behind them. A post-hoc rescore is labelled
post-hoc. Check: every number in a report can be recomputed by a named script from stored files.

## 2. Freeze before measuring

Before a scored run, the questions, the rule (`compose.py`), the fact extraction and the evidence
cut are hashed into a `FROZEN.txt` together with the bars and the answer key. Scoring rechecks the
hashes. A change after the answers were seen makes the next run a new, post-hoc condition, never
the frozen measurement. Change one thing per arm. Check: `shasum -a 256` over the frozen files
equals `FROZEN.txt`.

## 3. Retrieval measured separately from judgment

Two different questions, never merged into one accuracy number:
- Retrieval: did the packet hold the code the comment is about? Measured by how many packets a
  cut changed, and how many reference labels changed when the labeller saw the new packet.
- Judgment: on the same packet, did Jev's answers combined by the rule match the answer key?
Reference labels are bound to the exact packet by `request_sha256`. A label for another packet is
never reused. Check: every scored label's hash equals the hash of the packet Jev saw.

## 4. Three search outcomes kept apart

- Found: the search opened code it judged to be what the comment describes. The spans are listed.
- Searched and not found: every candidate was opened or ruled out. The places are listed.
- Not yet inspected: the budget ran out or only unsure places remain. The unopened places are
  listed. This is unfinished work and is never counted as proof of absence.
Unresolved call edges (a name the parser could not bind) are listed as unresolved, not dropped.
Check: every escalated row names its search outcome and its places.

## 5. Every edit reviewed against the real file

A proposed edit carries `file:line@commit` and the exact comment text. Before anyone applies it,
the text at that location and commit is compared with the stored text; a mismatch blocks the
edit. The agent applying the edit reads the whole file, not the row. Check: the integrity script
reports matches out of rows.

## 6. A durable journal of every request and raw response, for our own code only

For Heedvane and analysis-engine, the exact request is written before dispatch and the raw
response bytes before parsing, through the Evals `ProviderResponseJournal`. Errors and malformed
replies are kept. The answer store keeps requests (`keep_requests=True`) only for these two
repositories. Customer code is never stored: for any other repository the journal and request
storage are refused. Check: journal rows equal Jev calls; every stored request names an own
repository.

## 7. Every comment found stays in the denominator

Code deciding that a comment is noise, a header or a directive is itself a decision. The sweep
calls `find_comments` with `include_noise=True` and writes one row per comment block, with its kind
and the reason when code decided it, so totals count every comment found. Check: rows per unit
equal the blocks `find_comments` returns for that unit with noise included.

## 8. Jobs run directly

Run tests, lint, type checks, builds, benchmarks and labelling jobs directly and in parallel;
never queue behind `run-slot` or wait for a job slot. Watch free memory on heavy parallel jobs.
This is André's 28 September 2026 replacement of the machine-slot rule.

## Design rule: jev-navigator stays a general library

Andre, 28.09.2026: "jev-navigator stays a library: general, extendable and configurable, serving
a broad range of use cases, not customised for ours. Small composable pieces, Unix philosophy."
- Ask the library only for general primitives, such as facts with spans plus a pluggable filter,
  or a Journal protocol. Never ask it for comment-tool behaviour.
- Comment policy stays in this directive: the questions, rule A, thresholds, the escalation band,
  and filters such as "a date inside a file or ADR name is not a time reference".
- Our journal is fitted to the library's Journal protocol by a thin adapter on our side.
- When something cannot be composed from library pieces, ask for the smallest general primitive.

## Applied to what exists (28.09.2026, before 03:56 CEST)

| Rule | State found | Action |
|---|---|---|
| 1 | REPORT.md numbers carry denominators; rounds 1 and 2 are marked post-hoc. | None. |
| 2 | Round-3 hashes still match `round3/FROZEN.txt` (4 of 4 files). `round3-nav-described` changed the evidence cut after round 3 was seen. | Report it as a post-hoc arm, not the frozen result. |
| 3 | 30 fresh blind Sol labels exist, 30 of 30 bound to the new packets by hash, 0 errors. 9 of 30 packets are unchanged from round 3; 21 changed. | Score judgment on the same packets, and report label changes on the 21 changed packets as the retrieval effect. |
| 4 | Sweep rows kept only the outcome word. All 127 escalations of the lib sweep ended with the budget spent (not yet inspected); 3 searches found code; 0 ended as searched and not found. | Record found spans, ruled-out places and unopened places per row. |
| 5 | 1001 of 1001 sweep rows match the file text at a3bde2aa. The old sweep read a live worktree; the rebuilt one reads the commit from git objects (`CodeIndex.at_commit`). | Keep the integrity check as a sweep step. |
| 6 | The answer stores keep no request text, and the SDK adapter parses before anything is stored, so no raw response was journalled. | New runs go through the Evals journal. |
