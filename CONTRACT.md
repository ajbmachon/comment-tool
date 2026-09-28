# Comment classification: output contract

What `classify.py` prints, one JSON object per line on stdout, one per comment. The tool only classifies: it never edits a file and writes no comment text. The calling agent, or another system, acts on each row (Andre, 28.09.2026: "calling agent rewrites, our tool just classifies").

## Contents

- [How to run it](#how-to-run-it)
- [How to read a row](#how-to-read-a-row)
- [Fields](#fields)
- [Example rows](#example-rows)

## How to run it

```text
uv run python classify.py <repository> <commit> <journal dir> --files <path> ...
uv run python classify.py <repository> <commit> <journal dir> --diff <base>
```

With `--diff`, only the comments a change touches are classified: a comment whose own lines, or the code it describes, hold a line changed between the merge base of `<base>` and `<commit>`. Only Python and TypeScript source files are read, never tests or generated code. A summary goes to stderr. Every Jev exchange is journaled in `<journal dir>`, so only our own repositories (Heedvane and analysis-engine) can be classified.

## How to read a row

1. **Is `escalate` present?** Then the tool is not sure. `action` is only its best guess, and `escalate.reasons` says why, in the form `<answer> <value>`. The caller decides, and a human decides after the caller if needed.
2. **Otherwise `action` is the classification:**

| `action` | Meaning | What the caller does |
|---|---|---|
| `keep` | The comment earns its place | Nothing |
| `remove` | Adds nothing a reader needs, and is only a title, repeats the code, tells history or is a TODO without an owner. Never given to a doc comment | Delete the comment |
| `refactor_instead` | A better name would say it all. Never given to a doc comment | Rename or extract, then delete the comment |
| `rewrite` | Worth keeping but badly written. A doc comment that fails lands here instead of `remove` or `refactor_instead` | Write a new comment from `rewrite_job` (see `rewrite/PROMPT-DRAFT.md`) |
| `fix_stale` | The comment and the code disagree | Make them agree. For now this always comes with `escalate` (the provisional 0.80 bar), except from the list check |

3. **A list claim** (`list_claim` with `failing` entries) is only a proposal: `caller_decides` says "comment or list may be wrong, caller decides". Check the code before editing either one.
4. **`stale_check: "not_checkable_detail_not_shown"`** means the comment names a detail the shown code does not hold, so its staleness was not checked. The action stands on everything else.

## Fields

| Field | When present | Content |
|---|---|---|
| `location`, `commit` | Always | `file:first line` of the comment, and the full commit it was read at |
| `kind` | Always | `docstring`, `jsdoc`, `header`, `declaration` (these four are doc comments), `inline`, `block` or `tool_directive` |
| `comment` | Always | The comment text; for a comment trailing code, only the comment part |
| `decided_by` | Always | `code` (settled without a model), `jev+rule`, `jev+rule after definition_fetch`, `jev+rule after find_code` (decided after more code was shown) or `escalated` |
| `reason` | `decided_by: code` | `tool_directive` (kept) or `commented_out_code` (removed; never for a doc comment) |
| `evidence` | Jev rows | The lines the comment was shown with: `before_comment` and `after_comment`, each with file, lines, commit and how it was reached |
| `probabilities` | Jev rows | Jev's answer to each closed question, from 0 to 1 |
| `decision_path` | Jev rows | The values the rule actually read, in order |
| `suggestion`, `argument_suggestions` | Jev rows | Jev's own pick of action and kind of fix; they only suggest phrasing, and the rule never reads them |
| `change_risk` | Jev rows | How much a reader would lose without the comment, 0 to 3; for ordering a queue |
| `request_sha256` | Jev rows | The hash of the exact request, to find it in the journal |
| `escalate` | When unsure | `route` (`calling_llm`), `fallback` (`human`) and `reasons` |
| `stale_check` | When not checkable | `not_checkable_detail_not_shown` |
| `definitions` | Before `fix_stale` | Code fetched for the names in the described code's conditions: `fetched` pieces, `unresolved` names (no definition) and `unknown` names (their file could not be parsed). Either kind of missing name escalates |
| `first_answer`, `search` | When more code was fetched or searched | The first answer before the extra code, and the search's outcome (`found`, `searched_not_found` or `not_yet_inspected`), places, history and any `unparsed_files` |
| `rewrite_job` | Decided `rewrite` | `doc_kind`, `old_comment`, `why_rewrite` (plain words with the deciding value), `signature` (the parser's reading of what it documents) and `documented_code` (`lines` and `code`, none for a module-level doc) |
| `list_claim` | Comment above a list it makes a claim about | `list`, `definitions`, `unresolved`, `unknown`, `entries` (each entry's probability of meeting the claim), `failing` and, when an entry fails, `caller_decides` |

## Example rows

These are real stored rows, recomposed with the current rule, in the row shape `classify.py` prints today. Long texts are cut and end in "...". Example 1 shows every field. The later examples leave out `evidence`, `suggestion`, `argument_suggestions`, `change_risk`, `request_sha256` and `probabilities`, which have the same shape as in example 1. There is no example of a decided `refactor_instead`: under the current rule it occurs in the stored data only as an escalation, with the same fields as example 3.

**1. `keep`, with staleness not checked** (a file header in Heedvane):

```json
{
 "location": "apps/web/src/app/(app)/quality/page.tsx:1",
 "commit": "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590",
 "kind": "header",
 "comment": "// Quality & Tech-Debt dashboard. SERVER component. KPIs + the domain breakdown\n// come from the api's resolved overview view. Health/churn/debt are genuinely\n/...",
 "evidence": {
  "before_comment": null,
  "after_comment": {
   "file": "apps/web/src/app/(app)/quality/page.tsx",
   "lines": [
    4,
    8
   ],
   "commit": "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590",
   "reached_by": "code_described_by_comment"
  }
 },
 "suggestion": {
  "choice": "keep",
  "confidence": 0.82,
  "probabilities": {
   "refactor_instead": 0.02,
   "keep": 0.85,
   "remove": 0.03,
   "fix_stale": 0.02,
   "link_owner": 0.01,
   "rewrite": 0.07
  }
 },
 "argument_suggestions": {
  "refactor_instead.kind": {
   "choice": "extract_function",
   "confidence": 0.2,
   "probabilities": {
    "rename_variable": 0.28,
    "extract_constant": 0.13,
    "extract_function": 0.4,
    "rename_function": 0.19
   }
  },
  "link_owner.kind": {
   "choice": "owner_doc",
   "confidence": 0.34,
   "probabilities": {
    "spec": 0.29,
    "adr": 0.15,
    "owner_doc": 0.56
   }
  }
 },
 "change_risk": {
  "score": 2.27,
  "confidence": 0.43,
  "probabilities": {
   "0": 0.02,
   "1": 0.11,
   "2": 0.45,
   "3": 0.42
  }
 },
 "request_sha256": "8e4b4ee8fabd2e0516dc658303e24f908326a74accdf0f04c2907bfe4600a794",
 "probabilities": {
  "code_is_hard_to_follow": 0.19,
  "explains_how_or_why": 0.71,
  "states_hidden_rule": 0.88,
  "teaches_needed_knowledge": 0.69,
  "points_to_owner": 0.12,
  "only_restates_code": 0.05,
  "has_time_reference": 0.08,
  "is_noise": 0.03,
  "contradicts_code": 0.08,
  "names_specific_detail": 0.71,
  "code_shows_same_detail": 0.28,
  "code_differs_from_comment": 0.15,
  "name_would_replace": 0.1,
  "addressed_to_agent": 0.06
 },
 "decision_path": {
  "stale": 0.15,
  "value": 0.88,
  "has_time_reference": 0.08
 },
 "action": "keep",
 "stale_check": "not_checkable_detail_not_shown",
 "decided_by": "jev+rule"
}
```

**2. `remove`** (an inline comment that only labels a field; its answers are from the gate replay):

```json
{
 "location": "apps/web/src/lib/dashboard-types.ts:130",
 "commit": "a3bde2aa8c1d548db862c933403dd97f35c85635",
 "kind": "inline",
 "comment": "// OWASP/CWE etc",
 "decision_path": {
  "stale": 0.12,
  "value": 0.29,
  "is_noise": 0.66,
  "has_time_reference": 0.02
 },
 "action": "remove",
 "decided_by": "jev+rule"
}
```

**3. Escalated: `keep` is only the best guess** (the value answer 0.56 sits inside the 0.40 to 0.60 band):

```json
{
 "location": "apps/web/src/components/app/guide-resume-banner.tsx:12",
 "commit": "39d8a3dcf6e9d744c329d7c18c8a3d46b8246590",
 "kind": "declaration",
 "comment": "// This banner is the single path back after a user exits incomplete setup.",
 "decision_path": {
  "stale": 0.2,
  "value": 0.56,
  "has_time_reference": 0.08
 },
 "action": "keep",
 "escalate": {
  "route": "calling_llm",
  "fallback": "human",
  "reasons": [
   "value 0.56"
  ]
 },
 "decided_by": "escalated"
}
```

**4. `rewrite`, with its rewrite job** (a JSDoc naming a ticket):

```json
{
 "location": "apps/web/src/lib/git-activity-server.ts:393",
 "commit": "a3bde2aa8c1d548db862c933403dd97f35c85635",
 "kind": "jsdoc",
 "comment": "/**\n * Resolve a Git activity read to an honest empty overview if it fails, so a single failing panel\n * (e.g. a Prisma error or `safeNumber` throwing on an ove...",
 "decision_path": {
  "stale": 0.18,
  "value": 0.66
 },
 "action": "rewrite",
 "decided_by": "jev+rule",
 "rewrite_job": {
  "doc_kind": "jsdoc",
  "old_comment": "/**\n * Resolve a Git activity read to an honest empty overview if it fails, so a single failing panel\n * (e.g. a Prisma error or `safeNumber` throwing on an ove...",
  "why_rewrite": [
   "names a date or ticket (#146)"
  ],
  "signature": {
   "kind": "FunctionDeclaration",
   "name": "gitActivityOrEmpty",
   "exported": true,
   "type_parameters": [
    "E",
    "R"
   ],
   "parameters": [
    {
     "name": "overview",
     "type": "Effect.Effect<GitActivityOverview, E, R>",
     "optional": false,
     "default": null
    },
    {
     "name": "rangeDays",
     "type": "number",
     "optional": false,
     "default": null
    },
    {
     "name": "organizationId",
     "type": "string | undefined",
     "optional": false,
     "default": null
    }
   ],
   "return_type": "Effect.Effect<GitActivityOverview, never, R>",
   "declared_type": null,
   "failure_type": "never",
   "thrown_or_failed": [],
   "heritage": [],
   "members": []
  },
  "documented_code": {
   "lines": [
    399,
    410
   ],
   "code": "export function gitActivityOrEmpty<E, R>(\n  overview: Effect.Effect<GitActivityOverview, E, R>,\n  rangeDays: number,\n  organizationId: string | undefined,\n): Ef..."
  }
 }
}
```

**5. `fix_stale`, escalated under the provisional 0.80 bar** (a docstring):

```json
{
 "location": "enginepy/host/pi_runtime.py:755",
 "commit": "65ce1972665975d20bb09f3638a6155f6fb3f9b9",
 "kind": "docstring",
 "comment": "        \"\"\"The full ping result: {ok, protocolVersion, catalogVersion, capabilities} on a current\n        sidecar. A missing result (or an error frame) means th...",
 "decision_path": {
  "stale": 0.71,
  "value": 0.82,
  "has_time_reference": 0.1
 },
 "action": "fix_stale",
 "definitions": {
  "fetched": [],
  "unresolved": [],
  "unknown": []
 },
 "escalate": {
  "route": "calling_llm",
  "fallback": "human",
  "reasons": [
   "fix stale below bar: code_differs_from_comment 0.71"
  ]
 },
 "decided_by": "escalated"
}
```

**6. A failing list claim: proposed, caller decides.** The same comment is also escalated, because its own stale answer sits below the bar:

```json
{
 "location": "enginepy/model/model_parts/queries.py:1091",
 "commit": "65ce1972665975d20bb09f3638a6155f6fb3f9b9",
 "kind": "block",
 "comment": "# verdict = the RAW engine claim status, kept honest/raw:\n# provisional | verified | overturned | hallucinated | uncertain | blocked. The\n# DERIVED excluded/ref...",
 "decision_path": {
  "stale": 0.63,
  "value": 0.89,
  "has_time_reference": 0.08
 },
 "action": "fix_stale",
 "definitions": {
  "fetched": [],
  "unresolved": [],
  "unknown": []
 },
 "list_claim": {
  "list": "_VERDICT_OF",
  "definitions": [],
  "unresolved": [],
  "unknown": [],
  "entries": {
   "\"verified\": \"verified\"": 0.84,
   "\"overturned\": \"overturned\"": 0.68,
   "\"hallucinated\": \"hallucinated\"": 0.63,
   "\"uncertain\": \"uncertain\"": 0.85,
   "\"blocked\": \"blocked\"": 0.86,
   "\"provisional\": \"provisional\"": 0.86,
   "\"narrowed-superseded\": \"narrowed-superseded\"": 0.15
  },
  "failing": [
   "\"narrowed-superseded\": \"narrowed-superseded\""
  ],
  "caller_decides": "comment or list may be wrong, caller decides"
 },
 "escalate": {
  "route": "calling_llm",
  "fallback": "human",
  "reasons": [
   "fix stale below bar: code_differs_from_comment 0.63"
  ]
 },
 "decided_by": "escalated"
}
```

**7. Decided by code: a tool directive is kept.** A commented-out code line is decided the same way, with `action: "remove"` and `reason: "commented_out_code"`:

```json
{
 "location": "apps/web/src/lib/pr-review-posting/review-draft.ts:196",
 "commit": "a3bde2aa8c1d548db862c933403dd97f35c85635",
 "kind": "tool_directive",
 "comment": "// eslint-disable-next-line complexity -- Review planning applies independent safety and presentation gates.",
 "action": "keep",
 "decided_by": "code",
 "reason": "tool_directive"
}
```
