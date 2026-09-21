# Project context

*This file is the context file for the Claude Code CLI, which is the tool being used to
build the project. The project itself runs on OpenAI — see Stack below.*

## What this is

An LLM support-triage system for **Hearth & Loom**, a fictional online homewares retailer
selling into the UK. Built as a portfolio project for a Forward Deployed Engineer role, so
the engineering judgement on show matters as much as the result: honest evaluation,
stated limitations, clear commits.

The system routes incoming support tickets — deciding intent, urgency and whether a human
must handle it — answering routine ones from policy documents and an orders database, and
escalating risky or uncertain ones to a human review queue.

## Where we are

**Phase 1 and Phase 2 complete.** 252 tickets (216 Bitext, 36 authored hard cases), labels
drafted by `gpt-5.6-terra`, split 144 dev / 108 test.

The client brief is now at **v3**: six clarifications total across two versions, each
prompted by a contested or contradictory label found in review or by an open question
logged in `DECISIONS.md`, with a changelog in `docs/client-brief.md` §7. v3 settled D-018
(a simulated-client decision, since there is no real client to ask — see D-020): an
account-level admin task that blocks nothing paid for is `low`, not `normal`. 23 labels
have now been changed by rule sweeps across the two brief versions (13 at v2, 10 at v3).
The baseline prompt restates the same v3 policy and both splits were re-run against it —
that is the current **baseline of record**.

Label checking to date, none of it by a person:
- **85 of 252** through a second-opinion review by `claude-opus-5` (round 1: 55 tickets;
  round 2: a fresh random block of 30 drawn from the never-reviewed remainder).
- **23** changed by rule sweeps (13 at brief v2, 10 at brief v3), which apply a rule
  without re-reading and are *not* a check.
- Label error rate: **round 1 block 20.0%** (6/30, 95% CI 9.5–37.3%, restated upwards
  from 16.7% after round 2 found an error round 1 had confirmed); **round 2 block 3.3%**
  (1/30, 95% CI 0.6–16.7%). The two rounds sample different populations and are never
  pooled.

