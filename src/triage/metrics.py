"""Scoring. Kept separate from the run loop so results can be re-scored without re-paying."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from itertools import pairwise

from triage.taxonomy import ESCALATION_REASONS, INTENTS, URGENCIES


def _accuracy(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    return round(sum(1 for gold, pred in pairs if gold == pred) / len(pairs), 4)


def _per_class(pairs: list[tuple[str, str]], classes: list[str]) -> dict:
    """Per-class support, recall and precision. Recall is the interesting one here:
    it says which categories the system loses."""
    out = {}
    for cls in classes:
        support = sum(1 for gold, _ in pairs if gold == cls)
        predicted = sum(1 for _, pred in pairs if pred == cls)
        hits = sum(1 for gold, pred in pairs if gold == cls and pred == cls)
        if support == 0 and predicted == 0:
            continue
        out[cls] = {
            "support": support,
            "predicted": predicted,
            "recall": round(hits / support, 4) if support else None,
            "precision": round(hits / predicted, 4) if predicted else None,
        }
    return out


def _confusions(pairs: list[tuple[str, str]], top: int = 10) -> list[dict]:
    counts = Counter((gold, pred) for gold, pred in pairs if gold != pred)
    return [
        {"gold": gold, "predicted": pred, "n": n}
        for (gold, pred), n in counts.most_common(top)
    ]


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% confidence interval for a proportion, Wilson score method.

    Wilson rather than the textbook p +/- z*sqrt(p(1-p)/n): the normal approximation is
    poor at the sample sizes and small proportions this project actually has, and it
    happily returns a lower bound below zero. Wilson stays inside [0, 1] and holds its
    coverage at n in the tens, which is the regime the review sample lives in.
    """
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def label_error_rate(tickets: list[dict]) -> dict:
    """How often the drafted labels were wrong, measured on reviewed tickets.

    Reported separately for the random block and the targeted picks, because only the
    former estimates anything about a population. The targeted rate is expected to be
    higher and is not a population estimate: those tickets were chosen for being
    suspicious. Quoting them together, or averaging them, would be the mistake.

    Blocks from different review rounds are also kept apart, for the same reason in a
    different guise: round 1 drew from all 252 tickets before any correction, round 2
    from the never-reviewed remainder after the rule sweep. `random_block` reports the
    latest round -- the only one that describes the set as it stands -- and `by_round`
    keeps the history.
    """

    def measure(subset: list[dict]) -> dict:
        reviewed = [t for t in subset if t.get("reviewed")]
        if not reviewed:
            return {"reviewed": 0, "corrected": None, "error_rate": None, "ci95": None}
        corrected = sum(1 for t in reviewed if t.get("review_corrected"))
        low, high = wilson_interval(corrected, len(reviewed))
        return {
            "reviewed": len(reviewed),
            "corrected": corrected,
            "error_rate": round(corrected / len(reviewed), 4),
            "ci95": [low, high],
            "ci95_method": "Wilson score",
        }

    def selection(t: dict) -> dict:
        return t.get("review_selection") or {}

    def in_block(t: dict) -> bool:
        return bool(selection(t).get("in_random_block"))

    def round_of(t: dict) -> int:
        return int(selection(t).get("round", 1))

    blocks = [t for t in tickets if in_block(t)]
    rounds = sorted({round_of(t) for t in blocks})
    by_round = {
        str(n): measure([t for t in blocks if round_of(t) == n]) | {
            "population": (
                "all tickets, before any correction"
                if n == 1
                else "tickets not reviewed in an earlier round, after the rule sweep"
            )
        }
        for n in rounds
    }
    # The headline is the LATEST round: it is the only one that describes the label set
    # as it stands now. Earlier rounds measured a population that has since been
    # corrected, so pooling them would report an error rate for a set that no longer
    # exists -- and the rounds sample different populations anyway.
    latest = rounds[-1] if rounds else None

    return {
        "random_block": measure([t for t in blocks if latest is None or round_of(t) == latest]),
        "random_block_round": latest,
        "by_round": by_round,
        "targeted_picks": measure(
            [t for t in tickets if t.get("reviewed") and not in_block(t)]
        ),
        "note": (
            "Only a random block estimates the label error rate of a population. The "
            "targeted picks were chosen for being suspicious, so their rate is biased "
            "upwards by construction and is a diagnostic, not a population estimate. "
            "Rounds sample different populations at different times and are never "
            "pooled or averaged: `random_block` is the latest round alone."
        ),
    }


