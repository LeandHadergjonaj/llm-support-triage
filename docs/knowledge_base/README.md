# Hearth & Loom knowledge base

Six policy documents written for this project by Claude Sonnet 5, in the voice of Hearth &
Loom's internal policy team — **not real company documents**, and not written or reviewed by
any human at Hearth & Loom, which doesn't exist. They exist so that a later answering system
has something to ground its answers in, and so the answer eval (`data/eval/answers_*.jsonl`)
has something to check answers against.

They must **agree with `docs/client-brief.md` v3** wherever the two overlap (the £100
refund threshold, the pre-dispatch window, the account-admin urgency rule) — the brief still
governs every triage label, per `CLAUDE.md` rule 1. Where these documents go further than the
brief (return windows, restocking fees, processing times), that is new policy content the
brief was never asked to define, invented here as a reasonable retailer's policy would read,
not as a rule that changes any label.

| Document | Covers |
|---|---|
| `returns_and_refunds.md` | Refund and return eligibility, windows, the £100 review threshold, cancellation fees |
| `delivery_and_shipping.md` | Delivery options and timescales, address changes, late/lost deliveries |
| `cancellations_and_order_changes.md` | Cancelling, editing or adding to a live order, the dispatch cutoff |
| `payments_and_billing.md` | Accepted payment methods, failed payments, authorisation holds, invoices |
| `accounts.md` | Account creation, editing, deletion, password/PIN reset, account security |
| `product_safety.md` | Handling a report that goods caused or could cause harm |

## The planted inconsistency

`returns_and_refunds.md` states Hearth & Loom's refund timeline (5 working days from
approval) as authoritative for the whole company. `delivery_and_shipping.md`'s "Late or
delayed deliveries" section, written independently by whoever last touched that document,
quotes a different figure (10 working days) for the delivery-charge portion of a late-order
refund — the same kind of promise, a different number, with no cross-reference back to the
returns document. `returns_and_refunds.md` states the precedence rule: it governs refund
timing wherever another document states a different figure. Real staff documents accumulate
exactly this kind of drift because different sections get edited by different people at
different times; this one is planted on purpose so the answer eval (`hl-a0003` — see
`data/eval/answers_dev.jsonl`) can check whether an answer resolves it correctly (5 working
days, citing the precedence rule) rather than picking whichever document it happened to
retrieve first.

## Decisions made writing these

Two places where the brief is silent and a real retailer's policy would still need an
answer. Both logged in `DECISIONS.md` (D-022): a restocking fee on large, two-person-delivery
furniture returned for change of mind, and a standard refund-processing timeline. Neither
changes a triage label — the brief's `returns_and_refunds` category already covers
"cancellation fees" and "refund ... policy questions" without saying what the fee or the
timeline is.
