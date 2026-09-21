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
from pathlib import Path

from pydantic import ValidationError

from triage import baseline
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
from triage.metrics import label_error_rate, score_escalation, score_slices
from triage.schema import Prediction, Ticket, prediction_json_schema

EVAL_DIR = REPO_ROOT / "data" / "eval"
RESULTS = REPO_ROOT / "results"
SMOKE_EVAL_DIR = REPO_ROOT / "data" / "smoke"
SMOKE_RESULTS = RESULTS / "smoke"

SMOKE_BANNER = (
    "> **SMOKE TEST -- NOT A BASELINE.** A handful of tickets, labelled by a cheap "
    "model at low effort, run to prove the pipeline works end to end. The accuracy "
    "figures below are meaningless as a measure of the system."
)


def load_split(split: str, eval_dir: Path, smoke: bool) -> list[Ticket]:
    path = eval_dir / f"{split}.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found. Run: make data")
    tickets = [
        Ticket.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()
    ]
    # The two directions of the same guard: a smoke set holds cheap-model labels on a
    # handful of tickets, so its numbers are not a baseline and must never be filed as
    # one; and --smoke pointed at the real set would overwrite nothing but would report
    # a real run under a smoke-test heading.
    stamped = [t.id for t in tickets if t.smoke_test]
    if stamped and not smoke:
        raise SystemExit(
            f"{path} contains smoke-test tickets ({len(stamped)} of {len(tickets)}). "
            "These are not an eval set. Run `make data` to build the real one, or pass "
            "--smoke to score this as a pipeline check."
        )
    if smoke and not stamped:
        raise SystemExit(f"--smoke was passed but {path} holds no smoke-test tickets.")
    return tickets


def _all_tickets(eval_dir: str | Path) -> list[dict]:
    """Every ticket in the eval set, both splits, as raw dicts."""
    out = []
    for name in ("dev", "test"):
        path = Path(eval_dir) / f"{name}.jsonl"
        if path.exists():
            out += [
                json.loads(line) for line in path.read_text().splitlines() if line.strip()
            ]
    return out


def replay(results_path: str | Path, tickets: list[Ticket]) -> tuple[list[dict], Usage, dict]:
    """Re-pair saved predictions with the current labels. Costs nothing.

    After a review pass the model's answers are unchanged -- only the labels they are
    marked against have moved. Re-running the baseline would spend money to reproduce
    predictions already on disk, and would not reproduce them exactly. Replaying is both
    cheaper and a cleaner comparison: any movement in the scores is the labels moving,
    with the predictions held fixed.
    """
    prior = json.loads(Path(results_path).read_text())
    saved = {row["id"]: row for row in prior["predictions"]}
    missing = [t.id for t in tickets if t.id not in saved]
    if missing:
        raise SystemExit(
            f"{results_path} has no prediction for {len(missing)} ticket(s) in this "
            f"split, e.g. {missing[:3]}. Re-scoring needs a results file from a complete "
            f"run of the same split."
        )
    rows = []
    for ticket in tickets:
        row = dict(saved[ticket.id])
        # Predictions are frozen; everything describing the ticket is refreshed.
        row.update(
            text=ticket.text,
            hard_case=ticket.hard_case,
            hard_case_kind=ticket.hard_case_kind,
            reviewed=ticket.reviewed,
            gold=ticket.labels.model_dump(),
        )
        rows.append(row)
    rows.sort(key=lambda r: r["id"])
    usage = Usage(**{k: v for k, v in prior["usage"].items() if k in
                     ("input_tokens", "output_tokens", "cached_tokens",
                      "cache_write_tokens", "reasoning_tokens", "calls")})
    return rows, usage, prior["run"]


