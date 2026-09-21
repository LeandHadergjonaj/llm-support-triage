"""Checks that need no API key.

The one that earns its place is `test_brief_and_taxonomy_agree`: the brief is the source
of truth and taxonomy.py is a hand-maintained copy of it, so they can drift silently.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from triage.baseline import system_prompt
from triage.labeler import BRIEF_PATH
from triage.metrics import score, score_escalation
from triage.schema import Prediction, Ticket, prediction_json_schema
from triage.taxonomy import (
    BITEXT_INTENT_TO_CATEGORY,
    ESCALATION_REASONS,
    INTENTS,
    REFUND_THRESHOLD_GBP,
    URGENCIES,
)

REPO = Path(__file__).resolve().parents[1]


def test_brief_and_taxonomy_agree():
    brief = BRIEF_PATH.read_text()
    for name in list(INTENTS) + list(URGENCIES) + list(ESCALATION_REASONS):
        assert f"`{name}`" in brief, f"{name} is in taxonomy.py but not in the brief"
    assert f"£{REFUND_THRESHOLD_GBP}" in brief


def test_every_bitext_intent_maps_to_a_real_category():
    assert set(BITEXT_INTENT_TO_CATEGORY.values()) <= set(INTENTS)
    assert len(BITEXT_INTENT_TO_CATEGORY) == 27


def test_categories_without_upstream_source_are_the_expected_two():
    unmapped = set(INTENTS) - set(BITEXT_INTENT_TO_CATEGORY.values())
    assert unmapped == {"product_issue", "out_of_scope"}


def test_prediction_schema_is_strict():
    schema = prediction_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    assert schema["properties"]["intent"]["enum"] == list(INTENTS)


def test_prediction_rejects_labels_outside_the_taxonomy():
    with pytest.raises(ValidationError):
        Prediction(
            intent="not_a_category",
            urgency="low",
            escalate=False,
            confidence=0.5,
            rationale="x",
        )


def test_baseline_prompt_names_every_label():
    prompt = system_prompt()
    for name in list(INTENTS) + list(URGENCIES) + list(ESCALATION_REASONS):
        assert f"`{name}`" in prompt


def test_escalation_outcomes_are_counted_the_right_way_round():
    def row(gold: bool, pred: bool) -> dict:
        return {
            "gold": {"escalate": gold, "escalation_reasons": ["product_safety"] if gold else []},
            "pred": {"escalate": pred, "escalation_reasons": ["product_safety"] if pred else []},
        }

    result = score_escalation([row(True, True), row(False, True), row(True, False), row(False, False)])
    assert result["correct_escalations"] == 1
    assert result["unnecessary_escalations"] == 1  # escalated when it should not have
    assert result["missed_escalations"] == 1  # the expensive one
    assert result["correct_non_escalations"] == 1
    assert result["accuracy"] == 0.5


def test_score_runs_on_a_minimal_row():
    rows = [
        {
            "gold": {
                "intent": "order_management",
                "urgency": "low",
                "escalate": False,
                "escalation_reasons": [],
            },
            "pred": {
                "intent": "order_management",
                "urgency": "low",
                "escalate": False,
                "escalation_reasons": [],
                "confidence": 0.9,
                "rationale": "r",
            },
        }
    ]
    result = score(rows)
    assert result["intent_accuracy"] == 1.0
    assert result["all_three_correct"] == 1.0


@pytest.mark.skipif(
    not (REPO / "data" / "eval" / "dev.jsonl").exists(), reason="eval set not built yet"
)
def test_built_eval_set_validates_and_is_internally_consistent():
    for split in ("dev", "test"):
        path = REPO / "data" / "eval" / f"{split}.jsonl"
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            ticket = Ticket.model_validate_json(line)
            # An escalation with no reason, or a reason with no escalation, is a
            # contradiction the label set must not contain.
            assert bool(ticket.labels.escalation_reasons) == ticket.labels.escalate, ticket.id
            raw = json.loads(line)
            if raw["source"] == "bitext":
                assert raw["label_provenance"]["intent"] == "bitext_mapped"
            else:
                assert raw["label_provenance"]["intent"] == "model_drafted"


@pytest.mark.skipif(
    not (REPO / "data" / "eval" / "dev.jsonl").exists(), reason="eval set not built yet"
)
def test_dev_and_test_do_not_overlap():
    def ids(split: str) -> set[str]:
        path = REPO / "data" / "eval" / f"{split}.jsonl"
        return {json.loads(line)["id"] for line in path.read_text().splitlines() if line.strip()}

    dev, test = ids("dev"), ids("test")
    assert dev and test
    assert not (dev & test)