def _macro_recall(pairs: list[tuple[str, str]]) -> float | None:
    """Mean per-class recall over the classes that actually occur in the reference.

    The metric to read when the classes are skewed: plain accuracy on a set that is 69%
    one class is mostly a report on that class.
    """
    classes = {gold for gold, _ in pairs}
    if not classes:
        return None
    recalls = []
    for cls in classes:
        support = sum(1 for gold, _ in pairs if gold == cls)
        hits = sum(1 for gold, pred in pairs if gold == cls and pred == cls)
        recalls.append(hits / support)
    return round(sum(recalls) / len(recalls), 4)


def majority_class_baseline(pairs: list[tuple[str, str]]) -> dict:
    """The model against a constant predictor that always says the commonest class.

    Worth stating explicitly wherever the reference distribution is lopsided: a good
    accuracy can be most of the way to free. The constant predictor scores its own class
    perfectly and every other class zero, so its macro recall is 1/k -- which is the
    number the model has to beat to be doing more than following the skew.
    """
    if not pairs:
        return {}
    counts = Counter(gold for gold, _ in pairs)
    cls, hits = counts.most_common(1)[0]
    baseline_acc = hits / len(pairs)
    model_acc = _accuracy(pairs)
    return {
        "most_common_class": cls,
        "its_share_of_the_reference": round(baseline_acc, 4),
        "baseline_accuracy": round(baseline_acc, 4),
        "model_accuracy": model_acc,
        "accuracy_gain_pp": round((model_acc - baseline_acc) * 100, 1),
        "baseline_macro_recall": round(1 / len(counts), 4),
        "model_macro_recall": _macro_recall(pairs),
    }


def score_escalation(rows: list[dict]) -> dict:
    """Escalation broken into the four outcomes the client cares about.

    `unnecessary` is a ticket the system sent to a human that did not need one -- wasted
    reviewer time. `missed` is a ticket that needed a human and did not get one -- the
    expensive kind of error.
    """
    correct = unnecessary = missed = correct_no = 0
    for row in rows:
        gold, pred = row["gold"]["escalate"], row["pred"]["escalate"]
        if gold and pred:
            correct += 1
        elif not gold and pred:
            unnecessary += 1
        elif gold and not pred:
            missed += 1
        else:
            correct_no += 1

    gold_pos = correct + missed
    pred_pos = correct + unnecessary
    precision = round(correct / pred_pos, 4) if pred_pos else None
    recall = round(correct / gold_pos, 4) if gold_pos else None

    # Reason-level agreement, counted only on tickets both sides escalated.
    both = [r for r in rows if r["gold"]["escalate"] and r["pred"]["escalate"]]
    exact_reasons = sum(
        1
        for r in both
        if set(r["gold"]["escalation_reasons"]) == set(r["pred"]["escalation_reasons"])
    )
    reason_counts: dict[str, dict[str, int]] = defaultdict(
        lambda: {"gold": 0, "predicted": 0, "both": 0}
    )
    for row in rows:
        gold_reasons = set(row["gold"]["escalation_reasons"])
        pred_reasons = set(row["pred"]["escalation_reasons"])
        for reason in ESCALATION_REASONS:
            if reason in gold_reasons:
                reason_counts[reason]["gold"] += 1
            if reason in pred_reasons:
                reason_counts[reason]["predicted"] += 1
            if reason in gold_reasons and reason in pred_reasons:
                reason_counts[reason]["both"] += 1

    return {
        "correct_escalations": correct,
        "unnecessary_escalations": unnecessary,
        "missed_escalations": missed,
        "correct_non_escalations": correct_no,
        "accuracy": round((correct + correct_no) / len(rows), 4) if rows else None,
        "precision": precision,
        "recall": recall,
        "gold_escalation_rate": round(gold_pos / len(rows), 4) if rows else None,
        "predicted_escalation_rate": round(pred_pos / len(rows), 4) if rows else None,
        "exact_reason_match_when_both_escalate": (
            f"{exact_reasons}/{len(both)}" if both else "0/0"
        ),
        "by_reason": {k: dict(v) for k, v in sorted(reason_counts.items())},
    }


