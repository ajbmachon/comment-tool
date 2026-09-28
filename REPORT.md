# Comment-value tool: A vs B vs escalation (2026-09-28)

The data files this report names by relative path (round folders, frozen records, labels, journals) live in `~/.claude/handoffs/effect-2026-09-25/comment-tool`, not in this repository.

Andre, both readouts ran on all 32 comments. Code combining the yes/no answers (A) matched Sol on 22, and the action Jev picks directly (B) matched on 25. With escalation at 0.60, the tool decided 12 of 32 on its own and matched Sol on 11 of those 12. The other 20 were escalated, and those include 11 of the 12 comments where A or B was wrong.

The harness would not let me write `comment-tool/REPORT.md`, since agents in my role must return findings as text. Everything below is the report; the data and scripts are in `~/.claude/handoffs/effect-2026-09-25/comment-tool/`.

## Results

| Readout | Decided automatically | Match Sol, of decided | Escalated | Of the 12 A-or-B mistakes, how many escalated |
|---|---|---|---|---|
| A alone | 32 of 32 | 22 of 32 | 0 | – |
| B alone | 32 of 32 | 25 of 32 | 0 | – |
| A+B, escalate at 0.50 | 20 of 32 | 18 of 20 | 12 | 10 |
| **A+B, escalate at 0.60** | **12 of 32** | **11 of 12** | **20** | **11** |
| A+B, escalate at 0.70 | 7 of 32 | 7 of 7 | 25 | 12 |

The 0.60 cut-off comes from the self-consistency cookbook and was not tuned on these 32 comments.

- **Escalation targets the real mistakes.** Of the 20 escalated comments, 11 were real errors and 9 were cases A and B both got right.
- **The one mistake decided automatically is `en-09`.** Both readouts said "fix stale comment" with 0.67 on the top action. Jev read "no file-count cap" as contradicting a per-agent batch size below it; Sol did not.
- **It escalates too much.** 20 of 32 is about 63 of every 100 comments; the cookbook escalated 26 of every 100.
- **Routing.** Every escalation would go to the calling LLM first, meaning the agent applying the edit, which has the whole file. A human only sees it if that agent can't decide. This is recorded, not built.

## Why the tool went wrong

1. **A turns section titles into "rename" instead of "remove"** (`en-06`, `en-08`, `en-15`, `hv-08`, `hv-21`). A title like "# Dispatch" above `def _dispatch` gets "a name would replace it" = yes, because the existing name already says it. Sol answered yes too, and my rule checks rename before remove, so this is a defect in my rule, not in Jev.
2. **B's action pick is often split.** 13 of 32 comments had a top action probability below 0.60, mostly keep against rewrite when a useful comment carries a date or ticket number. That is where most escalations come from.
3. **Two cases where Andre's rule and Sol disagree:**
   - `hv-16` contains "per codex #6". Your rule counts ticket and PR numbers as a time reference, so A says rewrite. Sol says keep, and I would treat Sol's label as the one to revisit.
   - `en-04` ("the subprocess used to exec") is history and Sol says rewrite. Jev put history at only 0.38, so both readouts kept it.
4. **My code cut produced one false "stale" label** (`hv-17`). The comment says "Exported (read-only)", and the exported `COST_CONVERTIBLE_BINDINGS` sits just below a blank line that ended the case. Sol's "fix stale" is right for what it was shown, but wrong about the real file.
5. **Sol's labels are good but not gold.** An earlier Sol pass over 18 of the same comments gave the same answer on 172 of 180 labels; the 8 changes are all borderline.

## Question design and call counts

**Per call:** 14 questions, all in one call per comment:
- 10 yes/no questions, including "addressed to an AI agent", which is recorded only;
- 1 Score, used only to rank the review queue;
- 3 Choices: the action plus two argument choices;
- 0 "stated" questions, because no argument is optional.

**Two changes to the proposed actions:**
- I folded "rewrite as a pointer to the owning doc" into "link to owner", because two overlapping options split the probability.
- I added "fix stale comment" so a comment that contradicts the code has a correct action.

**Kept by code, never sent to Jev:**
- docstrings, file headers and tool directives;
- a comment attached directly to a function, class or type.

That takes 9 of the 41 seeded comments, leaving 32 for Jev.

**Found by code and fed into the rule:** dates, ticket or PR numbers, a TODO without an owner, dividers and commented-out code. The secret scan found nothing.

**How well Jev's yes/no answers matched Sol:**

| Question | Matched Sol | Notes |
|---|---|---|
| Addressed to an AI agent | 32 of 32 | |
| Only a title or label | 32 of 32 | |
| States a hidden rule | 31 of 32 | |
| Only restates the code | 30 of 32 | |
| A name would replace it | 30 of 32 | |
| Tells history | 29 of 32 | |
| Teaches needed knowledge | 28 of 32 | |
| Contradicts the shown code | 28 of 32 | |
| Points to the owner of a rule | 27 of 32 | Jev over-reads phrases like "one owner" as a pointer |
| Explains hard code | 24 of 32 | Weakest; the Meta Builder design review also flags it as two questions in one |

The Score landed within half a level of Sol's on 19 of 32.

**Calls made:**
- the Meta Builder design review on 2 representative comments: 15 calls each, 30 in total;
- the pilot: 32 calls, a median of 0.6 seconds each.

The pilot ran at 01:50 Berlin. The Meta Builder design review found no critical problems, and its free structural check on all 32 had no findings. The installed Meta Builder is now version 0.4.0; it was 0.3.1 when I started.

## Recommendation

Use **A to decide whether a comment needs to change, B to decide how, and escalate every disagreement**. Neither works well enough alone: A has the ordering defect, and B's pick is too split to act on without A.

Next steps, to be measured on new comments rather than these 32:

1. In rule A, check "title or label" before "rename", and reword the name question to "a *better* name than the current one would carry this".
2. Split "explains hard code" into "the code is hard to follow" and "the comment explains how or why".
3. Continue the code cut below a comment past blank lines.
4. Have Sol blind-label 30 fresh comments and rerun at the unchanged 0.60. Success means at least 70 of every 100 comments decided automatically, with at least 90 of every 100 of those matching Sol.


# Round 2: 30 fresh comments (2026-09-28 02:05 Berlin)

The fresh round fails the success bar you set. At the fixed 0.60 cut-off, the tool decided only 8 of 30 comments on its own (we wanted at least 70 of 100), and 6 of those 8 matched Sol (we wanted at least 90 of 100).

The main cause is the action Jev picks directly (readout B), which is much worse on new comments. Code combining the yes/no answers (readout A) held up at 22 of 30.

The round finished at 02:05 Berlin. I made all four changes before running it:
- Rule A now checks "title or label" before "rename".
- The name question now asks for a better name than the current one.
- "Explains hard code" is split into two questions.
- The code cut below a comment now continues past blank lines.

The 30 comments came from files none of the first 41 came from, picked by a fixed hash order with one comment per file. Every comment got a Jev answer and a blind Sol label, with no errors. Sol's actions were 22 keep, 3 remove, 3 rewrite and 2 refactor.

| Readout | Decided automatically | Match Sol, of decided | Escalated | A-or-B mistakes escalated |
|---|---|---|---|---|
| A alone | 30 of 30 | 22 of 30 | 0 | – |
| B alone | 30 of 30 | 14 of 30 | 0 | – |
| A+B, escalate at 0.50 | 15 of 30 | 9 of 15 | 15 | 10 of 16 |
| **A+B, escalate at 0.60** | **8 of 30** | **6 of 8** | **22** | **14 of 16** |
| A+B, escalate at 0.70 | 1 of 30 | 1 of 1 | 29 | 16 of 16 |

**Why B collapsed.** Jev's pick of the action is often split and does not agree with its own yes/no answers.
- It picked "link to owner" 5 times and "fix stale comment" 3 times where Sol said keep. On those same comments, Jev's own "contradicts the code" answer was low.
- Its top action probability was below 0.60 on 19 of 30 comments, which is what drives most of the escalations.

**The yes/no answers themselves are good.** Jev matched Sol on 25 to 30 of 30 for each of the 11 questions. The weakest was "teaches needed knowledge" at 25. The two halves of the old "explains hard code" question now score 27 and 29, where the combined question scored 24 of 32 last round. The Meta Builder design review no longer flags either half as two questions in one. The reworded name question does get mild clarity warnings, between 0.55 and 0.64.

