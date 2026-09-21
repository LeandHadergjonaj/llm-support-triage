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
| `docs/client-brief.md` | The client, the 11 categories, the urgency definitions, the escalation rules. **Source of truth for every label.** Versioned, with a changelog in §7. |
| `src/triage/taxonomy.py` | Machine-readable mirror of the brief, plus the 27→11 intent mapping |
| `src/triage/build_dataset.py` | Sample → fill placeholders → draft labels → split |
| `src/triage/labeler.py` | Drafts urgency and escalation labels from the full brief |
| `src/triage/baseline.py` | The single-prompt baseline |
| `src/triage/evaluate.py` | Runs the baseline over a split and scores it |
| `src/triage/metrics.py` | Scoring, separate from the run loop so results can be re-scored free |
| `src/triage/export_review.py` | Exports a review sample: targeted picks plus a random block, per round |
| `src/triage/sweep.py` | Applies brief clarifications to every label they touch, by rule |
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
are marked as such on every ticket. **No label here has been checked by a person.** 85 of
252 have been through a second-opinion review by a model of a different family from the
drafter, and 13 have had a brief rule applied without being re-read; `reviewed`,
`reviewed_by`, `sweep` and `label_provenance` record exactly which is which.

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

`baseline_v1` on `gpt-5.6-terra` at `effort=high`, run 2026-09-21 **against client brief
v3**, scored against labels as corrected by the second-opinion review, the brief v2 rule
sweep, and the brief v3 `account_admin_no_live_order` sweep. Full records in `results/`;
`results/latest_dev.json` is the bar later versions must beat.

> ### These are not an improvement over the previous run
>
> Brief v3 settles `DECISIONS.md` D-018 — a simulated-client call on whether account admin
> that blocks nothing paid for is `low` or `normal` — and moved both the **labels** and the
> **prompt** at once, the same as v1 → v2. A system cannot be marked against policy it was
> never given, but the number that results is **a new bar, not evidence of progress**. Only
> v3-vs-v3 comparisons (the router, next) say anything about design. Every result record
> carries `run.brief_version`; the brief v1 and v2 runs stay in `results/` under their
> timestamps. See `DECISIONS.md` D-020.

> **These are still largely self-agreement figures.** The same model drafted the urgency
> and escalation labels it is scored against, and **no label has been checked by a
> person** — 85 of 252 tickets have been through a second-opinion review by
> `claude-opus-5`, a different model family, 13 more had a brief v2 rule applied to them
> without being re-read, and 10 more a brief v3 rule, also without being re-read. Intent is
> the partial exception: for the 216 Bitext tickets it comes from a deterministic mapping.
> Read these as a fixed bar for later versions, not as a measure of how good the triage is.

Columns marked *v2* are the previous baseline of record, kept for context only — they were
scored against brief v2 labels with a brief v2 prompt and are **not** a like-for-like
comparison. (Brief v1 numbers are in `results/` under their timestamps and are no longer
carried in this table.)

| Metric | Dev (144) | Dev, v2 | Test (108) | Test, v2 |
|---|---:|---:|---:|---:|
| Intent accuracy | 95.1% | 95.1% | 96.3% | 96.3% |
| Urgency accuracy | 99.3% | 95.1% | 96.3% | 91.7% |
| Urgency macro recall | 99.7% | 94.5% | 96.8% | 92.4% |
| — always predict `low` | 73.6% acc / 33.3% macro | 68.8% / 33.3% | 75.0% acc / 33.3% macro | 72.2% / 33.3% |
| Escalation accuracy | 97.9% | 98.6% | 99.1% | 98.2% |
| Escalation precision / recall | 0.85 / 0.92 | 0.86 / 1.00 | 0.92 / 1.00 | 0.85 / 1.00 |
| All three correct | 94.4% | 91.0% | 93.5% | 88.9% |
| Escalations in the labels | 12 | 12 | 11 | 11 |
| Missed escalations | 1 | 0 | 0 | 0 |
| Unnecessary escalations | 2 | 2 | 1 | 2 |
| Cost per ticket | $0.00129 | $0.00128 | $0.00131 | $0.00125 |
| Latency p50 / p95 | 2.1s / 3.3s | 2.1s / 3.3s | 2.1s / 3.2s | 2.1s / 3.0s |

