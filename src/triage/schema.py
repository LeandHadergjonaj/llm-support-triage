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
    """Where each label came from. Nothing here is hand-labelled unless `human_reviewed`."""

    intent: Literal["bitext_mapped", "model_drafted"]
    urgency: Literal["model_drafted"]
    escalate: Literal["model_drafted"]


class Ticket(BaseModel):
    """One evaluation ticket."""

    id: str
    text: str
    source: Literal["bitext", "authored_hard_case"]
    hard_case: bool
    hard_case_kind: str | None = None
    labels: Labels
    label_provenance: LabelProvenance
    human_reviewed: bool = False
    review_note: str | None = None
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