**Why A missed 8.** When I apply rule A to Sol's own yes/no labels, it matches Sol's chosen action on only 24 of 30. So even perfect Jev answers cannot reach the 90-of-100 bar against Sol's action labels.
- **Sol is stricter than its own answers.** On hv-f02, hv-f10 and hv-f15, Sol's own answers say the comment has value, yet Sol chose "remove". Andre asked for "a little more leeway", which points to the rule's "keep".
- **A date inside a file name counts as history.** On hv-f09, an ADR name that ends in a date makes the code-found facts treat it as a time reference, so the rule says "rewrite" while Sol keeps the pointer. That is a defect in my code.
- **One judgment call.** On hv-f08, "before this service was an Effect" is history with no other content; Sol wants a rewrite and the rule says remove.
- **Only 3 misses are Jev's fault.** Jev missed the history in "4c billing selection" (en-f10), missed the rename on en-f05, and on en-f13 Sol's own answers disagree with Sol's own action.

**A post-hoc check, not pre-registered.** If B is dropped and A escalates only when an answer it depends on falls between 0.40 and 0.60, the tool decides 27 of 30 on its own and matches Sol on 21 of those 27. That clears the automation bar but still misses the 90-of-100 bar.

**What I'd do next:**
1. Drop B's action pick as a deciding input. Keep it only as a suggestion for how to phrase the edit.
2. Stop code from reading dates inside file, path or ADR names as time references.
3. Decide what counts as the right answer. Either it is Sol's yes/no labels combined by the rule, or it is Sol's direct action pick. Sol's direct pick is stricter than Andre's leeway. This choice decides whether the tool is at 24 of 30 or has room to reach the bar, so Andre should make it.

The Jev and Sol calls for this round were 30 each, plus one Meta design review of 15 calls.

Everything is in `~/.claude/handoffs/effect-2026-09-25/comment-tool/`. The fresh cases, candidates, Jev answers and Sol labels are in the `round2/` folder. The questions are in `questions.json`, the rule is in `compose.py` and the scoring is in `score_round.py`. `REPORT.md` has not been updated with this round; it still holds the first report you saved.


# Rescore after dropping B as decider (post-hoc)

Both rounds are rescored from the stored answers, with no new Jev or Sol calls. Against Sol's own yes/no labels combined by the rule (b), round 2 meets both bars: 27 of 30 decided automatically, with 26 of 27 matching. Against Sol's direct action pick (a), it decides as much but only 22 of 27 match. I haven't picked a reference.

Both rounds are now after-the-fact results, not pre-registered. Round 1's rule order was fixed after I had seen those 32 comments, and round 2 is rescored with rules changed after seeing its answers.

I made both changes first:
1. Readout A decides alone and escalates when an answer it depends on sits strictly between 0.40 and 0.60. B's action pick is now only a suggestion for how to phrase the edit.
2. Code no longer counts a date inside a file, path, ADR or incident name as a time reference; a date standing on its own still counts.

| | Round 1: (a) Sol's direct action | Round 1: (b) Sol's labels combined by the rule | Round 2: (a) Sol's direct action | Round 2: (b) Sol's labels combined by the rule |
|---|---|---|---|---|
| A alone matches the reference | 27 of 32 | 27 of 32 | 23 of 30 | 28 of 30 |
| Decided automatically | 28 of 32 (88 of 100) | 28 of 32 (88 of 100) | 27 of 30 (90 of 100) | 27 of 30 (90 of 100) |
| Match, of those decided | 25 of 28 (89 of 100) | 25 of 28 (89 of 100) | 22 of 27 (81 of 100) | 26 of 27 (96 of 100) |
| Escalated | 4 | 4 | 3 | 3 |
| A's mistakes that were escalated | 2 of 5 | 2 of 5 | 2 of 7 | 1 of 2 |

The bars were at least 70 of 100 decided automatically and at least 90 of 100 of those matching Sol.
- **Automation:** every column clears it.
- **Match:** only round 2 against reference (b) clears it. Round 1 misses by a hair (89) under both references, and round 2 against (a) reaches only 81.

**How far apart the two references are:**
- In round 1 they agree on 31 of 32 comments, so the choice barely matters there.
- In round 2 they agree on only 25 of 30. On hv-f02, hv-f10 and hv-f15, Sol's own labels say the comment has value, yet Sol's direct pick was "remove". On en-f13 the labels say keep and the pick was "refactor"; on hv-f08 the labels say remove and the pick was "rewrite". This is the whole difference Andre is deciding.

**B as a suggestion** matched Sol's direct pick on 25 of 32 in round 1 and 14 of 30 in round 2, so it is not reliable enough even for phrasing.

**Where A still goes wrong under both references:**
- **Stale-comment answer fires too often:** en-09, hv-01 and hv-16 in round 1 come out as "fix stale comment". Two of them were escalated.
- **Code cut too short:** hv-17 in round 1. Round 1 Jev saw the old, shorter cut, and the fixed cut applies only to round 2 and later.
- **History missed:** en-04 in round 1 and en-f10 ("4c billing selection") in round 2.
- **Rename missed:** en-f05 in round 2, which was escalated.

The new rescoring script is `comment-tool/rescore.py`. I haven't changed `REPORT.md`.

**Andre 2026-09-28 ~02:15 Berlin:** answer key = the rule applied to Sol's yes/no labels (reference b). Sol's direct pick is shown beside it but does not count.


# Round 3 (pre-registered) and billing pass

Round 3 failed the registered bar on accuracy. The tool decided 26 of 30 comments on its own (87 of 100, bar 70), but only 23 of those 26 matched the answer key (88 of 100, bar 90). The billing pass is done and found 3 removals, not the 5 you asked to see.

## Round 3: the measurement registered in advance

Before any round 3 Jev call, I froze `questions.json`, `compose.py`, `extract_cases.py` and `build_candidates.py`. Their hashes are in `round3/FROZEN.txt`, and they still matched after scoring. The 30 comments came from files not used in rounds 1 or 2, in the same hash order, one per file.

The one change before the freeze was to the stale-comment question. It now counts a contradiction only when the comment and a line in the shown code talk about the same thing. A different quantity, or a use of the code somewhere else, no longer counts. On the rounds 1 and 2 answers, that dropped the false alarms from 3 to 1 (`en-09` still fires).

| Result | (b) Sol's labels combined by the rule (the answer key) | (a) Sol's direct pick (not counted) |
|---|---|---|
| Readout A alone matches | 26 of 30 | 25 of 30 |
| Decided automatically | 26 of 30 (87 of 100) | 26 of 30 |
| Match, of those decided | **23 of 26 (88 of 100)** | 22 of 26 (85 of 100) |
| Escalated | 4 | 4 |
| A's mistakes that were escalated | 1 of 4 | 1 of 5 |

The two references agreed on 28 of 30 comments. Rounds 1 and 2 were rescored after the fact at about 89 to 96 of 100; round 3 is the honest number at 88.

There were three mistakes the tool decided without escalating:
- **`en-g05`**, "Code absent from the packet and a packet too large to send are different causes." Jev read it as a hidden rule (0.69). Sol read it as restating the code, so the answer key says remove.
- **`hv-g01`**, "Complete coverage: a verdict for every page…". Sol says it restates the code; Jev gave that 0.40, just below the escalation band. The answer key says remove.
- **`hv-g15`**, the tab-title comment with `(#671)`. Jev's stale-comment answer was 0.60, just past the band, so A picked "fix stale". The answer key says rewrite.

The stale-comment question still fires falsely even after the rewording.

## Billing pass

This ran on Heedvane `apps/web/src/lib/billing` at origin/develop (`911a1f74`). It only reads files; the one side effect is `git fetch origin develop` in `~/Projects/heedvane`, which updates the remote-tracking branch but no files.

There were 169 comments. Code decided 45 of them, all as keeps. The secret scan ran before any Jev call, the other 124 went to Jev, and the scan blocked none.

| Action | Count |
|---|---|
| Keep | 129 (45 decided by code, 84 by Jev plus the rule) |
| Rewrite | 16 |
| Remove | 3 |
| Refactor | 0 |
| Escalate | 21 |

Of the 21 escalations, 11 are unsure about the stale-comment question and 7 about the history question.

The results are in `~/.claude/handoffs/effect-2026-09-25/comment-tool/pass/heedvane-apps-web-src-lib-billing.jsonl`. Each line has the file and line, the comment, the action, its argument, B's phrasing suggestion, and for escalations the unclear question.

## The removals

