# Decisions

Running log of decisions that shape the project, with the reasoning behind them. Started
when the client handed decision-making over; before that, decisions are in the commit
history and in `CLAUDE.md`.

Newest first. A decision here is one that a later reader could reasonably have made
differently — not every implementation choice.

---

## 2026-09-21

### D-027 — Phase 5a: close the understated-refund gap, settle D-024's ground-rule-3 scope, deploy a public demo

**Part 1a: an understated or unstated refund claim must not slip past the £100 review once
the record is known.** Brief v4 §5 is correct that the *router* must escalate on the stated
figure alone — it never sees the order record (`hl-a0012`, D-025). But the *answering* step
(`evaluate_answerer.py`) does look the order up for every ticket, whether the router kept
it or not, and until now nothing used that fact for policy — a ticket where the customer
says nothing, or understates the amount, and the record shows an unresolved refund over
£100 would sail through as `self`. As the simulated client (no real one to ask — D-020's
standing basis): **once the order record is known, an unresolved refund, credit or
compensation over £100 must go to a human, regardless of what the customer stated or
whether they stated anything.** "Unresolved" matters — a refund already `paid` needs no
further review, and a self-handled reply reporting that fact (`hl-a0006`, sub-£175, already
paid, wrongly *not* flagged by a naive "any order with a refund over £100" version of this
rule — checked and excluded) is exactly correct, not a violation.

Implemented as a second, later policy layer, `router.enforce_record_policy` (`router.py`),
run in `evaluate_answerer.generate_one` right after the order lookup that already happens
for the answer, so it costs nothing new: the router's `enforce_policy` (D-021) stays exactly
as before, operating on ticket text only. `answerer.matched_orders` (`answerer.py`) exposes
the parsed order records `order_facts_block` was already rendering to prose. Unit-tested
with no API key (`tests/test_router.py`) for: an understated/unstated claim with an
unresolved record refund over threshold (forces escalation); a resolved (`paid`) refund over
threshold (does not); an unresolved refund under threshold (does not); no matching order
(no-op).

**Verified against the real eval set at zero cost, no regeneration.** Replayed
`enforce_record_policy` over every existing dev and test `answerer_v1` candidate's already-
looked-up order records: **zero tickets flip** on either split. The only two orders in
`data/orders/orders.jsonl` with an unresolved refund over £100 are `49001` (`hl-0233`,
already `human` for `legal_or_chargeback_threat` — unaffected) and `50902` (not referenced
by any eval ticket). So this closes a real design gap with no eval ticket currently
exercising it end-to-end — the fix is forward-looking, not a score bump, and no eval run
was needed or spent on it.

