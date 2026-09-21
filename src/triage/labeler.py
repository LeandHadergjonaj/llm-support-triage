"""Drafts urgency and escalation labels for the evaluation set.

These labels are MODEL-DRAFTED. Every ticket records that in `label_provenance`.
`reviewed` stays false until the ticket has been through the second-opinion review pass,
which is run by a model of a different family -- not by a person. No label in this
project is hand-labelled at any point.

The drafter is deliberately not the baseline: it sees the whole client brief, is asked
to reason about one ticket at a time, and is asked to flag its own uncertainty. It is
also asked for an intent it cannot see the dataset's answer to, so the rate at which it
disagrees with the Bitext mapping is an independent read on label quality.
"""

from __future__ import annotations

from pathlib import Path

from triage.taxonomy import BRIEF_PATH, ESCALATION_REASONS, INTENTS, URGENCIES, brief_version

__all__ = ["BRIEF_PATH", "brief_version", "labeler_json_schema", "labeler_system", "labeler_user"]


def _brief() -> str:
    return Path(BRIEF_PATH).read_text()


LABELER_SYSTEM_TEMPLATE = """\
You are building the reference labels for a support-ticket triage evaluation set. These \
labels become the ground truth other systems are scored against, so they need to be \
defensible rather than quick.

The client brief below is the only authority. Where your instincts and the brief \
disagree, the brief wins.

<client_brief>
{brief}
</client_brief>

For each ticket you are given, decide:

1. `intent` -- one category, the customer's primary ask.
2. `urgency` -- judged on what happens if the ticket waits, not on tone.
3. `escalate` and `escalation_reasons` -- apply section 5 literally. List every reason \
that applies; the list must be empty when `escalate` is false and non-empty when it is true.
4. `uncertain` -- true if a reasonable colleague reading the same brief could justify a \
different answer. Be honest here. A label set where nothing is flagged is less useful \
than one where the genuinely contested cases are marked.
5. `note` -- one sentence. If `uncertain`, say what the competing reading is. Otherwise \
say what decided it.

Things that catch people out, all drawn from the brief:

- A forgotten password is not `account_security`. A lockout the customer did not cause is.
- Ordinary frustration is not `severe_customer_anger`. The bar is abuse, threats, or an \
explicit end to the relationship.
- `product_safety` applies even when the customer is calm and asks for nothing.
- `refund_over_threshold` needs a figure in the ticket. Never infer a price from the \
item. Where several amounts are being returned together, the total is what counts.
- A short, vague or badly typed ticket is usually still routine. Thin context is not \
urgency.
- Tickets written as fragments or keywords ("invoice 8841 copy pls") are real tickets. \
Label the ask you can see.
"""


def labeler_system() -> str:
    return LABELER_SYSTEM_TEMPLATE.format(brief=_brief())


def labeler_user(text: str) -> str:
    return f"<ticket>\n{text}\n</ticket>"


def labeler_json_schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": list(INTENTS)},
            "urgency": {"type": "string", "enum": list(URGENCIES)},
            "escalate": {"type": "boolean"},
            "escalation_reasons": {
                "type": "array",
                "items": {"type": "string", "enum": list(ESCALATION_REASONS)},
            },
            "uncertain": {"type": "boolean"},
            "note": {"type": "string"},
        },
        "required": ["intent", "urgency", "escalate", "escalation_reasons", "uncertain", "note"],
        "additionalProperties": False,
    }