There are only three decided removals, all section titles in `credit-ledger-reason.ts`:
1. `apps/web/src/lib/billing/credit-ledger-reason.ts:26` `// -- Currently written ----...`
2. `apps/web/src/lib/billing/credit-ledger-reason.ts:75` `// -- Internal ----...`
3. `apps/web/src/lib/billing/credit-ledger-reason.ts:84` `// -- Classification ----...`

No escalated case has remove as its proposed action, so there were no more to show. Nothing has been edited.

## What to fix next

These would go into a round 4, frozen again before it runs:
- The stale-comment question needs one more principled narrowing, or a stricter bar than the others.
- The "only restates the code" question misses short summary comments.

The billing pass ran with a runner that has since been replaced; the current runner is `comment-tool/sweep.py`. Its answer store is keyed by the exact request, so a rerun makes no repeat calls for unchanged comments.


# Round 4: the stale-comment question split into three (pre-registered)

Round 4 met both goals set before it ran. The tool decided 27 of 30 fresh comments on its own (90 of 100; the goal was at least 70), and 25 of those 27 matched the answer key (93 of 100; the goal was at least 90). Round 3, measured the same way, decided 26 of 30 and matched 23 of 26 (88 of 100), so it missed the accuracy goal.

The split of the stale-comment question accounts for only part of that gain. On the same Jev answers and the same Sol labels, the old single question would have decided 26 of 30 and matched 24 of 26 (92 of 100). The split added one correct decision (en-h14). The rest of the difference is a new set of comments, so it is not an effect of the change.

## What was measured, and how

- **Andre's approval:** "Run it as written", 04:25 Berlin, for the three stale-comment questions and the search stop question.
- **What was frozen, and when:** the questions, the rule, the fact rules, the comment discovery, the directive, the search step with its stop question, the sampler, the runner, the scoring script, the journal and the Sol labeller. All were hashed into `round4/FROZEN.txt` at 04:19 CEST. The 30 comments' hash was added at 04:36, before any model call. All 13 hashes still matched after scoring.
- **The library:** jev-navigator at 9e2a483, exported to a fixed snapshot.
- **The comments:** 15 Heedvane comments from outside `apps/web/src/lib` (so none come from the lib sweep) and 15 analysis-engine comments. They were taken at the round-3 commits, one per file, in a fixed hash order, from files no earlier round used. Only whole-line comments that code does not decide by itself were eligible, which is the kind of comment the labels cover.
- **The evidence shown with each comment:** the 8 lines above the comment and the whole code block `code_described_by_comment` returns. Before any call, all 30 packets were rebuilt from git objects and matched the labelled ones exactly.
- **The answer key:** the round-4 rule applied to Sol's blind yes/no labels on the exact packet. 30 labels, 0 errors, and all 30 are bound to their packet by hash.
- **Calls:**
  - Jev: 38 in the run, from 04:37 to 04:38 Berlin. These were 30 first answers, 2 answers asked again after a search, and 6 search calls.
  - Jev: 54 in the history replay, at 04:40.
  - Meta Builder: one paid review, which wrote 92 receipts.
  - Sol: 30 calls, finished by 04:42, with a median of 25 seconds each.
  - All exchanges are journalled (92 requests and 92 raw responses, all HTTP 200), and every heavy job ran through run-slot.

## Results

| | Round 3 (frozen) | Round 4 | Round 4 answers, old stale rule |
|---|---|---|---|
| Rule alone matches its key | 26 of 30 | 26 of 30 | 26 of 30 |
| Decided on the first answer | 26 of 30 | 27 of 30 | 26 of 30 |
| Of those, matching the key | 23 of 26 | 25 of 27 | 24 of 26 |

The two mistakes that were decided without escalation:
- **hv-h12** ("Clear the cookie so a later connect cannot repeat the attribution attempt…"): Jev answered all three stale parts yes (0.82, 0.89 and 0.70), so the rule decided "fix stale comment". Sol says the code matches the comment, and the key says keep. The old single question fired here too (0.79).
- **en-h06** ("statuses_not is a port EXTENSION… parity with the legacy tool"): the rule keeps it, but Sol read "legacy tool" as history, so the key says rewrite. Jev put history at under 0.5. This is not a stale-comment case.

## The stale-comment split in detail

- **"Fix stale comment" proposed by Jev plus the rule:** 3 times under either rule. The new rule fired on hv-h12, en-h10 and en-h13; the old one on hv-h12, en-h13 and en-h14. The key has 2 stale comments, en-h11 and en-h13.
- **Found correctly:** en-h13, under both rules.
- **Wrong and decided:** hv-h12, under both rules.
- **Wrong but escalated:** the old rule on en-h14 (0.56). The new rule on en-h10, where the weakest of the three answers was 0.58.
- **Missed by both rules:** en-h11. Sol answered yes to all three parts, but Jev put "the code's version differs" at 0.15.
- **The one decision that changed:** en-h14. The old question put it in the escalation band as stale; with the split, the weakest part was 0.39, so the rule kept it, which matches the key.

Jev's yes/no answers agreed with Sol on 26 of 30 for "names a specific detail", 28 of 30 for "the code shows that detail" and 27 of 30 for "the code's version differs". The old single question also agreed on 27 of 30. The weakest questions in this round were "the code is hard to follow" (20 of 30) and "teaches needed knowledge" (21 of 30). Neither was changed in round 4.

**The ambiguity signal on question 3.** Meta Builder rated the reference in question 3 as ambiguous at 0.77 on the packet it reviewed (the old question scored 0.70 on the same check). Jev and Sol disagreed on question 3 for 3 of 30 comments: hv-h12, en-h10 and en-h11. By my own reading, each of those three comments names more than one detail. hv-h12 says the cookie is cleared, that it is cleared even on a non-match, and that the reward is idempotent. en-h10 names `self.repo = str(repo)` and how the run configuration now arrives. en-h11 names a list of filenames and a separate content check "below". This reading is mine, not a reference label, and I did not count how many of the 27 agreeing comments also name several details. So it is consistent with the "which detail?" reading of the flag, but it does not prove it. The proposed rewording ("for at least one of them") would need its own blind-labelled round.

## The code search with the history stop question

3 of 30 comments escalated on the first answer, and each got one search. All 3 searches ended as "found" on the first place they opened, the function around the comment, after 2 calls each (one to open the place, one for the stop question).
- en-h10 and en-h11 were decided after the wider code was shown. Both came out as rewrite: en-h10 matches the key, and en-h11 does not, because it is the missed stale comment.
- en-h09 stayed escalated. The stop question said yes (0.94), but the opened function added no code beyond what the comment was already shown with.

No search in this round had to go past one step, so round 4 does not show whether a longer history helps.

## Replaying stored searches with a growing history

This measurement is thin. Only 14 of the 199 stored lib-sweep searches opened two or more places. Two of those were one comment text, "// 2, 3, or 4", searched at two lines of page-sections.ts; my first replay grouped searches by comment text and merged them into one curve. With both left out there are 13 searches and 49 history sizes. The numbers below are the corrected ones. The longest history was 3682 tokens, about a tenth of the 32,000 tokens the history may use. Nothing was labelled at this point, so the replay shows where the stop question's answer stops changing, not whether it is right; the labelled check is in the next section.

- How much the stop probability moved when one more opened place was added:
  - from 1 to 2 places: 0.06 on average over 13 searches (largest 0.13);
  - from 2 to 3: 0.05 over 12 (largest 0.13);
  - from 3 to 4: 0.03 over 4 (largest 0.06);
  - from 4 to 5: 0.01 over 4;
  - from 5 to 6: 0.02 over 3.
- Within these short searches, the answer settles after about four opened places. The replay says nothing about long histories.
- The stop question says yes (0.8 or more) already on the first opened place in 8 of the 13 searches. The search's own per-place check judged none of the opened places to be the target in 9 of the 13. The labelled check below shows which of the two is right.

## What I would change next (not done)

1. Put the question-3 rewording ("for at least one of them") to Andre as a variant, and measure it on fresh blind-labelled comments.
2. Before letting the history stop question end searches on its own, measure it against labels where it disagrees with the per-place check.
3. After this report, move the library pin to c41d51d, 6857bac and 02e6790, as agreed. Then delete our JSDoc split and per-search Judge workarounds and the duplicate request-hash code, and re-measure the facts on the stored comments.

## After round 4: library re-pinned to a9efa1b

This was done after round 4 was scored, as agreed. `round4/frozen-sources.tar.gz` keeps the 12 round-4 sources exactly as they ran; its hash is in `round4/FROZEN.txt`.

