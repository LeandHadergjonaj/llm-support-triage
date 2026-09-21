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
from triage.evaluate import load_split, markdown_summary
from triage.export_review import select
from triage.labeler import BRIEF_PATH, labeler_json_schema
from triage.llm import DEFAULT_BUDGET_USD, DEFAULT_MODEL, PRICING_PER_MTOK, Budget, Usage
from triage.metrics import (
    label_error_rate,
    majority_class_baseline,
    score,
    score_escalation,
    score_slices,
    wilson_interval,
)
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


@pytest.mark.parametrize("schema", [prediction_json_schema(), labeler_json_schema()])
def test_wire_schemas_meet_openai_strict_mode_rules(schema):
    """Strict mode requires every property in `required` and additionalProperties false
    on every object, and rejects keywords outside its supported subset."""
    unsupported = {"minimum", "maximum", "minLength", "maxLength", "pattern", "format",
                   "minItems", "maxItems", "default", "oneOf", "allOf"}

    def walk(node: dict, path: str = "$") -> None:
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False, path
            assert set(node.get("required", [])) == set(node.get("properties", {})), path
            for key, child in node.get("properties", {}).items():
                walk(child, f"{path}.{key}")
        if node.get("type") == "array":
            walk(node["items"], f"{path}[]")
        assert not (unsupported & set(node)), f"{path}: {unsupported & set(node)}"

    walk(schema)


def test_confidence_range_is_still_enforced_client_side():
    """The 0-1 bound was removed from the wire schema, so Prediction must hold it."""
    with pytest.raises(ValidationError):
        Prediction(
            intent="order_management",
            urgency="low",
            escalate=False,
            confidence=1.5,
            rationale="x",
        )


def test_default_model_is_priced():
    assert DEFAULT_MODEL in PRICING_PER_MTOK, (
        f"{DEFAULT_MODEL} has no pricing, so cost reporting would silently be NaN"
    )


def test_cached_tokens_are_treated_as_a_subset_of_input_tokens():
    """OpenAI reports cached and cache-write tokens inside input_tokens, not on top of
    it. Getting this wrong inflates reported cost."""
    model = "gpt-6-astra"
    in_rate, cached_rate, _out_rate = PRICING_PER_MTOK[model]

    all_uncached = Usage(input_tokens=1000, output_tokens=0, calls=1)
    all_cached = Usage(input_tokens=1000, cached_tokens=1000, output_tokens=0, calls=1)

    assert all_uncached.cost_usd(model) == pytest.approx(1000 * in_rate / 1e6)
    assert all_cached.cost_usd(model) == pytest.approx(1000 * cached_rate / 1e6)
    # A fully cached prompt must be cheaper, not more expensive.
    assert all_cached.cost_usd(model) < all_uncached.cost_usd(model)


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
            # A reviewed ticket may carry `second_opinion` on any field the review
            # changed; everything else keeps the provenance it was built with.
            drafted = "bitext_mapped" if raw["source"] == "bitext" else "model_drafted"
            assert raw["label_provenance"]["intent"] in (drafted, "second_opinion")
            if raw["label_provenance"]["intent"] == "second_opinion":
                assert raw["reviewed"], ticket.id
            # No ticket may claim a person checked it. `human_agent_request` is a real
            # category, so this bans the misleading phrasings, not the word.
            blob = json.dumps(raw).lower()
            for banned in ("human_reviewed", "human review", "hand-labelled",
                           "hand labelled", "hand-labeled", "reviewed by a human"):
                assert banned not in blob, f"{ticket.id} claims {banned!r}"
            if raw["reviewed"]:
                assert raw["reviewed_by"], ticket.id


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


# --- The smoke-test set must never be mistaken for the eval set -------------


def _ticket(**overrides) -> str:
    """A minimal valid ticket line, as it would appear in a .jsonl split."""
    base = {
        "id": "hl-0001",
        "text": "where is my order",
        "source": "bitext",
        "hard_case": False,
        "hard_case_kind": None,
        "labels": {
            "intent": "delivery_and_shipping",
            "urgency": "normal",
            "escalate": False,
            "escalation_reasons": [],
        },
        "label_provenance": {
            "intent": "bitext_mapped",
            "urgency": "model_drafted",
            "escalate": "model_drafted",
        },
    }
    return json.dumps(base | overrides)


