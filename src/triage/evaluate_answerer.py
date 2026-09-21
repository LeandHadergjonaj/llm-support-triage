"""Run the full ticket-answering pipeline over an answer-eval split and score it.

    .venv/bin/python -m triage.evaluate_answerer --split dev

Per ticket: the router decides `sent_to_human` (`router.py`, unchanged from Phase 2);
`answerer.py` then writes the customer reply (if kept) or the handover note (if sent to a
human), grounded only in `docs/knowledge_base/` and a database lookup on any order number
in the ticket text. `eval_answers.py` then judges the result against the ticket's answer
contract. Three LLM calls per ticket, all on the same model (project rule 7 / Phase 3b
brief: "use gpt-5.6-terra"), one shared spend cap across all three.

Candidates are saved to `results/*_candidates_<split>.jsonl` so the judge pass alone can
be re-run against them with `triage.eval_answers` directly, at no cost to re-generate.
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from pydantic import ValidationError

from triage import answerer
from triage import baseline as baseline_module
from triage import router as router_module
from triage.eval_answers import aggregate, load_answer_tickets, score_one
from triage.eval_answers import judge_ticket as llm_judge
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
)
from triage.schema import Prediction, prediction_json_schema

RESULTS = REPO_ROOT / "results"

# Tickets named in the Phase 3b brief as specific things to report on.
TRAP_TICKETS = {
    "hl-a0003": "refund-timing inconsistency (5 vs 10 working days)",
    "hl-a0004": "nonexistent order (53004)",
    "hl-a0001": "£100 boundary -- exactly £100, must not escalate/need review",
    "hl-a0002": "£100 boundary -- £100.01, must need review",
    "hl-0011": "£100 boundary -- two items combined over £100",
    "hl-a0013": "£100 boundary -- two items combined under £100",
}


def generate_one(client, model: str, router_effort: str, answer_effort: str, budget: Budget, ticket: dict) -> dict:
    """Router decides routing; answerer writes the reply or handover note."""
    raw_pred, usage = call_json(
        client, model=model, system=router_module.router_system_prompt(),
        user=baseline_module.user_prompt(ticket["text"]), json_schema=prediction_json_schema(),
        effort=router_effort,
    )
    budget.add(usage)
    try:
        pred = Prediction.model_validate(raw_pred).model_dump()
    except ValidationError as exc:
        raise RuntimeError(f"Unparseable router prediction for {ticket['id']}: {exc}") from exc
    pred, sent_to_human, notes = router_module.route(pred)

    # The router decided on ticket text alone; now that the order record is being looked
    # up anyway for the answer, catch an understated or unstated refund claim before it
    # self-handles (D-027).
    pred, forced = router_module.enforce_record_policy(pred, answerer.matched_orders(ticket["text"]))
    if forced and not sent_to_human:
        sent_to_human = True
        notes.append("record_refund_over_threshold")

    handled_by = "human" if sent_to_human else "self"
    escalation_context = ", ".join(pred["escalation_reasons"])

    answer_text, answer_usage = answerer.answer_ticket(
        client, model, answer_effort, ticket["text"], handled_by, escalation_context
    )
    usage.add(answer_usage)
    budget.add(answer_usage)

    return {
        "id": ticket["id"],
        "handled_by": handled_by,
        "answer_text": answer_text,
        "router_pred": pred,
        "router_notes": notes,
        "_usage": usage,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--router-effort", default="high", choices=EFFORTS)
    parser.add_argument("--answer-effort", default="medium", choices=EFFORTS)
    parser.add_argument("--judge-effort", default="low", choices=EFFORTS)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-cost", type=float, default=DEFAULT_BUDGET_USD, metavar="USD")
    parser.add_argument("--tag", default=None)
    args = parser.parse_args()

    if args.split == "test":
        print("NOTE: this is the held-out test split.\n", file=sys.stderr)

    tickets = load_answer_tickets(args.split)
    client = get_client()
    budget = Budget(args.max_cost, args.model)
    started = datetime.now(UTC)

    print(f"Generating {len(tickets)} answers on {args.model} "
          f"(router={args.router_effort}, answer={args.answer_effort}, cap ${args.max_cost:.2f})")
    generated: list[dict] = []
    usage_total = Usage()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [
            pool.submit(generate_one, client, args.model, args.router_effort, args.answer_effort, budget, t)
            for t in tickets
            if not budget.stop_now()
        ]
        for f in futures:
            row = f.result()
            usage_total.add(row.pop("_usage"))
            generated.append(row)
    generated.sort(key=lambda r: r["id"])
    incomplete = len(generated) < len(tickets)

    print(f"Judging {len(generated)} answers (effort={args.judge_effort})")
    candidates = {r["id"]: r for r in generated}

    def judge(ticket: dict, answer_text: str) -> tuple[dict, Usage]:
        if budget.stop_now():
            raise SystemExit(f"Budget cap hit mid-judging: {budget.report()}")
        verdict, usage = llm_judge(client, args.model, args.judge_effort, ticket, answer_text)
        budget.add(usage)
        return verdict, usage

    scores = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for score, usage in pool.map(
            lambda t: score_one(t, candidates.get(t["id"]), judge), tickets
        ):
            scores.append(score)
            usage_total.add(usage)

    report_scores = aggregate(scores)
    by_id = {s.id: s for s in scores}
    traps = {
        tid: {
            "description": desc,
            "handled_by": by_id[tid].handled_by if tid in by_id else None,
            "must_handle": by_id[tid].must_handle if tid in by_id else None,
            "routing_correct": by_id[tid].routing_correct if tid in by_id else None,
            "facts_covered": by_id[tid].facts_covered if tid in by_id else None,
            "forbidden_avoided": by_id[tid].forbidden_avoided if tid in by_id else None,
            "answer_text": candidates[tid]["answer_text"] if tid in candidates else None,
        }
        for tid, desc in TRAP_TICKETS.items()
    }

    record = {
        "run": {
            "split": args.split, "model": args.model,
            "router_effort": args.router_effort, "answer_effort": args.answer_effort,
            "judge_effort": args.judge_effort,
            "started_at": started.isoformat(timespec="seconds"), "tag": args.tag,
        },
        "complete": not incomplete,
        "usage": usage_total.summary(args.model),
        "scores": report_scores,
        "traps": traps,
        "per_ticket": [
            {
                "id": s.id, "must_handle": s.must_handle, "handled_by": s.handled_by,
                "routing_correct": s.routing_correct, "facts_covered": s.facts_covered,
                "forbidden_avoided": s.forbidden_avoided, "notes": s.notes,
            }
            for s in scores
        ],
    }

    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    tag = f"_{args.tag}" if args.tag else ""
    partial = "_INCOMPLETE" if incomplete else ""
    name = f"{stamp}_answerer_v1_{args.split}{tag}{partial}"
    (RESULTS / f"{name}.json").write_text(json.dumps(record, indent=2, ensure_ascii=False))
    with (RESULTS / f"{name}_candidates.jsonl").open("w") as fh:
        for r in generated:
            fh.write(json.dumps(r) + "\n")
    if not incomplete:
        (RESULTS / f"latest_answerer_{args.split}.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False)
        )

    print(json.dumps(report_scores, indent=2))
    print(f"\nWrote results/{name}.json (+ .jsonl candidates)")

    running = record_spend(f"evaluate_answerer:{args.split}", args.model, usage_total, note=f"{len(scores)} tickets")
    print(f"Spend logged; project total now ${running:.4f}")
    if incomplete:
        raise SystemExit(
            f"\nSTOPPED ON BUDGET after {len(generated)}/{len(tickets)} tickets. "
            f"latest_answerer_{args.split}.json was left untouched."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
