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

**Step 1b complete: eval set built, baseline scored on dev and test, review sample
exported. Awaiting the human label-review pass.**

252 tickets (216 Bitext, 36 authored hard cases), labels drafted by `gpt-5.6-terra`,
split 144 dev / 108 test. Baseline `baseline_v1` scored on both. Nothing is
human-reviewed yet, so every number is self-agreement — see `README.md`.

Next: correct `data/review/label_review_sample.csv`, run `make import-review`, re-run
`make eval`, and treat *that* as the baseline of record.

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
3. **Labels are model-drafted until a human says otherwise.** Never describe the eval set
   as hand-labelled. `label_provenance` and `human_reviewed` are per-ticket and must stay
   accurate.
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

Dev: intent 94.4%, urgency 93.1%, escalation 99.3%, all three 88.2%.
Test: intent 96.3%, urgency 90.7%, escalation 97.2%, all three 87.0%.
$0.61 spent building and scoring. Full table and the caveats that matter in `README.md`.
Pre-review; the labels are the model's own, so these are a bar, not a measure.
