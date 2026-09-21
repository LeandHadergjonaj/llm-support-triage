# Project context

*This file is the context file for the Claude Code CLI, which is the tool being used to
build the project. The project itself runs on OpenAI — see Stack below.*

## What this is

An LLM support-triage system for **Hearth & Loom**, a fictional online homewares retailer
selling into the UK. Built as a portfolio project for a Forward Deployed Engineer role, so
the engineering judgement on show matters as much as the result: honest evaluation,
stated limitations, clear commits.

The system routes incoming support tickets — deciding intent, urgency and whether a human
must handle it — answering routine ones from policy documents and an orders database, and
escalating risky or uncertain ones to a human review queue.

## Where we are

**Phase 1 complete.** 252 tickets (216 Bitext, 36 authored hard cases), labels drafted by
`gpt-5.6-terra`, split 144 dev / 108 test.

The client brief is now at **v2**: five clarifications, each prompted by a contested or
contradictory label found in review, with a changelog in `docs/client-brief.md` §7. Two of
the five made labels wrong that v1 allowed, so the whole set was swept by rule for them —
13 labels changed. The baseline prompt restates the same v2 policy and both splits were
re-run against it.

Label checking to date, none of it by a person:
- **85 of 252** through a second-opinion review by `claude-opus-5` (round 1: 55 tickets;
  round 2: a fresh random block of 30 drawn from the never-reviewed remainder).
- **13** changed by the brief v2 rule sweep, which applies a rule without re-reading and
  is *not* a check.
- Label error rate: **round 1 block 20.0%** (6/30, 95% CI 9.5–37.3%, restated upwards
  from 16.7% after round 2 found an error round 1 had confirmed); **round 2 block 3.3%**
  (1/30, 95% CI 0.6–16.7%). The two rounds sample different populations and are never
  pooled.

**Step 1 complete: evaluation set, versioned brief, and single-prompt baseline.**

Recommended before Phase 2, and not yet done: put `DECISIONS.md` D-018 to the client —
whether an account-level admin task that blocks nothing paid for is `low` or `normal`. It
accounts for 12 of the baseline's 16 remaining urgency errors and nine inconsistent
labels, and no amount of prompt work can settle it.

Deliberately *not* built yet: router, specialist answerers, retrieval over policy docs,
the orders database, the review queue UI, deployment. Each of those is a later step and
each will be measured against the baseline recorded in `results/` — **at the same brief
version**.

## The rules this project runs on

1. **`docs/client-brief.md` is the source of truth for every label.** Policy documents and
   the orders database added later must be consistent with it. If the brief and the code
   disagree, the brief wins and the code is the bug — `tests/` asserts they agree.
2. **The test split is held out.** Tune on `data/eval/dev.jsonl` only. `make eval` runs
   dev; scoring test is a separate command and prints a warning.
3. **No label in this project has been checked by a person, and none may be described as
   if it had.** Labels are model-drafted; some have since been through a second-opinion
   review by a model of a *different family* from the drafter (`gpt-5.6-terra` drafted,
   `claude-opus-5` reviewed). That is an independence check, not verification. Never write
   "hand-labelled", "human-reviewed" or "verified". `label_provenance`, `reviewed`,
   `reviewed_by` and `sweep` are per-ticket and must stay accurate; `tests/` asserts the
   banned phrasings never appear in the data.
   **A rule sweep is not a review.** `triage.sweep` applies a brief rule mechanically
   without re-reading anything, so it finds only the errors its rule describes. A swept
   ticket stays `reviewed: false` and still counts as unchecked in the error rate.
4. **Do not overstate results.** The baseline is scored against labels drafted by **the
   same model at the same effort**, not merely the same family. A model agreeing with its
   own judgement is not evidence that the judgement is right, so absolute accuracy is
   optimistic by an unknown margin and every report must say so up front. The human review
   pass is the only thing that shrinks this; until it lands, the numbers are a bar to beat,
   not a measure of quality.