**Step 1: evaluation set, versioned brief, and single-prompt baseline. Step 2: D-018
settled and a router built** (`src/triage/router.py`, `src/triage/evaluate_router.py`) —
same model and brief as the baseline, adding a prompt fix for the one known failure
pattern brief v3 did not cover, a deterministic policy layer enforcing two brief
invariants on live predictions, and a confidence gate that sends uncertain tickets to a
human instead of guessing (settling brief §5's deliberately-open question). **It does not
show a statistically significant improvement over the baseline at n=144/108** — McNemar
p=0.73 (dev), p=1.0 (test) on "all three correct" — though it demonstrably fixed the
specific failure pattern it targeted (3 for 3) and cannot emit two classes of
self-contradictory prediction by construction. See `DECISIONS.md` D-021 for the full,
unflattering-where-it-should-be account.

**Phase 3a complete: the client's knowledge and the answer eval are built; nothing answers
tickets yet.** Not chasing more triage accuracy for now — the router's McNemar p was 0.73
(dev) / 1.0 (test), and with errors down to single digits this eval set can no longer tell
triage designs apart (D-022). Phase 3a is the measuring stick for Phase 3, same as Phase 1
was for triage: `docs/knowledge_base/` (six policy documents, consistent with brief v3, with
one planted cross-document inconsistency and a stated precedence rule), `data/orders/` (a
30-order mock database), and `data/eval/answers_{dev,test}.jsonl` (36 tickets — 20 reused
from Phase 1, 16 newly authored — each carrying an answer contract: `must_handle`,
`expected_must_contain`, `expected_must_not_contain`, all traceable to a doc section or an
order field). `src/triage/eval_answers.py` scores a candidates file against it; the judge is
an LLM (`gpt-5.6-terra` by default) and that is **not independent verification**, for the
same reason a same-family label review isn't (D-011) — see D-022 and the module's own
docstring. Cost: $0, no API calls were needed to build this step.

**Phase 3b complete: the system now answers tickets.** `src/triage/answerer.py` — one LLM
call per ticket, the whole knowledge base in the prompt (no retrieval, not needed at this
size), order facts only from a deterministic regex-then-database lookup, never from the
model reading the ticket. The router (Phase 2, unchanged) decides `self` vs `human` first;
the answerer writes a customer reply or a handover note accordingly, and never claims to
have performed an order/account/refund action itself. **Dev, final: routing 95.0% (19/20),
required-fact coverage 100% (38/38), forbidden-content avoidance 100% (34/34), fully
correct 100% (19/19).** **Test, run once, unmodified after: routing 93.75% (15/16),
required-fact coverage 83.87% (26/31), forbidden-content avoidance 100% (25/25), fully
correct 80.0% (12/15).** Two structural additions, both earned by a specific dev failure
(state the £100 threshold and the pre-dispatch fee-free rule unprompted; pass the router's
own escalation reason into the handover note); one eval-authoring bug class found and fixed
before test (`hl-0242`/`hl-0033`, D-023) and two more instances of it found *after* test and
deliberately left uncorrected (`hl-0011`, `hl-0236`, D-024) — test's number is a genuine
underestimate by a known amount, stated rather than fixed. Judge check: Claude Sonnet 5
blind-graded every dev answer plus four deliberately broken ones — 100% agreement on 88
judgements, which says the judge catches clear-cut violations reliably, not that it is
tolerant of badly-worded criteria (it isn't — that's what the two post-test findings show).
Phase cost $0.2949; project-to-date $2.3860 (`make spend`). See `DECISIONS.md` D-024.

**Phase 4 complete: the human review queue.** Part 1 tidied up Phase 3b's three named
findings and settled brief §5's stated-vs-record question — brief moves to **v4**: a
stated-vs-record mismatch still escalates on the stated figure (triage never sees the
order record), but the record governs what is said once someone has it; corrected
`hl-a0012`'s `must_handle` (self → human, matching what the router already did) and
dropped two backwards-phrased `answers_test.jsonl` criteria (`hl-0011`, `hl-0236`, same
defect class as D-023). **`data/eval/answers_test.jsonl` is now a seen set** — required
fact coverage on the existing test candidates moves 83.87% → 90.62%, reported as
`test (seen)`, never blended with the original held-out 83.87%. See `DECISIONS.md` D-025.

Part 2: `src/triage/queue_app.py`, a small Flask app over a SQLite database
(`data/queue/queue.db`), built from Phase 3b's own answerer candidates rather than
reinventing them (`src/triage/build_queue_data.py` — 11 new API calls, one per
human-routed ticket, for a suggested customer-facing draft reply Phase 3b deliberately
never wrote). Every human-routed ticket becomes a ready-to-act package: the ticket, why it
was escalated, the verified order-facts lookup, the relevant policy document(s), the
router's own handover note, and a suggested reply the agent approves as-is, edits, or
rejects with a note — every decision recorded in `reviews`. A separate `/spotcheck` view
lists every self-handled ticket read-only with a flag/notes field, for auditing replies
the system already "sent" on its own. `/stats` reports acceptance/edit/reject rates and
the spot-check flag rate. `make queue-data` then `make queue`; nothing is ever sent to a
real customer — approving only records a decision. Phase 4 total spend: **$0.0626**
(judge re-scoring + 11 draft-reply calls), project-to-date **$2.4486**. See `DECISIONS.md`
D-025 and D-026.

**Phase 5a in progress: two policy gaps closed, deployment configured, pending account
creation only the client can do.** An understated or unstated refund claim can no longer
self-handle its way past the £100 review once the order record is known (a second policy
layer, `router.enforce_record_policy`, run in the answer pipeline after the order lookup
that already happens there — the router itself still decides on ticket text alone, per
brief v4 §5); D-024's open ground-rule-3 question is settled (it stays broad — the system
has no execution capability at all, for any account action, order/money or otherwise).
Zero eval tickets were affected (checked, not assumed) so no eval was re-run at cost beyond
one $0.0319 judge re-score for an eval-criterion fix. `render.yaml` and the demo-mode
seeding/reset code are ready for a public read-only-ish demo on Render's free tier (no
credit card, ephemeral filesystem doubles as the reset mechanism, no `OPENAI_API_KEY` in
its environment at all so it cannot spend API money even in principle); `make queue` is
unaffected locally. See `DECISIONS.md` D-027 for the full account, including what's still
pending: the client creating a Render account and connecting the repo.

