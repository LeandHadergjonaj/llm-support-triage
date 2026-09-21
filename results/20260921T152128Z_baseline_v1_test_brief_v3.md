# Baseline results -- test split

- Prompt: `baseline_v1` against client brief `v3`
- Model: `gpt-5.6-terra` (effort `high`)
- Run at: 2026-09-21T15:21:28+00:00
- Tickets: 108
- Reference labels drafted by: gpt-5.6-terra (effort high)
- Reviewed by: claude-opus-5 (Anthropic)

> ### :warning: These numbers are self-agreement, not accuracy
>
> `gpt-5.6-terra` **drafted the reference labels it is being scored against here.** Urgency and escalation labels came from the same model on the same brief. A model agreeing with its own earlier judgement is not evidence that the judgement was right, so every figure below is optimistic by an unknown margin -- most of all on the judgement calls (urgency, escalation) and least on intent, which for Bitext tickets comes from a deterministic mapping rather than from the model.
>
> **No label in this project has been checked by a person.** 42 of 108 tickets in this split have been through a second-opinion review by claude-opus-5 (Anthropic), a model of a different family from the drafter. That is a real independence check and it is not the same as human verification: where two models disagree you learn the label is contested, not which reading a person would have picked, and where they agree they may be agreeing about the same misreading.
>
> Treat this as **a fixed bar for later versions to beat, not a measure of how good the triage is.** Later versions are scored on the same labels, so the comparison between them stays valid even while the absolute number does not.

## Headline

| Metric | Value |
|---|---|
| Intent accuracy | 96.3% |
| Urgency accuracy | 96.3% |
| Escalation accuracy | 99.1% |
| All three correct | 93.5% |

## Escalation

| Outcome | Count |
|---|---:|
| Correct escalations | 11 |
| Unnecessary escalations | 1 |
| Missed escalations | 0 |
| Correct non-escalations | 96 |

Precision 0.9167, recall 1.0. Reference escalation rate 10.2%, predicted 11.1%.

### Reconciliation with the label set

The eval set holds **23 escalations across 252 tickets** (dev 12 of 144; test 11 of 108). The splits partition the set, so those counts add up rather than overlap.

This run scored the **test** split: 108 tickets carrying 11 reference escalations, of which 11 were caught and 0 missed, plus 1 escalations predicted that the reference does not have. 11 = 11 + 0.

## Label error rate

Measured on a **random block** -- tickets drawn uniformly from a defined population, which is the only part of a review sample that estimates anything. Rounds sample different populations at different times and are **never pooled or averaged**; the current estimate is the latest round.

| | Corrected | Reviewed | Error rate | 95% CI | Population sampled |
|---|---:|---:|---:|---:|---|
| Round 1 block | 6 | 30 | 20.0% | [9.5%, 37.3%] | all tickets, before any correction |
| Round 2 block **(current)** | 1 | 30 | 3.3% | [0.6%, 16.7%] | tickets not reviewed in an earlier round, after the rule sweep |
| Targeted picks | 6 | 25 | 24.0% | [11.5%, 43.4%] | chosen for looking wrong -- not a population |

Wilson score interval. The targeted picks were chosen for looking wrong, so their rate is biased upwards by construction -- a diagnostic of where the drafter struggles, not an estimate of the set. Do not average any of these rows.

Read the accuracy figures above against this: on the latest block roughly 3% of reference labels are wrong (95% CI 1%-17%), which bounds how precisely any of them can be known. That block was reviewed by the same model that wrote the correction rules it is checking, so it is not an independent measurement of their success.

## Urgency

Urgency is heavily skewed, so accuracy alone flatters any model that follows the skew. The comparison against always predicting the most common class is the one to read, and macro recall -- the mean of the per-class recalls -- is the number that does not improve just by guessing `low` more often.

| | Model | Always predict most common class |
|---|---:|---:|
| Accuracy | 96.3% | 75.0% (`low`, 75.0% of the reference) |
| Macro recall | 96.8% | 33.3% |

Accuracy gain over the constant predictor: **+21.3 points**.

| Urgency | Support | Predicted | Recall | Precision |
|---|---:|---:|---:|---:|
| `high` | 10 | 10 | 100.0% | 100.0% |
| `normal` | 17 | 19 | 94.1% | 84.2% |
| `low` | 81 | 79 | 96.3% | 98.7% |

## Cost and latency

- Total cost: **$0.1415** for 108 tickets
- Cost per ticket: $0.001310
- Latency: mean 2.27s, p50 2.13s, p95 3.17s (at 8 concurrent requests)
- Cache: 196128 input tokens served from cache, 2772 written
- Reasoning tokens: 653 (billed as output)

## Easy vs hard

| Slice | n | Intent | Urgency | Escalation |
|---|---:|---:|---:|---:|
| Bitext tickets | 90 | 95.6% | 96.7% | 98.9% |
| Authored hard cases | 18 | 100.0% | 94.4% | 100.0% |

### By hard-case kind

| Kind | n | Intent | Urgency | Escalation |
|---|---:|---:|---:|---:|
| ambiguous | 2 | 100% | 100% | 100% |
| angry | 2 | 100% | 100% | 100% |
| high_value_refund | 2 | 100% | 100% | 100% |
| legal | 2 | 100% | 100% | 100% |
| multi_issue | 2 | 100% | 100% | 100% |
| off_topic | 2 | 100% | 100% | 100% |
| safety | 2 | 100% | 100% | 100% |
| security | 2 | 100% | 50% | 100% |
| typos | 2 | 100% | 100% | 100% |

## Top intent confusions

| Reference | Predicted | n |
|---|---|---:|
| feedback_and_complaint | out_of_scope | 1 |
| returns_and_refunds | feedback_and_complaint | 1 |
| order_management | billing_and_payment | 1 |
| feedback_and_complaint | returns_and_refunds | 1 |

## Confidence calibration

| Confidence | n | All three correct |
|---|---:|---:|
| [0.00, 0.50) | 5 | 40.0% |
| [0.50, 0.70) | 10 | 90.0% |
| [0.70, 0.80) | 11 | 100.0% |
| [0.80, 0.90) | 6 | 100.0% |
| [0.90, 0.95) | 24 | 100.0% |
| [0.95, 1.00) | 52 | 94.2% |
