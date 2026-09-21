# Baseline results -- test split

- Prompt: `baseline_v1`
- Model: `gpt-5.6-terra` (effort `high`)
- Run at: 2026-09-21T14:40:33+00:00
- Tickets: 108
- Reference labels drafted by: gpt-5.6-terra (effort high)
- Reviewed by: claude-opus-5 (Anthropic)

> ### :warning: These numbers are self-agreement, not accuracy
>
> `gpt-5.6-terra` **drafted the reference labels it is being scored against here.** Urgency and escalation labels came from the same model on the same brief. A model agreeing with its own earlier judgement is not evidence that the judgement was right, so every figure below is optimistic by an unknown margin -- most of all on the judgement calls (urgency, escalation) and least on intent, which for Bitext tickets comes from a deterministic mapping rather than from the model.
>
> **No label in this project has been checked by a person.** 28 of 108 tickets in this split have been through a second-opinion review by claude-opus-5 (Anthropic), a model of a different family from the drafter. That is a real independence check and it is not the same as human verification: where two models disagree you learn the label is contested, not which reading a person would have picked, and where they agree they may be agreeing about the same misreading.
>
> Treat this as **a fixed bar for later versions to beat, not a measure of how good the triage is.** Later versions are scored on the same labels, so the comparison between them stays valid even while the absolute number does not.

## Headline

| Metric | Value |
|---|---|
| Intent accuracy | 97.2% |
| Urgency accuracy | 91.7% |
| Escalation accuracy | 98.2% |
| All three correct | 89.8% |

## Escalation

| Outcome | Count |
|---|---:|
| Correct escalations | 11 |
| Unnecessary escalations | 2 |
| Missed escalations | 0 |
| Correct non-escalations | 95 |

Precision 0.8462, recall 1.0. Reference escalation rate 10.2%, predicted 12.0%.

### Reconciliation with the label set

The eval set holds **25 escalations across 252 tickets** (dev 14 of 144; test 11 of 108). The splits partition the set, so those counts add up rather than overlap.

This run scored the **test** split: 108 tickets carrying 11 reference escalations, of which 11 were caught and 0 missed, plus 2 escalations predicted that the reference does not have. 11 = 11 + 0.

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
| Accuracy | 91.7% | 70.4% (`low`, 70.4% of the reference) |
| Macro recall | 82.4% | 33.3% |

Accuracy gain over the constant predictor: **+21.3 points**.

| Urgency | Support | Predicted | Recall | Precision |
|---|---:|---:|---:|---:|
| `high` | 6 | 5 | 66.7% | 80.0% |
| `normal` | 26 | 27 | 84.6% | 81.5% |
| `low` | 76 | 76 | 96.0% | 96.0% |

## Cost and latency

- Total cost: **$0.1248** for 108 tickets
- Cost per ticket: $0.001156
- Latency: mean Nones, p50 Nones, p95 Nones (at 8 concurrent requests)
- Cache: 129816 input tokens served from cache, 2772 written
- Reasoning tokens: 441 (billed as output)

## Easy vs hard

| Slice | n | Intent | Urgency | Escalation |
|---|---:|---:|---:|---:|
| Bitext tickets | 90 | 96.7% | 92.2% | 97.8% |
| Authored hard cases | 18 | 100.0% | 88.9% | 100.0% |

### By hard-case kind

| Kind | n | Intent | Urgency | Escalation |
|---|---:|---:|---:|---:|
| ambiguous | 2 | 100% | 100% | 100% |
| angry | 2 | 100% | 100% | 100% |
| high_value_refund | 2 | 100% | 100% | 100% |
| legal | 2 | 100% | 50% | 100% |
| multi_issue | 2 | 100% | 50% | 100% |
| off_topic | 2 | 100% | 100% | 100% |
| safety | 2 | 100% | 100% | 100% |
| security | 2 | 100% | 100% | 100% |
| typos | 2 | 100% | 100% | 100% |

## Top intent confusions

| Reference | Predicted | n |
|---|---|---:|
| feedback_and_complaint | out_of_scope | 2 |
| returns_and_refunds | feedback_and_complaint | 1 |

## Confidence calibration

| Confidence | n | All three correct |
|---|---:|---:|
| [0.00, 0.50) | 4 | 75.0% |
| [0.50, 0.70) | 8 | 87.5% |
| [0.70, 0.80) | 14 | 85.7% |
| [0.80, 0.90) | 16 | 87.5% |
| [0.90, 0.95) | 16 | 93.8% |
| [0.95, 1.00) | 50 | 92.0% |
