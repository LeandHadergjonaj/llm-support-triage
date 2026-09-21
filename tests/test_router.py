"""No API key needed: the deterministic policy layers, not the LLM call itself."""

from __future__ import annotations

from triage.router import enforce_policy, enforce_record_policy


def _pred(escalate=False, reasons=None, urgency="normal", intent="returns_and_refunds"):
    return {
        "intent": intent,
        "urgency": urgency,
        "escalate": escalate,
        "escalation_reasons": list(reasons or []),
        "confidence": 0.9,
        "rationale": "test",
    }


def test_product_safety_forces_high_urgency():
    pred, notes = enforce_policy(_pred(escalate=True, reasons=["product_safety"], urgency="normal"))
    assert pred["urgency"] == "high"
    assert notes == ["product_safety_forces_high"]


def test_out_of_scope_reason_dropped_when_intent_disagrees():
    pred, notes = enforce_policy(_pred(escalate=True, reasons=["out_of_scope"], intent="account_access"))
    assert pred["escalation_reasons"] == []
    assert pred["escalate"] is False
    assert notes == ["out_of_scope_reason_dropped"]


def test_understated_claim_is_escalated_once_the_record_is_known():
    """Customer states nothing over £100 (or nothing at all) but the order record shows an
    unresolved refund over the threshold -- the router couldn't have caught this on ticket
    text alone (brief v4 §5), but the answering step, which does have the record, must not
    self-handle it. See DECISIONS.md D-027."""
    order = {"order_id": "50902", "refund": {"requested_gbp": 149.0, "status": "processing"}}
    pred, forced = enforce_record_policy(_pred(escalate=False), [order])
    assert forced is True
    assert pred["escalate"] is True
    assert "refund_over_threshold" in pred["escalation_reasons"]


def test_a_resolved_refund_over_threshold_does_not_force_escalation():
    """Already paid -- nothing left to review, so a self-handled reply reporting the
    resolved fact is correct, not a policy violation."""
    order = {"order_id": "53003", "refund": {"requested_gbp": 175.0, "status": "paid"}}
    pred, forced = enforce_record_policy(_pred(escalate=False), [order])
    assert forced is False
    assert pred["escalate"] is False
    assert pred["escalation_reasons"] == []


def test_an_unresolved_refund_under_threshold_does_not_force_escalation():
    order = {"order_id": "1", "refund": {"requested_gbp": 42.0, "status": "processing"}}
    pred, forced = enforce_record_policy(_pred(escalate=False), [order])
    assert forced is False


def test_no_order_records_is_a_no_op():
    pred, forced = enforce_record_policy(_pred(escalate=False), [])
    assert forced is False