- **Pin:** jev-navigator a9efa1b, the committed head of feat/library-v0. It contains c41d51d (JSDoc and line comments stay separate), 6857bac (per-search budgets), 02e6790 (every result carries its request hash) and three later fixes: dropped comments come back with a reason, `code_above_comment` returns no code when none sits above, and the capturing client answers Score questions.
- **Removed from our side:** our JSDoc split, the separate Judge per search, the serialised store wrapper and our own request-hash recomputation. The library now does each of these.
- **Labels stay valid:** under the new pin, the 30 round-3 and 30 round-4 labelled packets rebuild byte-identically.
- **How the comments moved:** measured with no model call on the lib at a3bde2aa (`discovery_snapshot.py`).
  - Before the re-pin the tool found 5302 comments; after it, 5305. All 5302 earlier comments are still found at the same place.
  - Facts are identical on all 5302 of those.
  - Code kept 4318 before and 4325 after; 983 went to Jev before and 979 after.
  - 6 comments changed route. Four `eslint-disable` lines with written justifications are now tool directives, which code keeps. The comment at `analysis-provider-config.ts:266` ("An explicit model must be in the actor's allowlist") now counts as the doc of the declaration directly below it, which code keeps; before, our split sent it to Jev. One comment at `github-app.ts:1293` went the other way, from kept by code to sent to Jev.
  - 237 comments changed kind from header to JSDoc. They stay kept by code, so no action changes.


# After round 4: the search stop question, question 3, and the two shared mistakes

## Library re-pinned to 061baa9

061baa9 is a9efa1b plus the search's decision history. With no model call, its comment discovery on the lib at a3bde2aa is identical to a9efa1b: the same 5305 comments, in the same places, on the same routes. So the route moves reported in the re-pin section above are the whole change. The 60 labelled packets from rounds 3 and 4 rebuild byte-identically, and our facts match the measured facts on 5392 of 5392 stored comments. We never wrote a shape shim for the capturing client or a noise filter of our own, so there was nothing more to delete. We pass no drop rule, so every comment found is kept and counted.

One thing to know: at 061baa9 every opened place in the search history carries the per-place check's own probability and verdict, and the stop question reads that history. The stop question now sees the other check's answer, so the two are no longer independent. The measurement below was taken on the replayed histories, which hold only the fetched code.

## Is the stop question's early yes wrong? Mostly not.

**How it was measured:**
- Sol labelled, blind, the 13 replayed lib-sweep searches plus round-4 en-h09. That is 14 searches and 50 fetched places.
- One question per piece of code: "does this code contain the statement, value or condition the comment is about?". It was asked of the code shown with the comment and of every fetched place.
- Sol saw no Jev answer, no search verdict and no stop probability.
- There were 15 Sol calls. One reply failed to parse and was labelled again. The labeller now keeps every raw reply, because the failed call's raw reply was lost.

**Results:**
- **The stop question said yes 34 times, and 33 of those were right:** one of the places fetched so far did hold the target. Its one wrong yes was currency.ts:170 on the first place (0.81); the target was only fetched at the second place. It said "unsure" 16 times, and 14 of those were cases where the target had already been fetched. It never said no.
- **The search's own per-place check is the strict one.** Of the 23 places Sol says hold the target, it said yes on 4, unsure on 17 and no on 2. Of the 24 places Sol says do not, it said no on 12 and unsure on 12, and never yes. 3 places were labelled ambiguous. So the disagreement seen in the replay comes from the per-place check being too strict, not from the stop question leaning towards yes. This is not the pattern the old stale question had.
- **Is the early yes caused by code the comment was already shown with?** In the replay the stop question saw only the fetched code, never the shown code. But the first place a search opens is always the function around the comment: it overlapped the shown code in 14 of 14 searches, and Sol labelled that first place as holding the target in 12 of 14. Sol also says the shown code itself already held the target in 12 of 14 searches.
- **The early yes is right because the search re-fetches code the comment already had.** Separating shown from fetched code in the state will matter little; not starting these searches matters more.

**The searches should mostly not have started.** They were triggered by any escalation reason:
- whether the comment has value: 8;
- whether it tells history: 3;
- whether it is a problem (restates the code or is noise): 3;
- whether it is stale: 2.
Only the stale reasons depend on finding more code. After the search, 13 of the 14 comments stayed escalated.

**en-h09 is the clearest case.** It escalated on the history question alone (0.41), which is a question about the comment's own words. Sol says the shown code already held what the comment is about (`if insights_path.exists(): durable_delete(insights_path)`). The search re-fetched the enclosing function and the stop question said yes (0.94), correctly, but nothing it fetched could settle a history question.

**What this means:**
- **The stop question can end searches, but only as a signal to stop.** Its yes was right 33 of 34 times on 50 places from 14 searches. That is small, and one of the 34 was wrong, so it should only stop a search, never decide an edit.
- **Start a search only for the stale reason,** and only when the detail the comment names is not already in the shown code.
- **The per-place check's "no" is too strict** to be read as proof that the code is absent.

As agreed, none of this is wired into a production path yet.

## Question 3 and comments that name several details

To give the three question-3 disagreements a base rate, I wrote one mechanical rule, `multi_detail.py`. It splits a comment into clauses and counts the clauses that hold a checkable token: a digit, backticked code, a code-shaped name, an ALL-CAPS name, a number word, or an order or condition word. I checked it only against made-up examples, and its hash was recorded at 04:52 CEST, before it counted any round-4 comment (`round4/MULTI-DETAIL-RULE.txt`).

By that rule, 14 of the 30 round-4 comments name two or more details, 47 of every 100. The three comments where Jev and Sol disagree on question 3 come out as hv-h12 with 1 detail clause, en-h10 with 2 and en-h11 with 4. So 2 of the 3 are multi-detail, against a base rate of 14 of 30. Among the 27 comments where they agree, 12 are multi-detail. Three cases cannot show a link, and this count gives no reason for a rewording round. The rule is crude: it counts "Cleared even on a non-match" but not "Clear the cookie", so it undercounts plain action statements. My earlier reading of hv-h12 as multi-detail is not borne out by it.

## Why hv-h12 and en-h11 are wrong under both rules

**hv-h12, `apps/web/src/app/api/github/attach/route.ts:83`.** The comment says the referral cookie is "cleared even on a non-match". The shown code deletes it only `if (pendingReferral.shouldClear)`. Jev read that condition as contradicting the comment: all three stale parts came out yes (0.82, 0.89 and 0.70), and the old question gave 0.79. Sol said the comment and code are consistent. The code decides it, and it is one file away: at the case commit, `apps/web/src/lib/billing/referral-cookie.ts` sets `shouldClear: raw !== undefined`, so the cookie is cleared whenever it is present, including on a non-match. The comment is right. Jev judged a condition whose definition was not in the packet.

Design input: before "fix stale comment" can be decided, code should fetch the definition of every identifier in the shown line the comment's detail touches. That is a deterministic `find_definition`, not a search. The three stale questions then run on that packet. Without the definition, a stale verdict on a conditional line should escalate, not decide.

**en-h11, `enginepy/workflows/document_analysis/standards_scout.py:318`.** The comment says the filename list "only holds files whose PURPOSE is unambiguous from the name", and that broad or ambiguous config files are handled separately below. Sol counts the entry `.github/workflows/*.yml` as a contradiction, because a workflow file is not necessarily an enforcement artifact; its key says "fix stale comment". Jev put "the code's version differs" at 0.15, and the old question at 0.14. This is a claim about every item in a list ("only holds"). The three stale questions ask about one shared detail, and neither rule decomposes a quantifier. Sol's label is itself a judgement call about workflow files, so this case is less certain than hv-h12.

Design input: when a comment makes a claim over every item of a list or set ("only", "every", "all", "never"), code should split out the items and ask one property question per item, then apply the quantifier in code. That is the decomposition the lessons prescribe for universal claims. A question about "a detail" should not be asked to carry it.

# Doc comments, the search gate and the definition fetch (28.09.2026, from 05:35 Berlin)

