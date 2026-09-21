"""Fold hand corrections from the review CSV back into the eval set.

Every row present in the CSV is marked `human_reviewed: true`, whether or not it was
changed -- a reviewer confirming a label is as much a review as a reviewer fixing one.
Corrected labels have their provenance flipped from `model_drafted` to `human_reviewed`.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys

from triage.llm import REPO_ROOT
from triage.metrics import label_error_rate
from triage.taxonomy import ESCALATION_REASONS, INTENTS, URGENCIES

EVAL = REPO_ROOT / "data" / "eval"
SOURCE = REPO_ROOT / "data" / "review" / "label_review_sample.csv"
SMOKE_EVAL = REPO_ROOT / "data" / "smoke"
SMOKE_SOURCE = SMOKE_EVAL / "label_review_sample.csv"


def _parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"true", "yes", "y", "1"}:
        return True
    if lowered in {"false", "no", "n", "0"}:
        return False
    raise SystemExit(f"Cannot read {value!r} as true/false in CORRECTED_escalate")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Apply the review sample in data/smoke/ instead of the eval set.",
    )
    args = parser.parse_args()

    eval_dir, source = (SMOKE_EVAL, SMOKE_SOURCE) if args.smoke else (EVAL, SOURCE)
    if not source.exists():
        raise SystemExit(f"{source} not found. Run: make review")

    corrections: dict[str, dict] = {}
    with source.open(newline="") as fh:
        for row in csv.DictReader(fh):
            corrections[row["id"]] = row

    changed = confirmed = 0
    for split in ("dev", "test"):
        path = eval_dir / f"{split}.jsonl"
        tickets = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
        for ticket in tickets:
            row = corrections.get(ticket["id"])
            if row is None:
                continue
            ticket["human_reviewed"] = True
            ticket["review_note"] = row.get("reviewer_note") or None
            # Why this ticket was in the sample, carried onto the ticket so the error
            # rate can be reported for the random block separately from the targeted
            # picks. Only the random block estimates anything about the set as a whole.
            ticket["review_selection"] = {
                "reason": row.get("why_selected") or "unknown",
                "in_random_block": row.get("in_random_block", "false") == "true",
            }
            touched = False

            if (value := row["CORRECTED_intent"].strip()):
                if value not in INTENTS:
                    raise SystemExit(f"{ticket['id']}: unknown intent {value!r}")
                ticket["labels"]["intent"] = value
                ticket["label_provenance"]["intent"] = "human_reviewed"
                touched = True
            if (value := row["CORRECTED_urgency"].strip()):
                if value not in URGENCIES:
                    raise SystemExit(f"{ticket['id']}: unknown urgency {value!r}")
                ticket["labels"]["urgency"] = value
                ticket["label_provenance"]["urgency"] = "human_reviewed"
                touched = True
            if (value := row["CORRECTED_escalate"].strip()):
                ticket["labels"]["escalate"] = _parse_bool(value)
                ticket["label_provenance"]["escalate"] = "human_reviewed"
                touched = True
            if (value := row["CORRECTED_escalation_reasons"].strip()):
                reasons = sorted({r.strip() for r in value.split("|") if r.strip()})
                unknown = [r for r in reasons if r not in ESCALATION_REASONS]
                if unknown:
                    raise SystemExit(f"{ticket['id']}: unknown escalation reasons {unknown}")
                ticket["labels"]["escalation_reasons"] = reasons
                ticket["label_provenance"]["escalate"] = "human_reviewed"
                touched = True
            if not ticket["labels"]["escalate"]:
                ticket["labels"]["escalation_reasons"] = []

            ticket["review_corrected"] = touched
            changed += touched
            confirmed += not touched

        with path.open("w") as fh:
            for ticket in tickets:
                fh.write(json.dumps(ticket, ensure_ascii=False) + "\n")

    print(f"Applied review to {changed + confirmed} tickets: {changed} corrected, {confirmed} confirmed.")

    reviewed = [
        json.loads(line)
        for split in ("dev", "test")
        for line in (eval_dir / f"{split}.jsonl").read_text().splitlines()
        if line.strip()
    ]
    rates = label_error_rate(reviewed)
    block = rates["random_block"]
    if block["reviewed"]:
        low, high = block["ci95"]
        print(
            f"\nLabel error rate on the random block: {block['corrected']}/"
            f"{block['reviewed']} = {block['error_rate']:.1%}, "
            f"95% CI [{low:.1%}, {high:.1%}] (Wilson)."
        )
        targeted = rates["targeted_picks"]
        if targeted["reviewed"]:
            print(
                f"Targeted picks: {targeted['corrected']}/{targeted['reviewed']} = "
                f"{targeted['error_rate']:.1%} -- biased upwards by construction, "
                f"a diagnostic rather than an estimate of the set."
            )
    print("\nRe-run the eval to score against the corrected labels.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
