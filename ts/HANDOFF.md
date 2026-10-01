# Effect Decision + Discern rule A spike

## Contents

- [Availability and ownership](#availability-and-ownership)
- [Historical replay outcome](#historical-replay-outcome)
- [What was built](#what-was-built)
- [Comparison table](#comparison-table)
- [Exact commands and results](#exact-commands-and-results)
- [Bugs found and fixed in the spike](#bugs-found-and-fixed-in-the-spike)
- [Live integration](#live-integration)
- [Live pilot receipt](#live-pilot-receipt)
- [What Discern made easier](#what-discern-made-easier)
- [What Discern made harder](#what-discern-made-harder)
- [System One rules the TypeScript path cannot express natively yet](#system-one-rules-the-typescript-path-cannot-express-natively-yet)
- [Verdict](#verdict)

## Availability and ownership

This is an experimental spike. It is not a deployed Heedvane feature or an adoption decision for
Discern. Its original base is `b38b2c88b25f33f4d93f387d01ca29a66b63765a`; the retained compatibility
patch is still required. The live entry uses the original Python request and typed provider
observations, then delegates action, escalation and reasons to `src/policy.ts::evaluateCase`.
Python `compose.py` remains the independent comparison owner.

## Historical replay outcome

The TypeScript replay reaches the Python comment tool's final readout on all 120 labelled comments, using stored answers only:

- 120 of 120 rows compared
- 93 decided identically
- 27 escalated identically
- 0 action mismatches
- 0 escalation mismatches
- 0 reason mismatches
- no model call, network request, or `TYPESAFE_API_KEY` read

The generated evidence is:

- `output/rule-a-results.jsonl` — TypeScript runner output, one row per case
- `output/python-reference.jsonl` — output produced by importing the Python repository's own `per_band`, `compose`, and frozen round-3 rule
- `output/comparison.json` — counts and the complete mismatch list

## What was built

- `src/questions.ts` defines every Noul read by current rule A and the frozen round-3 rule as Effect probability Decisions over one `PolicyInputSchema`. `RuleADecisions` groups them explicitly with `Decision.make`. Criteria are flattened to strings because Effect Decision does not accept the Python questions' structured criterion objects.
- `src/policy.ts` implements the ordered action rule as a Discern policy. Min conjunctions use `Discern.and`, max alternatives use `Discern.or`, and the exact action threshold is 0.5. A second Discern policy follows the Python decision path with the open `(0.4, 0.6)` uncertainty band and the current rule's 0.80 stale bar. Doc-comment removal/refactor outcomes map to `rewrite`.
- `src/replay-model.ts` is an Effect `DecisionModel` layer keyed directly by the comment tool's `case_id` and the explicit decision/question id. It returns the parsed JSON number unchanged; it does not use Discern's content-addressed hash.
- `src/data.ts` resolves case request hashes into the actual stored `answers.jsonl` rows. Round 4 applies stored definition-reask answers only to the three stale questions. Round 3 uses its frozen `contradicts_code` rule and its stored answer requests.
- `src/runner.ts` runs the policies and writes one JSONL row per case with round, case id, final action, escalation flag, and reasons.
- `src/python-reference.ts` imports the Python repository's actual rule owners through `uv run --no-sync`; it does not copy their expected outputs into a fixture.
- `src/compare.ts` compares every action, escalation flag, and ordered reason list and writes the proof artifacts.
- Tests cover 0.40, 0.4000001, 0.60, the 0.80 stale bar, a doc comment that would otherwise be removed, and bit-for-bit preservation of `0.47000000000000003` through the replay model.

Code facts remain outside the model: `docComment`, extracted dates, ticket references, and unowned TODO status are deterministic policy guards.

## Comparison table

| Round | Cases | Decided | Escalated | TypeScript vs Python mismatches |
|---|---:|---:|---:|---:|
| round 3 | 30 | 25 | 5 | 0 |
| round 4 | 30 | 25 | 5 | 0 |
| docs 1 | 30 | 24 | 6 | 0 |
| docs 2 | 30 | 19 | 11 | 0 |
| **Total** | **120** | **93** | **27** | **0** |

Every mismatch: none. `output/comparison.json` contains `"mismatches": []`.

## Exact commands and results

The following are the original replay receipts. They used the then-required machine scheduler;
current jobs run directly under `../RIGOR.md` rule 8.

```text
npm run prepare
```

Result: exit 0. This applies the local, reproducible Effect rc.118 compatibility corrections described below.

```text
/Users/andremachon/.local/bin/run-slot -- npm run typecheck
```

Result: exit 0; `tsc --noEmit` completed under strict mode.

```text
/Users/andremachon/.local/bin/run-slot -- npm test
```

Result: exit 0; 6 tests passed, 0 failed.

```text
/Users/andremachon/.local/bin/run-slot -- npm run compare
```

Result: exit 0.

```json
{
  "summary": {
    "total": 120,
    "decided": 93,
    "escalated": 27,
    "mismatches": 0
  },
  "mismatches": []
}
```

`npm run compare` invokes the same `replayAll` runner used by `npm run replay` and wrote all 120 rows to `output/rule-a-results.jsonl`. A redundant runner-only invocation was queued through `run-slot`, but was cancelled before execution when machine load stayed above the scheduler's limit; it is not counted as a passing command here.

An earlier `npm run compare` used the `tsx` CLI and failed before execution because its IPC socket was refused by the sandbox (`listen EPERM`). The scripts now use `node --import tsx`, the same no-IPC loader path as the tests.

## Bugs found and fixed in the spike

Two Discern 0.5.0 integration failures were real library-boundary defects, not policy failures:

1. Discern 0.5.0 declares compatibility with Effect rc.118 but imports removed `effect/unstable/ai/*` subpaths. Effect rc.118 exports these namespaces from `effect/ai`, so importing Discern initially crashed with `ERR_MODULE_NOT_FOUND`.
2. Discern's `and` and `or` preview correctly removed semantic decisions behind a deterministically settled branch, but their later evaluator still evaluated every child. It then dereferenced an answer it had deliberately not requested. All five initial policy tests failed with `Cannot read properties of undefined (reading 'probability')`.

`scripts/patch-discern-rc118.mjs`, run by the package's `prepare` lifecycle, makes both corrections reproducibly in the installed 0.5.0 package. The second correction makes compound evaluation consume a child's already-resolved preview before evaluating it. This preserves Discern's documented deterministic short-circuiting instead of forcing unnecessary stored answers into impossible branches.

These fixes should be proposed upstream before treating the dependency as production-ready.

## Live integration

`../discern_live_pilot.py` selects one original request from its existing provider journal, checks
the canonical state/question hash and exact wire bytes, and has a free `prepare` mode. Its explicit
`live` mode asks the unchanged original questions and requested model through the existing
`journaled_client.py`, native Judge, final secret refusal, Evals journal and full answer store.
The journal owns exact response retention before parsing. A malformed body, parser failure,
HTTP error or incomplete read keeps its bytes and original cause. The adapter refuses missing
requested answers; no fallback probability fills one.

`src/live-pilot.ts` invokes that Python owner, decodes the observation using Effect Schema and
calls `evaluateCase`. It writes the request identity, concrete served model, probabilities, actual
outcome, artifact hashes and measured timings into one receipt. It does not copy the policy or
send the facts-only TypeScript question schema to Jev. The original structured criteria are
preserved; the speculative Choice and Score observations remain recorded and do not override
Rule A.

Run from `ts/`, with the original registered inputs and a fresh output directory:

```text
uv run --no-sync python ../discern_live_pilot.py prepare --journal <original-journal.jsonl> --request-id <canonical-sha256>
node --import tsx src/live-pilot.ts --journal <original-journal.jsonl> --request-id <canonical-sha256> --case-id <original-case-id> --cases <original-cases.jsonl> --out <fresh-directory> --receipt <receipt.json>
```

The normal live invocation uses the provider URL owned by the Evals helpers. `--endpoint` selects
the licensed local HTTP substitute for boundary tests. Tests do not count as live inference.
They use the actual Python executable, journal, store, parser, TS decoder and reducer, including
exact wire identity and the full 18-answer record. The numeric policy tests remain the primary
proof for thresholds; the new boundary suite covers executable transport and failure retention.

Current local proof: 13 Python boundary/journal cases and all 9 TS cases pass, with zero TS skips;
type checking, Ruff and the normal 43-case non-local Python gate pass. A real subprocess killed
before the first response JSON parse reopens the exact journaled body; the original transport
fails that regression. Removing transport-failure rejection is caught by all three selected
HTTP/read cases, and disconnecting `evaluateCase` fails the actual CLI outcome assertion.
The admitted original `hv-d01` provider attempt completed once; its measured receipt follows.
The request design review has no grounded atomicity/semantic contrast score and no automated TS
consumer coverage. This pilot cannot establish calibration, semantic accuracy or adoption readiness.

The previous isolated local-HTTP proof retains its corrected mutation result of 6 caught out of 7.
The undetected `hv-d01` stale-answer probe did not change the outcome because another minimum
prerequisite stayed lower. That is an invalid expected-outcome-change probe, not a reducer defect
or a complete mutation admission. Its historical source and failed evidence remain preserved.

## Live pilot receipt

The admitted live integration completed on 1 October 2026 at 17:47:33–17:47:34 UTC, using source
`1af71adaaefc91fa4f3200cee42aabf8b880aa06`. One original `hv-d01` request reached the actual provider
through the journaled Python owner, and the surviving TS reducer consumed those new observations.
No retry, endpoint override, label revision, question change or threshold change occurred.

| Observation | Measured result |
|---|---|
| Provider attempt | 1; HTTP 200 |
| Requested / served model | `jev-latest` / `jev-1.13.0` |
| Stored typed answers | 18: 14 Nouls, 3 Choices, 1 Score |
| Fresh Python and TS result | `keep`; no escalation; no reasons |
| Original stored result | `keep`; no escalation; no reasons |
| Raw provider usage | 4,016 input tokens; 594 output tokens |
| USD cost | Not measured (`null`) |
| Entire executable invocation | 0.9633976249606349 seconds |
| Python adapter / TS reduction | 508 ms / 3 ms |

The invocation time includes the executable and its children; adapter time includes transport,
journaling, parsing and answer storage. Neither is a separately measured provider latency.
The 14 individual probabilities changed by up to 0.06 from the original response. Those retained
deltas are observations from one request, not an estimate of variance or accuracy.

[The minimal versioned receipt](output/live-integration-receipt.json) binds the canonical request
`d64f8f8787f5cf5cba55297b67213f6776941a7f9905e4f7b5441485046ff8cf` and exact wire hash
`94853929762756f6eb0f8efbd9acf37a2400bcb4c2836e25f0df7725498fd3e5` to the actual raw journal,
full typed answer store, result and independent comparison hashes. The private evidence owner
retains the original requests, raw response, labels, Meta/root admissions, all failure receipts
and the complete original-versus-fresh comparison; those private inputs and logs are outside Git.

The fresh comparison imported the unchanged original Python `compose.py`; it did not replay an
old expected result or the copied isolated boundary reducer. Action, escalation and the ordered
reason list agree on the same new probabilities. The old copied reducer remains only in its
historical proof archive. The delivered live entry owns no second Rule A implementation.

The initial post-check compared raw JSON directly with the typed store and failed because the
API Score includes a presentation-only `legend`. The existing SDK stores its score, confidence
and full distribution; the raw journal retains the legend. The corrected check compares the
actual SDK projection and separately verifies that the exact raw response remains retained.
The failed observer and an earlier interpreter setup failure remain recorded. Neither caused
a second provider call or a product-source change.

One sourced lifetime limitation remains: `EvalsJournal.record_response` keeps a successful
exchange handle so a later parse failure can use the same owner; only failure removes it.
A long-lived successful sweep therefore retains those handles until its journal is released.
The single-call pilot did not measure sweep memory, and adds no journal completion protocol.

This accepts transport, provenance and reducer integration for one original workflow. It does
not admit semantic accuracy, calibrated policy or production adoption. The dependency patch,
Meta coverage gaps and historical 6-of-7 local mutation result remain explicit.

## What Discern made easier

- The rule reads like its semantics: `and` implements min-style prerequisites, `or` implements max-style alternatives, and ordered `when` cases preserve Python branch priority.
- The open uncertainty band is first-class. The identity `and(pattern, not(pattern))` isolates Discern's `Uncertain` state while mapping both decided states to `Miss`, which made the Python escalation path expressible without rounding a maybe into yes or no.
- Decision collection and batching are derived from policy patterns. The compiled policy owns the decision set instead of maintaining a separate list beside the branches.
- Deterministic guards and semantic patterns compose in one plan, which keeps dates, ticket references, doc status, and TODO ownership in code.
- The policy remains provider-neutral. The stored replay layer substitutes for Jev without changing rule code.

## What Discern made harder

- Version compatibility is currently brittle. The released package did not actually load with its permitted Effect rc.118 peer.
- The deterministic-preview bug broke the exact feature the policy needs: skipping legacy questions for current cases and skipping semantic questions when code facts decide.
- A policy's uncertainty handler receives the input and first uncertain case, but not the raw answer map. Python reports all uncertain quantities, in a stable order, so exact reason construction remains a deterministic readout over the same stored probabilities beside the boolean Discern escalation policy. The program asserts that Discern's escalation result and the reason list agree for every case.
- Discern's native recording/replay address hashes `{ decision, state }`. That is useful for new native workflows but cannot address the Python answer store, whose request bytes, structured criteria, and question versions differ. The spike therefore needs the small case-id/question-id replay model.

## System One rules the TypeScript path cannot express natively yet

- Effect probability criteria are `{ true: string, false: string }`; they cannot carry our structured `what`, `not_for`, and `examples` objects. Flattening is a new question version and must be re-measured before a live TypeScript Jev call.
- Effect/Discern do not natively retain the exact sent request bytes, served model id, or a question-wording hash. The live pilot delegates those facts to the existing Python transport/journal owner instead of introducing another transport wrapper.
- Discern's content address is not the comment tool's established request identity. Cross-language replay needs the explicit adapter built here, or a shared future journal contract.
- Discern does not natively emit every uncertain path quantity and its user-facing reason in one policy result. The deterministic reason readout remains necessary for parity.

## Verdict

Effect Decision plus Discern is a good architectural base for native Jev workflows: code owns facts and execution, model judgments remain typed observations, uncertainty is explicit, and the provider can be replaced cleanly for replay. This spike demonstrates exact end-to-end parity over a nontrivial composed rule rather than only API ergonomics.

Discern 0.5.0 itself is not an admitted unpatched production dependency. Both historical failures
sit on core advertised paths: Effect rc.118 loading and deterministic short-circuiting. The local
Python-to-TS boundary proof and one original live provider attempt establish scoped integration;
upstream dependency repairs and any production adoption remain separate decisions.
