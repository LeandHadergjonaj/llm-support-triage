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
4. **Do not overstate results.** The baseline is scored against labels drafted by the same
   model family; absolute accuracy is optimistic and every report must say so.
5. **Beat the baseline or justify the complexity.** A later version that does not improve
   on `results/latest_dev.json` has not earned its extra moving parts.
6. **The API key comes from the environment only.** `OPENAI_API_KEY` in `.env`, which
   is gitignored; never commit a key.

## Stack

Python 3.11, OpenAI Python SDK (Responses API), Pydantic for validation, strict
structured outputs (`text.format`, `strict: true`) so parsing is never the failure mode.
Model: `gpt-6-astra` for both label drafting and the baseline, overridable with
`TRIAGE_MODEL` or `--model`. No framework — at this stage it is a classification and
evaluation problem.

All provider-specific code lives in `src/triage/llm.py`; nothing else imports the SDK.

## Commands

```
make setup      venv + dependencies
make data       build the eval set (drafts labels; costs money, cached on disk)
make eval       score the baseline on dev            <-- the main one
make eval-test  score on the held-out test split
make review     export a label sample for hand correction
make test       checks that need no API key
```

## Current results

Not yet run — see the section in `README.md` once populated.
