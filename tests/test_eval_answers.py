"""No API key needed: exercises the scoring/aggregation logic with a stubbed judge."""

from __future__ import annotations

from triage.eval_answers import aggregate, load_answer_tickets, score_one
from triage.llm import Usage


def fake_judge_all_correct(ticket: dict, answer_text: str) -> tuple[dict, Usage]:
    verdict = {
        "contains_all_required": [True] * len(ticket["expected_must_contain"]),
        "avoids_all_forbidden": [True] * len(ticket["expected_must_not_contain"]),
        "notes": "stub",
    }
    return verdict, Usage()


def fake_judge_misses_one_fact(ticket: dict, answer_text: str) -> tuple[dict, Usage]:
    facts = [True] * len(ticket["expected_must_contain"])
    if facts:
        facts[0] = False
    verdict = {
        "contains_all_required": facts,
        "avoids_all_forbidden": [True] * len(ticket["expected_must_not_contain"]),
        "notes": "stub",
    }
    return verdict, Usage()


def test_answer_eval_files_load_and_have_required_fields():
    for split in ("dev", "test"):
        tickets = load_answer_tickets(split)
        assert tickets
        for t in tickets:
            assert t["must_handle"] in ("self", "human")
            assert isinstance(t["expected_must_contain"], list) and t["expected_must_contain"]
            assert isinstance(t["expected_must_not_contain"], list)


def test_missing_candidate_scores_as_routing_wrong_not_a_crash():
    ticket = {"id": "x", "must_handle": "self", "expected_must_contain": ["a"], "expected_must_not_contain": []}
    score, usage = score_one(ticket, None, fake_judge_all_correct)
    assert score.routing_correct is False
    assert score.handled_by == "MISSING"
    assert usage.calls == 0


def test_wrong_routing_is_not_content_graded():
    ticket = {"id": "x", "must_handle": "human", "expected_must_contain": ["a"], "expected_must_not_contain": ["b"]}
    candidate = {"handled_by": "self", "answer_text": "here's how to fix it yourself"}
    score, usage = score_one(ticket, candidate, fake_judge_all_correct)
    assert score.routing_correct is False
    assert score.facts_covered is None
    assert usage.calls == 0


def test_correct_routing_gets_content_graded():
    ticket = {"id": "x", "must_handle": "self", "expected_must_contain": ["a", "b"], "expected_must_not_contain": ["c"]}
    candidate = {"handled_by": "self", "answer_text": "an answer"}
    score, _ = score_one(ticket, candidate, fake_judge_all_correct)
    assert score.routing_correct is True
    assert score.facts_covered == [True, True]
    assert score.forbidden_avoided == [True]


def test_aggregate_reports_routing_and_content_rates():
    tickets = [
        {"id": "a", "must_handle": "self", "expected_must_contain": ["f1", "f2"], "expected_must_not_contain": []},
        {"id": "b", "must_handle": "human", "expected_must_contain": ["f1"], "expected_must_not_contain": ["g1"]},
    ]
    candidates = {
        "a": {"handled_by": "self", "answer_text": "..."},
        "b": {"handled_by": "human", "answer_text": "..."},
    }
    scores_usage = [
        score_one(tickets[0], candidates["a"], fake_judge_misses_one_fact),
        score_one(tickets[1], candidates["b"], fake_judge_all_correct),
    ]
    scores = [s for s, _ in scores_usage]
    report = aggregate(scores)

    assert report["tickets"] == 2
    assert report["routing_accuracy"]["rate"] == 1.0
    # 3 required facts total (2 + 1), one missed -> 2/3
    assert report["required_fact_coverage"]["rate"] == round(2 / 3, 4)
    assert report["forbidden_avoidance"]["rate"] == 1.0
    # ticket "a" missed a fact so is not fully correct; "b" is
    assert report["fully_correct_of_graded"]["rate"] == 0.5


def test_missing_candidates_are_named_for_debugging():
    tickets = [{"id": "z", "must_handle": "self", "expected_must_contain": ["a"], "expected_must_not_contain": []}]
    score, _ = score_one(tickets[0], None, fake_judge_all_correct)
    report = aggregate([score])
    assert report["missing_candidates"] == ["z"]