5. **Beat the baseline or justify the complexity.** A later version that does not improve
   on `results/latest_dev.json` has not earned its extra moving parts.
   **Compare only at the same brief version.** Every result carries `run.brief_version`.
   Clarifying the brief moves the labels *and* the prompt at once, so it produces a new
   bar, never evidence of improvement. A brief change needs a contested label behind it,
   an entry in `docs/client-brief.md` §7, and the labels and prompt updated in the same
   commit.
6. **The API key comes from the environment only.** `OPENAI_API_KEY` in `.env`, which
   is gitignored; never commit a key.
7. **`gpt-5.6-terra` is the triage model, for this step and every later one**, unless the
   client says otherwise. Fixed deliberately: a later version has to beat the baseline on
   design — routing, retrieval, better prompts — and not by being handed a stronger model.
   Changing it invalidates the comparison against `results/latest_dev.json`.
8. **No run costs more than $2 without asking first.** Enforced, not remembered: every
   command that calls the API takes `--max-cost` (default $2.00) and stops rather than
   spend past it. Running spend is appended to `results/spend_log.jsonl`; `make spend`
   prints the total. Projected cost goes in the plan before the money goes out.
9. **Claude owns the decisions on this project, and logs them.** Every meaningful decision
   goes in `DECISIONS.md`, dated and newest-first, with the reasoning and — where the
   brief was silent — the rule that should have been there. A decision a later reader
   could reasonably have made differently belongs in the log; routine implementation
   choices do not. Go back to the client only for what only they can supply: spend above
   the $2 cap, keys or account access, or a change to what the project is for. Everything
   else: decide, do it, write it down.

## Stack

Python 3.11, OpenAI Python SDK (Responses API), Pydantic for validation, strict
structured outputs (`text.format`, `strict: true`) so parsing is never the failure mode.
Model: `gpt-5.6-terra` for both label drafting and the baseline, overridable with
`TRIAGE_MODEL` or `--model`. The client brief is versioned and `taxonomy.brief_version()`
reads the version out of it, so every run records which policy it was scored under. No framework — at this stage it is a classification and
evaluation problem.

All provider-specific code lives in `src/triage/llm.py`; nothing else imports the SDK.

## Commands

```
make setup      venv + dependencies
make data       build the eval set (drafts labels; costs money, cached on disk)
make smoke      ~1c end-to-end pipeline check on 16 tickets (never an eval set)
make eval       score the baseline on dev            <-- the main one
make eval-test  score on the held-out test split
make review     export the round-1 label sample for correction
make review-round2  draw a fresh random block from the never-reviewed remainder
make sweep      show which labels the current brief's rules would change (dry run)
make spend      print total API spend recorded so far
make test       checks that need no API key
```

## Current results

Baseline of record (`results/latest_{dev,test}.json`), `baseline_v1` against **client
brief v2**:

Dev: intent 95.1%, urgency 95.1% (macro recall 94.5%), escalation 98.6%, all three 91.0%.
Test: intent 96.3%, urgency 91.7% (macro recall 92.4%), escalation 98.2%, all three 88.9%.
Escalation recall 1.00 on both splits, no missed escalations; 4 spurious `out_of_scope`
escalations remain, all on "make a claim / file a complaint" wording that v2 did not
address. `high` urgency recall 100% on both — **on 15 and 10 tickets**, so the 95% Wilson
interval reaches down to 79.6% and 72.3%; treat it as "no misses yet", not as reliable.

**These are a new bar, not an improvement.** Brief v2 gave the baseline the pre-dispatch
rule it was previously missing, so labels and prompt moved together. The brief v1 runs
stay in `results/` under their timestamps. See `DECISIONS.md` D-016.

Label error rate: round 1 block 20.0% (6/30, 95% CI 9.5–37.3%); round 2 block 3.3%
(1/30, 95% CI 0.6–16.7%). Never pooled. Round 2 is not independent — the same model wrote
the sweep rules and then measured what they left behind.

**$1.1165 spent in total** across the whole ledger (`make spend`), of which $0.1842 is a
backfilled pre-ledger entry for the smoke test and effort probe. The brief v2 re-run cost
$0.3197. Earlier documents quoted $0.61, which excluded the backfilled entry; the ledger
total is the number to use. Full table in `README.md`.
