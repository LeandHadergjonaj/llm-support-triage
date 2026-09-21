"""The label set, mirroring docs/client-brief.md.

The brief is the source of truth. If the two disagree, the brief wins and this
file is the bug.
"""

from __future__ import annotations

# --- Intent categories ------------------------------------------------------

INTENTS: dict[str, str] = {
    "order_management": "Placing an order, cancelling an order, changing order contents.",
    "delivery_and_shipping": (
        "Where is my order, delivery timescales and options, changing or setting a "
        "delivery address."
    ),
    "returns_and_refunds": (
        "Requesting a refund, chasing a refund already agreed, refund and returns policy "
        "questions, cancellation fees."
    ),
    "billing_and_payment": "Payment failures, accepted payment methods, invoices and receipts.",
    "account_management": "Creating, editing, deleting or switching an account.",
    "account_access": (
        "Cannot log in, password reset, registration problems, suspected unauthorised access."
    ),
    "product_issue": (
        "The goods themselves: damaged on arrival, faulty, wrong item, missing parts, "
        "safety problems."
    ),
    "feedback_and_complaint": (
        "Complaints about service, and unsolicited praise or reviews, where there is no "
        "other specific ask."
    ),
    "human_agent_request": (
        "Explicitly asking to speak to a person, or for a phone number or contact route."
    ),
    "marketing_preferences": "Newsletter and marketing email subscribe / unsubscribe.",
    "out_of_scope": (
        "Not a Hearth & Loom support request: spam, sales pitches, job applications, wrong "
        "company, questions outside the support team's remit."
    ),
}

# --- Urgency ----------------------------------------------------------------

URGENCIES: dict[str, str] = {
    "high": (
        "Waiting causes harm that cannot be undone later: physical safety, an account being "
        "actively misused, money moving irreversibly, or a time-boxed window about to close."
    ),
    "normal": (
        "The customer is blocked on something they are owed or have paid for, but a day's "
        "delay changes nothing material."
    ),
    "low": "Informational, administrative, or no one is blocked.",
}

# --- Escalation -------------------------------------------------------------

REFUND_THRESHOLD_GBP = 100

ESCALATION_REASONS: dict[str, str] = {
    "refund_over_threshold": (
        f"A refund, credit, replacement or compensation worth over £{REFUND_THRESHOLD_GBP} is "
        "being asked for. Use a stated figure; never infer one."
    ),
    "legal_or_chargeback_threat": (
        "Solicitors, legal action, small claims, trading standards, an ombudsman, a "
        "chargeback, a bank dispute, or going to the press or social media to damage the "
        "company."
    ),
    "product_safety": (
        "Any suggestion the goods caused or could cause physical harm: injury, burns, cuts, "
        "electrical faults, smoke, overheating, sharp edges, choking risk, collapse under "
        "load. Applies even when the customer is calm and asks for nothing."
    ),
    "account_security": (
        "Suspected unauthorised access: a lockout the customer did not cause, orders or "
        "address changes they did not make, unrecognised charges, suspected phishing. A "
        "plain forgotten password is not this."
    ),
    "severe_customer_anger": (
        "Sustained abuse, profanity directed at staff, threats, or an explicit statement "
        "that they are done with the company. Ordinary frustration is not this."
    ),
    "out_of_scope": (
        "Not a Hearth & Loom support request, or outside the support team's remit."
    ),
}

# --- Mapping from the upstream Bitext intents -------------------------------
#
# Deterministic many-to-one. Applied by build_dataset.py, so the intent label on
# every Bitext-sourced ticket is dataset-derived rather than a per-ticket judgement.
# `product_issue` and `out_of_scope` have no Bitext source and are populated only by
# the authored hard cases.

BITEXT_INTENT_TO_CATEGORY: dict[str, str] = {
    "place_order": "order_management",
    "cancel_order": "order_management",
    "change_order": "order_management",
    "track_order": "delivery_and_shipping",
    "delivery_options": "delivery_and_shipping",
    "delivery_period": "delivery_and_shipping",
    "change_shipping_address": "delivery_and_shipping",
    "set_up_shipping_address": "delivery_and_shipping",
    "get_refund": "returns_and_refunds",
    "track_refund": "returns_and_refunds",
    "check_refund_policy": "returns_and_refunds",
    "check_cancellation_fee": "returns_and_refunds",
    "payment_issue": "billing_and_payment",
    "check_payment_methods": "billing_and_payment",
    "check_invoice": "billing_and_payment",
    "get_invoice": "billing_and_payment",
    "create_account": "account_management",
    "edit_account": "account_management",
    "delete_account": "account_management",
    "switch_account": "account_management",
    "recover_password": "account_access",
    "registration_problems": "account_access",
    "complaint": "feedback_and_complaint",
    "review": "feedback_and_complaint",
    "contact_customer_service": "human_agent_request",
    "contact_human_agent": "human_agent_request",
    "newsletter_subscription": "marketing_preferences",
}

# Categories reachable from the Bitext sample, in mapping order.
BITEXT_BACKED_CATEGORIES: list[str] = list(dict.fromkeys(BITEXT_INTENT_TO_CATEGORY.values()))

HARD_CASE_KINDS: tuple[str, ...] = (
    "multi_issue",
    "typos",
    "angry",
    "off_topic",
    "ambiguous",
    "safety",
    "security",
    "legal",
    "high_value_refund",
)
