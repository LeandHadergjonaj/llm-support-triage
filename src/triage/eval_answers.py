"""Score a set of candidate ticket answers against `data/eval/answers_{dev,test}.jsonl`.

    .venv/bin/python -m triage.eval_answers --split dev --answers path/to/candidates.jsonl

This project has not built anything that answers tickets yet (Phase 3a builds the
measuring stick first, same as Phase 1 did for triage). This module is that measuring
stick: it takes a `candidates.jsonl` of `{"id", "handled_by", "answer_text"}` -- however
they were produced -- and checks each one against the ticket's answer contract in
`data/eval/answers_*.jsonl` (`must_handle`, `expected_must_contain`,
`expected_must_not_contain`).

**Who judges, and the bias that introduces.** Routing (`handled_by` vs `must_handle`) is
checked by exact match -- no judgement involved. Content (did the answer state the right
facts, did it avoid inventing anything) is graded by an LLM, `judge_ticket()` below,
because the criteria are natural-language claims ("acknowledges the item has already been
unplugged") that no keyword match can check reliably without both false positives (an
answer that mentions the keywords without meaning them) and false negatives (a correct
answer phrased differently). The judge model defaults to this project's own triage model,
`gpt-5.6-terra` (`DEFAULT_MODEL`) -- **the same vendor and, if a future answering system
also runs on it, potentially the same model** grading its own output. That is not
independent verification, in exactly the way `DECISIONS.md` D-011 says a same-family label
review is not: it can catch a badly-grounded answer, but it can also share the generating
model's blind spots. Passing `--judge-model` from a different vendor narrows this but does
not remove it -- a human check of a sample is what would.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

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
from triage.metrics import wilson_interval

EVAL_DIR = REPO_ROOT / "data" / "eval"
RESULTS = REPO_ROOT / "results"

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "contains_all_required": {"type": "array", "items": {"type": "boolean"}},
        "avoids_all_forbidden": {"type": "array", "items": {"type": "boolean"}},
        "notes": {"type": "string"},
    },
    "required": ["contains_all_required", "avoids_all_forbidden", "notes"],
    "additionalProperties": False,
}

JUDGE_SYSTEM = (
    "You are grading one customer-support answer against a checklist, for a fictional "
    "UK homewares retailer, Hearth & Loom. You will be given the ticket, the answer, a "
    "list of facts the answer MUST contain (in substance, not verbatim), and a list of "
    "things the answer MUST NOT contain or claim. For each required fact, return true only "
    "if the answer clearly states that fact or its clear equivalent. For each forbidden "
    "item, return true only if the answer AVOIDS it (true = safe, false = the answer says "
    "the forbidden thing). Return one boolean per list item, in order. Be strict: a vague "
    "or generic answer that never actually states a required fact should score false for it."
)


def load_answer_tickets(split: str) -> list[dict]:
    path = EVAL_DIR / f"answers_{split}.jsonl"
    if not path.exists():
        raise SystemExit(f"{path} not found.")
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_candidates(path: str | Path) -> dict[str, dict]:
    rows = [
        json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()
    ]
    by_id = {r["id"]: r for r in rows}
    for r in rows:
        if r.get("handled_by") not in ("self", "human"):
            raise SystemExit(f"{r['id']}: handled_by must be 'self' or 'human', got {r.get('handled_by')!r}")
    return by_id


@dataclass
class TicketScore:
    id: str
    routing_correct: bool
    must_handle: str
    handled_by: str
    facts_covered: list[bool] | None = None
    forbidden_avoided: list[bool] | None = None
    notes: str | None = None


def judge_ticket(
    client, model: str, effort: str, ticket: dict, answer_text: str
) -> tuple[dict, Usage]:
    """One LLM call grading one answer against one ticket's contract. See module docstring
    for what this judge is and is not evidence of."""
    required = ticket["expected_must_contain"]
    forbidden = ticket["expected_must_not_contain"]
    user = (
        f"TICKET:\n{ticket['text']}\n\n"
        f"CANDIDATE ANSWER:\n{answer_text}\n\n"
        f"REQUIRED FACTS ({len(required)}):\n"
        + "\n".join(f"{i}. {f}" for i, f in enumerate(required))
        + f"\n\nFORBIDDEN ({len(forbidden)}):\n"
        + "\n".join(f"{i}. {f}" for i, f in enumerate(forbidden))
    )
    return call_json(
        client,
        model=model,
        system=JUDGE_SYSTEM,
        user=user,
        json_schema=JUDGE_SCHEMA,
        effort=effort,
        schema_name="answer_judgement",
    )


def score_one(
    ticket: dict,
    candidate: dict | None,
    judge: Callable[[dict, str], tuple[dict, Usage]] | None,
) -> tuple[TicketScore, Usage]:
    """Score one ticket. `judge(ticket, answer_text) -> (verdict_dict, Usage)` is injected
    so this function -- and therefore the aggregation logic below -- is testable with no
    API key and no spend; see tests/test_eval_answers.py."""
    if candidate is None:
        return TicketScore(ticket["id"], False, ticket["must_handle"], "MISSING"), Usage()

    routing_correct = candidate["handled_by"] == ticket["must_handle"]
    score = TicketScore(
        ticket["id"], routing_correct, ticket["must_handle"], candidate["handled_by"]
    )
    if not routing_correct or judge is None:
        return score, Usage()

    verdict, usage = judge(ticket, candidate.get("answer_text") or "")
    n_req, n_forb = len(ticket["expected_must_contain"]), len(ticket["expected_must_not_contain"])
    facts = verdict["contains_all_required"]
    forbidden = verdict["avoids_all_forbidden"]
    if len(facts) != n_req or len(forbidden) != n_forb:
        raise RuntimeError(f"{ticket['id']}: judge returned the wrong number of verdicts")
    score.facts_covered = facts
    score.forbidden_avoided = forbidden
    score.notes = verdict.get("notes")
    return score, usage


def aggregate(scores: list[TicketScore]) -> dict:
    n = len(scores)
    routing_hits = sum(s.routing_correct for s in scores)
    graded = [s for s in scores if s.facts_covered is not None]

    fact_hits = sum(sum(s.facts_covered) for s in graded)
    fact_total = sum(len(s.facts_covered) for s in graded)
    forbidden_hits = sum(sum(s.forbidden_avoided) for s in graded)
    forbidden_total = sum(len(s.forbidden_avoided) for s in graded)
    fully_correct = sum(
        1 for s in graded if all(s.facts_covered) and all(s.forbidden_avoided)
    )

    def rate(hits: int, total: int) -> dict:
        if total == 0:
            return {"rate": None, "n": 0, "ci95": None}
        lo, hi = wilson_interval(hits, total)
        return {"rate": round(hits / total, 4), "n": total, "ci95": [lo, hi]}

    return {
        "tickets": n,
        "routing_accuracy": rate(routing_hits, n),
        "content_graded": len(graded),
        "required_fact_coverage": rate(fact_hits, fact_total),
        "forbidden_avoidance": rate(forbidden_hits, forbidden_total),
        "fully_correct_of_graded": rate(fully_correct, len(graded)),
        "missing_candidates": [s.id for s in scores if s.handled_by == "MISSING"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["dev", "test"], required=True)
    parser.add_argument("--answers", required=True, help="Path to a candidates.jsonl")
    parser.add_argument("--judge-model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", choices=EFFORTS, default="low")
    parser.add_argument("--max-cost", type=float, default=DEFAULT_BUDGET_USD)
    parser.add_argument("--no-judge", action="store_true", help="Score routing only, no API calls")
    args = parser.parse_args()

    if args.split == "test":
        print("WARNING: scoring the held-out test split.", file=sys.stderr)

    tickets = load_answer_tickets(args.split)
    candidates = load_candidates(args.answers)

    usage_total = Usage()
    if args.no_judge:
        scores = [score_one(t, candidates.get(t["id"]), None)[0] for t in tickets]
    else:
        client = get_client()
        budget = Budget(args.max_cost, args.judge_model)

        def judge(ticket: dict, answer_text: str) -> tuple[dict, Usage]:
            if budget.stop_now():
                raise SystemExit(f"Budget cap hit: {budget.report()}. Re-run with --max-cost to raise it.")
            verdict, usage = judge_ticket(client, args.judge_model, args.effort, ticket, answer_text)
            budget.add(usage)
            return verdict, usage

        scores = []
        with ThreadPoolExecutor(max_workers=8) as pool:
            for score, usage in pool.map(
                lambda t: score_one(t, candidates.get(t["id"]), judge), tickets
            ):
                scores.append(score)
                usage_total.add(usage)
        record_spend("eval_answers", args.judge_model, usage_total, note=f"split={args.split}")

    report = {
        "run": {
            "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "split": args.split,
            "judge_model": None if args.no_judge else args.judge_model,
        },
        "usage": usage_total.summary(args.judge_model) if not args.no_judge else None,
        "scores": aggregate(scores),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    stamp = report["run"]["at"].replace(":", "").replace("-", "")
    out = RESULTS / f"{stamp}_answer_eval_{args.split}.json"
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report["scores"], indent=2))
    print(f"\nWritten to {out}")


if __name__ == "__main__":
    main()
