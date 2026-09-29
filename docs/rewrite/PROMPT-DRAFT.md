# Rewrite guidance for the caller

**This is guidance for whoever writes the new comment, not something the tool runs.** The comment tool only classifies. It writes no comment text, calls no model to write one, and applies no repair. The calling agent, or another system that processes the tool's output, writes the new comment (Andre, 28.09.2026: "calling agent rewrites, our tool just classifies"). Nothing here has been sent to a model.

## What the tool hands over

The tool never deletes a docstring-like comment, meaning the doc comment of a module, class, function, type or field. It classifies such a comment "rewrite" instead. Any other comment may be classified "remove" (deleted). A decided "rewrite" row carries a `rewrite_job`, built by code with no model:
- `doc_kind` and `old_comment`: what kind of doc it is, and its text;
- `why_rewrite`: the reasons it failed, in plain words with the deciding answer;
- `signature`: the parser's reading of what it documents (parameters with types and defaults, return type, failures or raised errors, or a module's exported names);
- `documented_code`: the documented code and its lines (none for a module-level doc).

A list comment whose claim fails for some entries is only proposed. The row's `list_claim` names the `failing` entries and says `caller_decides`: "comment or list may be wrong, caller decides". The tool cannot tell which side is wrong, so a caller should check the code before editing either one (as worked example 1 shows).

A stale doc comment goes to the caller under the provisional 0.80 bar, with no rewrite job.

The rest of this page is a suggested way for the caller to write the new comment: a free static repair first (step 2), a model only when that repair does not fix every reason (step 3), then checks. If the caller sends a job to a model, the usual rule applies: only our own repositories (Heedvane and analysis-engine) go to a model, and only after the secret scan passes.

## Step 2: the free static repair

