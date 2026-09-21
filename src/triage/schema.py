"""Pydantic models for tickets, labels and baseline predictions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from triage.taxonomy import ESCALATION_REASONS, INTENTS, URGENCIES

Intent = Literal[tuple(INTENTS)]  # type: ignore[valid-type]
Urgency = Literal[tuple(URGENCIES)]  # type: ignore[valid-type]
EscalationReason = Literal[tuple(ESCALATION_REASONS)]  # type: ignore[valid-type]


class Labels(BaseModel):
    """The reference labels a prediction is scored against."""

    intent: Intent
    urgency: Urgency
    escalate: bool
    escalation_reasons: list[EscalationReason] = Field(default_factory=list)


class LabelProvenance(BaseModel):
    """Where each label came from.

    `second_opinion` means the label was corrected during the review pass by a model of a
    different family from the drafter. `rule_sweep` means it was corrected mechanically,
    by a rule derived from a clarification to the client brief, without anyone re-reading
    the ticket from scratch. No label in this project is written by a person: nothing here
    is hand-labelled, and neither value may be read as if it were.
    """

    intent: Literal["bitext_mapped", "model_drafted", "second_opinion", "rule_sweep"]
    urgency: Literal["model_drafted", "second_opinion", "rule_sweep"]
    escalate: Literal["model_drafted", "second_opinion", "rule_sweep"]


class Labeler(BaseModel):
    """Which model drafted the labels on this ticket, and how hard it thought.

    Recorded per ticket so a cheap throwaway run can never be mistaken for the real
    eval set just by looking at the file.
    """

    model: str
    effort: str


class ReviewSelection(BaseModel):
    """Why a ticket was put in front of a human, recorded when the review is imported.

    `in_random_block` is the one that matters statistically: those tickets are a uniform
    draw over the population being sampled, so their error rate estimates it. The
    targeted picks were chosen for looking wrong and cannot.

    `round` says which review pass drew this ticket, and the rounds are NOT poolable.
    Round 1 sampled all 252 tickets before any correction; round 2 sampled only the
    tickets no round had reviewed, after the brief v2 rule sweep. They measure different
    populations at different times, so their rates are reported side by side and never
    averaged.
    """

    reason: str
    in_random_block: bool = False
    round: int = 1


class Sweep(BaseModel):
    """A label changed by the rule sweep rather than by re-reading the ticket.

    The sweep applies a named rule from a specific version of the client brief to every
    ticket that matches it. That is a consistency mechanism, not a check: it can only
    find the errors the rule describes, it cannot notice anything else that is wrong, and
    it is run by a model, not by a person. A swept ticket is therefore NOT `reviewed`,
    and the label error rate must not count it as checked.
    """

    pattern: str
    brief_version: str
    brief_change: str
    by: str
    note: str
    was: dict


class Ticket(BaseModel):
    """One evaluation ticket."""

    id: str
    text: str
    source: Literal["bitext", "authored_hard_case"]
    hard_case: bool
    hard_case_kind: str | None = None
    labels: Labels
    label_provenance: LabelProvenance
    labeler: Labeler | None = None
    # True on throwaway pipeline-check sets built by `--smoke`. Such a set is never a
    # valid eval set: it is tiny and its labels come from whatever cheap model was to
    # hand. `evaluate.py` refuses to score one as a baseline.
    smoke_test: bool = False
    # True once the ticket has been through the second-opinion review pass. That pass is
    # run by a model of a different family from the drafter, NOT by a person.
    reviewed: bool = False
    reviewed_by: str | None = None
    review_selection: ReviewSelection | None = None
    review_corrected: bool | None = None
    review_note: str | None = None
    # Set when the rule sweep changed this ticket's labels. Independent of `reviewed`:
    # a sweep applies a rule, a review re-reads the ticket.
    sweep: Sweep | None = None
    # Provenance back to the upstream row, null for authored cases.
    bitext_intent: str | None = None
    bitext_flags: str | None = None


class Prediction(BaseModel):
    """What the baseline returns for one ticket."""

    intent: Intent
    urgency: Urgency
    escalate: bool
    escalation_reasons: list[EscalationReason] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


def prediction_json_schema() -> dict:
    """JSON Schema handed to the API via `output_config.format`.

    Built from taxonomy.py rather than from `Prediction.model_json_schema()`: strict
    schemas need every property required and `additionalProperties: false` throughout,
    which is fiddly to retrofit onto Pydantic's output. Both this and `Prediction` read
    the same enums, so they cannot drift on the values that matter.
    """
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
            # No `minimum`/`maximum`: OpenAI's strict mode accepts only a subset of
            # JSON Schema and numeric bounds are not reliably among it. The 0-1 range is
            # still enforced, by the `Prediction` model on the way back in.
            "confidence": {"type": "number"},
            "rationale": {"type": "string"},
        },
        "required": [
            "intent",
            "urgency",
            "escalate",
            "escalation_reasons",
            "confidence",
            "rationale",
        ],
        "additionalProperties": False,
    }
