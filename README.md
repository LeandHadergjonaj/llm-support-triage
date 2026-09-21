# LLM support triage — Hearth & Loom

Routing customer support tickets for a fictional online homewares retailer: what is this
ticket about, how urgent is it, and does a human need to handle it.

This repository is at **step 1 of a staged build**. Step 1 is an evaluation set and a
deliberately simple baseline — one LLM call per ticket — whose job is to be the bar that
every later, more complicated version has to beat. There is no router, no retrieval, no
agent and no UI yet, on purpose.

## Quick start

```bash
make setup                                    # venv + dependencies
cp .env.example .env && $EDITOR .env          # add OPENAI_API_KEY
.venv/bin/python scripts/fetch_dataset.py     # 19 MB upstream CSV
make smoke                                    # optional: ~1c end-to-end check of the pipeline
make data                                     # build the eval set (drafts labels; costs money)
make eval                                     # score the baseline on dev  <-- the command
```

`make eval` prints a summary and writes it to `results/`. `make test` runs the checks that
need no API key.

`make smoke` runs all five stages over 16 tickets on the cheapest model at zero reasoning
effort, writing to `data/smoke/` and `results/smoke/` (both gitignored). It proves the
plumbing works before spending on a real run. It is **not** an evaluation: every ticket it
builds is stamped `smoke_test`, and `make eval` refuses to score a set carrying that stamp.

### What a run costs

