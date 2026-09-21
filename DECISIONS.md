# Decisions

Running log of decisions that shape the project, with the reasoning behind them. Started
when the client handed decision-making over; before that, decisions are in the commit
history and in `CLAUDE.md`.

Newest first. A decision here is one that a later reader could reasonably have made
differently — not every implementation choice.

---

## 2026-09-21

### D-011 — The label review is a second opinion, not verification, and the wording says so everywhere

The eval set's labels were drafted by `gpt-5.6-terra` and reviewed by `claude-opus-5`. A
different model family is a genuine independence check: it cannot repeat the drafter's
mistakes by construction, only by coincidence. It is *not* human verification, and the
difference matters for how much the numbers can be trusted.

Every place that said `human_reviewed` now says `reviewed`, with `reviewed_by` naming the
model. Provenance `human_reviewed` became `second_opinion`. A test asserts no ticket
contains the strings "human_reviewed", "human review", "hand-labelled" or "reviewed by a
human", so the claim cannot creep back in through a docstring.

**Why it matters:** two models agreeing may be agreeing about the same misreading. Where
they disagree you learn a label is contested, not which reading a person would pick.

### D-010 — Review method: change a label only where the draft is wrong against the brief, not merely where I would have chosen differently

Formed my own label for all 55 tickets from the brief and the ticket text alone, written
to disk *before* looking at the drafts. Blind agreement was 41/55. Of the 14
disagreements I changed 11 and left 3.

The three left alone (`hl-0093`, `hl-0097`, `hl-0239`) are genuine coin-flips where the
brief supports both readings. Changing them would add churn without evidence and would
quietly encode my taste as ground truth. Where the draft was internally inconsistent with
its own treatment of near-identical tickets, or contradicted an explicit line of the
brief, I changed it.

**Why it matters:** a second-opinion review that rewrites every marginal call stops being
a check and becomes a re-labelling by a second model, with no way to tell which one was
right.

### D-009 — Pre-dispatch order changes are `high` urgency, not just cancellations

The brief lists `high` as including "a time-boxed window about to close (a cancellation or
address change before dispatch)". The parenthetical illustrates the principle rather than
exhausting it, so removing items (`hl-0140`) and correcting an order (`hl-0227`) are also
`high`: same closing window, same consequence if missed — unwanted goods ship and have to
come back.

Adding items (`hl-0226`) stays `low`. Missing that window costs the customer a second
order, not a return. The brief's test is consequence-based, and the consequences differ.

**Proposed brief change (not made):** replace the parenthetical with "any change to an
order that must happen before dispatch — cancellation, address change, or changing what is
in it — except additions, where missing the window only means placing another order."

### D-008 — A product name or feature absent from the brief does not make a ticket out of scope

The drafter escalated `hl-0023`, `hl-0231` and `hl-0237` as `out_of_scope` because
"premium account removals", "freemium accounts" and "withdrawal fees" are not terms the
brief uses — while assigning intents of `account_management` and `returns_and_refunds` to
the same tickets. Those two claims cannot both hold.

`out_of_scope` in the brief means "not a Hearth & Loom support request… or outside the
support team's remit": spam, job applications, wrong company. A customer asking how to
close their account is a support request whatever the tier is called.

**Proposed brief change (not made):** add to the `out_of_scope` row — "Unfamiliar product,
tier or fee names are not grounds for out_of_scope. Judge the request, not the vocabulary.
If a ticket's intent is any of the other ten categories, it is in scope."

### D-007 — `product_safety` implies `high` urgency

`hl-0125` was escalated `product_safety` but left at `normal`. The brief defines `high` as
"waiting causes harm that cannot be undone later: physical safety…", so a ticket accepted
as a safety risk cannot also be a 3–5 working day ticket. Corrected to `high`, matching
`hl-0050` which the drafter did label `high`.

**Proposed brief change (not made):** state in §5 that `product_safety` always implies
`high` urgency, as the one place where an escalation reason fixes the urgency. Every other
reason stays independent of urgency, as §5 already says.

### D-006 — Multi-issue tickets resolve to the ask with the irreversible outcome

`hl-0236` asks three things: chase a refund, change the address, stop marketing emails.
Labelled `delivery_and_shipping` / `high` on the address change. The refund is recoverable
by asking again; a parcel sent to an address the customer has left may not be.

**Proposed brief change (not made):** add to §3 — "Where several asks compete, prefer the
one whose outcome cannot be undone by handling it a day later. Where none is irreversible,
prefer the one with the largest sum attached."

### D-005 — Left `hl-0097` as `order_management` despite reading it as a payment failure

"I can no longer pay for order 52315" reads to me as a payment failure
(`billing_and_payment`), but "no longer" also reads as a change in ability to pay, which
leads to cancellation — and the upstream Bitext intent is `cancel_order`. Two defensible
readings, so the draft stands under D-010.

**Proposed brief change (not made):** §3 should say which way "I can't pay for this any
more" routes, since affordability-driven cancellation and payment failure need different
handling.

### D-004 — Re-scoring after the review replays saved predictions instead of re-running the baseline

`evaluate --rescore <results.json>` pairs the predictions already on disk with the current
labels. Cheaper, but mainly cleaner: the model's answers are held fixed, so any movement
in the scores is the labels moving and nothing else. Re-running would not reproduce the
same predictions and would confuse the two effects.

A replay logs no spend. The first version did, and inflated the ledger from $0.80 to
$1.37 by re-recording the replayed run's cost — money that was never spent twice and
would have eaten the $2 cap. The bogus entries were removed and a test now pins the
behaviour. The usage block in a replayed record carries `inherited_from_replay: true`.

### D-003 — Escalation and urgency stay independent axes, including for profanity

`hl-0224` ("need to switch to the fucking premium account help me") was drafted `normal`
and escalated `severe_customer_anger`. The brief says profanity about the situation is not
severe anger, and says explicitly that urgency and anger are separate axes. Six sibling
tier-switch tickets are all `low` and unescalated. Corrected to `low`, not escalated.

### D-002 — Review sample stays at 55 tickets for now; the remaining 197 get a rule sweep, not a full review

The random block gives a label error rate of 16.7% (95% CI 7.3–33.6%). Reviewing all 252
would tighten that, but the errors found are not randomly distributed — they are two
enumerable rules (D-008, D-009). A sweep that finds every ticket matching those patterns
is a better use of effort than a full pass, and the random block then re-measures what is
left. Logged as the recommended next step rather than done now, because it changes the
labels the baseline of record is scored against.

### D-001 — Decision ownership moves to me; this log is the record

The client has handed over decision-making. Recorded as rule 9 in `CLAUDE.md`. Anything
only the client can supply — spend above the $2 cap, keys, account access, or a change to
what the project is for — still comes back to them. Everything else is decided here and
written down, with the reasoning, so a decision can be argued with later.
