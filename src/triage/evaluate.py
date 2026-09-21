"""Run the baseline over a split and score it.

    .venv/bin/python -m triage.evaluate --split dev

Writes a timestamped JSON record plus a readable Markdown summary to results/, and
updates results/latest_<split>.json so later steps have a fixed thing to compare against.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from pydantic import ValidationError

from triage import baseline
from triage.llm import DEFAULT_MODEL, REPO_ROOT, Usage, call_json, get_client
from triage.metrics import score_slices
from triage.schema import Prediction, Ticket, prediction_json_schema

EVAL_DIR = REPO_ROOT / "data" / "eval"
RESULTS = REPO_ROOT / "results"


def load_split(split: str) -> list[Ticket]:
    path = EVAL_DIR / f"{split}.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run: make data")
    return [
        Ticket.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]


def run(tickets: list[Ticket], model: str, workers: int, effort: str) -> tuple[list[dict], Usage]:
    client = get_client()
    system = baseline.system_prompt()
    schema = prediction_json_schema()
    total = Usage()

    def one(ticket: Ticket) -> dict:
        raw, usage = call_json(
            client,
            model=model,
            system=system,
            user=baseline.user_prompt(ticket.text),
            json_schema=schema,
            effort=effort,
        )
        try:
            prediction = Prediction.model_validate(raw)
        except ValidationError as exc:  # schema-valid but semantically off
            raise RuntimeError(f"Unparseable prediction for {ticket.id}: {exc}") from exc
        # Normalise: an empty reason list on an escalation is a contradiction, so keep
        # both fields as returned and let the metrics show it rather than papering over it.
        return {
            "id": ticket.id,
            "text": ticket.text,
            "hard_case": ticket.hard_case,
            "hard_case_kind": ticket.hard_case_kind,
            "human_reviewed": ticket.human_reviewed,
            "gold": ticket.labels.model_dump(),
            "pred": prediction.model_dump(),
            "_usage": usage,
        }

    rows: list[dict] = []
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for row in pool.map(one, tickets):
            total.add(row.pop("_usage"))
            rows.append(row)
            done += 1
            if done % 25 == 0 or done == len(tickets):
                print(f"  scored {done}/{len(tickets)}", flush=True)
    rows.sort(key=lambda r: r["id"])
    return rows, total


def markdown_summary(record: dict) -> str:
    meta, scores, usage = record["run"], record["scores"], record["usage"]
    overall = scores["overall"]
    esc = overall["escalation"]
    reviewed = record["label_quality"]["human_reviewed"]

    lines = [
        f"# Baseline results -- {meta['split']} split",
        "",
        f"- Prompt: `{meta['prompt_version']}`",
        f"- Model: `{meta['model']}` (effort `{meta['effort']}`)",
        f"- Run at: {meta['started_at']}",
        f"- Tickets: {overall['n']}",
        "",
        (
            "> Reference labels for urgency and escalation are **model-drafted**, not "
            f"hand-labelled. {reviewed} of {overall['n']} tickets in this split have been "
            "corrected by a human. Treat the absolute numbers as provisional; they are "
            "meaningful mainly as a fixed bar for later versions to beat."
        ),
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Intent accuracy | {overall['intent_accuracy']:.1%} |",
        f"| Urgency accuracy | {overall['urgency_accuracy']:.1%} |",
        f"| Escalation accuracy | {esc['accuracy']:.1%} |",
        f"| All three correct | {overall['all_three_correct']:.1%} |",
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
        (
            f"Precision {esc['precision']}, recall {esc['recall']}. "
            f"Reference escalation rate {esc['gold_escalation_rate']:.1%}, "
            f"predicted {esc['predicted_escalation_rate']:.1%}."
        ),
        "",
        "## Cost and latency",
        "",
        f"- Total cost: **${usage['total_cost_usd']:.4f}** for {usage['calls']} tickets",
        f"- Cost per ticket: ${usage['cost_per_ticket_usd']:.6f}",
        (
            f"- Latency: mean {usage['latency_mean_s']}s, p50 {usage['latency_p50_s']}s, "
            f"p95 {usage['latency_p95_s']}s (at {meta['workers']} concurrent requests)"
        ),
        (
            f"- Cache: {usage['cached_tokens']} input tokens served from cache, "
            f"{usage['cache_write_tokens']} written"
        ),
        f"- Reasoning tokens: {usage['reasoning_tokens']} (billed as output)",
        "",
        "## Easy vs hard",
        "",
        "| Slice | n | Intent | Urgency | Escalation |",
        "|---|---:|---:|---:|---:|",
    ]
    slices = (("bitext_only", "Bitext tickets"), ("hard_cases_only", "Authored hard cases"))
    for key, label in slices:
        if key in scores:
            s = scores[key]
            lines.append(
                f"| {label} | {s['n']} | {s['intent_accuracy']:.1%} | "
                f"{s['urgency_accuracy']:.1%} | {s['escalation']['accuracy']:.1%} |"
            )

    if scores.get("by_hard_case_kind"):
        lines += [
            "",
            "### By hard-case kind",
            "",
            "| Kind | n | Intent | Urgency | Escalation |",
            "|---|---:|---:|---:|---:|",
        ]
        for kind, s in scores["by_hard_case_kind"].items():
            lines.append(
                f"| {kind} | {s['n']} | {s['intent_accuracy']:.0%} | "
                f"{s['urgency_accuracy']:.0%} | {s['escalation_accuracy']:.0%} |"
            )

    conf = overall["intent_confusions"]
    if conf:
        lines += [
            "",
            "## Top intent confusions",
            "",
            "| Reference | Predicted | n |",
            "|---|---|---:|",
        ]
        lines += [f"| {c['gold']} | {c['predicted']} | {c['n']} |" for c in conf]

    lines += [
        "",
        "## Confidence calibration",
        "",
        "| Confidence | n | All three correct |",
        "|---|---:|---:|",
    ]
    for bucket in overall["confidence_calibration"]:
        lines.append(f"| {bucket['confidence_range']} | {bucket['n']} | {bucket['all_three_correct']:.1%} |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="Score only the first N tickets.")
    parser.add_argument("--tag", default=None, help="Label this run in the results filename.")
    args = parser.parse_args()

    if args.split == "test":
        print(
            "NOTE: this is the held-out test split. Do not use it to tune the prompt.\n",
            file=sys.stderr,
        )

    tickets = load_split(args.split)
    if args.limit:
        tickets = tickets[: args.limit]

    started = datetime.now(UTC)
    print(f"Scoring {len(tickets)} {args.split} tickets with {args.model} (effort={args.effort})")
    rows, usage = run(tickets, args.model, args.workers, args.effort)

    record = {
        "run": {
            "split": args.split,
            "prompt_version": baseline.VERSION,
            "model": args.model,
            "effort": args.effort,
            "workers": args.workers,
            "started_at": started.isoformat(timespec="seconds"),
            "tag": args.tag,
        },
        "label_quality": {
            "urgency_and_escalation_labels": "model_drafted",
            "human_reviewed": sum(1 for r in rows if r["human_reviewed"]),
            "total": len(rows),
        },
        "usage": usage.summary(args.model),
        "scores": score_slices(rows),
        "predictions": rows,
    }

    RESULTS.mkdir(exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    tag = f"_{args.tag}" if args.tag else ""
    name = f"{stamp}_{baseline.VERSION}_{args.split}{tag}"
    (RESULTS / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    summary = markdown_summary(record)
    (RESULTS / f"{name}.md").write_text(summary)
    (RESULTS / f"latest_{args.split}.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False)
    )

    print("\n" + summary)
    print(f"\nWrote results/{name}.json and results/{name}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