def test_smoke_tickets_are_refused_as_a_baseline(tmp_path):
    """A cheap throwaway set scored as `make eval` would file fake baseline numbers."""
    (tmp_path / "dev.jsonl").write_text(
        _ticket(smoke_test=True, labeler={"model": "gpt-5.6-luna", "effort": "none"}) + "\n"
    )
    with pytest.raises(SystemExit, match="smoke-test tickets"):
        load_split("dev", tmp_path, smoke=False)


def test_real_tickets_are_refused_as_a_smoke_run(tmp_path):
    (tmp_path / "dev.jsonl").write_text(_ticket() + "\n")
    with pytest.raises(SystemExit, match="no smoke-test tickets"):
        load_split("dev", tmp_path, smoke=True)
    assert len(load_split("dev", tmp_path, smoke=False)) == 1


def test_tickets_default_to_not_being_smoke_tests():
    assert Ticket.model_validate_json(_ticket()).smoke_test is False


# --- Spend cap (rule 8) -----------------------------------------------------


def test_budget_trips_once_the_cap_is_reached():
    budget = Budget(limit_usd=0.01, model=DEFAULT_MODEL)
    assert not budget.stop_now()
    # One call well under the cap leaves the budget open.
    budget.add(Usage(input_tokens=100, output_tokens=10, calls=1))
    assert not budget.stop_now()
    # A call that takes it over closes it.
    budget.add(Usage(input_tokens=0, output_tokens=1_000_000, calls=1))
    assert budget.stop_now()
    assert budget.spent_usd >= 0.01


def test_budget_default_is_the_documented_two_dollars():
    assert DEFAULT_BUDGET_USD == 2.00


def _fake_record(same_model: bool) -> dict:
    """A run record built by the real scoring code, so this fixture cannot drift."""
    rows = [
        {
            "id": f"hl-{i:04d}",
            "text": "t",
            "hard_case": i == 0,
            "hard_case_kind": "safety" if i == 0 else None,
            "reviewed": False,
            "gold": {"intent": "product_issue", "urgency": "low" if i else "high",
                     "escalate": i == 0,
                     "escalation_reasons": ["product_safety"] if i == 0 else []},
            "pred": {"intent": "product_issue", "urgency": "low" if i else "high",
                     "escalate": i == 0,
                     "escalation_reasons": ["product_safety"] if i == 0 else [],
                     "confidence": 0.9, "rationale": "r"},
        }
        for i in range(4)
    ]
    return {
        "run": {"split": "dev", "prompt_version": "baseline_v1", "model": "m",
                "effort": "high", "workers": 8, "started_at": "now", "tag": None},
        "label_quality": {"reviewed": 0, "total": len(rows), "smoke_test": False,
                          "labelers": ["m (effort high)"],
                          "scored_against_own_labels": same_model},
        "usage": {"total_cost_usd": 0.1, "calls": len(rows), "cost_per_ticket_usd": 0.025,
                  "latency_mean_s": 1.0, "latency_p50_s": 1.0, "latency_p95_s": 1.0,
                  "cached_tokens": 0, "cache_write_tokens": 0, "reasoning_tokens": 0},
        "escalation_reconciliation": {
            "eval_set": {"tickets": 4, "escalations": 1},
            "by_split": {"dev": {"tickets": 4, "escalations": 1}},
            "this_run": {"split": "dev", "tickets_scored": 4,
                         "escalations_in_reference": 1, "of_which_caught": 1,
                         "of_which_missed": 0, "predicted_but_not_in_reference": 0},
            "checks": {"ok": True},
        },
        "scores": score_slices(rows),
    }


def test_same_model_scoring_is_flagged_in_the_summary():
    """The caveat has to be impossible to miss when a model marks its own work."""
    summary = markdown_summary(_fake_record(same_model=True))
    assert "self-agreement, not accuracy" in summary
    assert "drafted the reference labels it is being scored against here" in summary
    # It must come before the numbers, not in a footnote.
    assert summary.index("self-agreement") < summary.index("## Headline")
    assert "self-agreement, not accuracy" not in markdown_summary(_fake_record(False))


def test_summary_shows_urgency_per_class_and_the_majority_class_comparison():
    summary = markdown_summary(_fake_record(same_model=True))
    assert "## Urgency" in summary
    assert "Always predict most common class" in summary
    assert "Macro recall" in summary
    for urgency in ("low", "high"):
        assert f"| `{urgency}` |" in summary


