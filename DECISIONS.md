# Decisions

Running log of decisions that shape the project, with the reasoning behind them. Started
when the client handed decision-making over; before that, decisions are in the commit
history and in `CLAUDE.md`.

Newest first. A decision here is one that a later reader could reasonably have made
differently — not every implementation choice.

---

## 2026-09-21

### D-018 — Three more urgency inconsistencies found, and deliberately not swept

Round 2 and the re-run between them exposed a third shape of label error, the same shape
as D-009 but on different intents: near-identical tickets split across two urgencies.

| Upstream intent | Split | Minority |
|---|---|---|
| `recover_password` | 8 `low`, 4 `normal` | `hl-0088`, `hl-0173`, `hl-0189`, `hl-0191` |
| `registration_problems` | 10 `low`, 2 `normal` | `hl-0245`, `hl-0250` |
| `change_shipping_address` | 3 `normal`, 2 `low` | `hl-0139`, `hl-0180` |

I fixed only `hl-0225`, because it was drawn in round 2's random block. The other eight
are left alone on purpose. Round 2's block is the measurement; sweeping a pattern the
block itself surfaced would change the population after measuring it, and the 3.3% would
then describe a set that no longer exists. The estimate is worth more than eight labels.

The address-change group is not merely an inconsistency, either: brief v2 §4 says the ask
must presuppose a live order, and none of those five tickets names one. The baseline
predicts `low` for all three of the `normal` ones and is arguably right. That is a
question for the client, not a sweep.

**Proposed brief change (not made):** §4 should say whether an account-level admin task
that blocks nothing paid for — a password reset, a sign-up failure, an address edit with
no order behind it — is `low` or `normal`. Nine minority labels turn on it, and so do
**12 of the baseline's 16 remaining urgency errors**, in both directions. That makes it
the single highest-value thing to ask the client, and worth more than any prompt change
available at this step.

### D-017 — `hl-0093` corrected, revising round 1, and round 1's error rate restated upwards

Round 2 drew `hl-0064` and `hl-0137` — "how soon can I expect my order" — both drafted
`low`. My blind labels said `normal`, by analogy with `hl-0093`, which round 1 had read
and confirmed as `normal`. Checking the group, four of the five `delivery_period` tickets
are `low` and the brief's `normal` example turns on the order being *late*. Nothing in any
of them is late.

So the drafts were right and my blind label was wrong, and `hl-0093` is the outlier. It is
corrected to `low`. Round 1's random-block error rate is restated from **16.7% (5/30) to
20.0% (6/30)**: round 1 confirmed a label that was wrong, and pretending otherwise would
leave a number on record I know to be an undercount.

`hl-0093` is in the **test** split. It was decided from the brief and the ticket text
before any v2 run existed, not from a score — but it did cost the baseline a point on
test, which is the direction that makes the claim credible rather than convenient.

**Why it matters:** this is the clearest evidence in the project so far that a
second-opinion review by a model is not verification. Round 1 read this ticket, thought
about it, wrote a note explaining why it was leaving it, and was wrong.

### D-016 — The post-v2 baseline is a new bar, not an improvement, and the v1 baseline stays on record

Brief v2 spelled out the pre-dispatch window, which was the baseline's single largest
failure mode. Its `high` urgency recall went from 50% to 100% on dev and 67% to 100% on
test. **None of that is the system getting better.** Two things moved at once: the labels
(the sweep) and the prompt (the same clarification). A system cannot be marked against
policy it was never given, so giving it the rule was right — but the resulting number
measures the policy, not the design.

`results/latest_{dev,test}.json` now hold the v2 run, and the v1 runs stay in `results/`
under their timestamps. Every result record carries `run.brief_version`, so the two can
never be quietly compared. **Only v2-vs-v2 comparisons are evidence about design**, which
is what every later step will be measured on.

The temptation this creates is worth naming: it would be easy to keep "improving" the
system by clarifying the brief, and every clarification would look like progress. The
guard is that a brief change must be justified by a contested label found in review,
written into `docs/client-brief.md` §7 with the ticket that prompted it, and applied to
the labels and the prompt in the same commit.

