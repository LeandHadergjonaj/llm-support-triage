# Delivery & shipping

*Internal policy reference. See `cancellations_and_order_changes.md` for changing what is
in an order or where it goes before dispatch; this document covers delivery itself once an
order is on its way, and the ordinary delivery options offered at checkout.*

## 1. Delivery options

| Option | Timescale | Notes |
|---|---|---|
| Standard | 2–5 working days | Default option, single courier drop |
| Next-day | Next working day | Cut-off 2pm for same-day dispatch; order placed after 2pm dispatches the following working day |
| Two-person delivery | 5–10 working days, by appointment | Required for large furniture (sofas, bed frames, dining tables, wardrobes, and anything over 30kg); the courier calls to book a slot once the item reaches the local depot |

Delivery is available UK-wide including the Scottish Highlands and islands, Northern
Ireland, and offshore addresses, though two-person delivery to these areas can run at the
top of its stated window or slightly beyond it because of ferry and courier scheduling
outside the mainland network.

## 2. Tracking

A dispatch confirmation email with a tracking link goes out as soon as an order leaves the
warehouse. Where a customer says they cannot see a status and the order record shows
`dispatch_state: not_dispatched`, the honest answer is that it has not shipped yet — there is
nothing to track — rather than a generic "check your tracking link."

## 3. Changing a delivery address

Before dispatch, an address change is a change to the order — see
`cancellations_and_order_changes.md` §3, which also covers what happens if the change
arrives too close to the dispatch cut-off. **Once an order has dispatched, an address change
can only be requested through the courier directly** and is not guaranteed: most UK couriers
can redirect a parcel already in their network to a different address on the same
postcode-sortation route, but not to a different one, and cannot redirect at all once a
delivery slot has been booked for two-person items. Set expectations accordingly rather than
promising a redirect will succeed.

## 4. Late or delayed deliveries

An order is late once it has passed its `expected_delivery_date` shown on the order record
with no `delivered_date`. First step is always to check the courier's own tracking for a
scan update in the last 48 hours — a stalled tracking status for longer than that means the
parcel should be treated as lost, not merely delayed, and a replacement or refund process
should start rather than asking the customer to keep waiting.

Where a late delivery has caused the customer to miss something time-critical (a house move,
an event), treat it as they describe it rather than downgrading it because "the parcel is
probably still coming" — the client brief's urgency test is about consequence, and a missed
event is not undone by the parcel eventually turning up.

If a delivery is confirmed lost or a replacement is agreed, we will refund the delivery
charge itself within 10 working days of the request being approved, separately from any
refund for the goods, which follows the standard returns process.

## 5. Missing or short-shipped items

Where an order has more than one item and the courier's tracking shows the parcel delivered
but the customer disputes receiving all of it, check whether the order was shipped as
multiple parcels — large orders often are — before assuming the whole delivery is lost. A
short-shipment (one parcel genuinely never left the warehouse) is a warehouse error, not a
courier one, and should be resolved by dispatching the missing line rather than treating it
as a lost-parcel investigation.

## 6. What this document does not cover

Order changes and cancellations before dispatch: `cancellations_and_order_changes.md`.
Refund amounts, timelines and the £100 review threshold: `returns_and_refunds.md`.