def test_summary_reconciles_escalations_with_the_label_set():
    summary = markdown_summary(_fake_record(same_model=True))
    assert "Reconciliation with the label set" in summary
    assert "1 = 1 + 0" in summary  # reference = caught + missed


def test_majority_class_baseline_beats_nothing_on_a_skewed_set():
    pairs = [("low", "low")] * 90 + [("high", "low")] * 10
    maj = majority_class_baseline(pairs)
    assert maj["most_common_class"] == "low"
    assert maj["baseline_accuracy"] == 0.9
    # A model that only ever says "low" matches the constant predictor exactly, and
    # macro recall is what exposes that.
    assert maj["model_accuracy"] == maj["baseline_accuracy"]
    assert maj["accuracy_gain_pp"] == 0.0
    assert maj["model_macro_recall"] == maj["baseline_macro_recall"] == 0.5


def test_dev_and_test_escalations_sum_to_the_label_set():
    """The 17 + 12 = 29 check, asserted rather than eyeballed."""
    splits = {}
    for name in ("dev", "test"):
        path = REPO / "data" / "eval" / f"{name}.jsonl"
        if not path.exists():
            pytest.skip("eval set not built")
        rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        splits[name] = rows
    ids = [r["id"] for rows in splits.values() for r in rows]
    assert len(ids) == len(set(ids)), "a ticket appears in both splits"
    total_escalations = sum(r["labels"]["escalate"] for rows in splits.values() for r in rows)
    per_split = {k: sum(r["labels"]["escalate"] for r in v) for k, v in splits.items()}
    assert sum(per_split.values()) == total_escalations


# --- Label error rate from the random block --------------------------------


def test_wilson_interval_stays_inside_zero_to_one():
    """The reason for Wilson over the textbook normal approximation."""
    low, high = wilson_interval(0, 30)
    assert low == 0.0 and 0.0 < high < 0.25
    low, high = wilson_interval(30, 30)
    assert high == 1.0 and 0.75 < low < 1.0
    # Normal approximation would put the lower bound below zero at 0/30; Wilson does not.
    assert wilson_interval(1, 20)[0] >= 0.0


def test_wilson_interval_narrows_as_the_sample_grows():
    """30 random tickets is meaningfully tighter than 15 -- the whole point of raising it."""
    def width(k, n):
        low, high = wilson_interval(k, n)
        return high - low
    assert width(2, 15) > width(4, 30) > width(8, 60)


def _reviewed(ticket_id, in_block, corrected):
    return {"id": ticket_id, "reviewed": True, "review_corrected": corrected,
            "review_selection": {"reason": "r", "in_random_block": in_block}}


def test_label_error_rate_keeps_the_random_block_separate():
    tickets = (
        [_reviewed(f"r{i}", True, i < 4) for i in range(30)]
        + [_reviewed(f"t{i}", False, i < 9) for i in range(25)]
        + [{"id": "unreviewed", "reviewed": False}]
    )
    rates = label_error_rate(tickets)
    assert rates["random_block"] == {
        "reviewed": 30, "corrected": 4, "error_rate": 0.1333,
        "ci95": list(wilson_interval(4, 30)), "ci95_method": "Wilson score",
    }
    assert rates["targeted_picks"]["reviewed"] == 25
    assert rates["targeted_picks"]["error_rate"] == 0.36
    # The biased rate must never be silently folded into the estimate.
    assert rates["random_block"]["error_rate"] < rates["targeted_picks"]["error_rate"]


def test_label_error_rate_is_none_before_anyone_reviews():
    rates = label_error_rate([{"id": "a", "reviewed": False}])
    assert rates["random_block"]["error_rate"] is None
    assert rates["random_block"]["reviewed"] == 0


def test_review_sample_growth_never_drops_a_row():
    """Raising the random block must top up, not redraw -- reviewers keep their file."""
    rows = [
        {"id": f"hl-{i:04d}", "labels": {"escalate": i % 9 == 0, "escalation_reasons": []},
         "hard_case": i % 7 == 0, "drafter_uncertain": i % 5 == 0,
         "intent_disagreement": i % 11 == 0}
        for i in range(252)
    ]
    first = select(rows, n=42, seed=7, random_controls=15)
    pinned = {r["id"]: (why, in_block) for r, why, in_block in first}
    second = select(rows, n=57, seed=7, random_controls=30, pinned=pinned)

    assert {r["id"] for r, _, _ in first} <= {r["id"] for r, _, _ in second}
    assert sum(1 for _, _, b in first if b) == 15
    assert sum(1 for _, _, b in second if b) == 30
    # Everything in the old block is still in the new one.
    assert ({r["id"] for r, _, b in first if b}) <= ({r["id"] for r, _, b in second if b})
    # Reasons are stable for rows carried over.
    before = {r["id"]: why for r, why, _ in first}
    after = {r["id"]: why for r, why, _ in second}
    assert all(after[i] == why for i, why in before.items())