### D-015 — The fresh random block is drawn from the never-reviewed remainder, and rounds are never pooled

Round 2 draws 30 tickets uniformly from the 197 that no round had reviewed, not from all
252. Two reasons. A draw over the whole set would mostly re-read tickets I have already
read and would measure me agreeing with myself. It would also mix two populations — a
corrected stratum and an uncorrected one — into a single number describing neither.

Tickets the sweep touched stay in the pool. The sweep is not a check, so a block that
excluded them could not catch it being wrong; in the event it drew two of them
(`hl-0018`, `hl-0123`) and confirmed both.

`metrics.label_error_rate` therefore reports per round and never pools: round 1 sampled
all 252 before any correction, round 2 the unchecked remainder after the sweep. The
headline is the latest round alone, because it is the only one describing the set as it
now stands. A test pins this.

**The limit of the round 2 number:** the same model wrote the sweep rules and then
measured what they left behind. 3.3% is what one reviewer finds after correcting the
errors that reviewer knows about. It is not an independent audit and must not be quoted
as one.

### D-014 — The remaining 197 tickets are swept by rule, and a swept ticket is not "reviewed"

`triage.sweep` applies brief v2 changes 3 and 4 to every ticket they match: 13 labels
across 13 tickets — 2 contradictory `out_of_scope` escalations dropped, 11 pre-dispatch
order changes raised to `high`. One of the 13 (`hl-0097`) had already been reviewed and
changes because the brief moved under it, not because the review was wrong.

Two choices inside that worth arguing with:

**Matched on the upstream Bitext intent, not on the ticket text.** `cancel_order` and
`change_order` are dataset-derived labels, so selecting on them cannot smuggle my own
reading into the selection. Matching on phrasing would have made this a re-labelling
wearing a sweep's clothes.

**Where the contradiction was `out_of_scope` escalation vs in-scope intent, the intent
wins.** On a Bitext ticket the intent comes from the upstream mapping and is the
better-evidenced of the two.

**A swept ticket is not marked `reviewed`, and `label_error_rate` still counts it as
unchecked.** The sweep applies a rule; it does not re-read anything, and it can only find
the errors its rule describes. Marking its 13 tickets as checked would claim a verification
that did not happen. A test asserts it.

### D-013 — "I can no longer pay for order X" is `order_management`, and therefore `high`

`hl-0097` was the one label D-005 left unresolved. The rule: `billing_and_payment` is a
payment the customer is *trying* to make and cannot — a declined card, a checkout error,
a rejected method. Where they can no longer afford or no longer wish to pay, the thing
that has to happen is to the *order*, so it is `order_management`.

The consequence is that `hl-0097` also picks up the pre-dispatch rule and becomes `high`,
matching `hl-0136` ("I cannot afford order 46104, I need help canceling it"), which was
already `high`. Both are the same ticket with different amounts of politeness.

**A later reader could reasonably disagree**, and this is the change in brief v2 I am least
sure of: `hl-0097` never uses the word cancel. I have taken consistency with `hl-0136` and
`hl-0031` over literal reading, because a support agent's next action is the same in all
three.

### D-012 — The brief goes to v2 with the five clarifications, and is versioned from now on

All five proposals from the review (D-005 to D-009) are now in `docs/client-brief.md`,
with a changelog in §7 naming the ticket that prompted each. This is the step a real
client does once you put the ambiguous cases in front of them: the brief was not wrong,
it was silent, and silence is what the labels disagreed inside.

Three of the five (multi-ask tie-break, "can no longer pay", `product_safety` implies
`high`) codify what the labels already did — `product_safety` changed nothing at all, as
all five safety tickets were already `high`. Two of them (the `out_of_scope` vocabulary
rule, the pre-dispatch window) make labels wrong that were previously defensible, which
is why the sweep exists.

The brief now declares a version, `taxonomy.brief_version()` reads it, and every result
record carries `run.brief_version`. A score is only interpretable next to the version of
the brief that produced it, and a test asserts the declared version has a changelog entry.

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
