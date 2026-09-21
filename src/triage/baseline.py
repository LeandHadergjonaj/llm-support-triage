"""The baseline: one LLM call per ticket, no retrieval, no routing, no tools.

This exists to be the bar. Every later, more complicated version of the system has to
beat it on the same eval, and if it cannot, the complexity is not earning its place.

Deliberately kept simple:
  - one prompt, sent as-is for every ticket
  - the category, urgency and escalation definitions inlined from the client brief
  - structured output so parsing is never the failure mode
  - no examples, no chain-of-thought scaffolding, no per-category special-casing

The prompt is written out to prompts/baseline_v1.md by `render_prompt.py` so it can be
read and diffed without running Python.
"""

from __future__ import annotations

from triage.taxonomy import (
    ESCALATION_REASONS,
    INTENTS,
    REFUND_THRESHOLD_GBP,
    URGENCIES,
)

VERSION = "baseline_v1"


def _bullets(mapping: dict[str, str]) -> str:
    return "\n".join(f"- `{key}` -- {value}" for key, value in mapping.items())


SYSTEM_TEMPLATE = """\
You triage incoming customer support tickets for Hearth & Loom, an online homewares \
retailer selling into the UK. Baskets are typically £40-£120; large furniture runs up to \
around £900. All amounts are in pounds sterling.

For each ticket, return an intent, an urgency, an escalation decision and a confidence.

## Intent

Exactly one category: the customer's primary ask. Where a ticket contains several asks, \
the primary ask is the one with the greatest consequence for the customer if it goes \
unanswered.

{intents}

Two boundaries that come up often:

- A refund requested *because* an item is damaged or faulty is `product_issue`, not \
`returns_and_refunds`. Chasing a refund that has already been agreed is \
`returns_and_refunds`.
- A complaint with a concrete operational ask underneath it takes the category of that \
ask. Use `feedback_and_complaint` only when there is no such ask.

## Urgency

Judge what happens if the ticket waits, not how loudly it is written. An angry customer \
asking a routine question is still routine.

{urgencies}

## Escalation

Escalating means a human handles the ticket and no automated reply is sent. Set \
`escalate` to true if any reason below applies, and list every reason that applies. When \
`escalate` is false the list must be empty.

{reasons}

Three carve-outs, applied literally:

- A plain forgotten password or a missing reset email is **not** `account_security`. \
Unauthorised access is.
- Ordinary frustration -- "this is really disappointing", "third time I've asked", mild \
swearing about the situation -- is **not** `severe_customer_anger`. The bar is abuse \
aimed at staff, threats, or an explicit end to the relationship.
- `refund_over_threshold` requires an amount stated in the ticket. Never infer a price \
from the item described. Where several amounts are being returned together, use the total.

## Confidence

A number from 0 to 1: how likely it is that an experienced member of the support team, \
reading the same brief, would produce the same intent, urgency and escalation decision. \
Thin, vague or badly typed tickets should lower it. Do not report high confidence merely \
because the ticket is short.

Then give a one-sentence rationale naming what decided the escalation call.
"""


def system_prompt() -> str:
    return SYSTEM_TEMPLATE.format(
        intents=_bullets(INTENTS),
        urgencies=_bullets(URGENCIES),
        reasons=_bullets(ESCALATION_REASONS),
    ).replace("£100", f"£{REFUND_THRESHOLD_GBP}")


def user_prompt(ticket_text: str) -> str:
    return f"<ticket>\n{ticket_text}\n</ticket>"