**Part 1b: D-024's ground-rule-3 question, settled.** D-024 asked whether ground rule 3
("never claim to have already cancelled, changed, refunded, or performed any account
action") is broader than brief §6 requires, since §6 only names order and money changes as
human-only and is silent on reversible account admin (an address change, a marketing
unsubscribe). **As the simulated client: ground rule 3 stays exactly as broad as it is,
covering every account action, not narrowed to order/money.** The two questions are
different axes, not one: brief §6 asks *who is allowed to make the change* (a human, for
order/money); ground rule 3 asks *what the system may claim has already happened* — and this
system has no execution capability at all, for any category, order/money or address/
marketing alike (no write path exists anywhere in this codebase; `answerer.py` only reads
`orders.jsonl` and drafts text). Narrowing ground rule 3 would make the system claim an
address or unsubscribe change is "done" when, architecturally, nothing anywhere ever
executes it — a false claim regardless of brief §6's scope. This resolves `hl-0236`'s two
"actioned" criteria as **eval defects, same class as D-023**: reworded from claiming
completion ("the address change is actioned") to what an honest reply can state ("the
address change is recorded / will be used ..."). Re-scored against the existing,
unregenerated test candidate (`--no-judge` not used — a real judge pass, $0.0319, test
remains `test (seen)` per D-025) and **the number does not move** (still 90.62% required-
fact coverage, 29/32): the candidate answer, generated before this fix existed, doesn't
claim the address/marketing change is done, correctly per ground rule 3 — but it also
doesn't confirm *receipt* of the request, which the reworded criteria do ask for and the
answer doesn't clearly give either. That is a mild, honestly-reported answer-quality gap,
not a criterion defect, and is left alone rather than regenerating a frozen test candidate
to chase a rewording I just wrote — flagged as the natural next step, not fixed here.

**Part 2: a public demo, Render's free tier.** Checked current terms rather than trusting
memory (Render's own docs, fetched live): free web services need no credit card, get 750
instance-hours/month, sleep after 15 minutes idle and cold-start in about a minute — and,
the detail this design leans on, **free-tier services have an ephemeral filesystem: local
SQLite files are wiped on every restart, redeploy, or spin-down.** That is the demo's reset
mechanism, for free, with no code: a public visitor's queue decisions vanish the next time
the service naturally idles out. `render.yaml` (a Blueprint, so setup is "connect the repo
and click," not manual dashboard field-filling) runs `gunicorn triage.queue_app:app` with no
`OPENAI_API_KEY` in its environment at all — verified in an isolated venv
(`pip install .` then serving with gunicorn, no key set) that the app never imports or calls
`triage.llm.get_client`, so **the public demo cannot spend API money even in principle, not
just under a spend cap.** `gunicorn` added as a normal dependency (`pyproject.toml`) — the
one new dependency this phase adds, for production serving in place of Flask's dev server.

One supporting piece, in already-existing files, nothing new: `queue_db.py` gained
`dump_packages` / `seed_if_empty` — `build_queue_data.py` now always writes
`data/queue/seed_packages.json` (36 tickets, 64KB, committed) from whatever's in the local
`queue.db`, and `queue_app.py` seeds an empty `packages` table from it once at process
start. This also means a fresh clone that runs `make queue` without ever running
`make queue-data` now sees a working demo instead of an empty queue — `make queue-data`
remains how a real rebuild happens, seeding only fires when the table is empty.

`/ponytail-review` on this diff before commit cut a second reset path: a first draft added
a `DEMO_MODE`-gated 30-minute in-process wipe of `reviews`/`spot_checks`, as a belt-and-
braces reset for a session that stays continuously busy past the 15-minute idle window.
Flagged `yagni` — it duplicates the ephemeral-disk reset that is already the design's
primary mechanism, for a sustained-traffic scenario a low-traffic portfolio demo won't hit.
Cut, along with a second finding on the same diff (`seed_if_empty` was running on every
request via `before_request` instead of once at import). `queue_db.reset_reviews` stays as
a small, tested, manually-invocable escape hatch (`python -c "from triage.queue_db import
connect, reset_reviews; ..."`) if the demo ever does need a mid-session clean-up without a
redeploy — not wired into any automatic path.

Landing page (`/`, `queue_app.py`) is new; the former `/` (the queue) moved to `/queue`. It
states plainly: Hearth & Loom is fictional, nothing is sent to a real customer, every reply
shown was generated once offline (zero live model calls), and this is a shared public demo
whose data periodically resets — set expectations before a hiring manager clicks anything.

**Not built:** authentication (nothing here is sensitive enough to need it — synthetic
tickets, no real customer data, explicit demo framing), and no protection against a visitor
seeing another visitor's in-flight edits (a shared single-file demo does not need one; if
this stopped being fine, per-session isolation would be the fix, not attempted here).
Visual polish is explicitly Phase 6's job, per the phase brief.

**Spend.** One eval_answers re-score (Part 1b), $0.0319 — Part 1a and Part 2 made zero API
calls. Phase total **$0.0319**; project-to-date **$2.4805** (`make spend`).

**Next step, once a live URL exists:** watch whether Render's 60-second cold start after 15
minutes idle is a bad first impression for a hiring manager clicking a cold link, and if so
consider a low-effort keep-warm ping — not built pre-emptively since it may never matter.

Sources checked for Render's current free tier: [Deploy for Free](https://render.com/docs/free),
[Persistent Disks](https://render.com/docs/disks).

### D-026 — Phase 4 part 2: the human review queue

**Reuse over regeneration.** The queue is built from Phase 3b's own saved answerer
candidates (`results/*_answerer_v1_{dev,test}_candidates.jsonl`) -- the router prediction,
escalation reasons, urgency, confidence, rationale, and (for `human` tickets) the handover
note were all already generated and paid for; `src/triage/build_queue_data.py` reads them
rather than re-running the router. The only new work is **one API call per human-routed
ticket** (11 total: 5 dev + 6 test) for a suggested customer-facing draft reply -- Phase 3b
deliberately never wrote one for escalated tickets ("the system does not send a reply"),
but an agent approving/editing/rejecting a draft needs a draft to start from. It reuses
`answerer.answer_ticket(..., handled_by="self")` verbatim, so the draft is grounded by
exactly the same `BASE_SYSTEM` rules as every other reply (no invented facts, no promise
the policy documents don't allow, never claims an account/order action already done) --
nothing about being a draft relaxes those rules; only human approval decides whether it is
ever used. Order facts and the policy-document pointer are both free: `order_facts_block`
already exists and is deterministic, and "relevant policy" is a static 11-intent →
document lookup table (11 intents, 6 documents -- a dict, not a retrieval system, same
reasoning as `answerer.py`'s own no-retrieval choice at this scale).

**Storage: SQLite, one file, no server.** A single support agent working a queue is a
single-writer workload; a real database process would be answering a scaling question this
prototype does not have. The schema is plain tables with no SQLite-only types, so migrating
to Postgres in Phase 5 is a driver swap, not a rewrite -- "avoid choices that make
deployment hard" was read as "don't build something a real deployment would have to
discard," not as "provision a server now." `packages` (built once, read-only from the
app's side) is separate from `reviews`/`spot_checks` (written by the agent) so rebuilding
the former with `--force` can never silently discard review history.

**Web layer: Flask, the one new dependency this phase adds.** Rung 3 of the ladder (stdlib)
was tried first and rejected: six routed pages with forms and redirects on raw
`http.server` would be more code, not less, than one small, well-known dependency doing
exactly that job -- and Flask deploys as ordinarily as anything in Phase 5 would need.
Templates are inline `render_template_string` calls in `queue_app.py`, not a `templates/`
folder -- one file, six routes, no reason to split it.

**What "ready-to-act" means here**, per the phase's own ask: `/ticket/<id>` shows the
ticket, the router's own escalation rationale and reasons, the verified order-facts lookup,
a link to the relevant policy document(s), the router's original handover note, and the
suggested reply -- editable in place. Three actions (`approve`, `edit_approve` diffed
against the suggested text server-side to decide `approved` vs. `edited`, `reject`,
which requires a note) are recorded in `reviews`; the diff logic is a small pure function
(`decide_status`, `queue_app.py`) precisely so it has a test that needs no Flask app and no
database (`tests/test_queue.py`). `/spotcheck` is the separate, read-only audit view the
phase asked for over self-handled tickets, with its own flag/notes field, so a client could
sample the system's unattended output before trusting it -- deliberately not merged into
the approval queue, since spot-checking an already-sent reply is a different action from
approving one that has not gone out.

**Verified end to end as an agent would use it**, not only through `tests/test_queue.py`:
ran the app, opened the queue (11 pending), opened a ticket, approved one as-is, edited and
approved another, rejected a third after confirming the reject-without-a-note path 400s,
opened a policy-document link, flagged one spot-check and cleared another, and read
`/stats` back to confirm the counts matched the actions taken. The three human reviews and
two spot-checks made during that pass were then cleared from `queue.db` before commit --
they were a walkthrough, not seed data for whoever opens the queue next. `data/queue/*.db`
is gitignored; `make queue-data` rebuilds it deterministically from `results/`, on top of
whichever candidates files are newest there.

**Cost.** 11 draft-reply calls on `gpt-5.6-terra`: $0.0308. Combined with D-025's judge
re-score ($0.0318), **Phase 4 total: $0.0626**; project-to-date **$2.4486** (`make spend`).
Comfortably under the $2 per-run cap on both runs individually.

**Not built, on purpose (Phase 5's job):** authentication, multi-agent concurrency
handling (SQLite's single-writer model is adequate for a prototype, not for six agents
hitting it at once), and deployment itself. **Natural next step:** the D-024 next-step item
this phase didn't touch -- ground rule 3's scope (does "never claim an account action
performed" match brief v4's actual §6, or is it broader) -- plus, now that agents will be
looking at real drafts, whatever the first real review session's edit patterns turn out to
need that this prototype didn't anticipate.

### D-025 — Phase 4 part 1: settle the stated-vs-record figure, fix two eval criteria, brief v4

Three items named in the Phase 4 brief as tidy-up from D-024's "next step", all on
`data/eval/answers_test.jsonl` -- **test is now treated as seen from this commit on**, per
the Phase 4 brief; any later test number is labelled that way, and `83.87%` stays the
number of record for the original held-out run.

1. **`hl-0011`**: dropped the `expected_must_contain` item `"not a specific refund date"`.
   Same defect class as D-023 -- an absence phrased as a positive requirement, and already
   covered by the existing `expected_must_not_contain` item on the same ticket ("a promised
   refund amount or payout date"). A grep across both splits for the D-023 pattern
   (`not `/`silence on`/`no `-led items) found no further instances; `hl-0159` and
   `hl-a0013`'s `"no senior review is needed"` are genuine positive claims an answer can
   state, not this defect.
2. **`hl-0236`**: dropped the literal `2026-09-09` from the refund-chase criterion, kept the
   substance ("approved and still awaiting payout, now overdue against the 5 working day
   window"). No natural reply states an ISO date; the judge marked a correct "9 September"
   answer wrong for omitting the year, which is a criterion defect, not an answer defect
   (D-024 flagged this at the time). The other tension D-024 raised for this ticket --
   ground rule 3 ("never claim to have performed an account action") vs. an expectation that
   the address/unsubscribe be "actioned" -- is left as is: brief v3/v4 §6 only names *order*
   and *money* actions as human-only, and an address/marketing-preference change is
   reversible, non-financial account administration, which ground rule 3's own reasoning
   (irreversible actions need a person) does not obviously reach. Not changing the ground
   rule on one ticket's evidence; flagged for the next full review pass.
3. **`hl-a0012`**: `must_handle` corrected from `self` to `human`, and brief v4 §5 settles
   the general rule (as the simulated client, since there is no real one -- D-020's
   standing basis for this kind of call): **a stated-vs-record mismatch does not add a new
   escalation reason; the stated figure still governs escalation** (triage never has the
   order record, only the ticket text, so v3's "where a figure is stated, use it" already
   answers this), **and the order record governs what is actually said** once a human or
   the answerer has it. `hl-a0012`'s customer claims £150 for an item the record shows is a
   £95 pendant light; the router correctly escalated on the stated £150 under the existing
   rule, but the eval's `self` label assumed grounding happened before routing, which is
   not how the system is built (route first on ticket text, ground only what is then
   answered or handed over). The router's behaviour was right; the label was wrong. This
   is a labels-and-brief change together per rule 5, so the brief moves to **v4** with a
   changelog entry (§7) -- no triage label changes, and `answers_dev.jsonl` is untouched.

Re-scored `data/eval/answers_test.jsonl` against the existing test candidates
(`results/20260921T160726Z_answerer_v1_test_candidates.jsonl`, no regeneration, judge pass
only) after these three fixes -- see the Phase 4 report for the corrected number, reported
as `test (seen)`, never blended with `83.87%`.

## 2026-09-21

### D-024 — Phase 3b: the system answers tickets. Dev converges to a clean pass; test surfaces two real, left-alone findings

**Design: the simplest thing that could work, per the brief.** `src/triage/answerer.py` is
one LLM call per ticket, on `gpt-5.6-terra` (rule 7 / the Phase 3b brief). The whole
knowledge base (~5k tokens, six documents) goes straight into the system prompt -- no
retrieval. Retrieval solves a cost/precision problem at a scale this project does not have;
adding it now would be a new failure mode (fetching the wrong section) traded for a
non-existent saving. **Order facts never come from the model reading the ticket**:
`extract_order_ids` pulls order numbers out of the ticket text with a regex (the same
deterministic step a real system would take before an orders-API call), looks them up in
`data/orders/orders.jsonl`, and that verified block is the *only* source of order facts the
model is given -- the prompt tells it to say "no record found" rather than invent one, and
`tests/test_answerer.py` pins this with no API key needed. The router (`router.py`,
Phase 2, unchanged) decides `self` vs `human` first; `answerer.py` then writes a customer
reply (`self`) or a handover note for the person picking it up (`human`) -- never a
customer-facing reply on an escalated ticket, per brief v3 §5 ("the system does not send a
reply"). Ground rule 3 in the prompt also bars the system from ever claiming to have
already cancelled, changed or refunded anything, since brief v3 §6 makes those human
actions in every version of this system; the model may describe what will happen, not
declare it done.

**Two structural additions, both earned by a specific dev failure, nothing else added:**

1. Two dev tickets missed facts about the £100 review threshold and the free-of-charge
   pre-dispatch process even though the knowledge base states both -- the model resolved
   the customer's literal question and stopped, without volunteering policy the customer
   didn't know to ask about. Added two explicit ground rules (7, 8: always say a
   pre-dispatch change is fee-free; always say whether a refund figure needs senior review).
   Dev's `required_fact_coverage` moved from 74.4% (29/39) to 92.7% (38/41) on this change
   alone -- the denominator itself moved too, because the fix also flipped `hl-0033`'s
   routing to the correct one that run, giving it a content grade it hadn't had before.
2. Human-routed handover notes never stated *why* the ticket was escalated or its urgency,
   even though the router had already computed both (`escalation_reasons`) -- because the
   answerer was never given them. Passed `router_pred["escalation_reasons"]` through to the
   handover-note prompt and required the note to open with the escalation and state urgency
   explicitly, so a calm safety report is not written up as routine and an angry-but-routine
   complaint is not written up as urgent. This was the fix that took dev's
   `fully_correct_of_graded` from 63.2% to 85%.

Nothing else was added: no specialist sub-agents, no extra pipeline stage, no per-category
branching beyond the one route split the router already provides.

**A third, larger gain came from an eval-authoring fix, not a system change** -- see
D-023 below, found by inspecting *why* two of the same dev tickets kept failing after the
two prompt fixes above. `hl-0242` and `hl-0033` both had a required-fact item phrased as
the *absence* of bad content, which cannot be satisfied by any answer's text no matter how
good. Fixing that (D-023) took dev's `required_fact_coverage` to 100% and
`fully_correct_of_graded` to 100% on 19/20 correctly-routed tickets. This was done, and
logged, **before test was touched at all.**

**Final dev (n=20), before test was run or the eval touched again:**

| Metric | Rate | n | 95% CI |
|---|---:|---:|---|
| Routing accuracy | 95.0% | 20 | 76.4–99.1% |
| Required fact coverage | 100% | 38 | 90.8–100% |
| Forbidden-content avoidance | 100% | 34 | 89.9–100% |
| Fully correct (of routed-correctly) | 100% | 19 | 83.2–100% |

**Final test (n=16), run once, nothing changed after:**

| Metric | Rate | n | 95% CI |
|---|---:|---:|---|
| Routing accuracy | 93.75% | 16 | 71.7–98.9% |
| Required fact coverage | 83.87% | 31 | 67.4–92.9% |
| Forbidden-content avoidance | 100% | 25 | 86.7–100% |
| Fully correct (of routed-correctly) | 80.0% | 15 | 54.8–93.0% |

Test is lower, and the two splits' 95% CIs overlap heavily at n=16-20 -- this is not
evidence the system is worse on test, it is what a coin-flip's worth of sampling noise
looks like at this n, exactly the point rule 4 and every prior CI in this project's
`results/` already makes. Two specific things behind the test gap, found by reading the
failures rather than trusting the aggregate:

- **`hl-a0012` (must_handle=self) was routed to a human**, and I now think the *ground
  truth is wrong, not the router*. The ticket states "£150" for an item the order record
  later shows is actually a £95 pendant light, not a desk lamp. The router never sees the
  order record -- it only sees ticket text -- so escalating on a stated £150 is exactly
  what brief v3 §5 says to do ("where a figure is stated, use it"). I set `must_handle:
  self` in Phase 3a on the assumption grounding would happen before routing; the actual,
  brief-consistent design routes first and grounds only what it then answers or hands over.
  **Left uncorrected on this run** -- the rule is test changes nothing once it has been run,
  and this is exactly why: however confident the diagnosis, correcting it now would be
  indistinguishable from tuning to what test just showed. It goes in the next review pass.
- **`hl-0236`'s three required facts about actioning an address change and a marketing
  opt-out were marked unmet**, and reading the judge's own notes, one of the three
  (the refund-status fact) actually *was* stated correctly -- the judge penalised omitting
  the year ("9 September" vs "2026-09-09") from a criterion I had written with a literal
  ISO date in it, which no one writes to a customer. That is a second instance of the same
  authoring-defect class as D-023 (`hl-0011`'s "not a specific refund date" is a third,
  found the same way) -- a criterion phrased so no correct answer could satisfy it
  literally. **Also left uncorrected on this run**, same reason: found only after test was
  scored, so it goes in the next review pass, not into a same-session rescoring. The other
  two of `hl-0236`'s three facts are a genuine, if debatable, design tension: ground rule 3
  (never claim to have performed an account action) directly conflicts with an expectation
  that the address/unsubscribe be "actioned" -- brief v3 §6 only names *order* and *money*
  actions as human-only, so this ground rule may be broader than the brief requires. Also
  left alone; see "next step" below.

**Reading test's headline number honestly:** at least 2 of test's 5 missed required facts
(across `hl-0236` and `hl-0011`) are now known to be criterion defects rather than answer
defects. Recomputed by hand *for this write-up only, not for the recorded score*:
excluding those two items would put required fact coverage at 28/29 = 96.6%, much closer to
dev. The recorded 83.87% stands as the number of record, exactly because "it would score
higher if I fixed the eval" is precisely the reasoning rule 4 and this phase's own brief
warn against acting on immediately after seeing test.

**The judge check.** I (Claude Sonnet 5, a different model family from the judge,
`gpt-5.6-terra`) blind-graded every one of dev's 19 correctly-routed answers against their
criteria before looking at the judge's saved verdicts, and separately fed the judge four
answers I deliberately broke (wrong-document figure, boundary misapplied, an invented
refund+date+return-by-parcel, a bogus fee) to see if it would catch them. **Agreement was
100% across all 88 individual pass/fail judgements** (72 from the real dev answers, 16 from
the four adversarial cases) -- the judge caught every injected defect and matched my own
read on every real answer. This establishes the judge reliably catches *clear-cut*
violations, matching or missing content in the way a human grader reading the same
checklist would. It does **not** establish the judge is reliable on subtler, more literal
calls: the two test-time findings above (`hl-0236`'s year, `hl-0011`'s double-negative
criterion) are exactly the judge being *too* literal about criterion wording rather than
too lenient about content -- so the 100% figure describes the judge's ability to catch bad
answers, not its tolerance for badly-worded criteria, and should not be read as "the judge
is reliable" without that qualifier. Combined with D-022's caveat (same-vendor grading is
not independent verification), the honest summary is: this judge is trustworthy for
routing correctness (exact match, no judgement involved) and for catching answers that
invent facts or omit required policy -- it is not yet trustworthy enough to read its
literal per-fact score to two decimal places without checking the failures by hand, which
is what this write-up did.

**Cost and latency**, three LLM calls per ticket (router, answer, judge), all
`gpt-5.6-terra`: dev $0.1082 total / $0.001834 per ticket, mean latency 2.97s; test $0.1265
/ $0.002692 per ticket, mean latency 2.87s (test's higher per-ticket cost is a smaller,
less cache-friendly run, not a more expensive design). Two smoke checks and a judge
stress-test before the real runs cost $0.0602 combined, logged honestly to
`results/spend_log.jsonl` even though they were not formal eval runs. **Phase total:
$0.2949.** Project-to-date: $2.3860 (`make spend`) -- every individual run stayed
comfortably under the $2 cap; the cumulative figure is not itself capped.

**Not done, on purpose:** Phase 4 (the human review queue) was explicitly out of scope
and nothing here builds toward it beyond the `human` handover notes the router already
required. **Natural next step:** a small review pass to fix the three now-identified
criterion defects (the two named above plus a sweep for the same double-negative pattern
class-wide, D-023's method) and a decision on ground rule 3's scope (does "no account
action claimed" match brief v3 §6, or is it broader than the brief needs) -- both cheap,
both would tighten test's number without touching the system.

### D-023 — Four answer-eval criteria fixed for backwards phrasing, found while running Phase 3b, before scoring

Running the first real answerer against `data/eval/answers_dev.jsonl` surfaced four
criteria in the Phase 3a set that were logically backwards, not merely strict: an
`expected_must_contain` item that described the *absence* of bad behaviour ("not to
attempt a fix or refund itself", `hl-0242`; "not to make any new representation about the
case", `hl-0190`) and an `expected_must_not_contain` item that described the *absence* of
good content ("silence on the 14-day / restocking-fee question…", `hl-0033`; "silence on
any of the three asks", `hl-0236`). A `must_contain` item has to be checkable as something
a good answer states; "not to do X" is not a thing text can be checked for containing, and
the same logic in reverse breaks a `must_not_contain` item. These would have scored a
*correct* answer as wrong no matter how it was phrased, on both criteria being tested
simultaneously (`hl-0242`, `hl-0033` were the exact two tickets the first dev run failed
this way).

**This is not "the system disagreed with the label"** — the Phase 3b brief's line against
that is about defensible policy calls, not about a criterion that cannot be satisfied by
any correctly-behaving answer. Fixed by moving each to the list it belongs in, restated as
positive content:

| Ticket | Was (wrong list) | Now |
|---|---|---|
| `hl-0242` | contain: "not to attempt a fix or refund itself" | not_contain: "an offered repair, replacement or fix decided by the system itself" |
| `hl-0190` | contain: "not to make any new representation about the case" | removed -- already covered by the existing not_contain item "a new offer, apology admitting fault, or refund figure" |
| `hl-0033` | not_contain: "silence on the 14-day / restocking-fee question…" | contain: "notes that the large-furniture return rules (14-day window, 15% restocking fee) apply to this two-person-delivery item" -- softened from the original's implicit ask that the system compute the window had *already expired*, which needs a "today's date" the order record does not carry; stating the rule applies is the fair, checkable version |
| `hl-0236` | not_contain: "silence on any of the three asks" | removed -- already covered by the three separate positive `must_contain` items for each ask |

`tests/test_taxonomy_and_metrics.py::test_answer_eval_set_is_well_formed_and_grounded`
still passes (every ticket keeps at least one `expected_must_contain` fact). Dev was
re-scored after this fix, before test was run at all -- test had not yet been touched, so
this is not a case of tuning the eval to a test-split result either.

**Not exhaustive.** Running the real test split afterward (D-024) found a third instance of
the same backwards-phrasing bug (`hl-0011`'s "not a specific refund date") and a related but
distinct defect -- a criterion written with a literal machine-format date no natural reply
would reproduce (`hl-0236`). Both are named in D-024 and deliberately left uncorrected on
that run, because they surfaced after test had already been scored; this audit should have
been a full pass over both splits rather than the four caught by one keyword grep, and the
next review pass should finish it.

### D-022 — Stop chasing triage accuracy; Phase 3a builds the client's knowledge and the answer eval, not an answering system

**Not pursuing further triage-accuracy work on this eval set.** D-021 found no
statistically significant difference between the router and the baseline (McNemar p=0.73
dev, p=1.0 test). With per-run errors down to single digits — 6-8 tickets wrong out of
144-108 depending on split — this eval set's sample size cannot distinguish one triage
design from another any more; the McNemar test on this few disagreements has essentially no
power. Getting a real answer would need either a much larger eval set or a design change big
enough to move double-digit numbers of tickets, and nothing on the table right now is that.
The router's individual components (the "make a claim" prompt fix, the policy layer, the
confidence gate) stay as built — none of this is a regression, it is a statement that this
project has extracted what this eval set can tell it about triage design, for now.

**Phase 3a builds the measuring stick, not the thing being measured** — same shape as
Phase 1 building the eval set and baseline before any triage design existed. Three
artifacts, all authored by Claude Sonnet 5, none of it costing API spend:

1. **`docs/knowledge_base/`** — six policy documents (returns & refunds, delivery &
   shipping, cancellations & order changes, payments & billing, accounts, product safety),
   consistent with `docs/client-brief.md` v3 wherever they overlap (the £100 threshold, the
   pre-dispatch window, the account-admin urgency rule). One cross-document inconsistency is
   planted on purpose — `returns_and_refunds.md`'s 5-working-day refund timeline vs
   `delivery_and_shipping.md`'s 10-working-day figure for the delivery-charge portion of a
   late order — with `returns_and_refunds.md` stating the precedence rule, so the answer
   eval (`hl-a0003`) can check an answer resolves it correctly rather than picking whichever
   document it retrieves first.
2. **`data/orders/orders.jsonl`** — 30 synthetic orders, 27 tied to specific tickets already
   in the eval set or the new answer eval (grounding real order facts to real tickets rather
   than inventing generic ones), covering pre/post dispatch, refunds either side of £100
   (including a combined-items case and an exact-£100 boundary case), a late delivery, a
   short-shipment, and a case with no matching order at all (`53004`, deliberately absent).
3. **`data/eval/answers_{dev,test}.jsonl`** — 36 tickets (20 reused from Phase 1, 16 newly
   authored), each with an answer contract (`must_handle`, `expected_must_contain`,
   `expected_must_not_contain`) instead of a triage label, and `src/triage/eval_answers.py`
   to score a candidates file against it.

**Two policy-content decisions made as the simulated client**, since the brief's taxonomy
mentions these without defining them and there is no real client to ask (rule 9):

- **A 15% restocking fee on large, two-person-delivery furniture returned for change of
  mind**, waived for faults/damage/wrong item. The brief's `returns_and_refunds` category
  already names "cancellation fees" as in scope (§3) without saying what one is; a flat
  furniture-only fee is the simplest rule consistent with brief v3 §1's mention of
  two-person delivery's operational cost, and it does not touch any label.
- **A 5-working-day refund timeline from approval**, chosen as a round, defensible number
  for a company this size and stated as authoritative in `returns_and_refunds.md` — see the
  planted inconsistency above, which needs exactly one document to win.

**The answer-eval judge is not independent verification, and this is stated up front.**
`eval_answers.judge_ticket()` grades a candidate answer's content with an LLM, because the
required/forbidden facts are natural-language claims a keyword match cannot check reliably.
It defaults to this project's own triage model, `gpt-5.6-terra` — the same vendor, and
potentially the same model, that a future answering system might also run on. That is the
same shape of bias D-011 names for the label review: it can catch a badly grounded answer,
but shares the generating model's blind spots and must never be quoted as human
verification. Routing correctness (`handled_by` vs `must_handle`) needs no judge at all —
it is an exact match — and is the one number in this eval that is not subject to this
caveat.

No API spend this step: `make test` covers the new data with no key needed
(`test_orders_db_is_well_formed`, `test_answer_eval_set_is_well_formed_and_grounded`) and
`tests/test_eval_answers.py` exercises the scorer's aggregation logic with a stubbed judge.

### D-021 — Router built: same model, a policy layer, a confidence gate — and it does not beat the baseline outside noise

Phase 2's second half: build a triage design that beats the brief-v3 baseline (D-020) on
the same model and brief, and that knows when to hand a ticket to a human instead of
guessing. `src/triage/router.py` + `src/triage/evaluate_router.py`; same `gpt-5.6-terra`,
same brief v3, one call per ticket — the difference is entirely design, not a bigger model.

**What it adds, in order of how mechanical it is:**

1. A prompt clarification for the one failure pattern brief v3 did not touch: "make a
   claim" / "file a complaint" read as a legal process instead of `feedback_and_complaint`
   (README "What is still wrong"). Router-only, not folded into the baseline prompt,
   because it is a design fix for a model failure mode, not a brief ambiguity like D-018 —
   the brief already classifies these unambiguously.
2. A deterministic policy layer, `enforce_policy()`, applying the same two invariants
   `sweep.py` applies to the label set — `product_safety` implies `high`, and the
   `out_of_scope` reason requires an `out_of_scope` intent — but to the model's live
   predictions instead of to stored labels. Needs no `bitext_intent`, so unlike
   `pre_dispatch_window` it is not eval-set-specific and would hold on a real ticket.
3. A confidence gate, settling the question brief §5 explicitly left open ("how low
   confidence feeds the review queue is a decision for a later step"): a ticket sent to a
   human (`sent_to_human`) is now `escalate OR confidence < threshold`, broader than the
   formal `escalate` field scored against the brief's six reasons.

**Threshold chosen on dev only**, from `evaluate_router.py`'s built-in scan (paid for once,
re-finalized locally at nine thresholds for free — see `--rescore`): self-handled accuracy
peaks at **0.7** (96.8% self-handled, 13.9% queued) and climbs no further with a higher
threshold. Checked why: the three dev tickets the router still gets wrong are all
high-confidence (0.83, 0.94, 0.98) — confidence is not tracking those errors, so raising
the bar past 0.7 only queues tickets the model was already right about, for no accuracy
gain. `0.7` is now `router.CONFIDENCE_THRESHOLD`; never touched after seeing test.

**Results — honest reading, not the one I'd have preferred:**

| | Dev (144) | Test (108) |
|---|---:|---:|
| All three correct, router | 95.8% | 92.6% |
| All three correct, baseline | 94.4% | 93.5% |
| Fixed / broken (matched pairs) | 5 / 3 | 2 / 3 |
| McNemar exact p | 0.73 | 1.0 |

**The router does not demonstrate a win over the baseline at these sample sizes.** Dev
moved in its favour, test moved against it, and neither is significant — McNemar p is
nowhere near 0.05 on either split, and single-digit disagreement counts are exactly the
regime where "which one is ahead this run" is noise, not signal. Per rule 4, reporting only
the dev number and stopping there would have overstated it; rule 3 already establishes this
project does not do that with labels, and it should not do it with results either.

What the router *did* demonstrably do, independent of the noisy headline number: fixed
both dev `out_of_scope` mislabels the design targeted (`hl-0112`, `hl-0219`) and the one
equivalent case on test (`hl-0005`) — 3 for 3 on the specific pattern it was built to fix —
and it can now never emit a `product_safety`-without-`high` or an internally-contradictory
`out_of_scope` reason, by construction rather than by hoping the model gets it right. The
three tickets it breaks on test (`hl-0162`, `hl-0234`, `hl-0247`) are all urgency-only
misses unrelated to either design change — `hl-0234` ("how soon can I expect my shipment")
is the same `delivery_period` low/normal boundary D-017 already documented as unstable
across runs, not a router regression.

Cost and latency: router $0.001385/ticket on dev, $0.001335 on test, against baseline's
$0.001294 / $0.001310 — the extra ~6-7% is the longer prompt (one added clarification
paragraph); the policy layer and confidence gate are pure post-processing and cost
nothing. Not worth optimising away at these amounts.

**Next step, not taken here:** the failure-pattern fix generalises and is worth keeping;
the confidence gate is sound in design (§5's open question, now answered) but has not yet
been shown to move the headline number, because the model's errors on this eval set are
mostly *confident* errors rather than *uncertain* ones. A router with a real accuracy edge
probably needs a second, narrower check on the specific patterns still failing (the
`normal`/`low` boundary on delivery and refund-chasing tickets) rather than a global
confidence threshold, which this phase shows has limited headroom left to give.

Total phase spend: $1.7879 project-to-date (`make spend`), of which D-018's re-baseline
(dev + test) cost $0.3278 and the router's dev + test runs cost $0.3436 — comfortably
under the $2 cap on every individual run.

### D-020 — D-018 settled: account admin blocking nothing paid-for is `low` (simulated client decision)

Phase 2 opened with D-018 still unresolved: the client brief was silent on whether an
account-level admin task (password reset, sign-up problem, address administration with no
order behind it) is `low` or `normal`, and the drafted labels split both ways on
near-identical wording. There is no real client to ask, so — as rule 9 directs when the
brief is silent — I made the call myself, as a reasonable client would, and wrote it down
rather than leaving the ambiguity in place for the router to inherit.

**The call:** these tasks are `low`. Reasoning, not preference: the brief's own definition
of `normal` already requires the customer to be "blocked on something they are owed or have
paid for" (§4). None of the four affected task types — a password/PIN reset, a
registration/sign-up problem, or address administration with no live order — blocks
anything owed or paid for. A locked-out customer is stuck and possibly annoyed, but nothing
they have bought is at risk or delayed. Reading the existing definition literally settles
this without inventing a new rule, which is why it goes in as a *clarification* (brief v3)
rather than a policy change. It also matches the pattern already visible in the data: D-018
itself noted the baseline was predicting `low` on the disputed `change_shipping_address`
tickets and was "arguably right" — the drafted labels were the noisy signal, not the
model's judgement.

**Applied to the label set** via a new rule sweep, `account_admin_no_live_order` (see
`src/triage/sweep.py`), matched on the four upstream Bitext intents D-018 identified
(`recover_password`, `registration_problems`, `change_shipping_address`,
`set_up_shipping_address`) and guarded on the same "does the ticket name a live order"
check `pre_dispatch_window` already uses, so the two rules can never disagree about the
same ticket. 10 labels changed (7 dev, 3 test): `hl-0007`, `hl-0030`, `hl-0032`, `hl-0088`,
`hl-0114`, `hl-0173`, `hl-0189`, `hl-0191`, `hl-0245`, `hl-0250` — all `normal` -> `low`.
Same caveat as every sweep: this is a consistency mechanism, not a check. None of these ten
tickets become `reviewed`.

**Left alone on purpose:** `hl-0042`, an authored hard case (a fully locked-out account,
`normal`) that sits in the same territory but carries no `bitext_intent`, so the mechanical
rule does not reach it and I did not hand-correct it. It was authored to test the
`account_security` escalation carve-out, not this urgency question, and hand-picking single
tickets outside a rule's stated scope is exactly the drift the sweep mechanism exists to
avoid — see `src/triage/sweep.py`'s own docstring. It is a candidate for the next review
round, not for this sweep.

Re-ran the baseline (`baseline_v1`, `gpt-5.6-terra`, effort `high`) against brief v3 on both
splits. This is the **new baseline of record** — see the current-results update in
`README.md` — and, per rule 5, a new bar rather than evidence of improvement: the label set
and the prompt moved together, same as the v1 -> v2 transition (`DECISIONS.md` D-016).

### D-019 — Adopted Ponytail, audited the repo, cut two dead symbols

Installed the Ponytail plugin (intensity `full`) and added it as standing rule 10 in
`CLAUDE.md`: least code that works, `/ponytail-review` on every diff, with an explicit
carve-out for evaluation rigour (metrics, CIs, budget guard, spend log, reconciliation
checks, the same-model and reviewed-by-Claude caveats, `DECISIONS.md`, and the tests
covering all of that) — that machinery is the product, not overhead, and Ponytail does
not get to thin it.

Before touching anything: `make test` (38/38 pass) and `--rescore` against both
`results/latest_dev.json` and `results/latest_test.json` (zero API calls, scores byte-
identical) — confirmed the baseline of record was reproducible before any edit, so any
later mismatch would be attributable to the trim.

Ran `/ponytail-audit` over the whole repo (`src/`, `tests/`, `scripts/`, `Makefile`,
`pyproject.toml`) by reading every file rather than trusting a static-analysis pass —
`vulture` wasn't installable in the offline venv, and `ruff` found nothing because
`taxonomy.py`'s two dead symbols are used by nothing, not shadowed or unreachable.

**Cut**, both in `src/triage/taxonomy.py`, both zero-reader dead code:
- `BITEXT_BACKED_CATEGORIES` — no caller anywhere in `src`/`tests`/`scripts`.
- `HARD_CASE_KINDS` — no caller; `hard_case_kind` values come straight from
  `data/hard_cases.jsonl` and nothing validates against this tuple.

**Kept on purpose**, everything else the audit touched: `llm.py`'s budget/spend/pricing
code, `metrics.py`'s Wilson intervals and macro-recall, `evaluate.py`'s markdown
caveats and reconciliation, `export_review.py`'s targeted/random sampling split,
`sweep.py`'s rule provenance, and every test in `test_taxonomy_and_metrics.py` — all
fall under the rule 10 exception. None of it is an abstraction with one caller or a
config nobody sets; each piece backs a specific claim the results make (an interval, a
provenance field, a reconciliation check) and removing it would make the project's own
numbers less defensible, which is the opposite of what a housekeeping pass is for.

Net: -13 lines (3,652 -> 3,639 across `src/` + `tests/`). Re-ran `make test` and both
`--rescore` checks after the cut: 38/38 pass, both splits' scores still byte-identical
to `results/latest_{dev,test}.json`. No OpenAI calls made this session.

The smallness of the diff is itself informative: the project's own rules (8 and 9 in
particular — the spend guard and the decision log) already push hard against
unrequested scaffolding, so there was very little left for a lazy-code pass to find.

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