Projections, not yet a full measurement — but grounded in real calls rather than in
guessed token counts. Input token counts and cache behaviour are measured over the 30
calls of a `make smoke` run; output token counts come from eight `effort=high` calls on
the two candidate models, one short ticket and one hard case per model per stage. The
range spans that pair: the low end weights them by the set's actual composition (216
Bitext tickets to 36 authored hard cases), the high end assumes a 50/50 split. Rates are
[OpenAI's published ones](https://developers.openai.com/api/docs/pricing) read 2026-09-21.

| Stage | Calls | `gpt-6-astra` (default) | `gpt-5.6-terra` |
|---|---:|---:|---:|
| `make data` — draft 252 labels (one-off, cached to disk) | 252 | $6.18 – $9.05 | $0.60 – $1.08 |
| `make eval` — dev | 144 | $2.24 – $3.70 | $0.20 – $0.33 |
| `make eval-test` — held-out test | 108 | $1.68 – $2.77 | $0.15 – $0.24 |
| **All three** | 504 | **$10.10 – $15.53** | **$0.95 – $1.65** |

Reasoning tokens are billed as output and dominate: at `effort=high` `gpt-6-astra` spent
two to three times as many output tokens per ticket as `gpt-5.6-terra`, on top of an
output rate four times higher. Prompt caching pulls the other way — 92% of labelling
input tokens and 97% of scoring input tokens came back from cache, because the system
prompt is byte-identical across every ticket in a run.

Set `TRIAGE_MODEL=gpt-5.6-terra` in `.env`, or pass `--model`, to run the cheaper tier.
Actual cost is reported by every run from the API's own usage figures, so the first real
run replaces these projections with measurements.

## What is here

| Path | What it is |
|---|---|
| `docs/client-brief.md` | The client, the 11 categories, the urgency definitions, the escalation rules. **Source of truth for every label.** |
| `src/triage/taxonomy.py` | Machine-readable mirror of the brief, plus the 27→11 intent mapping |
| `src/triage/build_dataset.py` | Sample → fill placeholders → draft labels → split |
| `src/triage/labeler.py` | Drafts urgency and escalation labels from the full brief |
| `src/triage/baseline.py` | The single-prompt baseline |
| `src/triage/evaluate.py` | Runs the baseline over a split and scores it |
| `src/triage/metrics.py` | Scoring, separate from the run loop so results can be re-scored free |
| `src/triage/export_review.py` | Exports a sample of labels for a human to correct |
| `prompts/baseline_v1.md` | The baseline prompt, rendered so it can be read and diffed |
| `data/README.md` | Licence position, provenance, and every transformation applied |
| `tests/` | Checks that run without an API key |

## The evaluation set

252 tickets: 216 sampled from [Bitext's customer support
dataset](https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset)
(CDLA-Sharing-1.0, redistribution permitted — see `data/README.md`) and 36 written for
this project to cover what public data does not: multiple issues in one message, heavy
typos, angry customers, off-topic requests, ambiguity, product safety, account security,
legal threats and high-value refunds.

Split into dev (144) and test (108) — a 60/40 target, with per-stratum rounding landing at
57/43. **The test split is held out** and is not used to tune the
prompt.

### Labels are model-drafted

Intent on Bitext tickets comes from a deterministic mapping of the upstream label. Urgency
and escalation — and intent on the authored hard cases — were **drafted by a model** and
are marked as such on every ticket. Nothing here is hand-labelled until a person has
reviewed it; `human_reviewed` and `label_provenance` record exactly which is which.

This is a real limitation, not a formality: the baseline is scored against labels drafted
by the same model family, so absolute accuracy is optimistic. `make review` exports a
sample weighted towards the labels most likely to be wrong, for correcting by hand.

## What is measured

Intent accuracy and urgency accuracy, overall and per class. Escalation split into the
four outcomes that cost different things — correct, **unnecessary** (wasted reviewer
time), **missed** (the expensive one), and correct non-escalation. Cost and latency per
ticket. Confidence calibration. Everything is also sliced easy-vs-hard and per hard-case
kind, because an average over both hides the only interesting part.

## Baseline results

`baseline_v1` on `gpt-5.6-terra` at `effort=high`, run 2026-09-21. Full records in
`results/`; `results/latest_dev.json` is the bar later versions must beat.

> **These are self-agreement figures, not accuracy.** The same model drafted the urgency
> and escalation labels it is scored against here, and **no ticket has been reviewed by a
> human yet**. A model agreeing with its own earlier judgement is not evidence the
> judgement was right. Intent is the partial exception: for the 216 Bitext tickets it
> comes from a deterministic mapping, not from the model. Read the escalation and urgency
> numbers as a fixed bar for later versions, not as a measure of how good the triage is.

| Metric | Dev (144) | Test (108) |
|---|---:|---:|
| Intent accuracy | 94.4% | 96.3% |
| Urgency accuracy | 93.1% | 90.7% |
| Escalation accuracy | 99.3% | 97.2% |
| All three correct | 88.2% | 87.0% |
| Escalations in the labels | 17 | 12 |
| Missed escalations | 1 | 1 |
| Unnecessary escalations | 0 | 2 |
| Cost per ticket | $0.00112 | $0.00116 |
| Latency p50 / p95 | 2.1s / 2.8s | 2.1s / 3.1s |

The 17 and 12 reconcile with the 29 escalations in the label summary: the splits
partition the set, so gold escalations sum across them exactly (17 + 12 = 29), as do
tickets (144 + 108 = 252). `make test` now asserts this rather than leaving it to be
checked by eye.

Dev and test agree to within a couple of points on every metric, which is what you would
expect from one prompt applied to two halves of one stratified sample. It says the split
is sound; it says nothing about whether the labels are right.

The escalation numbers are the ones to distrust most. Precision 1.00 and recall 0.94 on
dev is not a credible measure of a first attempt — it mostly measures the same model
applying the same rules the same way twice. The single missed escalation is instructive:
on `hl-0224` (*"need to switch to the fucking premium account help me"*) the labeller
called `severe_customer_anger` and the baseline did not. The brief says mild swearing
about the situation is **not** severe anger, so the baseline looks right and the label
looks wrong. That ticket is in the review sample.

## Label quality

The reference labels are model-drafted, so how often they are *wrong* bounds how
precisely anything else can be known. `make review` exports a sample in two blocks that
must not be mixed:

- a **random block** of 30 tickets drawn uniformly from all 252 (`in_random_block=true`).
  This, and only this, estimates the error rate of the label set. Thirty gives a 95%
  Wilson interval of roughly ±13 points around a rate near 15% — enough to separate "a
  few percent" from "a third", not enough to separate 10% from 20%. Fifteen would have
  been ±18.
- **targeted picks** — drafter disagreements, self-flagged uncertainty, escalations, hard
  cases. Chosen for looking wrong, so their error rate is biased upwards by construction.
  A diagnostic of where the drafter struggles, never a population estimate.

`make import-review` folds corrections back in and prints both rates with intervals; the
next `make eval` carries them into the results. Re-exporting is additive: rows already in
the file stay, with anything already typed into them, and growing the random block tops it
up rather than redrawing it.

## Status

See `CLAUDE.md`.