def reconcile_escalations(eval_dir: str | Path, split: str, rows: list[dict]) -> dict:
    """Tie the escalations scored in this run back to the escalations in the label set.

    Three counts get quoted in different places and are easy to confuse: how many
    escalations the whole 252-ticket set carries, how many are in this split, and how
    many this run actually scored (fewer, if --limit was used). They only agree if the
    splits partition the set, so the arithmetic is done here and printed rather than
    left to whoever is reading two documents side by side.
    """
    eval_dir = Path(eval_dir)
    per_split: dict[str, dict[str, int]] = {}
    for name in ("dev", "test"):
        path = eval_dir / f"{name}.jsonl"
        if not path.exists():
            continue
        labels = [
            json.loads(line)["labels"]
            for line in path.read_text().splitlines()
            if line.strip()
        ]
        per_split[name] = {
            "tickets": len(labels),
            "escalations": sum(1 for x in labels if x["escalate"]),
        }

    esc = score_escalation(rows)
    scored_gold = esc["correct_escalations"] + esc["missed_escalations"]
    this = per_split.get(split, {"tickets": len(rows), "escalations": scored_gold})
    set_tickets = sum(v["tickets"] for v in per_split.values())
    set_escalations = sum(v["escalations"] for v in per_split.values())

    return {
        "eval_set": {"tickets": set_tickets, "escalations": set_escalations},
        "by_split": per_split,
        "this_run": {
            "split": split,
            "tickets_scored": len(rows),
            "escalations_in_reference": scored_gold,
            "of_which_caught": esc["correct_escalations"],
            "of_which_missed": esc["missed_escalations"],
            "predicted_but_not_in_reference": esc["unnecessary_escalations"],
        },
        "checks": {
            "splits_partition_the_set": set_tickets
            == sum(v["tickets"] for v in per_split.values()),
            "split_escalations_sum_to_set": set_escalations
            == sum(v["escalations"] for v in per_split.values()),
            "run_scored_the_whole_split": len(rows) == this["tickets"],
            "reference_escalations_match_split": scored_gold == this["escalations"],
        },
    }


def run(
    tickets: list[Ticket], model: str, workers: int, effort: str, budget: Budget
) -> tuple[list[dict], Usage]:
    client = get_client()
    system = baseline.system_prompt()
    schema = prediction_json_schema()
    total = Usage()

    def one(ticket: Ticket) -> dict | None:
        if budget.stop_now():
            return None
        raw, usage = call_json(
            client,
            model=model,
            system=system,
            user=baseline.user_prompt(ticket.text),
            json_schema=schema,
            effort=effort,
        )
        budget.add(usage)
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
            "reviewed": ticket.reviewed,
            "gold": ticket.labels.model_dump(),
            "pred": prediction.model_dump(),
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


def _pct(value: float | None) -> str:
    return "--" if value is None else f"{value:.1%}"


def _label_error_lines(record: dict) -> list[str]:
    """How often the drafted labels were actually wrong, where a human has checked."""
    rates = record.get("label_error_rate")
    if not rates:
        return []
    block, targeted = rates["random_block"], rates["targeted_picks"]
    if not block["reviewed"]:
        return [
            "## Label error rate",
            "",
            (
                "Not yet measurable: no ticket in the random review block has been "
                "through the review pass. Until it has, the accuracy figures above have "
                "no known error bar on the labels themselves."
            ),
            "",
        ]
    low, high = block["ci95"]
    lines = [
        "## Label error rate",
        "",
        (
            f"Measured on the **random block** -- {block['reviewed']} tickets drawn "
            f"uniformly from all {record['escalation_reconciliation']['eval_set']['tickets']}, "
            f"which is the only part of the review sample that estimates the set as a "
            f"whole."
        ),
        "",
        "| | Corrected | Reviewed | Error rate | 95% CI |",
        "|---|---:|---:|---:|---:|",
        (
            f"| Random block | {block['corrected']} | {block['reviewed']} | "
            f"{block['error_rate']:.1%} | [{low:.1%}, {high:.1%}] |"
        ),
    ]
    if targeted["reviewed"]:
        t_low, t_high = targeted["ci95"]
        lines.append(
            f"| Targeted picks | {targeted['corrected']} | {targeted['reviewed']} | "
            f"{targeted['error_rate']:.1%} | [{t_low:.1%}, {t_high:.1%}] |"
        )
    lines += [
        "",
        (
            "Wilson score interval. The targeted picks were chosen for looking wrong, "
            "so their rate is biased upwards by construction -- a diagnostic of where "
            "the drafter struggles, not an estimate of the set. Do not average the two "
            "rows."
        ),
        "",
        (
            f"Read the accuracy figures above against this: roughly "
            f"{block['error_rate']:.0%} of reference labels are wrong (95% CI "
            f"{low:.0%}-{high:.0%}), which bounds how precisely any of them can be known."
        ),
        "",
    ]
    return lines


