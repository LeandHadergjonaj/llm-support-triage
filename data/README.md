# Evaluation data

## Licence and provenance

The tickets in `eval/dev.jsonl` and `eval/test.jsonl` are derived from the **Bitext
Customer Service Tagged Training Dataset for LLM-based Virtual Assistants**:

> Bitext, *Bitext - Customer Service Tagged Training Dataset for LLM-based Virtual
> Assistants*. https://huggingface.co/datasets/bitext/Bitext-customer-support-llm-chatbot-training-dataset
> Licensed under CDLA-Sharing-1.0.

**CDLA-Sharing-1.0 permits redistribution, including of modified data, so the derived
evaluation set is committed to this repository.** The obligations it imposes are met as
follows:

- The data here is published under the same unmodified licence, whose full text is in
  `LICENSE-CDLA-Sharing-1.0.txt`.
- Attribution to Bitext is preserved above, and each derived ticket keeps its upstream
  intent and language-variation flags in the `bitext_intent` and `bitext_flags` fields.
- **Change notice (required by section 3.1(b)): the files in `eval/` contain changed
  data.** The changes made are listed under "What was changed" below.

The obligations do not extend to `results/` — CDLA-Sharing-1.0 section 3.5 places no
restrictions on the publication of Results, which is what the scored model outputs are.

The 19 MB upstream CSV is *not* committed, for repository size rather than licensing.
Fetch it with:

```
.venv/bin/python scripts/fetch_dataset.py
```

## Why this dataset

Its 27 intents map cleanly onto an online retailer's inbox — orders, delivery, refunds,
payment, accounts — which is exactly the shape of Hearth & Loom's traffic. Each row also
carries language-variation flags (typos, colloquialisms, politeness, offensive language),
which makes it possible to slice results by how messily a ticket is written rather than
guessing. No other public customer-support set found offered both retailer-shaped intents
and a permissive redistribution licence.

Its limitations are real and are the reason `hard_cases.jsonl` exists — see below.

## What was changed

1. **Sampled**, not taken whole: 216 of 26,872 rows, stratified to 24 per target category.
   The upstream set is near-uniform across its 27 intents; stratifying by the 11-category
   target taxonomy keeps per-class accuracy interpretable. This is *not* the natural
   distribution of a real inbox and the eval does not claim to model one.
2. **Intents remapped** from the upstream 27 to the 11 categories in
   `docs/client-brief.md`, by the deterministic table in `src/triage/taxonomy.py`.
3. **Placeholders filled.** Upstream text contains tokens like `{{Order Number}}` and
   `{{Refund Amount}}` with no values. These were replaced with plausible Hearth & Loom
   values. Refund amounts are drawn from a distribution straddling the £100 escalation
   threshold; without this the threshold rule would be untestable.
4. **Money-bearing rows front-loaded.** Only `track_refund` and `get_refund` carry a
   refund-amount placeholder, in a minority of rows. An unweighted sample produced two
   tickets with a figure in them across the whole set. Up to half of those two intents'
   quota is now drawn from money-bearing rows. A deliberate departure from the upstream
   distribution, made so the escalation threshold has something to bite on.
5. **Deduplicated** on exact text within the sample.

## `hard_cases.jsonl` — authored, not sampled

36 tickets written for this project, 4 each across nine kinds: multiple issues in one
message, heavy typos, angry customers, off-topic requests, genuinely ambiguous tickets,
product safety, account security, legal and chargeback threats, and high-value refunds.

They exist because the upstream data is templated, single-intent and averages 47
characters. Real inboxes are not like that, and two of the eleven categories
(`product_issue`, `out_of_scope`) have no upstream source at all. Several hard cases are
deliberate near-misses that the brief says must **not** escalate — a £95 refund, a plain
forgotten password, ordinary frustration — because a triage system that escalates
everything scary-looking is not useful.

`author_note` on each records what the ticket was written to test. It is design intent,
not a label.

## Label provenance — read this before quoting any number

| Label | Source |
|---|---|
| `intent` on Bitext tickets | Deterministic mapping from the upstream intent |
| `intent` on hard cases | **Model-drafted** |
| `urgency` | **Model-drafted** |
| `escalate`, `escalation_reasons` | **Model-drafted** |

Urgency and escalation labels were drafted by Claude Opus 5 reading the full client brief
(`src/triage/labeler.py`), one ticket at a time, blind to the upstream intent. They are
**not hand-labelled**. `human_reviewed` is `false` on every ticket a person has not yet
checked, and `label_provenance` records the source of each field individually.

This matters for how the baseline's scores should be read: the baseline is being measured
against labels drafted by the same model family, so absolute accuracy is optimistic. The
numbers are useful as a fixed bar for later versions to beat, not as an estimate of how
the system would perform against a support team's own judgement. Correcting the labels by
hand is what fixes this — `make review` exports a sample to correct.

Two independent signals on label quality are recorded per ticket:

- `drafter_uncertain` — the drafter's own flag that a reasonable colleague could disagree.
- `intent_disagreement` — the drafter was asked for an intent without being shown the
  upstream one; this records where the two differ.

## Splits

60/40 dev/test, stratified on strata known before labelling (category for Bitext tickets,
hard-case kind for authored ones), seeded at 20260921.

**The test split is held out.** It is not used to tune the prompt. `make eval` runs dev;
scoring test is a separate command that prints a warning.
