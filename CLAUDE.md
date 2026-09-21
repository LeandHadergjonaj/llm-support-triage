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
`gpt-5.6-terra`, split 144 dev / 108 test. 55 tickets reviewed by `claude-opus-5` as a
second opinion, 11 corrected. Baseline re-scored against the corrected labels from saved
predictions; that is the baseline of record.

Recommended before Phase 2, and not yet done: sweep the remaining 197 tickets for the two
error patterns the review found (see `DECISIONS.md` D-008 and D-009). Two contradictory
`out_of_scope` escalations and roughly nine mis-urgencied order changes are already
identifiable by rule.

**Step 1 complete: evaluation set and single-prompt baseline.**

Deliberately *not* built yet: router, specialist answerers, retrieval over policy docs,
the orders database, the review queue UI, deployment. Each of those is a later step and
each will be measured against the baseline recorded in `results/`.

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
   "hand-labelled", "human-reviewed" or "verified". `label_provenance`, `reviewed` and
   `reviewed_by` are per-ticket and must stay accurate; `tests/` asserts the banned
   phrasings never appear in the data.
4. **Do not overstate results.** The baseline is scored against labels drafted by **the
   same model at the same effort**, not merely the same family. A model agreeing with its
   own judgement is not evidence that the judgement is right, so absolute accuracy is
   optimistic by an unknown margin and every report must say so up front. The human review
   pass is the only thing that shrinks this; until it lands, the numbers are a bar to beat,
   not a measure of quality.
5. **Beat the baseline or justify the complexity.** A later version that does not improve
   on `results/latest_dev.json` has not earned its extra moving parts.
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
`TRIAGE_MODEL` or `--model`. No framework — at this stage it is a classification and
evaluation problem.

All provider-specific code lives in `src/triage/llm.py`; nothing else imports the SDK.

## Commands

```
make setup      venv + dependencies
make data       build the eval set (drafts labels; costs money, cached on disk)
make smoke      ~1c end-to-end pipeline check on 16 tickets (never an eval set)
make eval       score the baseline on dev            <-- the main one
make eval-test  score on the held-out test split
make review     export a label sample for hand correction
make spend      print total API spend recorded so far
make test       checks that need no API key
```

## Current results

Post-review baseline of record (`results/latest_{dev,test}.json`):
Dev: intent 93.8%, urgency 91.7% (macro recall 77.7%), escalation 98.6%, all three 86.8%.
Test: intent 97.2%, urgency 91.7% (macro recall 82.4%), escalation 98.2%, all three 89.8%.
Escalation recall 1.00 on both splits; 4 spurious `out_of_scope` escalations remain.
Label error rate on the random review block: 16.7% (95% CI 7.3–33.6%, Wilson).
$0.61 spent in total; the review and re-score cost nothing. Full table in `README.md`.