def _reconciliation_lines(record: dict) -> list[str]:
    """Tie this split's escalation counts back to the label set's, in the report itself."""
    rec = record.get("escalation_reconciliation")
    if not rec:
        return []
    run, whole, splits = rec["this_run"], rec["eval_set"], rec["by_split"]
    per = "; ".join(
        f"{name} {v['escalations']} of {v['tickets']}" for name, v in sorted(splits.items())
    )
    lines = [
        "### Reconciliation with the label set",
        "",
        (
            f"The eval set holds **{whole['escalations']} escalations across "
            f"{whole['tickets']} tickets** ({per}). The splits partition the set, so "
            f"those counts add up rather than overlap."
        ),
        "",
        (
            f"This run scored the **{run['split']}** split: {run['tickets_scored']} "
            f"tickets carrying {run['escalations_in_reference']} reference escalations, "
            f"of which {run['of_which_caught']} were caught and {run['of_which_missed']} "
            f"missed, plus {run['predicted_but_not_in_reference']} escalations predicted "
            f"that the reference does not have. "
            f"{run['escalations_in_reference']} = {run['of_which_caught']} + "
            f"{run['of_which_missed']}."
        ),
        "",
    ]
    failed = [name for name, ok in rec["checks"].items() if not ok]
    if failed:
        lines += [f"> :warning: **Reconciliation check failed:** {', '.join(failed)}.", ""]
    return lines