Deliberately *not* built yet: Phase 5b (the real inbox) and visual polish (Phase 6). SQLite
and Flask were chosen to make deployment easy, not to pre-empt it.

## The rules this project runs on

1. **`docs/client-brief.md` is the source of truth for every label.** Policy documents and
   the orders database added later must be consistent with it. If the brief and the code
   disagree, the brief wins and the code is the bug — `tests/` asserts they agree.
2. **The test split is held out.** Tune on `data/eval/dev.jsonl` only. `make eval` runs
   dev; scoring test is a separate command and prints a warning.
3. **No label in this project has been checked by a person, and none may be described as
   if it had.** Labels are model-drafted; some have since been through a second-opinion
   review by a model of a *different family* from the drafter (`gpt-5.6-terra` drafted,
   `claude-opus-5` reviewed). That is an independence check, not verification. Never write
   "hand-labelled", "human-reviewed" or "verified". `label_provenance`, `reviewed`,
   `reviewed_by` and `sweep` are per-ticket and must stay accurate; `tests/` asserts the
   banned phrasings never appear in the data.
   **A rule sweep is not a review.** `triage.sweep` applies a brief rule mechanically
   without re-reading anything, so it finds only the errors its rule describes. A swept
   ticket stays `reviewed: false` and still counts as unchecked in the error rate.
4. **Do not overstate results.** The baseline is scored against labels drafted by **the
   same model at the same effort**, not merely the same family. A model agreeing with its
   own judgement is not evidence that the judgement is right, so absolute accuracy is
   optimistic by an unknown margin and every report must say so up front. The human review
   pass is the only thing that shrinks this; until it lands, the numbers are a bar to beat,
   not a measure of quality.
5. **Beat the baseline or justify the complexity.** A later version that does not improve
   on `results/latest_dev.json` has not earned its extra moving parts.
   **Compare only at the same brief version.** Every result carries `run.brief_version`.
   Clarifying the brief moves the labels *and* the prompt at once, so it produces a new
   bar, never evidence of improvement. A brief change needs a contested label behind it,
   an entry in `docs/client-brief.md` §7, and the labels and prompt updated in the same
   commit.
6. **The API key comes from the environment only.** `OPENAI_API_KEY` in `.env`, which
   is gitignored; never commit a key.
7. **`gpt-5.6-terra` is the triage model, for this step and every later one**, unless the
   client says otherwise. Fixed deliberately: a later version has to beat the baseline on
   design — routing, retrieval, better prompts — and not by being handed a stronger model.
   Changing it invalidates the comparison against `results/latest_dev.json`.
8. **No run costs more than $2 without asking first.** Enforced, not remembered: every
   command that calls the API takes `--max-cost` (default $2.00) and stops rather than
   spend past it. Running spend is appended to `results/spend_log.jsonl`; `make spend`
   prints the total. Projected cost goes in the plan before the money goes out.
9. **Claude owns the decisions on this project, and logs them.** Every meaningful decision
   goes in `DECISIONS.md`, dated and newest-first, with the reasoning and — where the
   brief was silent — the rule that should have been there. A decision a later reader
   could reasonably have made differently belongs in the log; routine implementation
   choices do not. Go back to the client only for what only they can supply: spend above
   the $2 cap, keys or account access, or a change to what the project is for. Everything
   else: decide, do it, write it down.
10. **Write the least code that works.** Ponytail-lazy by default: reuse before adding,
    stdlib before a dependency, no abstraction for one caller, shortest diff that is still
    correct. Run `/ponytail-review` on your own diff before every commit.
    **Exception: evaluation rigour is the product and is never simplified away.** That
    covers the metrics and their confidence intervals, the budget guard and spend log,
    reconciliation checks, the same-model and reviewed-by-Claude caveats, `DECISIONS.md`,
    and the tests that cover all of these. When the ladder and this exception conflict,
    the exception wins.