| Why it failed | Static repair | When it is enough on its own |
|---|---|---|
| Names a ticket or date, and does not tell history otherwise | Delete a parenthesised or bracketed group made only of the ticket and date tokens code already found (for example `(#146)`) | When "tells history" is below 0.5 and no ticket or date token is left afterwards |
| A list claim fails because the comment's enumeration leaves out entries | When the comment lists at least two of the list's entries with a single separator (`a \| b \| c`), insert the missing entries in code order | When every failing entry was simply missing from the enumeration |
| Parameters, return value or thrown errors are undocumented | Generate an `Args:` / `Returns:` / `Raises:` skeleton (Python, from `ast`) or `@param` / `@returns` / `@throws` tags (TypeScript, from the compiler's parser) | Only in a file whose other doc comments already use these sections. Otherwise the signature goes to the model as input |

**The skeleton rarely applies in our repositories.** Across each repository at HEAD, only 2 Heedvane files use `@param` and only 2 engine files use `Args:`. None of the 10 stored rewrite files uses either. Both repositories write prose doc comments, so a tag skeleton would break the house style. I kept the skeleton rule, but it only fires where the file already uses those sections.

**Of the 11 stored cases, the static repair would fix 2 on its own:** hv-r015, which only needs `(#146)` removed, and lr-06, whose list is missing one entry. The other 9 need the model:
- 4 Heedvane doc comments that tell history in their prose.
- 5 engine module docstrings flagged "only a title or label". Under Andre's 08:10 ruling ("Summaries are fine, keep"), these will most likely be kept rather than rewritten.

## Step 3: the prompt

The model receives the instructions below, followed by the packet as JSON. Code fills the reasons in plain words, without the probabilities.

```text
You rewrite one code comment. Reply with the new comment only: the full comment, including its
comment markers (/** */, //, """ or #) and the old comment's indentation. No explanation, no code
fence, and nothing before or after it.

You get:
- "documents": what the comment is attached to. "signature" is the parser's reading of the class,
  function or module (parameters with types and defaults, return type, failures or raised errors,
  exported names). "code" is the code itself, when it is a single declaration.
- "old_comment": the comment as it is now.
- "why_it_failed": the reasons a review gave. Fix exactly these and nothing else.
- "static_draft": a mechanical repair code already made, when there is one. Start from it.

How to fix each reason:
- "tells history" or "names a date or ticket": keep every statement about what the code does now
  and why. Drop how it came to be: ticket and pull-request numbers, dates, plan or stage codes,
  "originally", "no longer", "the old ... did", "converted from". A rule that was stated only
  through history gets stated in the present tense.
- "only a title or label": say in one or two sentences what a caller cannot get from the name and
  signature: the rule the code keeps, what it guarantees, how it fails, or who owns it. Take it
  from the code.
- "a better name would say it all": describe the contract the name cannot carry: what goes in,
  what comes out, and what happens on failure.
- "the list claim fails for these entries": make the comment's statement about the list true
  for every entry. Add the missing entries to an enumeration, or restate the condition so it
  covers them. You edit only the comment, never the list.

Rules for every rewrite:
- Every statement must be supported by the signature or the code you were given, or be carried
  over unchanged from the old comment when it concerns code you were not shown and none of the
  reasons concerns it. Do not add behaviour you cannot see.
- Keep the old comment's words wherever they are still right. This is an edit, not a new text.
- Be no longer than the old comment. Shorter is better when nothing true is lost.
- Name code identifiers exactly as they appear in the code, formatted the way the old comment
  formats them (for example in backticks).
- Do not mention the review, these instructions, or the fact that the comment was rewritten.
```

The packet follows as JSON:

```json
{"language": "...", "doc_kind": "jsdoc | docstring | header | declaration | line",
 "documents": {"signature": {...}, "code": "..."},
 "old_comment": "...", "why_it_failed": ["..."], "static_draft": null}
```

## Checking the new comment

This step is all code, except the last check.

1. **Markers and indentation:** the new comment uses the same comment markers and indentation as the old one.
2. **Tickets and dates:** code finds no ticket or date token in it, using the same finder as the review.
3. **Identifiers:** every identifier in backticks appears in the documented code, in the signature, or in the old comment.
4. **Length:** it is no longer than the old comment.
5. **Lists:** for a list comment, every entry of the list appears in the enumeration, or the enumeration is gone.
6. **The review again:** the round-5 questions are asked about the new comment, which is a paid Jev call, and rule A must reach "keep" without escalating.

A comment that fails any of these checks is not applied; the caller keeps the old comment and the classification stands.

## Worked example 1: lr-06, fixed by the static repair (no model)

`enginepy/model/model_parts/queries.py:1091`, from the list round. The comment enumerates the raw statuses of `_VERDICT_OF`:

```text
# verdict = the RAW engine claim status, kept honest/raw:
# provisional | verified | overturned | hallucinated | uncertain | blocked. The
```

The list has a seventh entry, `"narrowed-superseded"`. Jev put it at 0.15 and Sol labels it false, so the list check decided "fix stale comment". Before choosing which side to change, I checked the code. `narrowed-superseded` is a real stored status: `narrowed.py:224` writes it on the claim itself, and `foundation.py:18` lists it with the others. So the comment is out of date, and the list is right. The enumeration uses one separator and holds six of the seven entries, so the static repair inserts the missing one:

```text
# verdict = the RAW engine claim status, kept honest/raw:
# provisional | verified | overturned | hallucinated | uncertain | blocked | narrowed-superseded. The
```

The checks pass without a model, apart from the last one (the review again), which needs a Jev call. One caveat applies to the list case in general. A failing entry shows that the comment and the code disagree, but not which side is wrong. Here I checked by hand, but the tool cannot, so a list rewrite should reach the calling agent as a proposed edit, not an applied one.

## Worked example 2: hv-r147, needs the model

`apps/web/src/lib/code-host/credential-service.ts:252`, from the doc-rewrite sweep. The reason given is "tells history". There is no ticket or date to delete, so the static repair does nothing, and the model gets this packet (the code is shortened here):

```json
{"language": "typescript", "doc_kind": "jsdoc",
 "documents": {"signature": {"name": "markFailureOnError", "parameters": [
     {"name": "cause", "type": "Cause.Cause<CodeHostFailure>"},
     {"name": "input", "type": "{ database: PrismaClient; connectionId: string; organizationId: string; credentialId: string; workerId: string; now: Date; }"}],
   "return_type": "Effect.Effect<void>"},
   "code": "function markFailureOnError(cause, input): Effect.Effect<void> {\n  if (Cause.hasInterruptsOnly(cause)) {\n    return releaseRefreshLock(...).pipe(recoverFailures(... console.error ...));\n  }\n  const failed = ...;\n  const category = failed instanceof CodeHostError ? failed.category : \"transient\";\n  return markCredentialFailure({ ...input, category }).pipe(recoverFailures(... console.error ...));\n}"},
 "old_comment": "/** Runs after `rotateCredential` fails for any reason: a typed `CodeHostFailure`, an interruption,\n *  or a defect (a malformed encrypted envelope). Every non-interruption cause marks the credential's\n *  last error and, for an authorization failure, revokes it and degrades the connection -- exactly\n *  as the original Promise-based `catch` did for both typed and untyped throws. Marking never loses\n *  the original cause: ...",
 "why_it_failed": ["tells history"],
 "static_draft": null}
```

A good answer drops only the history clause, "exactly as the original Promise-based `catch` did for both typed and untyped throws", and keeps everything else word for word. The revoking and degrading happen inside `markCredentialFailure`, which the packet does not show. Since no reason concerns that statement, it is carried over unchanged. I wrote this answer by hand to show the target; no model produced it.

```text
/** Runs after `rotateCredential` fails for any reason: a typed `CodeHostFailure`, an interruption,
 *  or a defect (a malformed encrypted envelope). Every non-interruption cause marks the credential's
 *  last error and, for an authorization failure, revokes it and degrades the connection. Marking
 *  never loses the original cause: a failure to mark is only logged, and `onError`'s finalizer
 *  effect re-raises the original cause once this completes.
 *
 *  An interrupt-only cause (a shutdown mid-refresh) never earns a failure category -- there is no
 *  error to categorize -- but the refresh lock still must be released, or a shutdown mid-rotate
 *  holds it for the full `REFRESH_LEASE_MS` window and starves every other refresher until it
 *  expires on its own. */
```

The checks: markers and indentation unchanged; no ticket or date; every backticked name (`rotateCredential`, `CodeHostFailure`, `onError`, `REFRESH_LEASE_MS`) is in the old comment; 1 line and 91 characters shorter. The last check, the review again, would need a Jev call.

## Settled by Andre (28.09.2026)

1. **Who writes:** the calling agent or another system; the tool only classifies.
2. **Lists:** only proposed, never applied by the tool; the row says the caller decides.