def test_rescore_does_not_log_spend(tmp_path, monkeypatch):
    """Replaying saved predictions costs nothing, so it must not move the ledger.

    Logging the replayed run's usage again would double-count it against the $2 cap and
    make the ledger describe money that was never spent.
    """
    from triage import llm

    ledger = tmp_path / "spend_log.jsonl"
    monkeypatch.setattr(llm, "SPEND_LOG", ledger)
    llm.record_spend("real_run", DEFAULT_MODEL, Usage(input_tokens=1000, calls=1))
    after_real = llm.total_spend()
    assert after_real > 0
    # A rescore path must not call record_spend at all; the total stays put.
    assert llm.total_spend() == after_real
    assert ledger.read_text().count("\n") == 1


# --- The brief is versioned, and the sweep applies it ----------------------


def test_brief_declares_a_version_and_a_changelog():
    """A score is only interpretable next to the brief version that produced it."""
    from triage.taxonomy import brief_version

    version = brief_version()
    assert version.startswith("v")
    brief = BRIEF_PATH.read_text()
    assert "## 7. Changelog" in brief
    assert f"### {version} " in brief, f"the changelog has no entry for {version}"


def test_baseline_prompt_carries_the_v2_clarifications():
    """The baseline must not be marked against policy it was never given.

    Each assertion is one brief v2 change. They are checked on the prompt rather than
    trusted to a code review, because the whole justification for re-running the
    baseline at v2 is that the prompt states the same rules the labels were made under.
    """
    prompt = system_prompt().lower()
    assert "before dispatch" in prompt  # change 4: the pre-dispatch window
    assert "adding items is the exception" in prompt  # change 4: the carve-out
    assert "not the vocabulary" in prompt  # change 3: unfamiliar names
    assert "can no longer pay" in prompt  # change 2
    assert "cannot be undone" in prompt  # change 1: multi-ask tie-break
    assert "`product_safety` always implies `high`" in prompt  # change 5


def test_baseline_prompt_carries_the_v3_clarification():
    """Brief v3 (D-018/D-020): account admin blocking nothing paid-for is `low`."""
    prompt = system_prompt().lower()
    assert "password or pin reset" in prompt
    assert "blocked on something owed or paid for" in prompt


def test_sweep_rules_do_what_the_brief_says():
    from triage.sweep import out_of_scope_contradiction, pre_dispatch_window

    def ticket(**kw):
        base = {
            "id": "hl-0001",
            "text": "cancel order 51986",
            "bitext_intent": "cancel_order",
            "labels": {
                "intent": "order_management",
                "urgency": "normal",
                "escalate": False,
                "escalation_reasons": [],
            },
        }
        base["labels"].update(kw.pop("labels", {}))
        return base | kw

    # Change 4: a cancellation on a live order is high...
    assert pre_dispatch_window(ticket())[0] == {"urgency": "high"}
    # ...but an addition is the exception...
    assert pre_dispatch_window(ticket(text="how do I add items to order 52020?")) is None
    # ...and an ask that presupposes no live order is untouched.
    assert pre_dispatch_window(ticket(text="how do I update my address")) is None
    assert pre_dispatch_window(ticket(bitext_intent="place_order")) is None
    assert pre_dispatch_window(ticket(labels={"urgency": "high"})) is None

    # Change 3: the out_of_scope reason needs the matching intent.
    contradictory = ticket(
        labels={"escalate": True, "escalation_reasons": ["out_of_scope"]},
        bitext_intent="check_invoice",
    )
    assert out_of_scope_contradiction(contradictory)[0] == {
        "escalate": False,
        "escalation_reasons": [],
    }
    genuine = ticket(
        labels={
            "intent": "out_of_scope",
            "escalate": True,
            "escalation_reasons": ["out_of_scope"],
        }
    )
    assert out_of_scope_contradiction(genuine) is None
    # Another reason alongside it survives; only the contradictory one is dropped.
    both = ticket(
        labels={"escalate": True, "escalation_reasons": ["out_of_scope", "product_safety"]}
    )
    assert out_of_scope_contradiction(both)[0] == {
        "escalate": True,
        "escalation_reasons": ["product_safety"],
    }


