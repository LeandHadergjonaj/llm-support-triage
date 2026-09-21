# Client brief: Hearth & Loom

*Status: fictional client, written for this project. This document is the source of truth
for the triage label set. Policy documents and the orders database in later steps must be
consistent with it.*

**Version: v2** — 2026-09-21. Changelog in §7. Every label, every prompt and every result
in this repository must state which version of this brief it was produced under.

---

## 1. The client

Hearth & Loom is an online homewares retailer selling into the UK. Soft furnishings,
lighting, tableware, small furniture. Typical basket is £40–£120; the long tail runs up to
around £900 for sofas, bed frames and large rugs. All prices and refunds are in **GBP (£)**.

They sell direct-to-consumer through their own website only — no marketplace listings, no
trade accounts, no physical shops. Delivery is by third-party courier, 2–5 working days
standard, with a next-day option. Larger furniture ships on a two-person delivery slot.

Support is a team of six, handling roughly 400 tickets a day through a shared inbox. They
have no tiering today: whoever picks a ticket up owns it. The two things that hurt are
(a) genuinely urgent tickets sitting behind routine ones, and (b) the tickets that should
never have been answered without a senior person looking at them.

## 2. What we are building

A triage layer in front of that inbox. For each incoming ticket it decides what the ticket
is about, how urgent it is, and whether a human must handle it. Routine tickets are answered
from policy documents and the orders database; anything risky or uncertain goes to a human
review queue.

This document defines the labels. It does not define the answers.

## 3. Intent categories

Eleven categories. Every ticket gets exactly one — the customer's **primary** ask.

| Category | Covers |
|---|---|
| `order_management` | Placing an order, cancelling an order, changing the contents of an order |
| `delivery_and_shipping` | Where is my order, delivery timescales and options, changing or setting a delivery address |
| `returns_and_refunds` | Requesting a refund, chasing a refund already agreed, refund and returns policy questions, cancellation fees |
| `billing_and_payment` | Payment failures, accepted payment methods, invoices and receipts |
| `account_management` | Creating, editing, deleting or switching an account |
| `account_access` | Cannot log in, password reset, registration problems, and suspected unauthorised access |
| `product_issue` | The goods themselves: damaged on arrival, faulty, wrong item, missing parts, and safety problems |
| `feedback_and_complaint` | Complaints about service, and unsolicited praise or reviews, where there is no other specific ask |
| `human_agent_request` | Explicitly asking to speak to a person, or for a phone number or contact route |
| `marketing_preferences` | Newsletter and marketing email subscribe / unsubscribe |
| `out_of_scope` | Not a Hearth & Loom support request: spam, sales pitches, job applications, wrong company, questions the support team has no remit over |

### Picking the primary ask when a ticket contains several

Work down this order and stop at the first rule that separates them:

1. **Irreversibility.** Prefer the ask whose outcome cannot be undone by handling it a day
   later. A refund can be chased again next week; a parcel sent to an address the customer
   has left may not come back.
2. **Value.** Where none of the asks is irreversible, prefer the one with the largest sum
   attached.
3. **Order of mention.** Where neither rule separates them, take the ask the customer
   raised first.

Praise attached to a complaint or a question is never the primary ask.

### Boundaries that come up constantly

- A refund **request caused by** a damaged item is `product_issue`, not `returns_and_refunds`.
  The defect is the thing that needs handling; the refund follows from it. Chasing a refund
  that has already been agreed is `returns_and_refunds`.
- "I want to complain about my late delivery" is `delivery_and_shipping`. Route
  `feedback_and_complaint` only when there is no concrete operational ask underneath.
- **"I can't pay for this any more" is `order_management`, not `billing_and_payment`.**
  `billing_and_payment` is for a payment the customer is *trying* to make and cannot — a
  declined card, a checkout error, a rejected payment method. Where the customer is saying
  they can no longer afford or no longer wish to pay for an order, the thing that has to
  happen is to the order, so it is `order_management` and follows the cancellation rules in
  §4.
- **An unfamiliar product, tier or fee name is not grounds for `out_of_scope`.** Judge the
  request, not the vocabulary. "Premium account removals", "freemium accounts" and
  "withdrawal fees" are a customer's words for closing an account, opening an account and
  cancellation charges. If a ticket's primary ask falls in any of the other ten categories,
  it is in scope, and `out_of_scope` may not also be recorded as an escalation reason
  (see §5).

## 4. Urgency

Three levels, judged on **what happens if this ticket waits**, not on how loudly it is written.
An angry customer asking a routine question is still routine; urgency and anger are separate
axes, and anger is handled by the escalation rules below.

| Level | Meaning | Target response |
|---|---|---|
| `high` | Waiting causes harm that cannot be undone later: physical safety, an account being actively misused, money moving irreversibly, or a time-boxed window about to close | Same working day |
| `normal` | The customer is blocked on something they are owed or have paid for, but a day's delay changes nothing material | 1–2 working days |
| `low` | Informational, administrative, or no one is blocked | 3–5 working days |

### The pre-dispatch window

The commonest time-boxed window is an order that has not shipped yet. A ticket is `high`
when it asks for **a change to a live order that has to take effect before dispatch**:

- cancelling it, in whole or in part — including "I no longer want it" and "I can no longer
  pay for it", which are cancellations in the customer's own words;
- removing items from it, swapping items, or correcting a mistake in it;
- changing the delivery address for goods that are on their way.

**Adding items is the exception and stays `low`.** Missing that window costs the customer a
second order, not a return. The test is consequence-based and the consequences differ.

Two qualifiers:

