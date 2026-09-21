# LLM support triage — Hearth & Loom

Routing customer support tickets for a fictional online homewares retailer: what is this
ticket about, how urgent is it, does a human need to handle it, and — as of step 3b — what
should the reply say.

This repository is at **step 3b of a staged build**. Step 1 was an evaluation set and a
deliberately simple baseline — one LLM call per ticket. Step 2 settled the one open policy
question the baseline could not answer on its own (`DECISIONS.md` D-018/D-020) and added a
router: a prompt fix, a deterministic policy layer, and a confidence gate. It did **not**
beat the baseline outside noise (McNemar p=0.73 dev, p=1.0 test), and with errors down to
single digits this eval set can no longer tell triage designs apart — see `DECISIONS.md`
D-022. Step 3a stopped chasing triage accuracy and built the next measuring stick instead: a
knowledge base (`docs/knowledge_base/`), a mock orders database (`data/orders/`), and an
answer eval (`data/eval/answers_{dev,test}.jsonl`). Step 3b builds the thing that eval
measures: `src/triage/answerer.py`, one LLM call per ticket, no retrieval, order facts only
from a deterministic database lookup, never from the model's own reading. Dev converges to
100% required-fact coverage and forbidden-content avoidance on the tickets it routes
correctly; test (run once, unmodified after) sits lower, and `DECISIONS.md` D-024 explains
exactly why rather than smoothing it over. There is still no review-queue UI and no
deployment, on purpose.

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
| `src/triage/router.py` | The router: a prompt fix, a deterministic policy layer, a confidence gate |
| `src/triage/evaluate_router.py` | Runs the router over a split and compares it to the baseline of record |
| `prompts/baseline_v1.md` | The baseline prompt, rendered so it can be read and diffed |
| `docs/knowledge_base/` | Six policy documents an answering system will ground replies in, consistent with the brief, with one planted cross-document inconsistency |
| `data/orders/` | A 30-order mock database, mostly tied to specific tickets rather than generic filler |
| `data/eval/answers_{dev,test}.jsonl` | The answer eval: 36 tickets with `must_handle` + grounding contracts instead of triage labels |
| `src/triage/eval_answers.py` | Scores a candidate-answers file against the answer eval; states its own judge bias |
| `src/triage/answerer.py` | Writes the customer reply or human handover note; KB in the prompt, order facts from a DB lookup only |
| `src/triage/evaluate_answerer.py` | Runs router + answerer + judge over a split end to end and scores it |
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

## Router results

`router_v1` (`src/triage/router.py`, run via `make eval-router` / `make eval-router-test`):
the same model and the same brief v3 prompt as the baseline, plus three additions —

1. A prompt clarification for the "make a claim / file a complaint" failure pattern above.
2. A deterministic policy layer applied to every live prediction: `product_safety` always
   forces `urgency=high`, and an `out_of_scope` escalation reason is dropped whenever the
   intent isn't also `out_of_scope` — the same two invariants `sweep.py` enforces on the
   label set, enforced here on the model's own output instead.
3. A confidence gate: `sent_to_human = escalate OR confidence < 0.7`. The threshold was
   chosen on dev only, from a scan over nine candidate values computed for free from
   predictions already paid for (`--rescore`, no extra API calls) — self-handled accuracy
   peaks at 0.7 and climbs no further, because the three dev tickets the router still gets
   wrong are all high-confidence (0.83–0.98); no threshold catches those. It answers brief
   §5's explicitly open question about how low confidence should feed the review queue.

> ### It does not beat the baseline outside noise
>
> | | Dev (144) | Test (108) |
> |---|---:|---:|
> | All three correct, router | 95.8% | 92.6% |
> | All three correct, baseline | 94.4% | 93.5% |
> | Fixed / broken (matched pairs) | 5 / 3 | 2 / 3 |
> | McNemar exact p | 0.73 | 1.0 |
>
> Dev moved in the router's favour, test moved against it, and neither is remotely
> significant — an exact McNemar test on tickets where the two systems disagree gives
> p=0.73 and p=1.0, and single-digit disagreement counts are exactly the regime where
> "which one is ahead this run" is noise. **Read this as: no demonstrated accuracy win at
> this sample size**, not as a negative result either — see `DECISIONS.md` D-021 for what
> the router did and did not do, and why.