def calibration(rows: list[dict], bins: tuple[float, ...] = (0.5, 0.7, 0.8, 0.9, 0.95)) -> list[dict]:
    """Does a confident prediction actually get all three labels right more often?"""
    edges = [0.0, *bins, 1.01]
    out = []
    for low, high in pairwise(edges):
        group = [r for r in rows if low <= r["pred"]["confidence"] < high]
        if not group:
            continue
        fully_right = sum(
            1
            for r in group
            if r["gold"]["intent"] == r["pred"]["intent"]
            and r["gold"]["urgency"] == r["pred"]["urgency"]
            and r["gold"]["escalate"] == r["pred"]["escalate"]
        )
        out.append(
            {
                "confidence_range": f"[{low:.2f}, {min(high, 1.0):.2f})",
                "n": len(group),
                "all_three_correct": round(fully_right / len(group), 4),
                "mean_confidence": round(
                    sum(r["pred"]["confidence"] for r in group) / len(group), 3
                ),
            }
        )
    return out


def score(rows: list[dict]) -> dict:
    """Score a list of {gold, pred, ...} rows."""
    intent_pairs = [(r["gold"]["intent"], r["pred"]["intent"]) for r in rows]
    urgency_pairs = [(r["gold"]["urgency"], r["pred"]["urgency"]) for r in rows]

    all_three = sum(
        1
        for r in rows
        if r["gold"]["intent"] == r["pred"]["intent"]
        and r["gold"]["urgency"] == r["pred"]["urgency"]
        and r["gold"]["escalate"] == r["pred"]["escalate"]
    )

    return {
        "n": len(rows),
        "intent_accuracy": _accuracy(intent_pairs),
        "urgency_accuracy": _accuracy(urgency_pairs),
        "all_three_correct": round(all_three / len(rows), 4) if rows else None,
        "escalation": score_escalation(rows),
        "intent_per_class": _per_class(intent_pairs, list(INTENTS)),
        "urgency_per_class": _per_class(urgency_pairs, list(URGENCIES)),
        "urgency_macro_recall": _macro_recall(urgency_pairs),
        "intent_macro_recall": _macro_recall(intent_pairs),
        "urgency_vs_majority_class": majority_class_baseline(urgency_pairs),
        "intent_vs_majority_class": majority_class_baseline(intent_pairs),
        "intent_confusions": _confusions(intent_pairs),
        "urgency_confusions": _confusions(urgency_pairs, top=6),
        "confidence_calibration": calibration(rows),
    }


def score_slices(rows: list[dict]) -> dict:
    """Headline plus the slices that matter: easy vs hard, and per hard-case kind."""
    out = {"overall": score(rows)}
    for name, subset in (
        ("bitext_only", [r for r in rows if not r["hard_case"]]),
        ("hard_cases_only", [r for r in rows if r["hard_case"]]),
    ):
        if subset:
            out[name] = score(subset)
    by_kind = defaultdict(list)
    for row in rows:
        if row["hard_case"]:
            by_kind[row["hard_case_kind"]].append(row)
    out["by_hard_case_kind"] = {
        kind: {
            "n": len(group),
            "intent_accuracy": _accuracy([(r["gold"]["intent"], r["pred"]["intent"]) for r in group]),
            "urgency_accuracy": _accuracy(
                [(r["gold"]["urgency"], r["pred"]["urgency"]) for r in group]
            ),
            "escalation_accuracy": score_escalation(group)["accuracy"],
        }
        for kind, group in sorted(by_kind.items())
    }
    return out
