# Cancellations & order changes

*Internal policy reference. This is the document behind the client brief's "pre-dispatch
window" (brief v3 §4) — the brief defines which tickets are urgent because of it; this
document defines what actually happens to the order.*

## 1. The dispatch cutoff

An order can be cancelled, have items removed or swapped, or be corrected, free of charge
and without question, **at any point before it dispatches**. Once the warehouse has picked
and packed an order for collection by the courier, none of this is possible any more through
the ordinary process — see §4 for what to do instead.

Orders typically dispatch within 1–2 working days of being placed for standard delivery, and
same-day for next-day orders placed before the 2pm cut-off (`delivery_and_shipping.md` §1).
**There is no reliable way to tell from the order record alone exactly how many hours remain
before dispatch** — the warehouse batches picking runs through the day, so an order placed
an hour ago is not automatically safe. Treat any request that arrives while
`dispatch_state` still reads `not_dispatched` as still actionable, and pass it to the
warehouse queue immediately rather than waiting to see whether it "should" have shipped by
now.

## 2. Cancelling or changing part of an order

- **Cancelling** the whole order before dispatch: full refund, no fee, processed under
  `returns_and_refunds.md` §4–5.
- **Removing or swapping items**: free before dispatch. If the change reduces the order
  total, refund the difference the same way.
- **Correcting a mistake** (wrong size, wrong colour, wrong quantity): treated the same as a
  swap.
- **Adding items**: this is a new addition to an existing order, not a change that has to
  race the dispatch clock. Where the addition would push the order over the two-person
  delivery threshold (large item added to a standard order), it may need to be raised as a
  new order instead — check `delivery_and_shipping.md` §1 before promising one dispatch date
  for the whole lot.

## 3. Changing the delivery address before dispatch

An address change before dispatch is a change to the order and follows §1's cutoff exactly
like a cancellation. Once dispatched, it becomes a courier-side redirect request instead —
see `delivery_and_shipping.md` §3 — which is not guaranteed to succeed, so do not treat the
two situations as interchangeable when replying.

## 4. After dispatch

Once an order has dispatched, none of §1–3 apply through this process. The customer's
options are: refuse the delivery when it arrives and it will be treated as a return once the
courier brings it back (`returns_and_refunds.md` §1, and note the two-person restocking fee
at §2 if it is large furniture and the reason is change of mind rather than a fault), or wait
for delivery and return it under the normal returns window. There is no way to intercept a
dispatched parcel from this side of the courier network.

## 5. What this document does not cover

Refund amounts and timelines: `returns_and_refunds.md`. Payment failures at checkout, or a
customer no longer wishing to pay for an order (which is a cancellation under this document,
not a billing matter — client brief v3 §3): `payments_and_billing.md` for the payment side
only.
