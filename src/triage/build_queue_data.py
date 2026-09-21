"""Build the review-queue packages from Phase 3b's answerer candidates.

    .venv/bin/python -m triage.build_queue_data

Reuses `results/*_answerer_v1_{dev,test}_candidates.jsonl` rather than re-running the
router -- those already carry the router's prediction and, for `human` tickets, the
handover note; regenerating either would cost money for no new information. The only new
API calls this script makes are one `answer_ticket(..., handled_by="self")` per
human-routed ticket, to get a **suggested customer reply** for the agent to review --
Phase 3b deliberately never wrote one for escalated tickets (brief: "the system does not
send a reply"), but the queue needs a draft to approve, edit or reject. It is grounded by
the same `BASE_SYSTEM` rules as every other reply (no invented facts, no promises the
policy documents don't allow) -- nothing in the queue relaxes that; the draft is simply
never sent without a human's approval.

Idempotent and cheap to re-run: packages already in the database are skipped unless
`--force`, so accidentally running this twice does not repeat the ~11 LLM calls.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from triage import answerer
from triage.llm import (
    DEFAULT_BUDGET_USD,
    DEFAULT_MODEL,
    EFFORTS,
    REPO_ROOT,
    Budget,
    Usage,
    get_client,
    record_spend,
)
from triage.queue_db import connect, package_ids, upsert_package

RESULTS = REPO_ROOT / "results"
EVAL_DIR = REPO_ROOT / "data" / "eval"

# Static, zero-cost mapping from intent to the policy document(s) an agent should read
# alongside this ticket. Six documents, eleven intents -- a lookup table, not a retrieval
# system; see answerer.py's own docstring for why retrieval isn't warranted at this size.
INTENT_TO_POLICY_DOCS: dict[str, list[str]] = {
    "order_management": ["cancellations_and_order_changes.md"],
    "delivery_and_shipping": ["delivery_and_shipping.md"],
    "returns_and_refunds": ["returns_and_refunds.md"],
    "billing_and_payment": ["payments_and_billing.md"],
    "account_management": ["accounts.md"],
    "account_access": ["accounts.md"],
    "product_issue": ["product_safety.md", "returns_and_refunds.md"],
    "feedback_and_complaint": [],
    "human_agent_request": [],
    "marketing_preferences": ["accounts.md"],
    "out_of_scope": [],
}


def latest_candidates_path(split: str):
    matches = sorted(RESULTS.glob(f"*_answerer_v1_{split}_candidates.jsonl"))
    if not matches:
        raise SystemExit(
            f"No results/*_answerer_v1_{split}_candidates.jsonl found -- run `make answer` "
            f"(dev) or `make answer-test` (test) first."
        )
    return matches[-1]


def load_tickets_by_id(split: str) -> dict[str, dict]:
    path = EVAL_DIR / f"answers_{split}.jsonl"
    return {row["id"]: row for row in (json.loads(l) for l in path.read_text().splitlines() if l.strip())}


def build_package(ticket: dict, candidate: dict, split: str, suggested_reply: str) -> dict:
    pred = candidate["router_pred"]
    handled_by = candidate["handled_by"]
    return {
        "id": ticket["id"],
        "split": split,
        "ticket_text": ticket["text"],
        "intent": pred["intent"],
        "urgency": pred["urgency"],
        "confidence": pred["confidence"],
        "escalation_reasons": pred["escalation_reasons"],
        "rationale": pred["rationale"],
        "handled_by": handled_by,
        "order_facts": answerer.order_facts_block(ticket["text"]),
        "policy_docs": INTENT_TO_POLICY_DOCS.get(pred["intent"], []),
        "handover_note": candidate["answer_text"] if handled_by == "human" else None,
        "suggested_reply": suggested_reply,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--effort", default="medium", choices=EFFORTS)
    parser.add_argument("--max-cost", type=float, default=DEFAULT_BUDGET_USD, metavar="USD")
    parser.add_argument("--force", action="store_true", help="Regenerate packages already in the DB")
    args = parser.parse_args()

    with connect() as conn:
        existing = set() if args.force else package_ids(conn)

        client = None
        budget = Budget(args.max_cost, args.model)
        usage_total = Usage()
        n_new_calls = 0

        for split in ("dev", "test"):
            candidates = {
                json.loads(l)["id"]: json.loads(l)
                for l in latest_candidates_path(split).read_text().splitlines() if l.strip()
            }
            tickets = load_tickets_by_id(split)

            for tid, candidate in sorted(candidates.items()):
                if tid in existing:
                    continue
                ticket = tickets[tid]
                if candidate["handled_by"] == "human":
                    if budget.stop_now():
                        print(f"Budget cap hit ({budget.report()}); stopping before {tid}.")
                        break
                    client = client or get_client()
                    suggested_reply, usage = answerer.answer_ticket(
                        client, args.model, args.effort, ticket["text"], "self"
                    )
                    budget.add(usage)
                    usage_total.add(usage)
                    n_new_calls += 1
                else:
                    suggested_reply = candidate["answer_text"]

                pkg = build_package(ticket, candidate, split, suggested_reply)
                upsert_package(conn, pkg)
                print(f"  {tid} ({split}, {candidate['handled_by']})")

    print(f"\n{n_new_calls} new suggested-reply calls on {args.model}.")
    if n_new_calls:
        running = record_spend("build_queue_data", args.model, usage_total, note=f"{n_new_calls} tickets")
        print(f"Spend: ${usage_total.cost_usd(args.model):.4f} this run; project total now ${running:.4f}")
    print("Queue data ready: .venv/bin/python -m triage.queue_app")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
