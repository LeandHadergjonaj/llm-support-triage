# Client brief: Hearth & Loom

*Status: fictional client, written for this project. This document is the source of truth
for the triage label set. Policy documents and the orders database in later steps must be
consistent with it.*

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

Eleven categories. Every ticket gets exactly one — the customer's **primary** ask. Where a
ticket contains several asks, the primary ask is the one with the greatest consequence for
the customer if it goes unanswered.

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

Two notes on boundaries, because they come up constantly:

- A refund **request caused by** a damaged item is `product_issue`, not `returns_and_refunds`.
  The defect is the thing that needs handling; the refund follows from it. Chasing a refund
  that has already been agreed is `returns_and_refunds`.
- "I want to complain about my late delivery" is `delivery_and_shipping`. Route
  `feedback_and_complaint` only when there is no concrete operational ask underneath.

## 4. Urgency

Three levels, judged on **what happens if this ticket waits**, not on how loudly it is written.
An angry customer asking a routine question is still routine; urgency and anger are separate
axes, and anger is handled by the escalation rules below.

| Level | Meaning | Target response |
|---|---|---|
| `high` | Waiting causes harm that cannot be undone later: physical safety, an account being actively misused, money moving irreversibly, or a time-boxed window about to close (a cancellation or address change before dispatch) | Same working day |
| `normal` | The customer is blocked on something they are owed or have paid for, but a day's delay changes nothing material | 1–2 working days |
| `low` | Informational, administrative, or no one is blocked | 3–5 working days |

Worked examples:

- `high` — "the glass shade cracked and cut my hand", "someone has changed my address and ordered a lamp", "cancel order 48812 before it ships today", "I've been charged three times for one order".
- `normal` — "where is order 48812, it was due Tuesday", "the refund you agreed on the 3rd hasn't arrived", "the bedside table arrived with a leg missing".
- `low` — "what are your delivery options to Scotland", "please take me off the newsletter", "do you accept Amex", "just wanted to say the cushions are lovely".

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
| `out_of_scope` | The ticket is not a Hearth & Loom support request, or asks for something outside the support team's remit. |

Notes:

- Escalation and urgency are independent. A £400 refund request with no time pressure is
  `normal` urgency and escalated. A "cancel before dispatch" is `high` urgency and not escalated.
- Uncertainty is not itself an escalation reason at this stage. The baseline reports a
  confidence score; how low confidence feeds the review queue is a decision for a later step.

## 6. Out of scope for the system

The triage layer never issues refunds, never changes an order, and never makes a goodwill
gesture. It classifies and routes. Anything that moves money or changes an order is a human
action in every version of this system.