## Contents
- [Doc comments are never removed](#doc-comments-are-never-removed)
- [Library re-pinned to 7f45346](#library-re-pinned-to-7f45346)
- [The search gate](#the-search-gate)
- [The definition fetch before "fix stale comment"](#the-definition-fetch-before-fix-stale-comment)
- [How many doc comments a sweep adds](#how-many-doc-comments-a-sweep-adds)
- [Doc comments validated on 30 blind Sol labels](#doc-comments-validated-on-30-blind-sol-labels)
- [Static rewrite packets](#static-rewrite-packets)
- [Claims about every entry of a list (built, not yet run)](#claims-about-every-entry-of-a-list-built-not-yet-run)
- [Fixes after the library verifier's report](#fixes-after-the-library-verifiers-report)
- [First labelled run of the list-claim check](#first-labelled-run-of-the-list-claim-check)
- [Accuracy by confidence band, and a draft bar for "fix stale comment"](#accuracy-by-confidence-band-and-a-draft-bar-for-fix-stale-comment)

## Doc comments are never removed

Andre's rulings: at 04:49 Berlin, "keep but check stale and for other quality issues to i was naive those comments can be bad too"; at 04:52 Berlin, "it should just be clear those comments shouldnt be removed instead targeted for rewriting".

- **What a doc comment is:** a JSDoc block, a Python docstring, a declaration comment or a file header. They now go to Jev with a `doc_comment` fact. Code keeps only tool directives, and it never removes a doc comment as commented-out code.
- **The rule in `compose.py`:** where the answers lead to "remove", or to "refactor instead" (rename the code and drop the comment), a doc comment gets "rewrite". "Fix stale comment", keep and the escalation band are unchanged.
- **"Only restates the code" is ignored for doc comments:** describing what the code does is a doc's job. The question is still asked and recorded, but neither the action nor the escalation reads it. I made this choice in `compose.py`, and Andre confirmed it at about 07:20 Berlin, when the lead asked him ("Ignore 'restates' on docs").
- **Tests:** `compose_test.py`. The new behaviour tests failed first at 05:35 Berlin: 5 failed and 2 pins passed.
- **Round 4 stays as scored:** its scorer imports `round4/compose_round4.py`, a byte copy of the frozen rule (hash 131a113a). The round-4 numbers are unchanged.

## Library re-pinned to 7f45346, then to 7faaba2, 02a893b and 7e05d9a

7faaba2 is the public jev-navigator (github.com/ajbmachon/jev-navigator), with a tree identical to 91e3723. None of its renames touch our imports. Every module imports, all 28 tests pass, and all 90 labelled packets (rounds 3 and 4, and the 30 doc comments) rebuild byte-identically. The tsconfig path alias reader in `definition_fetch.py` went away with the 02a893b re-pin below.

- **02a893b (library PR #1, 28.09.2026):** the library now resolves TypeScript path aliases from the commit's tsconfig files and reads imports that span several lines. Our own alias reader (about 35 lines) is deleted, and `definition_fetch.py` asks the library instead. We had no workaround for imports over several lines, so nothing else was removed. With no model call, all 120 labelled packets (round 3, round 4 and both doc rounds) rebuild byte-identically, and all 40 tests pass, including the 7 list-claim tests. The hv-h12 test still fetches the same two pieces, the local binding in `route.ts` and the declaration in `referral-cookie.ts`, and that import goes through the `@/` alias, so the test proves the library's alias resolution. The frozen records of the docs, docs2 and list rounds note the change at 09:46 Berlin.
- **7e05d9a (library PR #2, 28.09.2026 10:15 CEST):** the library parses the scope once, and a file it cannot parse in time is now "unknown", not absent. A binding that may depend on such a file says "unknown", and a search over such a scope ends as "scope_incomplete" instead of "nothing left". Our side:
  - A condition name or list entry whose definition may sit in an unparsed file is recorded as `unknown` and escalates, exactly like an unresolved one ("definition unknown, file not parsed"). Tested with an injected unparsed file (the test failed first).
  - A search that ends as "scope_incomplete" is recorded as "not yet inspected", never "searched, not found", and the row lists the unparsed files. A test now checks that every library search outcome has a label.
  - With no model call: all 120 labelled packets rebuild byte-identically (30 of 30 in each of round 3, round 4, docs and docs2; none changed), the 10 stored rewrite jobs and the six lists' entry items rebuild unchanged, the per-band and list scores reproduce their stored outputs byte for byte, and all 47 tests pass, including the hv-h12 definition fetch.

- **Journal:** our Evals journal adapter now takes the library's raw response (exact bytes, HTTP status, content type). A response that fails to parse keeps its bytes instead of an empty body.
- **Labels stay valid:** `packets_rebuild.py` rebuilt the 30 round-3 packets (the ones the fresh labels were given) and the 30 round-4 packets. All 60 are byte-identical, with no model call.
- **The history record:** the search history is now stored step by step, because the old accessor is gone.

## The search gate

A search starts only when stale lies inside the escalation band (0.40 to 0.60), the comment names a detail (at least 0.5) and the shown code does not surely hold it (below 0.60, the band's top). This is `compose.search_could_settle`. The stop question may end a search, but the edit comes from the three stale questions asked again with the found code in its own field (see the verifier fixes below).

The first version required the detail to be below 0.5. Together with the stale band, that opened the gate only when "the shown code holds the detail" sat between 0.40 and 0.50, while this report described it more widely. At the library verifier's finding, the gate now opens on the whole band. Recomputed with no model call on the same answers: round 4 still starts 0 searches; round 3 starts 1 of its 5 escalations; the lib sweep starts 4 of 201 (before, 1). Of the 39 lib decisions a search had settled that the gate took away, 3 get their search back.

- **Round 4** (stored answers, no new calls): 3 searches before and 0 under the gate. The gate takes away two decisions a search had settled. en-h10's "rewrite" matched Sol's key, so that is a loss. en-h11's "rewrite" did not match the key, which says "fix stale comment". The bars score the first answer, so they are unchanged.
- **Round 3 and the lib sweep** asked one stale question, which the gate cannot read. So I asked the round-4 questions once on their stored packets (206 Jev calls).
- **Caveat on the lib numbers below (library verifier, 28.09.2026):** the 201 lib packets came from the answer store, which keeps each request with its keys sorted, not the bytes the sweep sent. On one packet the verifier measured 0.83 on the store's copy against 0.70 on the exact bytes, the same minute. So these 201 answers are not a replay of the sweep's requests. They will be asked again from the journal's exact bytes once the library stores them. Round 3's 5 packets came from its cases file as sent and are not affected.
  - Round 3: 4 of its 5 escalations still escalate, and the gate searches none.
  - Lib sweep: 112 of 201 still escalate, and the gate starts 1 search where the sweep ran 201.
  - Of the 80 lib decisions a search had settled, 41 now decide on the first answer and 39 would go to escalation. There are no labels to say whether those 39 were right.
- **The gate stays (lead's ruling).** The 39 stay unlabelled for now. They are the gate's open cost: more comments handed to the calling agent.
- **en-h10 is the one labelled loss of the gate.** The lead predicted the definition fetch would win it back. It did not, because the code it describes holds no condition to resolve, so it stays escalated.
- **Gate and fetch together on the 16 lib stale doubts, with no model call:**
  - 4 get a search under the widened gate (activation-state.ts:377, hub-run-snapshot.ts:226, runDisplay.ts:72, review-draft.ts:653).
  - 8 have "fix stale comment" as their first answer, but the fetch finds no condition to resolve, so they stay escalated.
  - The other 7 propose keep and stay escalated.
  - So the fetch settles none of them. It helps only where a condition's meaning lives outside the packet, as in hv-h12.
- **Open design gap (not built, by the lead's ruling):** a stale doubt about a detail the shown code already holds cannot be settled by more code or by a definition. In the lib sweep, 8 comments escalate for this reason.
- **The stop question now reads only the fetched code.** It reads the `fetched` history section, not the search's own per-place verdicts: the same question on the view Sol labelled. The lead ruled this a variant of an approved question, not a new design. It has not been measured yet; it will be frozen and measured the next time a search runs.

## The definition fetch before "fix stale comment"

Before "fix stale comment" fires, code reads the if, elif and while conditions in the code the comment describes. It fetches each starting name's definition: its local binding (with the function it is bound to, when it is bound to a call), its function signature when it is a parameter, the declaration it is imported from, or a declaration in the file. Language builtins need none. The definitions go into their own state field, `code.elsewhere`, and only the three stale questions are asked again (see the verifier fixes below). A name without a definition escalates. Path aliases come from the nearest `tsconfig.json`, because the library resolves only relative imports. This is `definition_fetch.py`, with 8 tests.

- **hv-h12:** code fetched the `pendingReferralCookie` call and the function that sets `shouldClear: raw !== undefined`. Stale fell to 0.45, so the comment escalates, and its proposed action is keep, which matches the key.
- **en-h10 and en-h13:** the code they describe holds no condition, so nothing changed.
- **Round 4 with the fetch:** 26 of 30 decided, and 25 of 26 matching. The frozen rule gave 27 of 30 and 25 of 27. The only decided mistake left is en-h06.

## How many doc comments a sweep adds

With no model call, on `apps/web/src/lib` at a3bde2aa, the count is the same at 061baa9 and at 7f45346:
- **4319 doc comments in all:** 3982 JSDoc blocks, 127 declaration comments, 210 file headers and no docstrings.
- **Where they sit:** 2249 are on a named function or class.
- **Checkable details:** by the mechanical rule in `multi_detail.py`, 3574 name at least one.
- **The cost:** each is one more Jev request. A lib sweep goes from 978 comments reviewed by Jev to 5297.

## Doc comments validated on 30 blind Sol labels

- **The sample:** 15 Heedvane and 15 engine doc comments, one per file, in a fixed hash order, from files no earlier round used. By kind, 15 are docstrings, 13 JSDoc blocks and 2 declaration comments.
- **The freeze:** at 07:36 Berlin, before any call (`docs/FROZEN.txt`). Two later edits are recorded there with their hashes, and neither changed a result.
- **The packet:** for a docstring, it shows the rest of its function or class.
- **The calls:** 30 Jev and 30 Sol.

**Results:**
- **Decided on the first answer:** 24 of 30. The bar is 70 of 100, so it is met.
- **Matching the key, of those decided:** 20 of 24, which is 83 of 100. The bar is 90 of 100, so it is missed.
- **Proposed actions:** Jev said keep 25 times, rewrite 4 times and fix stale once (en-d09, escalated). The key says keep 22 times and rewrite 8 times. No doc comment was proposed for removal.
- **The 4 decided mistakes are thin one-line docs Jev kept and the key rewrites:** en-d05, en-d15, hv-d10 and en-d12. For the first three, Sol answered yes to "only a title or label". For en-d12, Sol said a better name would say it all. On 3 of the 4, Jev found value through "states a rule the code does not show" (0.62 to 0.69).
- **Andre's ruling at about 08:10 Berlin: "Summaries are fine, keep".** `questions.round5.json` is round 4's set with one change. The `is_noise` "true" exclusion now reads: "A heading followed by sentences that explain rules, reasons or knowledge, and a doc comment that says in a sentence what the function, class, type or module it documents does, returns or holds." Doc comments still read "a better name would replace it". Historic runs keep `questions.round4.json`.
- **A fresh validation round of 30 doc comments is frozen** (`docs2/FROZEN.txt`, 08:16 Berlin): 14 docstrings, 9 JSDoc blocks, 4 declaration comments and 3 file headers, with no file shared with earlier rounds and no list claim triggered. Its Jev and Sol calls wait for the adversarial verifier's report.
- **Post hoc, not a validation:** had docs read neither `is_noise` nor "a better name would replace it", these labels would give 26 of 30 decided and 26 of 26 matching.
- **File headers have no reference labels:** they are reviewed as doc comments under the never-remove rule, but none came up in the 30-doc sample. The 210 lib headers are not covered by any Sol label yet.
- **The definition fetch bug this run found:** builtins and parameters counted as missing definitions. It is fixed and tested, and it changed no result.

## Static rewrite packets

Andre's idea at 04:55 Berlin: code builds a static job packet from the parser, an LLM writes the new comment, and code checks it again. His later ruling (28.09.2026, below) settles who writes: the tool only classifies, and the packet travels in the classification output as `rewrite_job` for the caller.

- **Finding 10 real rewrites (Jev only, no Sol, 225 new calls plus 6 stored answers):**
  - Heedvane needed 149 lib doc comments for 5 decided rewrites.
  - The engine needed 79 doc comments for 5.
  - Of all 228, 63 escalated (28 of 100).
  - 3 were decided as "fix stale comment", with no reference labels yet.
- **What a packet holds (`rewrite_packet.py`):**
  - the old comment;
  - why it goes to rewrite, in plain words with the deciding number (`compose.rewrite_reasons`);
  - the parser's signature: parameters with types and defaults, return type, and failure or raised types (Python through `ast`, TypeScript through the compiler's parser in `ts_parse.mjs`);
  - the documented code. A module-level doc gets the module's exported or public names instead.
- **The Heedvane rewrites** are docs that tell history or carry tickets and dates.
- **The engine rewrites** are all module docstrings judged "only a title or label". Under Andre's 08:10 ruling they will likely become keeps, so the 5 Heedvane packets are the pilot set for the rewrite prompt. The prompt goes to Andre first.

- **Rewrite prompt drafted (28.09.2026, no model call):** `rewrite/PROMPT-DRAFT.md`. Of the 11 stored cases (10 rewrite packets and lr-06), a free static repair alone fixes 2: hv-r015 (removing `(#146)`) and lr-06 (adding the missing list entry). A skeleton built from the signature (`Args:` or `@param`) fits almost nowhere in our repositories: only 2 files in each use those sections, and none of the 10 rewrite files does.
- **The tool only classifies (Andre, 28.09.2026: "calling agent rewrites, our tool just classifies"; on lists he picked "Only propose"):**
  - The tool writes no comment text and runs no static repair. `rewrite/PROMPT-DRAFT.md` is now guidance for the calling agent or another system, and says so at its top.
  - A decided "rewrite" row now carries a `rewrite_job`: what the comment documents (the parser's signature and the code), the old comment, and why it failed, in plain words. It is the same builder the stored packets use; the 10 stored packets rebuild byte-identically. Tested in `sweep_test.py` (failed first).
  - A docstring-like comment is never deleted. A new test runs rule A over every yes/no combination of the 12 answers with 4 sets of code facts (16,384 cases for each kind): no doc comment ever gets "remove" or "refactor instead", and inline comments do get "remove". The test passed at once, because the rule already held, so I checked it by removing the rewrite mapping, which made it fail, and then restored the code.
  - A failing list now says `caller_decides`: "comment or list may be wrong, caller decides". Tested in `list_claims_test.py` (failed first).
  - **No stored verdict changes:** the action set is the same as before, so nothing was rescored. `per_band.py` and `score_list_round.py` reproduce their stored outputs byte for byte.

## Claims about every entry of a list (built, not yet run)

Andre approved the two questions, the trigger and the combination exactly as drafted, with "Run it as written", at about 08:00 Berlin. A newer rule (about 08:05 Berlin) says every Jev task gets an adversarial verifier before its Jev calls run. So this is built and tested offline, and no Jev call has been made.

- **Trigger (code, `list_claims.py`):** the comment uses only, every, all, each, always, never or none. The code it describes must be a single list-like literal with at least 2 entries, read with the language's parser: a Python tuple, list, set or dict through `ast`, or a TypeScript array, object, enum or union type through the compiler's parser (`ts_parse.mjs`). A list of more than 60 entries escalates as "list too long".
- **Questions (`questions.list-claims.json`, verbatim as approved):** A, `states_condition_for_every_entry`, joins the comment's first request. B, `entry_meets_stated_condition`, is asked once per entry through the library's `check_each`, and only when A is yes.
- **Andre approved new wording ("Approve new wording", relayed by the lead after the verifier's report).** en-h11's comment states two conditions, so "one condition" and "the condition" became "at least one" and "every". The changed parts, old then new:
  - A, instructions: "Does `comment.text` state one condition that every entry of the list in `code.after_comment` must meet?" became "Does `comment.text` state at least one condition that every entry of the list in `code.after_comment` must meet?"
  - A, true: "... all entries of the shown list share a property, ..." became "... all entries of the shown list share at least one property, ..."
  - B, instructions: "Does the entry in `{item}.code` meet the condition that `comment.text` states for every entry of the list?" became "Does the entry in `{item}.code` meet every condition that `comment.text` states for all entries of the list?"
  - B, true: "Read as written, the condition in `comment.text` is true of the entry in `{item}.code`." became "Read as written, each condition in `comment.text` is true of the entry in `{item}.code`, with the code in `{item}.definitions` when the entry names other code."
  - B, true, not_for: "Whether the condition is a good rule, ..." became "Whether the conditions are a good rule, ..."
  - B, false: "Read as written, the condition in `comment.text` is not true of the entry in `{item}.code`." became "Read as written, the entry in `{item}.code` fails at least one condition that `comment.text` states for all entries."
  - Everything else, including all examples, is unchanged.
- **B's state holds only the comment text and the entries.** The drafted state also carried the list's name, which no question reads, so the lead ruled it out. That is a trim with no wording change.
- **Combination (`compose.list_claim`):**
  - If A is inside the band, the comment escalates.
  - If A is yes, an entry at 0.20 or less (Jev's no bar) makes the comment "fix stale comment", naming those entries. Any entry between 0.20 and 0.60 escalates, named. This bar replaced the first version's 0.40 at the library verifier's finding: with up to 60 entries, one noisy answer must not decide the edit.
  - An entry that is or holds a name (a constant, a spread, a call's argument, or a callee defined in the repository) carries the definitions code finds for those names, as `definitions`. A name without one escalates the comment before B is asked. A callee imported from outside the repository, such as `re.compile`, needs no definition. `position` is no longer sent.
- **Tests (`list_claims_test.py`, 6 tests):** the trigger words; the 11 entries of en-h11's real list; TypeScript arrays, enums and unions; the combination; and en-h11 end to end on a scripted client. That run puts A in the first request, asks B per entry, and ends in "fix stale comment" naming the workflow entry.
- **Free Meta Builder prepare step** (`meta-list-claims/`, en-h11's two exact requests, re-run after the trim): every path the questions name resolves to the state (`comment.text`, `code.after_comment`, `items[n].code`). The paid review, with `compose.list_claim` as its consumer code, runs together with the Jev calls after the verifier's report.

## Fixes after the library verifier's report

The verifier's report (28.09.2026, 08:05 to 08:20 Berlin) is at `~/.local/share/system-one-proof/verifiers/library/VERIFY-2026-09-28.md`. These are the fixes in our code, each with tests (40 tests pass):

- **Fetched code has its own field.** After a definition fetch or a search, the extra code goes in `code.elsewhere` as `{file, lines, commit, reached_by, code}`, never into `code.after_comment`. Only the three stale questions are asked again. Every other answer, and so the value, noise and history branches of the rule, stays the first packet's. The two stale questions that name the shown code get `code.elsewhere` added to that list of fields, derived in code from the current question set (`comment_review.stale_reask_checks`). Before this, hv-h12's "the code is hard to follow" moved from 0.38 to 0.66 once another file's code was pasted in as "after the comment".
- **"Staleness not checked" is recorded.** A comment that names a detail (at least 0.5) the shown code does not hold (below 0.5) now carries `stale_check: "not_checkable_detail_not_shown"`. Its low stale value is missing evidence, not a finding that it is current. Counted on stored answers: 3 of 30 round-4 comments (hv-h07, hv-h14, en-h15), 6 of 30 doc comments (hv-d04, hv-d11, en-d03, en-d07, en-d12, en-d14), and 16 of 201 lib-sweep escalations. The sweep's totals and the doc scorer count them.
- **The search gate opens on the whole escalation band** (see the search gate section).
- **List claims:** the no bar of 0.20 for an entry to decide, and definitions for named entries (see the list-claim section). The wording change the verifier asks for (A: "at least one condition"; B: "every condition") changes texts Andre approved, so the exact texts went to the lead for him. The list claims do not run until he answers.
- **The gate replay's lib numbers have a caveat:** they were asked on the answer store's key-sorted copy, not the sent bytes (see the search gate section).
- **Waiting on the library:** `open_first`'s missing "none of these" option and the store's exact sent bytes. We re-pin when those land.

**hv-h12 is no longer fixed under the corrected design.** Asked the verifier's way, with the definitions in `code.elsewhere` and only the stale questions re-asked (1 Jev call, `round4-definitions-elsewhere/`), "the code's version differs" is 0.63. That is above the band, so hv-h12 is decided as "fix stale comment" again, which is wrong. The earlier 0.45, which escalated it, came from pasting the definitions into `code.after_comment`. Round 4 with the fetch is back to 27 of 30 decided and 25 of 27 matching, with hv-h12 and en-h06 as the decided mistakes. So the definition fetch alone does not stop a wrong "fix stale comment" here, even with the definition in view.

## The fresh doc round (docs2, after the verifier fixes)

The round was frozen at 08:16 Berlin and re-frozen with the verifier fixes before any call. It used the round-5 questions (the one-sentence summary exclusion in `is_noise`) and cost 30 Jev calls and 30 Sol calls.

- **Decided on the first answer:** 20 of 30. The bar is 70 of 100, so it is missed by one comment.
- **Matching the key, of those decided:** 19 of 20, which is 95 of 100. The bar is 90 of 100, so it is met.
- **The 10 escalations:** 7 for value (0.42 to 0.56), 2 for stale (0.41 and 0.42) and 2 for "a better name would replace it" (0.43 and 0.46); one comment has two reasons. 9 of the 10 proposed actions match the key. Counting the proposals as well, the rule matches the key on 28 of 30.
- **The one decided mistake is en-e10:** a docstring decided as "fix stale comment" where Sol says the code agrees with it. Jev put "the code's version differs" at 0.71. Its described code holds no condition, so the definition fetch had nothing to add.
- **The summary question now agrees with Sol on 30 of 30.** The four summary mistakes of the first doc round are gone.
- **Staleness not checked:** 6 of 30 (hv-e01, hv-e06, hv-e09, hv-e14, en-e02, en-e12).
- **File headers:** none of the 3 in this sample escalated or was a mistake.

## First labelled run of the list-claim check

The run used Andre's approved wording and the verifier's fixes, and was frozen before any call (`list-round/FROZEN.txt`). The free prepare step on en-h11's two requests found every named path in the state.

- **The six lists:** chosen from 153 comments the trigger fires on (found with no model call, `list_candidates.py`). They are en-h11, the verifier's two controls and three more in a fixed hash order:
  - `COST_KEY_TO_CREDITS_KEY`: every entry meets the condition;
  - `CATALOG_REFUSALS`: 12 entries that are names, each sent with its definition.
- **Calls:** 10 Jev requests and 6 Sol calls (one per list, labelling A and every entry).
- **Question A (does the comment state a condition for every entry?)** agrees with Sol on 6 of 6.
- **Question B (does this entry meet it?)** agrees with Sol at 0.5 on 29 of 30 entries.
- **Only one entry reached 0.20 or less**, the only answers that may decide. It is `"narrowed-superseded"` in `_VERDICT_OF` (0.15), which the comment's list of raw statuses does not include. Sol labels it false too. So lr-06 is decided as "fix stale comment", and the key agrees.
- **en-h11 was not caught.** Jev put `.github/workflows/*.yml` at exactly 0.60, the top edge of the band, so it neither decided nor escalated. Sol labels it false. Sol's note shows why this case is debatable: a workflow file's name does not say whether it enforces anything.
- **The every-entry control** passed in the tool (all three entries between 0.78 and 0.85). Sol labelled all three ambiguous, so the key escalates it.
- **The names control** resolved all 12 definitions and matched the key: nothing to fix.
- **One hash-order list (lr-04)** escalated because three entries use icons imported from a package (`Globe`, `Terminal`, `CircleCheck`), which have no definition in the repository. The key says nothing to fix.
- **What this shows:** on six lists, the check made one correct decided edit and no wrong one. It missed en-h11 at the band edge and escalated one list for missing definitions. Six lists cannot carry bars.
- **Rule change after the run (lead, 28.09.2026):** a name imported from a package now passes as it is, whether it is a value like these icons or a function like `re.compile`. Only a name defined inside the repository that cannot be resolved still escalates. That keeps one rule for both. Rescored from stored answers with no new call (`score_list_round.py`, which now finds unresolved names again from git), lr-04 no longer escalates for missing definitions, but it cannot be scored: the stored run stopped before asking B about its three entries, so there are no entry answers to combine. Every other list scores as before, and the B items of all six lists rebuild exactly as Sol labelled them. The change is logged in `list-round/FROZEN.txt` as a post-freeze rule change.
- **The list check keeps deciding alone at 0.20 or less (lead, 28.09.2026).** That bar is far stricter than the 0.80 stale bar, and its one case was right. Its decided verdicts are counted here and the bar is revisited at 10. Count so far: 1 decided verdict (lr-06), 1 right.
- **The paid question review's description of B was out of date:** it still said an entry at 0.40 or less decides. It now describes the rule as it is (0.20 or less decides, below 0.60 escalates, package names pass), and the two en-h11 review requests were exported again with no model call. Only that description changed; the state and questions are the same, and the free prepare step accepts both.

## Accuracy by confidence band, and a draft bar for "fix stale comment"

**Decision (lead, 28.09.2026): the bar is 0.80, and it is provisional.** A "fix stale comment" verdict decides alone only when "the code's version differs" is 0.80 or higher; below that, the calling agent decides. On today's data this means every such verdict goes to the calling agent. The bar rests on only 3 stored verdicts, 2 of them wrong, and is fitted on the same labels it is judged by, so it gets refit once a fresh labelled round has more stale cases. It lives in `compose.py` as `STALE_DECIDES_AT`, tested in `compose_test.py` (both tests failed first). It does not touch the list-claim check, whose stale verdicts come from one entry at 0.20 or less.

With the bar applied, the tool decides 93 of 120 comments instead of 96, and 86 of those match the key instead of 87: the two wrong stale verdicts and the one right one now go to the calling agent. Per round, round 4 decides 25 of 30 (24 right) and the second doc round 19 of 30 (all 19 right), so docs2 now misses the "decide at least 70 of 100" bar by two comments instead of one. The table below is the measurement before the bar, which the decision was drawn from.

This part used stored answers only, with no model call (`per_band.py`, output in `per-band.txt`). It covers all 120 labelled comments: rounds 3 and 4 and both doc rounds.
- **The rule used:** each round's comments are scored with the rule the tool applies now. Round 3 uses the rule it was measured with, since it had one stale question.
- **Round 4's stale answers:** they are the ones asked again after the definition fetch.
- **A decided comment's confidence** is its deciding answer. For "fix stale comment" that is the stale value. For every other action it is the weakest answer on its decision path.

Across all four rounds, the tool decided 96 of 120 comments, and 87 of those matched the key:

| Action | 0.60 to 0.70 | 0.70 to 0.80 | 0.80 to 0.90 | 0.90 and above |
|---|---|---|---|---|
| keep | 25 of 32 right | 29 of 29 right | 17 of 17 right | 3 of 3 right |
| rewrite | 3 of 3 right | 3 of 3 right | 6 of 6 right | none |
| fix stale comment | 1 of 2 right | 0 of 1 right | none | none |

What the table shows:
- **Keeps are safe above 0.70.** Of the 7 wrong keeps between 0.60 and 0.70, 4 are the first doc round's one-sentence summaries, which Andre's 08:10 ruling has since settled.
- **Rewrites were right in every band.**
- **Only 3 decided "fix stale comment" verdicts exist in all 120 comments, and 2 are wrong.** The three stale answers for each (names a detail, the code shows it, the code's version differs):
  - hv-h12: 0.88, 0.91, 0.63. The key says keep, so it is wrong.
  - en-h13: 0.77, 0.85, 0.66. Right.
  - en-e10: 0.92, 0.83, 0.71. The key says keep, so it is wrong.

**The draft bar (not applied, sent to the lead for the decision).** "Fix stale comment" would decide alone only when "the code's version differs" reaches the bar; from 0.60 up to the bar, it goes to the calling agent. Across the three stored verdicts:

| Bar | Wrong verdicts sent to the calling agent | Right verdicts sent to the calling agent | Still decided alone |
|---|---|---|---|
| 0.65 | 1 (hv-h12) | 0 | 2, of which 1 is right |
| 0.70 | 1 (hv-h12) | 1 (en-h13) | 1, of which none is right |
| 0.75 or higher | 2 (hv-h12, en-e10) | 1 (en-h13) | 0 |

No bar separates right from wrong: the right verdict (0.66) sits between the two wrong ones (0.63 and 0.71). Three cases cannot fit a bar. The bar is fitted on these same labels, so only a fresh round can validate it.

## Toward use by an agent

- **Entry point (`classify.py`):** `classify.py <repository> <commit> <journal dir> (--files ... | --diff <base>)` prints one JSON row per comment on stdout and a summary on stderr. With `--diff`, a comment is in scope when its own lines or the code it describes changed since the merge base; a pure deletion counts as changing the lines on both sides of it. Three tests use a fake answerer with no model (they failed first, and the rule "the described code counts too" was checked by breaking it). A smoke run on a real diff with no source files made 0 Jev calls.
- **Output contract (`CONTRACT.md`):** how to read a row, every field, and seven example rows. The examples are real stored rows recomposed with the current rule.
- **Bug fixed on the way: prose read as commented-out code.** Code removes commented-out code without asking Jev, and it read any TypeScript line starting with `for`, `if`, `return`, `import` or `export` as code. The only code-decided removal in all stored sweeps, `// for custom agents` on a field in `dashboard-types.ts:320`, was prose, so it was wrongly removed. The pattern now needs code shape (`if (`, `const x =`, `from "..."`, a call, or a line ending in `;`, `{` or `}`). Tests failed first. None of the 515 stored cases changes its commented-out fact.
- **Requests per pull request (`count_pr_comments.py`, output in `pr-comment-counts.jsonl`, no model call):** the 5 most recently merged pull requests into develop in each repository (28.09.2026), with the diff from each merge commit's first parent.
  - 4 of the 10 change no Python or TypeScript source (CI, docs, scripts, a manifest), so they cost nothing.
  - The other 6 touch 16, 14, 8, 17, 48 and 81 comments. 3 of those comments are tool directives settled by code, so Jev gets 16, 14, 8, 17, 47 and 79 requests: 181 in all, 18 per pull request on average over all 10, 30 over the 6 that touch source, and 79 at most.
  - At most 2 more requests come from list claims (the per-entry batch, asked only when Jev says the comment states a condition). Re-asks after a definition fetch and searches happen only on escalation; in the stored rounds that was rare (3 stale verdicts in 120 comments, 4 searches in 201 lib comments under the gate), so they add a few percent.
  - Jev answered 2027 stored requests in 0.4 seconds at the median and 0.7 at the 90th percentile. With 6 comments in flight at once, the largest pull request (79 requests) needs about 6 seconds of Jev time.
- **Round 6 registered (items 6 and 9 together), no calls yet:** `round6/FROZEN.txt` holds the registration. 30 comments touched by the 6 recent pull requests that change source, 5 per pull request, as an agent calling `classify.py --diff` would see them: 23 doc comments and 7 block comments, as drawn. Bars on the tool's final row (at least 70 of 100 decided, at least 90 of 100 of those right); an escalated row, including a stale verdict sent to the caller by the 0.80 bar, counts as not decided. `run_docs.py` now runs each comment through the same path as `classify.py`. All 30 packets rebuild equal and the secret scan finds nothing. Waiting for the adversarial verifier before any Jev call.
- **Label catalog gap closed:** the six labelled sets of this tool (rounds 3 and 4, both doc rounds, the list round and the stop labels) are now in `~/.local/share/system-one-proof/labels/`, replacing an entry that said "not located".
- **Round 6 after the verifier (28.09.2026):** the Codex Luna verifier's report (`round6/VERIFIER-REPORT.md`, verdict "fix first") found five blocking and four further gaps. All are fixed as the lead ruled, and the round is frozen again from this repository on jev-navigator 1568d3d (`round6/manifest.json`; the first freeze is kept as `round6/FROZEN.superseded-1.txt`).
  - **What the round measures, renamed:** whether the tool reproduces Sol's judgments through rule A on 30 fresh model-reviewable comments (23 doc comments and 7 block comments). Rule A itself was approved separately; the round does not test whether rule A is the right policy. The scorer uses a hash-pinned copy of the rule frozen with the round, never the live one.
  - **The scorer fails closed:** the cases, results and Sol labels must be exactly the 30 registered ids; a partial run is invalid, never a smaller round. Every result row is recomputed from its journaled request and answers with the frozen rule, and each Sol label must carry the hash of its exact packet.
  - **The runner verifies before any paid call:** every source hash at the registered commit, the exact question file, the full case records rebuilt from git, the library commit, the Python version and the secret-scan receipt. Results are written to a partial file and renamed only when all 30 are done.
  - **Scope stated plainly:** comments in files a diff deletes are out of scope (a deleted comment needs no action). List claims are not in round 6; they come in the list round.
  - **The strata the sample leaves out, reported beside it:** the six pull requests touch 184 comments: 117 doc comments, 64 block comments and 3 tool directives decided by code; 4 comments carry dates, and 2 are list claims. The sample holds 30 of the 181 model-reviewable ones, 5 per pull request, and none of the date or list cases. No constructed controls, as Andre accepted.
  - **The sampler reads a hashed prior-label manifest** (every earlier labelled round, the root round and the stop labels included) and asserts 6 pull requests of 5 fresh comments, 15 per repository, 30 unique. The redraw is byte-identical to the first draw.