What it *did* do, independent of the non-significant headline: fixed all three
`out_of_scope` mislabels it targeted (`hl-0112`, `hl-0219` on dev, `hl-0005` on test — 3
for 3), and by construction can no longer emit a `product_safety` ticket below `high` or a
self-contradictory `out_of_scope` reason. The three tickets it breaks on test are all
urgency-only misses on the `normal`/`low` boundary unrelated to either design change — one
of them (`hl-0234`, "how soon can I expect my shipment") is the same boundary D-017 already
documented as unstable run to run, not a router regression.

| | Dev (144) | Test (108) |
|---|---:|---:|
| Sent to a human | 20 (13.9%) | 21 (19.4%) |
| Self-handled, all three correct | 96.8% (n=124) | 93.1% (n=87) |
| Cost per ticket | $0.001385 | $0.001335 |
| Baseline cost per ticket | $0.001294 | $0.001310 |

The router costs 6–7% more per ticket than the baseline — one added prompt paragraph; the
policy layer and confidence gate are free post-processing. Not worth optimising away at
these amounts, and not something that would offset an accuracy win this small anyway.

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

## Phase 3a: knowledge base, orders database, answer eval

Nothing in this phase answers a ticket. It exists so the next phase has something to
ground answers in and something to be scored against, in that order, per `DECISIONS.md`
D-022.

**`docs/knowledge_base/`** — six policy documents (returns & refunds, delivery & shipping,
cancellations & order changes, payments & billing, accounts, product safety), consistent
with `docs/client-brief.md` v3 wherever they overlap. They read like real staff documents:
cross-referenced, with exceptions buried mid-paragraph rather than bulleted up front. One
inconsistency is planted on purpose — `returns_and_refunds.md` states a 5-working-day
refund timeline as authoritative; `delivery_and_shipping.md`'s late-delivery section
quotes 10 working days for the delivery-charge portion of a late-order refund, with no
cross-reference back. `returns_and_refunds.md` states the precedence rule.

**`data/orders/orders.jsonl`** — 30 synthetic orders. 27 are tied to a specific ticket
already in `data/eval/` or `answers_{dev,test}.jsonl`, so the eval is grounded in facts
that actually match what a ticket says, not generic filler. Covers pre/post dispatch,
refunds either side of £100 (a combined-items case at £132, an exact-£100 boundary case),
a late delivery, a short-shipment, and one ticket that asks about an order that does not
exist (`53004`), on purpose.

**`data/eval/answers_{dev,test}.jsonl`** — 36 tickets, 20/16 dev-test, 20 reused from the
Phase 1 eval set (to ground facts, not just labels) and 16 newly authored to cover what
Phase 1 never needed to: refund-amount boundaries on both sides of £100, the pre-dispatch
vs dispatched-vs-delivered distinction for address changes, a customer misstating an
order's price, and the planted inconsistency above. Each ticket carries `must_handle`
(`self`/`human`) plus `expected_must_contain` / `expected_must_not_contain`, every item
traceable to a knowledge-base section or an order field.

**Scoring** (`src/triage/eval_answers.py`): routing (`handled_by` vs `must_handle`) is an
exact match, no judgement involved. Content — did the answer state the right facts, did it
avoid inventing anything — is graded by an LLM (`gpt-5.6-terra` by default), because the
criteria are natural-language claims a keyword match cannot check reliably. **This is not
independent verification**: the judge defaults to this project's own triage model, the
same vendor and potentially the same model a future answering system would run on, which
is the same shape of bias `DECISIONS.md` D-011 names for the label review. `tests/test_eval_answers.py`
exercises the aggregation logic with a stubbed judge, so the scorer's own correctness
does not depend on the API. No API spend was needed to build this step.

## Phase 3b: the system answers tickets

`src/triage/answerer.py` — one LLM call per ticket, `gpt-5.6-terra`. The router (Phase 2,
unchanged) decides `self` vs `human` first; the answerer writes the customer reply or the
handover note. The whole knowledge base goes in the prompt (~5k tokens, well under
anything that needs retrieval); order facts come only from a regex-extracted order number
looked up in `data/orders/orders.jsonl` — never from the model reading the ticket — and the
prompt requires saying "no record found" rather than guessing. The system never claims to
have already cancelled, changed or refunded anything, per brief v3 §6.

