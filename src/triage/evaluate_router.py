"""Run the router over a split, score it, and compare it against the baseline of record.

    .venv/bin/python -m triage.evaluate_router --split dev
    .venv/bin/python -m triage.evaluate_router --split dev --rescore results/<prior>.json --threshold 0.7

Same model and brief as `results/latest_<split>.json` -- the only difference is the
router's prompt clarification and its policy + confidence layer (`router.py`). Calls are
saved as RAW predictions, so `--threshold` can be re-tuned with `--rescore` and no further
API spend; that is how the confidence threshold was chosen on dev. See `DECISIONS.md`.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from triage import baseline
from triage import router as router_module
from triage.evaluate import EVAL_DIR, _pct, load_split
from triage.llm import (
    DEFAULT_BUDGET_USD,
    DEFAULT_MODEL,
    EFFORTS,
    REPO_ROOT,
    Budget,
    Usage,
    call_json,
    get_client,
    record_spend,
    total_spend,
)
from triage.metrics import mcnemar_exact_p, score_slices, wilson_interval
from triage.schema import Prediction, prediction_json_schema
from triage.taxonomy import brief_version

RESULTS = REPO_ROOT / "results"
SCAN_THRESHOLDS = (0.0, 0.5, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95)


def run(tickets, model: str, workers: int, effort: str, budget: Budget) -> tuple[list[dict], Usage]:
    """One call per ticket with the router prompt. Returns RAW predictions -- the policy
    layer and confidence gate are applied afterward by `finalize`, so the threshold can be
    tuned without paying for the calls again."""
    client = get_client()
    system = router_module.router_system_prompt()
    schema = prediction_json_schema()
    total = Usage()

    def one(ticket) -> dict | None:
        if budget.stop_now():
            return None
        raw, usage = call_json(
            client, model=model, system=system, user=baseline.user_prompt(ticket.text),
            json_schema=schema, effort=effort,
        )
        budget.add(usage)
        try:
            prediction = Prediction.model_validate(raw)
        except ValidationError as exc:
            raise RuntimeError(f"Unparseable prediction for {ticket.id}: {exc}") from exc
        return {
            "id": ticket.id,
            "text": ticket.text,
            "hard_case": ticket.hard_case,
            "hard_case_kind": ticket.hard_case_kind,
            "reviewed": ticket.reviewed,
            "gold": ticket.labels.model_dump(),
            "raw_pred": prediction.model_dump(),
            "_usage": usage,
        }

    rows: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(one, tickets):
            if row is None:
                continue
            total.add(row.pop("_usage"))
            rows.append(row)
            done += 1
            if done % 25 == 0 or done == len(tickets):
                print(f"  scored {done}/{len(tickets)}  ({budget.report()})", flush=True)
    rows.sort(key=lambda r: r["id"])
    return rows, total


def finalize(rows: list[dict], threshold: float) -> list[dict]:
    """Apply the policy layer and confidence gate to each row's raw prediction. Pure and
    free -- this is what `--rescore` re-runs to try a different threshold."""
    out = []
    for row in rows:
        pred, sent_to_human, notes = router_module.route(row["raw_pred"], threshold=threshold)
        out.append({**row, "pred": pred, "sent_to_human": sent_to_human, "notes": notes})
    return out


def threshold_scan(rows: list[dict]) -> list[dict]:
    """Self-handled accuracy and human-queue rate at each candidate threshold, computed
    once from the raw predictions already paid for. Purely informational."""
    return [self_handled_stats(rows, t) for t in SCAN_THRESHOLDS]


def self_handled_stats(raw_rows: list[dict], threshold: float) -> dict:
    """Self-handled accuracy and human-queue rate at one threshold, with Wilson CIs."""
    finalized = finalize(raw_rows, threshold)
    handled = [r for r in finalized if not r["sent_to_human"]]
    correct = sum(
        1 for r in handled
        if r["pred"]["intent"] == r["gold"]["intent"]
        and r["pred"]["urgency"] == r["gold"]["urgency"]
        and r["pred"]["escalate"] == r["gold"]["escalate"]
    )
    acc_low, acc_high = wilson_interval(correct, len(handled)) if handled else (0.0, 1.0)
    queued = len(raw_rows) - len(handled)
    q_low, q_high = wilson_interval(queued, len(raw_rows))
    return {
        "threshold": threshold,
        "self_handled_n": len(handled),
        "self_handled_accuracy": round(correct / len(handled), 4) if handled else None,
        "self_handled_ci95": [acc_low, acc_high],
        "human_queue_n": queued,
        "human_queue_rate": round(queued / len(raw_rows), 4),
        "human_queue_ci95": [q_low, q_high],
    }


def compare_to_baseline(router_rows: list[dict], baseline_rows: dict[str, dict]) -> dict:
    """Matched-pair comparison on the tickets both systems scored: fixed vs broken, with
    an exact McNemar test. Compared on the router's FINAL (post-policy) prediction, not
    on whether a ticket was sent to a human -- that is a routing decision, not a label."""

    def all_three(pred: dict, gold: dict) -> bool:
        return (
            pred["intent"] == gold["intent"]
            and pred["urgency"] == gold["urgency"]
            and pred["escalate"] == gold["escalate"]
        )

    fixed_ids, broken_ids = [], []
    both_right = both_wrong = 0
    esc_fixed = esc_broken = 0
    for row in router_rows:
        base = baseline_rows.get(row["id"])
        if base is None:
            continue
        gold = row["gold"]
        base_ok = all_three(base["pred"], gold)
        router_ok = all_three(row["pred"], gold)
        if base_ok and not router_ok:
            broken_ids.append(row["id"])
        elif router_ok and not base_ok:
            fixed_ids.append(row["id"])
        elif base_ok and router_ok:
            both_right += 1
        else:
            both_wrong += 1

        base_esc_ok = base["pred"]["escalate"] == gold["escalate"]
        router_esc_ok = row["pred"]["escalate"] == gold["escalate"]
        if base_esc_ok and not router_esc_ok:
            esc_broken += 1
        elif router_esc_ok and not base_esc_ok:
            esc_fixed += 1

    return {
        "n": len(router_rows),
        "fixed": sorted(fixed_ids),
        "broken": sorted(broken_ids),
        "both_right": both_right,
        "both_wrong": both_wrong,
        "mcnemar_p_all_three": mcnemar_exact_p(len(fixed_ids), len(broken_ids)),
        "escalation_fixed": esc_fixed,
        "escalation_broken": esc_broken,
        "mcnemar_p_escalation": mcnemar_exact_p(esc_fixed, esc_broken),
        "note": (
            "Exact two-sided McNemar test on the tickets where the two systems disagree. "
            "p < 0.05 is the usual bar for 'more than noise at this n'; with single-digit "
            "disagreement counts, treat anything above that as inconclusive, not as a tie."
        ),
    }


def markdown_summary(record: dict) -> str:
    meta = record["run"]
    scores = record["scores"]["overall"]
    esc = scores["escalation"]
    sh = record["self_handled"]
    cmp = record["vs_baseline"]
    usage = record["usage"]
    base_usage = record["baseline_usage"]

    lines = [
        f"# Router results -- {meta['split']} split",
        "",
        (
            "> Same model, same brief as the baseline of record. The only difference is "
            "design: a prompt clarification, a deterministic policy layer, and a "
            "confidence gate that sends uncertain tickets to a human. See `router.py` "
            "and `DECISIONS.md`."
        ),
        "",
        f"- Model: `{meta['model']}` (effort `{meta['effort']}`), brief `{meta['brief_version']}`",
        f"- Confidence threshold: `{meta['threshold']}`",
        f"- Tickets: {scores['n']}",
        "",
        "## Headline: router vs the baseline of record",
        "",
        "| Metric | Router | Baseline |",
        "|---|---:|---:|",
        f"| Intent accuracy | {scores['intent_accuracy']:.1%} | {record['baseline_scores']['intent_accuracy']:.1%} |",
        f"| Urgency accuracy | {scores['urgency_accuracy']:.1%} | {record['baseline_scores']['urgency_accuracy']:.1%} |",
        f"| Escalation accuracy | {esc['accuracy']:.1%} | {record['baseline_scores']['escalation_accuracy']:.1%} |",
        f"| All three correct | {scores['all_three_correct']:.1%} | {record['baseline_scores']['all_three_correct']:.1%} |",
        "",
        "## Matched-pair comparison (same tickets)",
        "",
        f"- Fixed (baseline wrong, router right): **{len(cmp['fixed'])}** -- {', '.join(cmp['fixed']) or 'none'}",
        f"- Broken (baseline right, router wrong): **{len(cmp['broken'])}** -- {', '.join(cmp['broken']) or 'none'}",
        f"- Both right: {cmp['both_right']}, both wrong: {cmp['both_wrong']}",
        f"- McNemar exact p (all three correct): **{cmp['mcnemar_p_all_three']}**",
        (
            f"- Escalation only -- fixed {cmp['escalation_fixed']}, broken "
            f"{cmp['escalation_broken']}, McNemar p: **{cmp['mcnemar_p_escalation']}**"
        ),
        f"- {cmp['note']}",
        "",
        "## Escalation",
        "",
        "| Outcome | Count |",
        "|---|---:|",
        f"| Correct escalations | {esc['correct_escalations']} |",
        f"| Unnecessary escalations | {esc['unnecessary_escalations']} |",
        f"| Missed escalations | {esc['missed_escalations']} |",
        f"| Correct non-escalations | {esc['correct_non_escalations']} |",
        "",
        f"Precision {esc['precision']}, recall {esc['recall']}.",
        "",
        "## Self-handled vs sent to a human",
        "",
        (
            "`sent_to_human` is broader than `escalate`: every escalated ticket goes to a "
            "human, and so does any ticket the model was not confident about, even with "
            "`escalate=False`. This is the brief's own open question (§5) resolved."
        ),
        "",
        "| | n | Rate / accuracy | 95% CI |",
        "|---|---:|---:|---|",
        (
            f"| Sent to a human | {sh['human_queue_n']} | {_pct(sh['human_queue_rate'])} | "
            f"[{_pct(sh['human_queue_ci95'][0])}, {_pct(sh['human_queue_ci95'][1])}] |"
        ),
        (
            f"| Self-handled, all three correct | {sh['self_handled_n']} | "
            f"{_pct(sh['self_handled_accuracy'])} | "
            f"[{_pct(sh['self_handled_ci95'][0])}, {_pct(sh['self_handled_ci95'][1])}] |"
        ),
        "",
        "## Per-class urgency",
        "",
        "| Urgency | Support | Predicted | Recall | Precision |",
        "|---|---:|---:|---:|---:|",
        *(
            f"| `{cls}` | {v['support']} | {v['predicted']} | "
            f"{_pct(v['recall'])} | {_pct(v['precision'])} |"
            for cls, v in scores["urgency_per_class"].items()
        ),
        "",
        "## Cost and latency vs baseline",
        "",
        (
            f"- Router: ${usage['total_cost_usd']:.4f} total, "
            f"${usage['cost_per_ticket_usd']:.6f}/ticket, p50 {usage['latency_p50_s']}s, "
            f"p95 {usage['latency_p95_s']}s"
        ),
        (
            f"- Baseline: ${base_usage['total_cost_usd']:.4f} total, "
            f"${base_usage['cost_per_ticket_usd']:.6f}/ticket, p50 {base_usage['latency_p50_s']}s, "
            f"p95 {base_usage['latency_p95_s']}s"
        ),
        "",
        "## Threshold scan (informational, computed from these same raw predictions)",
        "",
        "| Threshold | Self-handled n | Self-handled accuracy | Human queue rate |",
        "|---:|---:|---:|---:|",
    ]
    for row in record["threshold_scan"]:
        lines.append(
            f"| {row['threshold']} | {row['self_handled_n']} | "
            f"{_pct(row['self_handled_accuracy'])} | {_pct(row['human_queue_rate'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", choices=EFFORTS)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--threshold", type=float, default=router_module.CONFIDENCE_THRESHOLD)
    parser.add_argument("--tag", default=None)
    parser.add_argument(
        "--rescore", metavar="RESULTS_JSON", default=None,
        help="Re-finalize a prior run's raw predictions at a new --threshold. No API calls.",
    )
    parser.add_argument("--max-cost", type=float, default=DEFAULT_BUDGET_USD, metavar="USD")
    args = parser.parse_args()

    if args.split == "test":
        print("NOTE: this is the held-out test split.\n", file=sys.stderr)

    tickets = load_split(args.split, EVAL_DIR, smoke=False)

    baseline_path = RESULTS / f"latest_{args.split}.json"
    if not baseline_path.exists():
        raise SystemExit(f"{baseline_path} not found. Run `make eval` first.")
    baseline_record = json.loads(baseline_path.read_text())
    if baseline_record["run"]["brief_version"] != brief_version():
        raise SystemExit(
            f"{baseline_path} was scored against brief "
            f"{baseline_record['run']['brief_version']}, current brief is "
            f"{brief_version()}. Re-run `make eval` before comparing."
        )
    baseline_rows = {r["id"]: r for r in baseline_record["predictions"]}

    started = datetime.now(UTC)
    if args.rescore:
        prior = json.loads(Path(args.rescore).read_text())
        raw_rows = prior["raw_predictions"]
        model, effort, workers = prior["run"]["model"], prior["run"]["effort"], prior["run"]["workers"]
        usage = Usage(**{
            k: v for k, v in prior["usage"].items()
            if k in ("input_tokens", "output_tokens", "cached_tokens",
                      "cache_write_tokens", "reasoning_tokens", "calls")
        })
        print(f"Re-finalized {len(raw_rows)} saved {args.split} predictions at threshold "
              f"{args.threshold}. No API calls.")
        incomplete = False
    else:
        model, effort, workers = args.model, args.effort, args.workers
        budget = Budget(args.max_cost, args.model)
        print(f"Scoring {len(tickets)} {args.split} tickets with the router prompt on "
              f"{args.model} (effort={args.effort}, cap ${args.max_cost:.2f})")
        raw_rows, usage = run(tickets, args.model, args.workers, args.effort, budget)
        incomplete = len(raw_rows) < len(tickets)

    rows = finalize(raw_rows, args.threshold)
    scores = score_slices(rows)
    base_overall = baseline_record["scores"]["overall"]

    record = {
        "run": {
            "split": args.split, "router_version": router_module.ROUTER_VERSION,
            "model": model, "effort": effort, "workers": workers,
            "brief_version": brief_version(), "threshold": args.threshold,
            "started_at": started.isoformat(timespec="seconds"), "tag": args.tag,
            "rescored_from": Path(args.rescore).name if args.rescore else None,
        },
        "complete": not incomplete,
        "usage": usage.summary(model) | {"inherited_from_replay": bool(args.rescore)},
        "baseline_usage": baseline_record["usage"],
        "scores": scores,
        "baseline_scores": {
            "intent_accuracy": base_overall["intent_accuracy"],
            "urgency_accuracy": base_overall["urgency_accuracy"],
            "escalation_accuracy": base_overall["escalation"]["accuracy"],
            "all_three_correct": base_overall["all_three_correct"],
        },
        "self_handled": self_handled_stats(raw_rows, args.threshold),
        "vs_baseline": compare_to_baseline(rows, baseline_rows),
        "threshold_scan": threshold_scan(raw_rows),
        "raw_predictions": raw_rows,
        "predictions": rows,
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    tag = f"_{args.tag}" if args.tag else ""
    partial = "_INCOMPLETE" if incomplete else ""
    name = f"{stamp}_{router_module.ROUTER_VERSION}_{args.split}{tag}{partial}"
    (RESULTS / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    summary = markdown_summary(record)
    (RESULTS / f"{name}.md").write_text(summary)
    if not incomplete:
        (RESULTS / f"latest_router_{args.split}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False)
        )

    print("\n" + summary)
    print(f"\nWrote results/{name}.json and results/{name}.md")
    if not args.rescore:
        running = record_spend(f"evaluate_router:{args.split}", model, usage, note=f"{len(rows)} tickets")
        print(f"Spend logged; project total now ${running:.4f}")
    else:
        print(f"No spend logged (re-finalized predictions); project total ${total_spend():.4f}")
    if incomplete:
        raise SystemExit(
            f"\nSTOPPED ON BUDGET after {len(raw_rows)}/{len(tickets)} tickets. "
            f"Partial scores are not final and latest_router_{args.split}.json was left untouched."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
