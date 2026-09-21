# Baseline results -- dev split

- Prompt: `baseline_v1`
- Model: `gpt-5.6-terra` (effort `high`)
- Run at: 2026-09-21T14:40:32+00:00
- Tickets: 144
- Reference labels drafted by: gpt-5.6-terra (effort high)
- Reviewed by: claude-opus-5 (Anthropic)

> ### :warning: These numbers are self-agreement, not accuracy
>
> `gpt-5.6-terra` **drafted the reference labels it is being scored against here.** Urgency and escalation labels came from the same model on the same brief. A model agreeing with its own earlier judgement is not evidence that the judgement was right, so every figure below is optimistic by an unknown margin -- most of all on the judgement calls (urgency, escalation) and least on intent, which for Bitext tickets comes from a deterministic mapping rather than from the model.
>
> **No label in this project has been checked by a person.** 27 of 144 tickets in this split have been through a second-opinion review by claude-opus-5 (Anthropic), a model of a different family from the drafter. That is a real independence check and it is not the same as human verification: where two models disagree you learn the label is contested, not which reading a person would have picked, and where they agree they may be agreeing about the same misreading.
>
> Treat this as **a fixed bar for later versions to beat, not a measure of how good the triage is.** Later versions are scored on the same labels, so the comparison between them stays valid even while the absolute number does not.

## Headline

| Metric | Value |
|---|---|
| Intent accuracy | 93.8% |
| Urgency accuracy | 91.7% |
| Escalation accuracy | 98.6% |
| All three correct | 86.8% |

## Escalation

| Outcome | Count |
|---|---:|
| Correct escalations | 14 |
| Unnecessary escalations | 2 |
| Missed escalations | 0 |
| Correct non-escalations | 128 |

Precision 0.875, recall 1.0. Reference escalation rate 9.7%, predicted 11.1%.

### Reconciliation with the label set

The eval set holds **25 escalations across 252 tickets** (dev 14 of 144; test 11 of 108). The splits partition the set, so those counts add up rather than overlap.

This run scored the **dev** split: 144 tickets carrying 14 reference escalations, of which 14 were caught and 0 missed, plus 2 escalations predicted that the reference does not have. 14 = 14 + 0.

## Label error rate

Measured on the **random block** -- 30 tickets drawn uniformly from all 252, which is the only part of the review sample that estimates the set as a whole.

| | Corrected | Reviewed | Error rate | 95% CI |
|---|---:|---:|---:|---:|
| Random block | 5 | 30 | 16.7% | [7.3%, 33.6%] |
| Targeted picks | 6 | 25 | 24.0% | [11.5%, 43.4%] |

Wilson score interval. The targeted picks were chosen for looking wrong, so their rate is biased upwards by construction -- a diagnostic of where the drafter struggles, not an estimate of the set. Do not average the two rows.

Read the accuracy figures above against this: roughly 17% of reference labels are wrong (95% CI 7%-34%), which bounds how precisely any of them can be known.

## Urgency

Urgency is heavily skewed, so accuracy alone flatters any model that follows the skew. The comparison against always predicting the most common class is the one to read, and macro recall -- the mean of the per-class recalls -- is the number that does not improve just by guessing `low` more often.

| | Model | Always predict most common class |
|---|---:|---:|
| Accuracy | 91.7% | 69.4% (`low`, 69.4% of the reference) |
| Macro recall | 77.7% | 33.3% |

Accuracy gain over the constant predictor: **+22.2 points**.

| Urgency | Support | Predicted | Recall | Precision |
|---|---:|---:|---:|---:|
| `high` | 8 | 4 | 50.0% | 100.0% |
| `normal` | 36 | 38 | 86.1% | 81.6% |
| `low` | 100 | 102 | 97.0% | 95.1% |

## Cost and latency

- Total cost: **$0.1610** for 144 tickets
- Cost per ticket: $0.001118
- Latency: mean Nones, p50 Nones, p95 Nones (at 8 concurrent requests)
- Cache: 173104 input tokens served from cache, 3436 written
- Reasoning tokens: 229 (billed as output)

## Easy vs hard

| Slice | n | Intent | Urgency | Escalation |
|---|---:|---:|---:|---:|
| Bitext tickets | 126 | 93.7% | 91.3% | 98.4% |
| Authored hard cases | 18 | 94.4% | 94.4% | 100.0% |

### By hard-case kind

| Kind | n | Intent | Urgency | Escalation |
|---|---:|---:|---:|---:|
| ambiguous | 2 | 100% | 100% | 100% |
| angry | 2 | 100% | 100% | 100% |
| high_value_refund | 2 | 100% | 100% | 100% |
| legal | 2 | 100% | 100% | 100% |
| multi_issue | 2 | 50% | 50% | 100% |
| off_topic | 2 | 100% | 100% | 100% |
| safety | 2 | 100% | 100% | 100% |
| security | 2 | 100% | 100% | 100% |
| typos | 2 | 100% | 100% | 100% |

## Top intent confusions

| Reference | Predicted | n |
|---|---|---:|
| billing_and_payment | out_of_scope | 1 |
| order_management | billing_and_payment | 1 |
| feedback_and_complaint | returns_and_refunds | 1 |
| delivery_and_shipping | order_management | 1 |
| feedback_and_complaint | out_of_scope | 1 |
| returns_and_refunds | feedback_and_complaint | 1 |
| account_management | out_of_scope | 1 |
| delivery_and_shipping | returns_and_refunds | 1 |
| returns_and_refunds | out_of_scope | 1 |

## Confidence calibration

| Confidence | n | All three correct |
|---|---:|---:|
| [0.00, 0.50) | 2 | 50.0% |
| [0.50, 0.70) | 6 | 66.7% |
| [0.70, 0.80) | 18 | 83.3% |
| [0.80, 0.90) | 19 | 73.7% |
| [0.90, 0.95) | 23 | 95.7% |
| [0.95, 1.00) | 76 | 90.8% |