**Results** (`results/latest_answerer_{dev,test}.json`):

| Metric | Dev (n=20) | Test (n=16, run once) |
|---|---:|---:|
| Routing accuracy | 95.0% [76.4–99.1%] | 93.75% [71.7–98.9%] |
| Required fact coverage | 100% (38/38) [90.8–100%] | 83.87% (26/31) [67.4–92.9%] |
| Forbidden-content avoidance | 100% (34/34) [89.9–100%] | 100% (25/25) [86.7–100%] |
| Fully correct, of routed correctly | 100% (19/19) [83.2–100%] | 80.0% (12/15) [54.8–93.0%] |

Cost: $0.001834/ticket dev, $0.002692/ticket test (three calls per ticket — router, answer,
judge), mean latency ~2.9s. Phase total $0.2949; project-to-date $2.3860.

**The traps, specifically:**

| Trap | Ticket(s) | Result |
|---|---|---|
| Refund-timing inconsistency (5 vs 10 working days) | `hl-a0003` | Resolved correctly — cites 5 working days, the authoritative document |
| Nonexistent order (53004) | `hl-a0004` | Correctly reported as not found, asked for confirmation, nothing invented |
| £100 boundary, exactly £100 | `hl-a0001` | Correctly not escalated / no senior review stated |
| £100 boundary, £100.01 | `hl-a0002` | Correctly escalated |
| £100 boundary, two items summing over | `hl-0011` | Correctly escalated and grounded (one required fact mis-scored — see below) |
| £100 boundary, two items summing under | `hl-a0013` | Correctly not escalated |

**Test is lower than dev, and `DECISIONS.md` D-024 explains why rather than rounding it
up.** One routing "miss" (`hl-a0012`) is very likely a Phase 3a labelling mistake, not a
system error — the ticket states a £150 refund the router (which never sees order records)
correctly escalates on per brief v3 §5, even though the order record later shows the real
item is £95. Two required-fact "misses" (`hl-0011`, `hl-0236`) are eval-criterion defects
found only after test was scored — one criterion literally demanded the *absence* of
content (impossible to satisfy), the other demanded a machine-format date no natural reply
would include. **All three are left uncorrected on this run, on purpose**, exactly because
finding them after seeing test is not licence to fix them before reporting the number.
Recomputed by hand only for this paragraph: excluding the two known-bad criteria puts
required fact coverage at 28/29 = 96.6%, much closer to dev — the recorded 83.87% is the
number that stands.

**The judge check.** Claude Sonnet 5 (a different model family from the judge) blind-graded
all 19 correctly-routed dev answers before looking at the judge's verdicts, and separately
gave the judge four deliberately broken answers (wrong-document figure, a boundary
misapplied, an invented refund+date+return-by-parcel, a bogus fee). **100% agreement across
88 individual judgements.** This says the judge reliably catches clear-cut violations — it
does not say the judge is a careful reader of ambiguous criteria, which the two post-test
findings above show it is not. Treat `required_fact_coverage` as trustworthy for "did the
answer get the substance right," and treat any single-digit gap from 100% as needing a
human look at *why*, not as a precise defect count.

**One strong answer** (`hl-a0003`, resolving the planted inconsistency): *"Once approved,
refunds are returned to the original payment method within 5 working days. No refund
amount is being discussed here, so no senior-review threshold applies."* Grounded, correct
document, nothing invented.

**One weak answer** (`hl-0236`, the three-ask ticket): the reply correctly stated the
refund's approval date and status, but neither actioned nor clearly promised the address
change or the marketing opt-out, instead explaining how the customer or support *could* do
them — a direct consequence of the ground rule against claiming account actions were
performed, which may be broader than brief v3 §6 actually requires. A real design tension,
not a bug, and named as the next thing to resolve.

**Natural next step:** fix the three now-identified eval-criterion defects and the same
double-negative pattern class-wide (a proper sweep, not the one-keyword grep that caught
four of six); decide whether ground rule 3 should allow the system to action a saved
address or marketing preference, given brief v3 §6 only names *order* and *money* actions
as human-only. Phase 4 (the review queue) was explicitly out of scope for this step and
nothing here was built toward it.

## Status

See `CLAUDE.md`.