def test_account_admin_sweep_rule_does_what_brief_v3_says():
    from triage.sweep import account_admin_no_live_order

    def ticket(**kw):
        base = {
            "id": "hl-0001",
            "text": "I forgot my password and can't log in",
            "bitext_intent": "recover_password",
            "labels": {"urgency": "normal"},
        }
        return base | kw

    # A recognised admin intent at `normal`, no order named -> down to `low`.
    assert account_admin_no_live_order(ticket())[0] == {"urgency": "low"}
    # Not one of the four intents this rule is scoped to -> untouched.
    assert account_admin_no_live_order(ticket(bitext_intent="track_order")) is None
    # Already `low` -> nothing to change.
    assert account_admin_no_live_order(ticket(labels={"urgency": "low"})) is None
    # Names a live order -> pre_dispatch_window's territory, not this rule's.
    assert account_admin_no_live_order(ticket(text="update the address on order 51986")) is None


# --- Review rounds sample different populations and must not be pooled -----


def _round_ticket(ticket_id, round_no, corrected):
    return {
        "id": ticket_id,
        "reviewed": True,
        "review_corrected": corrected,
        "review_selection": {"reason": "r", "in_random_block": True, "round": round_no},
    }


def test_review_rounds_are_reported_separately_and_never_pooled():
    """Round 1 sampled the whole set before correction; round 2 the unchecked
    remainder afterwards. Pooling them would report a rate for a set that no longer
    exists, and averaging them would be worse."""
    tickets = (
        [_round_ticket(f"a{i}", 1, i < 6) for i in range(30)]
        + [_round_ticket(f"b{i}", 2, i < 1) for i in range(30)]
    )
    rates = label_error_rate(tickets)
    assert rates["by_round"]["1"]["error_rate"] == 0.2
    assert rates["by_round"]["2"]["error_rate"] == round(1 / 30, 4)
    # The headline is the latest round alone, not the 7/60 pooled rate.
    assert rates["random_block_round"] == 2
    assert rates["random_block"]["reviewed"] == 30
    assert rates["random_block"]["corrected"] == 1


def test_a_block_with_no_round_recorded_counts_as_round_one():
    """Tickets written before rounds existed must not silently form a round of their own."""
    rates = label_error_rate([_reviewed("a", True, True), _reviewed("b", True, False)])
    assert rates["random_block_round"] == 1
    assert rates["by_round"]["1"]["reviewed"] == 2


@pytest.mark.skipif(
    not (REPO / "data" / "eval" / "dev.jsonl").exists(), reason="eval set not built yet"
)
def test_the_sweep_never_claims_to_have_checked_a_ticket():
    """The sweep applies a rule without re-reading anything. Counting a swept ticket as
    reviewed would report 13 tickets as checked when none of them were."""
    swept = [
        json.loads(line)
        for split in ("dev", "test")
        for line in (REPO / "data" / "eval" / f"{split}.jsonl").read_text().splitlines()
        if line.strip() and json.loads(line).get("sweep")
    ]
    assert swept, "no swept tickets to check"
    for ticket in swept:
        # A swept ticket may also have been reviewed, but only by a review round that
        # put it in a CSV -- never by the sweep itself.
        if ticket["reviewed"]:
            assert ticket["review_selection"], ticket["id"]
        assert ticket["sweep"]["by"] and not ticket["sweep"].get("is_a_human_pass")
        for field, value in ticket["sweep"]["was"].items():
            assert ticket["labels"][field] != value or field == "escalation_reasons"


@pytest.mark.skipif(
    not (REPO / "data" / "eval" / "dev.jsonl").exists(), reason="eval set not built yet"
)
def test_the_label_set_obeys_the_v2_rules_it_was_swept_for():
    """The brief is the source of truth; these are the two rules it gained at v2."""
    for split in ("dev", "test"):
        for line in (REPO / "data" / "eval" / f"{split}.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            t = json.loads(line)
            labels = t["labels"]
            if "out_of_scope" in labels["escalation_reasons"]:
                assert labels["intent"] == "out_of_scope", t["id"]
            if "product_safety" in labels["escalation_reasons"]:
                assert labels["urgency"] == "high", t["id"]
