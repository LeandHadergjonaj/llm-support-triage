# Payments & billing

*Internal policy reference. Covers a payment the customer is trying to make and cannot, and
questions about how they are charged. Where the customer can no longer afford or no longer
wants to pay for an order already placed, that is a cancellation — see
`cancellations_and_order_changes.md` and client brief v3 §3, not this document.*

## 1. Accepted payment methods

Visa, Mastercard and Amex debit and credit cards, Apple Pay, Google Pay, and PayPal. There is
no invoice-on-account option — Hearth & Loom sells direct-to-consumer only, with no trade
accounts (client brief v3 §1), so every order is paid at checkout by one of these methods.

## 2. Declined or failing payments

Most checkout failures are the card issuer declining the authorisation, not a Hearth & Loom
system fault — check whether the customer has tried a second card or payment method before
escalating anything as a system problem. Common causes worth naming to the customer: the
card's contactless/online limit, insufficient funds, or the billing address on file not
matching what the bank has.

## 3. Authorisation holds and multiple pending charges

At checkout, card issuers place a temporary **authorisation hold** for the order amount,
which is separate from the actual **capture** that happens at dispatch. It is normal to see
what looks like a duplicate pending amount in the days between placing an order and it
dispatching — most issuers show the authorisation and, once dispatch triggers the real
capture, a second pending entry, before the original authorisation drops off automatically
(this can take up to 7 days on the issuer's side, which Hearth & Loom has no control over).
Only one of the two amounts is ever actually taken. This is not the same as being charged
twice; a genuine duplicate charge is where two amounts both settle (move from pending to
posted) for one order, which is rare and should be treated as a payment error requiring a
refund of the extra amount, not explained away as a hold.

## 4. Invoices and receipts

An order confirmation email doubles as a receipt for VAT purposes and is sent automatically
at checkout; a formal invoice, if needed for expensing or accounting, can be generated from
the same order record and should show the same items and total as the confirmation email.

## 5. Where this document does not apply

If a payment did go through and the question is about getting money back — a refund, a
return, an overcharge that already settled — that is `returns_and_refunds.md`, not this
document. If the customer's actual ask is to stop paying for an order that has not
dispatched, that is a cancellation (`cancellations_and_order_changes.md`), whatever words
they use for it ("I can't afford this any more", "please cancel the payment").
