# Mock orders database

`orders.jsonl`, one JSON object per line, keyed on `order_id`. **Entirely synthetic** —
written by Claude Sonnet 5 for this project, no real customer or order data. Customer names
are invented and unrelated to any real person.

31 of the 32 orders exist because a ticket in `data/eval/{dev,test}.jsonl` or
`data/eval/answers_{dev,test}.jsonl` names that order number — the DB was built to ground
those tickets' facts (item, price, dispatch state, refund status), not the other way round.
`53004` is deliberately **absent**: `hl-a0004` in the answer eval asks about an order that
does not exist, to test that an answer says so instead of inventing order details. `53005`
and `53006` exist purely to ground two authored answer-eval cases (a customer misstating an
order's price, and a two-item refund that stays under the £100 threshold even combined).

## Fields

| Field | Meaning |
|---|---|
| `order_id` | 5-digit string, matches the numbers referenced in ticket text |
| `items` | `[{name, unit_price_gbp, qty}]` |
| `order_total_gbp` | Sum of item lines; what "the order" means for the £100 refund threshold (brief v3 §5) unless a `refund` record states its own figure |
| `delivery_option` | `standard` / `next_day` / `two_person` (brief v3 §1) |
| `dispatch_state` | `not_dispatched` / `dispatched` / `delivered` — the fact the pre-dispatch window (brief v3 §4) turns on |
| `expected_delivery_date` | For late-delivery grounding: compare against `dispatched_date`/`delivered_date` and "today" (this project's reference date is 2026-09-21, matching the result timestamps in `results/`) |
| `status` | `active` / `cancelled` / `return_requested` |
| `refund` | `null`, or `{requested_gbp, requested_date, status, resolved_date, note}` — `status` is one of `processing`, `approved_awaiting_payout`, `paid` |
| `note` | Free-text operational detail a real order record would carry (short-shipment, disputed delivery, packaging refusal) — the fact an answer has to get right, not decoration |
| `payment` | Present only where a ticket raises a payment question (authorisation holds, capture state) |

## Coverage this deliberately includes

- **Pre- vs post-dispatch**: `not_dispatched` (e.g. `50339`, `51986`), `dispatched`-not-yet-
  delivered (`49488`, `47156`, `51647`, `53002`), `delivered` (`46115`, `48219`, `50441`, …).
- **Refunds either side of the £100 threshold**: `51877` (£95, no escalation), `53001`
  (exactly £100 — *not* over the threshold, brief v3 §5 says "over £100"), `46115` (£680,
  escalates), `52001` (two items, £74 + £58 = £132 combined — escalates only when read as
  one order, testing whether an answer sums the order rather than checking each line).
- **Late delivery**: `47156`, past its `expected_delivery_date` by over a week with no
  `delivered_date` and a stalled tracking note.
- **Disputed/short-shipped delivery**: `50118` (one line never dispatched), `49877` (courier
  says delivered, customer disputes one of two parcels).
- **Refund already agreed but not paid out**: `51204`, `49001` — chasing an agreed refund
  (`returns_and_refunds`, not `product_issue`), brief v3 §3.
- **A cancelled order with a completed refund**: `53003`, so an answer eval ticket can ask
  "what happened to order 53003" and be graded on citing a *closed* case correctly.
- **A collection refused / solicitor engaged**: `47338`, for the `legal_or_chargeback_threat`
  escalation case, where the correct answer is "a human is handling this," not new detail.