def markdown_summary(record: dict) -> str:
    meta, scores, usage = record["run"], record["scores"], record["usage"]
    overall = scores["overall"]
    esc = overall["escalation"]
    quality = record["label_quality"]
    reviewed = quality["reviewed"]
    n = overall["n"]
    maj = overall["urgency_vs_majority_class"]

    # The caveat that matters most goes first and is not softened. The same model drafted
    # these labels and produced these predictions, so a large part of the agreement below
    # is a model being consistent with itself.
    reviewers = quality.get("reviewers") or []
    who = ", ".join(reviewers) if reviewers else "nobody yet"
    review_line = (
        f"> **No label in this project has been checked by a person.** {reviewed} of {n} "
        f"tickets in this split have been through a second-opinion review by {who}, "
        f"a model of a different family from the drafter. That is a real "
        f"independence check and it is not the same as human verification: where two "
        f"models disagree you learn the label is contested, not which reading a person "
        f"would have picked, and where they agree they may be agreeing about the same "
        f"misreading."
    )
    if quality.get("scored_against_own_labels"):
        caveat = (
            f"> ### :warning: These numbers are self-agreement, not accuracy\n>\n"
            f"> `{meta['model']}` **drafted the reference labels it is being scored "
            f"against here.** Urgency and escalation labels came from the same model on "
            f"the same brief. A model agreeing with its own earlier judgement is not "
            f"evidence that the judgement was right, so every figure below is optimistic "
            f"by an unknown margin -- most of all on the judgement calls (urgency, "
            f"escalation) and least on intent, which for Bitext tickets comes from a "
            f"deterministic mapping rather than from the model.\n>\n"
            + review_line
            + "\n>\n> Treat this as **a fixed bar for later versions to beat, not a "
            "measure of how good the triage is.** Later versions are scored on the same "
            "labels, so the comparison between them stays valid even while the absolute "
            "number does not."
        )
    else:
        caveat = (
            "> Reference labels for urgency and escalation are **model-drafted**.\n>\n"
            + review_line
            + "\n>\n> Treat the absolute numbers as provisional; they are meaningful "
            "mainly as a fixed bar for later versions to beat."
        )

    smoke = record["label_quality"].get("smoke_test")
    lines = [
        f"# Baseline results -- {meta['split']} split",
        "",
        *([SMOKE_BANNER, ""] if smoke else []),
        f"- Prompt: `{meta['prompt_version']}`",
        f"- Model: `{meta['model']}` (effort `{meta['effort']}`)",
        f"- Run at: {meta['started_at']}",
        f"- Tickets: {n}",
        f"- Reference labels drafted by: {', '.join(quality['labelers']) or 'unknown'}",
        f"- Reviewed by: {who}",
        "",
        caveat,
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
        *_reconciliation_lines(record),
        *_label_error_lines(record),
        "## Urgency",
        "",
        (
            "Urgency is heavily skewed, so accuracy alone flatters any model that follows "
            "the skew. The comparison against always predicting the most common class is "
            "the one to read, and macro recall -- the mean of the per-class recalls -- is "
            "the number that does not improve just by guessing `low` more often."
        ),
        "",
        "| | Model | Always predict most common class |",
        "|---|---:|---:|",
        (
            f"| Accuracy | {maj['model_accuracy']:.1%} | {maj['baseline_accuracy']:.1%} "
            f"(`{maj['most_common_class']}`, {maj['its_share_of_the_reference']:.1%} of "
            f"the reference) |"
        ),
        (
            f"| Macro recall | {maj['model_macro_recall']:.1%} | "
            f"{maj['baseline_macro_recall']:.1%} |"
        ),
        "",
        (
            f"Accuracy gain over the constant predictor: "
            f"**{maj['accuracy_gain_pp']:+.1f} points**."
        ),
        "",
        "| Urgency | Support | Predicted | Recall | Precision |",
        "|---|---:|---:|---:|---:|",
        *(
            f"| `{cls}` | {v['support']} | {v['predicted']} | "
            f"{_pct(v['recall'])} | {_pct(v['precision'])} |"
            for cls, v in overall["urgency_per_class"].items()
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
    parser.add_argument("--effort", default="high", choices=EFFORTS)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="Score only the first N tickets.")
    parser.add_argument("--tag", default=None, help="Label this run in the results filename.")
    parser.add_argument(
        "--rescore",
        metavar="RESULTS_JSON",
        default=None,
        help=(
            "Re-score the predictions saved in this results file against the current "
            "labels, instead of calling the API. Use after a review pass: the model's "
            "answers have not changed, only the labels they are marked against."
        ),
    )
    parser.add_argument(
        "--max-cost",
        type=float,
        default=DEFAULT_BUDGET_USD,
        metavar="USD",
        help="Stop scoring once this much has been spent (project rule 8).",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help=(
            "Score the throwaway set in data/smoke/ and write to results/smoke/. "
            "Checks the pipeline runs; produces no baseline and no latest_*.json."
        ),
    )
    args = parser.parse_args()

    eval_dir = SMOKE_EVAL_DIR if args.smoke else EVAL_DIR
    results_dir = SMOKE_RESULTS if args.smoke else RESULTS
    if args.smoke:
        print(
            "SMOKE TEST: scoring cheap-model labels in data/smoke/. These are not "
            "baseline numbers and results/latest_*.json is left untouched.\n"
        )

    if args.split == "test":
        print(
            "NOTE: this is the held-out test split. Do not use it to tune the prompt.\n",
            file=sys.stderr,
        )

    tickets = load_split(args.split, eval_dir, args.smoke)
    if args.limit:
        tickets = tickets[: args.limit]

    started = datetime.now(UTC)
    if args.rescore:
        rows, usage, prior = replay(args.rescore, tickets)
        model, effort, workers = prior["model"], prior["effort"], prior["workers"]
        print(
            f"Re-scored {len(rows)} saved {args.split} predictions from "
            f"{Path(args.rescore).name} against the current labels. No API calls."
        )
    else:
        model, effort, workers = args.model, args.effort, args.workers
        budget = Budget(args.max_cost, args.model)
        print(
            f"Scoring {len(tickets)} {args.split} tickets with {args.model} "
            f"(effort={args.effort}, cap ${args.max_cost:.2f})"
        )
        rows, usage = run(tickets, args.model, args.workers, args.effort, budget)
    incomplete = len(rows) < len(tickets)

    record = {
        "run": {
            "split": args.split,
            "prompt_version": baseline.VERSION,
            "model": model,
            "effort": effort,
            "workers": workers,
            "rescored_from": Path(args.rescore).name if args.rescore else None,
            "started_at": started.isoformat(timespec="seconds"),
            "tag": args.tag,
        },
        "label_quality": {
            "urgency_and_escalation_labels": "model_drafted",
            "reviewed": sum(1 for r in rows if r["reviewed"]),
            "total": len(rows),
            "smoke_test": args.smoke,
            "labelers": sorted({
                f"{t.labeler.model} (effort {t.labeler.effort})" for t in tickets if t.labeler
            }),
            "reviewers": sorted({t.reviewed_by for t in tickets if t.reviewed_by}),
            "reviewed_by_a_person": False,
            # True when the model being scored also drafted the labels it is scored
            # against. It is then partly marking its own work, so agreement is inflated
            # by an unknown amount. Recorded per run so the caveat travels with the
            # numbers instead of living only in a README.
            "scored_against_own_labels": any(
                t.labeler and t.labeler.model == args.model for t in tickets
            ),
        },
        "complete": not incomplete,
        # On a rescore this is the replayed run's usage, not new spend.
        "usage": usage.summary(model) | {"inherited_from_replay": bool(args.rescore)},
        "escalation_reconciliation": reconcile_escalations(eval_dir, args.split, rows),
        # Measured over both splits: the random block spans the whole set, and cutting
        # it to one split would shrink the sample and bias it towards that split.
        "label_error_rate": label_error_rate(_all_tickets(eval_dir)),
        "scores": score_slices(rows),
        "predictions": rows,
    }

    results_dir.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    tag = f"_{args.tag}" if args.tag else ""
    partial = "_INCOMPLETE" if incomplete else ""
    name = f"{stamp}_{baseline.VERSION}_{args.split}{tag}{partial}"
    (results_dir / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    summary = markdown_summary(record)
    (results_dir / f"{name}.md").write_text(summary)
    # latest_<split>.json is the fixed bar later versions are compared against, so only
    # a real run is allowed to move it.
    if not args.smoke and not incomplete:
        (results_dir / f"latest_{args.split}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False)
        )

    print("\n" + summary)
    rel = results_dir.relative_to(REPO_ROOT)
    print(f"\nWrote {rel}/{name}.json and {rel}/{name}.md")
    # A rescore spends nothing: its usage is inherited from the run being replayed and
    # was logged when that run happened. Logging it again would double-count against the
    # $2 cap and make the ledger describe money that was never spent.
    if not args.smoke and not args.rescore:
        running = record_spend(
            f"evaluate:{args.split}", model, usage, note=f"{len(rows)} tickets"
        )
        print(f"Spend logged; project total now ${running:.4f}")
    elif args.rescore:
        print(f"No spend logged (replayed predictions); project total ${total_spend():.4f}")
    if incomplete:
        raise SystemExit(
            f"\nSTOPPED ON BUDGET after {len(rows)}/{len(tickets)} tickets "
            f"({budget.report()}). Partial scores are NOT a baseline and "
            f"latest_{args.split}.json was left untouched."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
