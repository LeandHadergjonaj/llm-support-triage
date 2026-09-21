# Router results -- test split

> Same model, same brief as the baseline of record. The only difference is design: a prompt clarification, a deterministic policy layer, and a confidence gate that sends uncertain tickets to a human. See `router.py` and `DECISIONS.md`.

- Model: `gpt-5.6-terra` (effort `high`), brief `v3`
- Confidence threshold: `0.7`
- Tickets: 108

## Headline: router vs the baseline of record

| Metric | Router | Baseline |
|---|---:|---:|
| Intent accuracy | 98.2% | 96.3% |
| Urgency accuracy | 93.5% | 96.3% |
| Escalation accuracy | 100.0% | 99.1% |
| All three correct | 92.6% | 93.5% |

## Matched-pair comparison (same tickets)

- Fixed (baseline wrong, router right): **2** -- hl-0005, hl-0141
- Broken (baseline right, router wrong): **3** -- hl-0162, hl-0234, hl-0247
- Both right: 98, both wrong: 5
- McNemar exact p (all three correct): **1.0**
- Escalation only -- fixed 1, broken 0, McNemar p: **1.0**
- Exact two-sided McNemar test on the tickets where the two systems disagree. p < 0.05 is the usual bar for 'more than noise at this n'; with single-digit disagreement counts, treat anything above that as inconclusive, not as a tie.

## Escalation

| Outcome | Count |
|---|---:|
| Correct escalations | 11 |
| Unnecessary escalations | 0 |
| Missed escalations | 0 |
| Correct non-escalations | 97 |

Precision 1.0, recall 1.0.

## Self-handled vs sent to a human

`sent_to_human` is broader than `escalate`: every escalated ticket goes to a human, and so does any ticket the model was not confident about, even with `escalate=False`. This is the brief's own open question (§5) resolved.

| | n | Rate / accuracy | 95% CI |
|---|---:|---:|---|
| Sent to a human | 21 | 19.4% | [13.1%, 27.9%] |
| Self-handled, all three correct | 87 | 93.1% | [85.8%, 96.8%] |

## Per-class urgency

| Urgency | Support | Predicted | Recall | Precision |
|---|---:|---:|---:|---:|
| `high` | 10 | 10 | 100.0% | 100.0% |
| `normal` | 17 | 20 | 88.2% | 75.0% |
| `low` | 81 | 78 | 93.8% | 97.4% |

## Cost and latency vs baseline

- Router: $0.1442 total, $0.001335/ticket, p50 2.04s, p95 3.06s
- Baseline: $0.1415 total, $0.001310/ticket, p50 2.13s, p95 3.17s

## Threshold scan (informational, computed from these same raw predictions)

| Threshold | Self-handled n | Self-handled accuracy | Human queue rate |
|---:|---:|---:|---:|
| 0.0 | 97 | 91.8% | 10.2% |
| 0.5 | 94 | 93.6% | 13.0% |
| 0.6 | 90 | 93.3% | 16.7% |
| 0.65 | 89 | 93.3% | 17.6% |
| 0.7 | 87 | 93.1% | 19.4% |
| 0.75 | 83 | 92.8% | 23.2% |
| 0.8 | 79 | 92.4% | 26.9% |
| 0.85 | 74 | 93.2% | 31.5% |
| 0.9 | 66 | 92.4% | 38.9% |
| 0.95 | 48 | 91.7% | 55.6% |
