"""The router: the baseline call, a deterministic policy layer, and a confidence gate.

Same model, same brief, one call per ticket -- the same shape as the baseline. What it adds
is design, not a bigger model:

  1. A boundary clarification in the prompt for the one failure pattern brief v3 did not
     touch: "make a claim" / "file a complaint" read as a legal process instead of the
     `feedback_and_complaint` it plainly is (see README "What is still wrong").
  2. A deterministic policy layer that enforces two brief invariants on every prediction
     -- `product_safety` implies `high` urgency, and the `out_of_scope` escalation reason
     requires an `out_of_scope` intent -- so the model cannot violate them even when its
     raw output would. These are the same two invariants `sweep.py` enforces on the label
     set; here they run on live predictions instead, so they need no `bitext_intent` and
     generalise past this eval set.
  3. A confidence gate: a ticket the model is not confident about is sent to a human
     instead of guessed, whether or not any formal escalation reason fired. Brief §5 says
     this is deliberately undecided policy ("a decision for a later step") -- this is that
     step. `sent_to_human` is therefore broader than `escalate`: every escalated ticket is
     sent to a human, but a low-confidence ticket is too, even with `escalate=False`.
"""

from __future__ import annotations

from triage.baseline import system_prompt

ROUTER_VERSION = "router_v1"

# Chosen on dev only, from the threshold scan in evaluate_router.py's own report (see
# results/*_router_v1_dev_final.md and DECISIONS.md D-021). Self-handled accuracy peaks
# here (96.8%) before the queue rate starts climbing for no further accuracy gain: the
# three dev tickets the router still gets wrong are all high-confidence (0.83-0.98), so
# no threshold below that would catch them -- raising it further only queues more
# tickets the model was already right about.
CONFIDENCE_THRESHOLD = 0.7

CLAIM_WORDING_CLARIFICATION = """

## One more boundary: "claim" and "complaint" wording

"I want to make a claim", "help me file a consumer complaint", "I'd like to leave a \
comment/review about your products" are a customer's own words for `feedback_and_complaint` \
(or, if there is a concrete operational ask underneath, that ask's category) -- they are \
not `out_of_scope` and not `legal_or_chargeback_threat`. Reserve `out_of_scope` for tickets \
with no genuine Hearth & Loom support content at all, and `legal_or_chargeback_threat` for \
an actual mention of solicitors, legal action, small claims, trading standards, an \
ombudsman, a chargeback or the press -- not for the word "claim" on its own.
"""


def router_system_prompt() -> str:
    """The baseline prompt plus the one boundary clarification brief v3 did not cover."""
    return system_prompt() + CLAIM_WORDING_CLARIFICATION


def enforce_policy(pred: dict) -> tuple[dict, list[str]]:
    """Brief invariants the model must never be allowed to violate. Same rules as
    `sweep.py` applies to the label set, applied here to a live prediction instead."""
    pred = dict(pred)
    reasons = list(pred["escalation_reasons"])
    notes = []

    if "product_safety" in reasons and pred["urgency"] != "high":
        pred["urgency"] = "high"
        notes.append("product_safety_forces_high")

    if "out_of_scope" in reasons and pred["intent"] != "out_of_scope":
        reasons = [r for r in reasons if r != "out_of_scope"]
        pred["escalation_reasons"] = reasons
        pred["escalate"] = bool(reasons)
        notes.append("out_of_scope_reason_dropped")

    return pred, notes


def route(pred: dict, threshold: float = CONFIDENCE_THRESHOLD) -> tuple[dict, bool, list[str]]:
    """Apply the policy layer, then decide whether a human sees this ticket at all.

    `sent_to_human` is the router's own decision, not a brief escalation reason: it is
    true whenever `escalate` is true OR the model's own confidence falls below `threshold`.
    Brief §5 leaves this policy for a later step; this is that step.
    """
    pred, notes = enforce_policy(pred)
    sent_to_human = bool(pred["escalate"]) or pred["confidence"] < threshold
    if sent_to_human and not pred["escalate"]:
        notes.append("low_confidence")
    return pred, sent_to_human, notes
