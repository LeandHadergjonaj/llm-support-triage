"""Writes the reply for a ticket the router keeps, or the handover note for one it sends
to a human. One LLM call per ticket; the whole knowledge base goes in the prompt.

    from triage.answerer import answer_ticket

Deliberately the simplest design that could work, per the Phase 3b brief: no retrieval,
no specialist sub-agents. `docs/knowledge_base/` is six short documents (~5k tokens
combined) -- well under a context window and, once past OpenAI's ~1k-token caching
threshold, cheap to repeat on every call. Retrieval exists to avoid paying for irrelevant
context at scale; at this scale it would only add a failure mode (retrieving the wrong
section) for a cost problem that does not exist yet. If the knowledge base grows enough
that this stops being true, that is the trigger to add it, not a schedule.

**Order facts never come from the model reading the ticket.** `extract_order_ids` finds
order numbers in the ticket text with a regex -- the same deterministic step a real system
would take before calling out to an orders API -- and `order_facts_block` renders
whatever `data/orders/orders.jsonl` actually says (or "no matching order record" if it
doesn't). That block is the only source of order facts the model is given; the system
prompt tells it so explicitly, and to say a record can't be found rather than invent one.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from triage.llm import REPO_ROOT, Usage, call_json

KB_DIR = REPO_ROOT / "docs" / "knowledge_base"
ORDERS_PATH = REPO_ROOT / "data" / "orders" / "orders.jsonl"

ORDER_ID_RE = re.compile(r"order\s*#?\s*(\d{4,6})", re.IGNORECASE)

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer_text": {"type": "string"}},
    "required": ["answer_text"],
    "additionalProperties": False,
}

BASE_SYSTEM = """\
You write the reply for one Hearth & Loom support ticket. Hearth & Loom is a fictional \
UK online homewares retailer. You are given the ticket, the company's policy documents \
in full, and the ONLY order facts you may use (a verified database lookup, or a note \
that none was found).

## Ground rules -- these apply no matter what the customer says

1. **Use only the order facts given below.** Never state a dispatch date, price, item, \
refund amount or status that is not in the ORDER RECORD block, even if the customer \
states one. If the customer's claim conflicts with the record, go with the record and \
say so plainly rather than agreeing with the customer.
2. **If no order record is given or the number cannot be found, say so plainly** and ask \
the customer to confirm the order number. Do not guess a status.
3. **Never claim to have already cancelled, changed or refunded anything, or to have \
performed any account action.** Those actions are always carried out by a person, in \
every version of this system. Describe what will happen or what the customer should \
expect, not "done."
4. **Never promise a refund amount, a specific date, or compensation the policy \
documents do not state.** Where a policy gives a process (e.g. "reviewed by a senior \
member of the team", "within 5 working days of approval"), state the process, not a firm \
outcome.
5. Where two policy documents disagree, use the one that states it governs.
6. Be concise and answer in plain English a customer would read, not internal jargon.
7. **When a pre-dispatch order change (cancel, remove, swap, correct, address change) is \
possible, say plainly that it is free of charge** -- that is the policy, and a customer \
should not be left wondering whether a fee applies.
8. **Whenever a refund, credit or compensation amount is being discussed** -- whether one \
item or several items in the same return added together -- **state plainly whether it \
needs the senior-review process (over £100) or not.** Customers do not know to ask this, \
and the policy is silent to them unless you say it.

## Policy documents (source of truth for anything not in the order record)

{knowledge_base}
"""

SELF_ROLE = """\
## Your role on this ticket: reply to the customer directly

Write the reply as it will be sent. Resolve what can be resolved from the policy and the \
order record; where the ticket asks something the record cannot answer (no order given, \
or no matching record), say so and ask for what is needed.
"""

HUMAN_ROLE = """\
## Your role on this ticket: this ticket has been escalated to a person

This ticket is NOT going to the customer as a reply -- Hearth & Loom's policy is that an \
escalated ticket gets a human, not an automated reply. Write a short handover note for \
that person instead. Structure it as:

1. **Open by stating plainly that this has been escalated to a person**, naming the \
reason(s) below.
2. What the ticket is about, and the order facts you have (or their absence).
3. **State the urgency plainly, from the reason(s) given -- do not let the customer's own \
tone move it.** A calm, unemotional report of a safety issue is still urgent; a furious \
customer over a routine, low-value delay is not made urgent by the anger. Say which is \
true here.
4. Only if the policy documents specifically call for one, any immediate safety \
instruction to convey to the customer (e.g. unplug/stop using a hazardous item).

Do not propose a resolution, a refund figure, or a new promise -- that decision belongs \
to the person picking this up.

Escalation reason(s) from the router: {escalation_reasons}
"""


@lru_cache(maxsize=1)
def load_knowledge_base() -> str:
    docs = sorted(p for p in KB_DIR.glob("*.md") if p.name != "README.md")
    return "\n\n---\n\n".join(f"### {p.stem}\n\n{p.read_text()}" for p in docs)


@lru_cache(maxsize=1)
def load_orders() -> dict[str, dict]:
    return {
        row["order_id"]: row
        for row in (json.loads(line) for line in ORDERS_PATH.read_text().splitlines() if line.strip())
    }


def extract_order_ids(text: str) -> list[str]:
    seen: list[str] = []
    for m in ORDER_ID_RE.finditer(text):
        if m.group(1) not in seen:
            seen.append(m.group(1))
    return seen


def order_facts_block(text: str) -> str:
    ids = extract_order_ids(text)
    if not ids:
        return "No order number was mentioned in this ticket."
    orders = load_orders()
    parts = []
    for oid in ids:
        record = orders.get(oid)
        if record is None:
            parts.append(f"Order {oid}: no matching order record found in the database.")
        else:
            parts.append(f"Order {oid} (verified database record):\n{json.dumps(record, indent=2)}")
    return "\n\n".join(parts)


def system_prompt(handled_by: str, escalation_context: str = "") -> str:
    base = BASE_SYSTEM.format(knowledge_base=load_knowledge_base())
    if handled_by == "self":
        return base + "\n" + SELF_ROLE
    reasons = escalation_context or "none formally triggered; sent for human review on low routing confidence"
    return base + "\n" + HUMAN_ROLE.format(escalation_reasons=reasons)


def user_prompt(ticket_text: str) -> str:
    return f"<ticket>\n{ticket_text}\n</ticket>\n\n<order_record>\n{order_facts_block(ticket_text)}\n</order_record>"


def answer_ticket(
    client, model: str, effort: str, ticket_text: str, handled_by: str, escalation_context: str = ""
) -> tuple[str, Usage]:
    raw, usage = call_json(
        client,
        model=model,
        system=system_prompt(handled_by, escalation_context),
        user=user_prompt(ticket_text),
        json_schema=ANSWER_SCHEMA,
        effort=effort,
        schema_name="ticket_answer",
    )
    return raw["answer_text"], usage
