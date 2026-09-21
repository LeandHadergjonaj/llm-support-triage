# Router results -- dev split

> Same model, same brief as the baseline of record. The only difference is design: a prompt clarification, a deterministic policy layer, and a confidence gate that sends uncertain tickets to a human. See `router.py` and `DECISIONS.md`.

- Model: `gpt-5.6-terra` (effort `high`), brief `v3`
- Confidence threshold: `0.7`
- Tickets: 144

## Headline: router vs the baseline of record

| Metric | Router | Baseline |
|---|---:|---:|
| Intent accuracy | 97.2% | 95.1% |
| Urgency accuracy | 98.6% | 99.3% |
| Escalation accuracy | 100.0% | 97.9% |
| All three correct | 95.8% | 94.4% |

## Matched-pair comparison (same tickets)

- Fixed (baseline wrong, router right): **5** -- hl-0033, hl-0098, hl-0112, hl-0219, hl-0232
- Broken (baseline right, router wrong): **3** -- hl-0047, hl-0137, hl-0178
- Both right: 133, both wrong: 3
- McNemar exact p (all three correct): **0.7266**
- Escalation only -- fixed 3, broken 0, McNemar p: **0.25**
- Exact two-sided McNemar test on the tickets where the two systems disagree. p < 0.05 is the usual bar for 'more than noise at this n'; with single-digit disagreement counts, treat anything above that as inconclusive, not as a tie.

## Escalation

| Outcome | Count |
|---|---:|
| Correct escalations | 12 |
| Unnecessary escalations | 0 |
| Missed escalations | 0 |
| Correct non-escalations | 132 |

Precision 1.0, recall 1.0.

## Self-handled vs sent to a human

`sent_to_human` is broader than `escalate`: every escalated ticket goes to a human, and so does any ticket the model was not confident about, even with `escalate=False`. This is the brief's own open question (§5) resolved.

| | n | Rate / accuracy | 95% CI |
|---|---:|---:|---|
| Sent to a human | 20 | 13.9% | [9.2%, 20.5%] |
| Self-handled, all three correct | 124 | 96.8% | [92.0%, 98.7%] |

## Per-class urgency

| Urgency | Support | Predicted | Recall | Precision |
|---|---:|---:|---:|---:|
| `high` | 15 | 15 | 100.0% | 100.0% |
| `normal` | 23 | 23 | 95.7% | 95.7% |
| `low` | 106 | 106 | 99.1% | 99.1% |

## Cost and latency vs baseline

- Router: $0.1994 total, $0.001385/ticket, p50 Nones, p95 Nones
- Baseline: $0.1863 total, $0.001294/ticket, p50 2.14s, p95 3.33s

## Threshold scan (informational, computed from these same raw predictions)

| Threshold | Self-handled n | Self-handled accuracy | Human queue rate |
|---:|---:|---:|---:|
| 0.0 | 132 | 96.2% | 8.3% |
| 0.5 | 130 | 96.2% | 9.7% |
| 0.6 | 129 | 96.1% | 10.4% |
| 0.65 | 128 | 96.1% | 11.1% |
| 0.7 | 124 | 96.8% | 13.9% |
| 0.75 | 116 | 96.5% | 19.4% |
| 0.8 | 107 | 97.2% | 25.7% |
| 0.85 | 100 | 98.0% | 30.6% |
| 0.9 | 95 | 97.9% | 34.0% |
| 0.95 | 70 | 98.6% | 51.4% |