Urgency is the number the brief change was aimed at, and it moved: macro recall 94.5% →
99.7% on dev, 92.4% → 96.8% on test. Escalation moved the other way on dev — one refund
threshold escalation was missed this run (`refund_over_threshold`, gold 3, predicted 2) —
which is a fresh API call, not the labels: gold escalations on dev are unchanged at 12,
brief v3 touched no escalation label. At n=12 that single miss is the entire movement, and
it is inside the noise a fresh sample of reasoning-model calls produces at this size — see
`DECISIONS.md` D-020 and the caveats below on small-n slices.

Per-class urgency, which is the part worth reading:

| Class | Dev support | Dev recall | Dev precision | Test support | Test recall | Test precision |
|---|---:|---:|---:|---:|---:|---:|
| `high` | 15 | 100.0% | 100.0% | 10 | 100.0% | 100.0% |
| `normal` | 23 | 100.0% | 95.8% | 17 | 94.1% | 84.2% |
| `low` | 106 | 99.1% | 100.0% | 81 | 96.3% | 98.7% |

**`high` urgency is measured on 15 tickets on dev and 10 on test.** At n=15 a single miss
is 6.7 points, and the 95% Wilson interval around 100% recall still runs from 79.6% to
100% (72.3% to 100% at n=10). Perfect recall here means "no misses in fifteen", which is
encouraging and is not the same as reliable. The same caveat applies to escalation (12 and
11 in the reference) and to every hard-case slice, which are 2 tickets each. Only `low`,
`normal` (now that D-018 has settled it), and intent overall have samples where a couple
of points mean anything.

### What is still wrong

- **Spurious `out_of_scope` escalations remain**, unchanged by brief v3: 2 of dev's 4
  `out_of_scope`-reason predictions and 1 of test's 3 have no matching gold reason, every
  one a "make a claim / file a complaint" ticket read as a legal or regulatory process
  rather than a customer complaint. Brief v2's clarification targeted unfamiliar *product
  and tier names*; this is a different trigger, on different vocabulary, and D-018 was the
  higher-value fix to make first. It is now the router's first target — see `DECISIONS.md`.
- D-018's account-admin question is settled (brief v3, `DECISIONS.md` D-020); it is no
  longer an open question in this table.
- Escalation recall on dev dropped to 0.92 this run (11/12, one missed
  `refund_over_threshold`) — noise at n=12, not a labels-vs-prompt effect; test recall
  stayed at 1.00 (11/11).

## Label quality

The reference labels are model-drafted, so how often they are *wrong* bounds how
precisely anything else can be known. This has now been measured twice, on two **random
blocks that must not be pooled** — they sample different populations at different times.

| | Corrected | Reviewed | Error rate | 95% CI (Wilson) | Population |
|---|---:|---:|---:|---:|---|
| Round 1 block | 6 | 30 | 20.0% | 9.5% – 37.3% | all 252, before any correction |
| **Round 2 block** | 1 | 30 | **3.3%** | 0.6% – 16.7% | the 197 never reviewed, after the sweep |
| Targeted picks | 6 | 25 | 24.0% | — | chosen for looking wrong; not a population |

Three things about those numbers:

- **Round 1 is restated from 16.7% to 20.0%.** Round 2 found `hl-0093`, a label round 1
  read and explicitly confirmed, to be wrong. That is the sharpest evidence in the project
  that a second-opinion review by a model is not verification. `DECISIONS.md` D-017.
- **Round 2 is not an independent audit.** The same model wrote the sweep rules and then
  measured what they left behind, so 3.3% is what one reviewer finds after correcting the
  errors that reviewer already knows about. The true residual rate is higher by an unknown
  margin.
- **Both intervals are wide.** Thirty tickets separates "a few percent" from "a third" and
  nothing finer. Separating 3% from 10% with any confidence needs roughly 150–200 in the
  block, or a genuinely independent reviewer, which is the only thing that fixes the first
  two points as well.

`make review` / `make review-round2` export the two kinds of sample; `make import-review`
folds corrections back in and prints both rounds with intervals. Re-exporting round 1 is
additive: rows already in the file stay, with anything already typed into them.

### The rule sweep

Brief v2 made two kinds of label wrong that v1 allowed, and both were enumerable, so
`make sweep` applies them to the whole set rather than re-reading 197 tickets one at a
time. It changed 13 labels: 2 contradictory `out_of_scope` escalations dropped, 11
pre-dispatch order changes raised to `high`.

A sweep is a **consistency mechanism, not a check**: it finds only the errors its rules
describe. Swept tickets are therefore *not* marked `reviewed` and still count as unchecked
in the error rate above — a test asserts it — and two of them landed in round 2's block,
where they were confirmed.

## Status

See `CLAUDE.md`.