- **The ticket does not have to name a deadline.** Where it does not say whether the order
  has been dispatched, assume the window is still open. Being wrong that way costs a ticket
  answered sooner than it needed to be; being wrong the other way means unwanted goods ship
  and have to come back.
- **The ask must presuppose a live order.** "Cancel order 51986" and "remove some items from
  order 46399" do; "how do I update my delivery address" and "I want to add a second
  shipping address to my account" do not — those are administrative and take their urgency
  from the ordinary test.

Worked examples:

- `high` — "the glass shade cracked and cut my hand", "someone has changed my address and
  ordered a lamp", "cancel order 48812 before it ships today", "cancelling order 52507",
  "I made a mistake, I need to correct order 50064", "I've been charged three times for one order".
- `normal` — "where is order 48812, it was due Tuesday", "the refund you agreed on the 3rd
  hasn't arrived", "the bedside table arrived with a leg missing".
- `low` — "what are your delivery options to Scotland", "how do I add some items to order
  52020", "please take me off the newsletter", "do you accept Amex", "just wanted to say the
  cushions are lovely".

## 5. Escalation rules

Escalation means a human handles the ticket. The system does not send a reply.

A ticket **must** be escalated if any of the following hold. Record every reason that applies.

| Reason | Trigger |
|---|---|
| `refund_over_threshold` | The customer is asking for a refund, credit, replacement or compensation with a value **over £100**. Where a figure is stated, use it. Where no figure is stated, do not infer one — this reason does not apply. |
| `legal_or_chargeback_threat` | The customer mentions solicitors, legal action, small claims, trading standards, an ombudsman, a chargeback, disputing the charge with their bank, or going to the press or social media to damage the company. |
| `product_safety` | Any suggestion the goods caused or could cause physical harm: injury, burns, cuts, electrical faults, smoke, overheating, sharp edges, choking risk, collapse under load. Applies even when the customer is calm and even when they ask for nothing. |
| `account_security` | Suspected unauthorised access: an account the customer cannot get into and did not lock themselves out of, orders or address changes the customer did not make, unrecognised charges, a suspected phishing email. A plain forgotten password is **not** this. |
| `severe_customer_anger` | Sustained abuse, profanity directed at staff, threats, or an explicit statement that they are done with the company. Ordinary frustration — "this is really disappointing", "third time I've had to ask" — is **not** this. The bar is a customer a human should speak to, not a customer who is annoyed. |
| `out_of_scope` | The ticket is not a Hearth & Loom support request, or asks for something outside the support team's remit. **Only available when the ticket's intent is also `out_of_scope`** — the two are the same judgement and may not disagree. |

Notes:

- Escalation and urgency are independent, with one exception. A £400 refund request with no
  time pressure is `normal` urgency and escalated. A "cancel before dispatch" is `high`
  urgency and not escalated.
- **The exception: `product_safety` always implies `high` urgency.** Accepting that goods
  could cause physical harm and then filing the ticket as a 3–5 working day job is a
  contradiction. No other escalation reason constrains urgency.
- Uncertainty is not itself an escalation reason at this stage. The baseline reports a
  confidence score; how low confidence feeds the review queue is a decision for a later step.

## 6. Out of scope for the system

The triage layer never issues refunds, never changes an order, and never makes a goodwill
gesture. It classifies and routes. Anything that moves money or changes an order is a human
action in every version of this system.

## 7. Changelog

### v2 — 2026-09-21

Five clarifications, all prompted by contested or contradictory labels found during the
second-opinion review of the evaluation set. Each one answers a question the brief was
silent on; none of them changes the label set, the urgency levels or the escalation reasons.
The review that prompted them was carried out by a model, not by a person.

| # | Section | Change | Prompted by |
|---|---|---|---|
| 1 | §3 | Multi-ask tickets resolve by irreversibility, then value, then order of mention | `hl-0236`, where a refund chase, an address change and an unsubscribe competed |
| 2 | §3 | "I can no longer pay" is `order_management`, not `billing_and_payment`; `billing_and_payment` is for a payment being attempted and failing | `hl-0097`, read two ways with no rule to separate them |
| 3 | §3, §5 | An unfamiliar product, tier or fee name is not grounds for `out_of_scope`; the `out_of_scope` escalation reason is only available when the intent is also `out_of_scope` | `hl-0023`, `hl-0231`, `hl-0237`, all labelled with an in-scope intent *and* escalated as out of scope |
| 4 | §4 | The pre-dispatch window spelled out: cancellations, removals, swaps, corrections and address changes on a live order are `high`; additions stay `low`; an unstated dispatch date is assumed open; the ask must presuppose a live order | `hl-0140`, `hl-0227`, `hl-0226` — the parenthetical "(a cancellation or address change before dispatch)" was read as an exhaustive list |
| 5 | §5 | `product_safety` implies `high` urgency, and is named as the only escalation reason that constrains urgency | `hl-0125`, escalated for safety and left at `normal` |

Changes 1, 2 and 5 codify what the labels already did. Changes 3 and 4 do not: they make
labels wrong that were previously defensible, and the evaluation set was swept for both —
see `DECISIONS.md` D-014.

**On change 4 and the baseline.** Under-calling pre-dispatch order changes was the
baseline's largest single failure mode before v2. Spelling the window out therefore hands
the baseline the rule it was missing. That is the right thing to do — a system cannot be
marked against policy it was never given — but it means the post-v2 baseline is **a new bar,
not evidence of improvement**. See `DECISIONS.md` D-016.

### v1 — 2026-09-21

Initial brief.