11. **Commit at the end of every piece of work; push to GitHub at the end of every
    phase.** A piece of work is done when its tests pass and, for anything touching the
    baseline, the eval reproduces — commit it then, don't batch unrelated changes into
    one commit. Pushing is coarser: it happens when a phase (as tracked in "Where we
    are") closes, not after every commit.

## Stack

Python 3.11, OpenAI Python SDK (Responses API), Pydantic for validation, strict
structured outputs (`text.format`, `strict: true`) so parsing is never the failure mode.
Model: `gpt-5.6-terra` for both label drafting and the baseline, overridable with
`TRIAGE_MODEL` or `--model`. The client brief is versioned and `taxonomy.brief_version()`
reads the version out of it, so every run records which policy it was scored under. No
framework for the triage/answering pipeline itself — that stays a classification and
evaluation problem. Phase 4's review queue is the one exception: Flask (a small dependency,
justified by needing several routed pages and forms) over SQLite (stdlib `sqlite3`, a
plain schema with no SQLite-only types, a single-writer workload — no server needed).

All provider-specific code lives in `src/triage/llm.py`; nothing else imports the SDK.

## Commands

```
make setup      venv + dependencies
make data       build the eval set (drafts labels; costs money, cached on disk)
make smoke      ~1c end-to-end pipeline check on 16 tickets (never an eval set)
make eval       score the baseline on dev            <-- the main one
make eval-test  score on the held-out test split
make eval-router       score the router on dev and compare it to the baseline
make eval-router-test  score the router on the held-out test split
make review     export the round-1 label sample for correction
make review-round2  draw a fresh random block from the never-reviewed remainder
make sweep      show which labels the current brief's rules would change (dry run)
make answer      run the full router+answerer+judge pipeline on dev and score it
make answer-test run the full pipeline on the held-out test split
make eval-answers ANSWERS=path.jsonl       score a candidates.jsonl against the DEV answer eval
make eval-answers-test ANSWERS=path.jsonl  score against the HELD-OUT TEST answer eval
make queue-data  build the review-queue packages (reuses answerer candidates; ~11 API calls)
make queue       run the review-queue web app at http://127.0.0.1:5050
make spend      print total API spend recorded so far
make test       checks that need no API key
```

## Current results

Baseline of record (`results/latest_{dev,test}.json`), `baseline_v1` against **client
brief v3**:

Dev: intent 95.1%, urgency 99.3% (macro recall 99.7%), escalation 97.9%, all three 94.4%.
Test: intent 96.3%, urgency 96.3% (macro recall 96.8%), escalation 99.1%, all three 93.5%.
`high` urgency recall 100% on both — **on 15 and 10 tickets**, so the 95% Wilson interval
reaches down to 79.6% and 72.3%; treat it as "no misses yet", not as reliable. Spurious
`out_of_scope` escalations on "make a claim / file a complaint" wording are still present
in the baseline (untouched, by design — the router below fixes them).

**These are a new bar, not an improvement.** Brief v3 settled D-018 (an account-admin
urgency question with no rule to decide it), so labels and prompt moved together, same as
v1 → v2. The brief v1 and v2 runs stay in `results/` under their timestamps. See
`DECISIONS.md` D-020.

**Router** (`router_v1`, `results/latest_router_{dev,test}.json`): same model and brief,
plus a prompt fix for the "make a claim" pattern, a deterministic policy layer, and a
confidence gate (threshold 0.7, chosen on dev) that sends uncertain tickets to a human.
All three correct: dev 95.8% vs baseline 94.4% (McNemar p=0.73, not significant); test
92.6% vs baseline 93.5% (p=1.0, not significant). **No demonstrated win over the baseline
at these sample sizes** — say so, don't round it up. It did fix 3/3 of the specific
`out_of_scope` mislabels it targeted, and cannot emit a `product_safety`-without-`high`
or a self-contradictory `out_of_scope` reason by construction. Self-handled accuracy 96.8%
(dev) / 93.1% (test) on the ~80-87% of tickets not sent to a human. See `DECISIONS.md`
D-021.

Label error rate: round 1 block 20.0% (6/30, 95% CI 9.5–37.3%); round 2 block 3.3%
(1/30, 95% CI 0.6–16.7%). Never pooled. Round 2 is not independent — the same model wrote
the sweep rules and then measured what they left behind.

**$1.7879 spent in total** across the whole ledger (`make spend`), of which $0.1842 is a
backfilled pre-ledger entry for the smoke test and effort probe. The brief v2 re-run cost
$0.3197, the brief v3 re-run $0.3278, and the router's dev + test runs $0.3436. Earlier
documents quoted $0.61, which excluded the backfilled entry; the ledger total is the
number to use. Full table in `README.md`.
