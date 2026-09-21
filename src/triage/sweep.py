"""Apply the brief v2 clarifications to every ticket they touch.

    .venv/bin/python -m triage.sweep --dry-run
    .venv/bin/python -m triage.sweep --apply

WHAT THIS IS, AND WHAT IT IS NOT

The second-opinion review pass read 55 tickets and found two systematic label errors
(`DECISIONS.md` D-008, D-009). Both were enumerable: a rule describes every ticket that
has them. Rather than re-read the remaining 197 one at a time, this applies those rules
mechanically, to the whole set, from the updated brief.

That is a **consistency mechanism, not a check.** It can only find the errors its rules
describe; it cannot notice anything else wrong with a ticket. A ticket it touches is
therefore NOT marked `reviewed`, and `metrics.label_error_rate` must keep counting it as
unchecked -- otherwise the sweep would appear to have verified 13 tickets when it has
verified none. Measuring what is left is the job of the fresh random review block.

It is run by a model. No part of it is a human pass.

THE TWO RULES

`out_of_scope_contradiction` (brief v2 change 3, from D-008)
    A ticket escalated with reason `out_of_scope` whose intent is one of the other ten
    categories. The brief now says the escalation reason is only available when the
    intent is also `out_of_scope`, because they are the same judgement. The intent is
    left alone and the escalation reason is dropped: intent on a Bitext ticket comes
    from the upstream mapping and is the better-evidenced of the two.

`pre_dispatch_window` (brief v2 change 4, from D-009)
    A cancellation or change to a live order, labelled below `high`. Matched on the
    upstream Bitext intent (`cancel_order`, `change_order`) rather than on the ticket
    text, because that label is dataset-derived rather than a judgement of mine, which
    is what keeps this a sweep rather than a re-labelling. Two carve-outs from the brief:
    additions stay `low`, and the ask must presuppose a live order.

Everything the sweep changes is written to results/sweep_<stamp>.json, with the previous
labels, so any of it can be argued with or undone.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime

from triage.llm import REPO_ROOT
from triage.taxonomy import brief_version

EVAL = REPO_ROOT / "data" / "eval"
RESULTS = REPO_ROOT / "results"

# The sweep is run by a model. This value is recorded on every ticket it touches and
# must never be written in a way that implies a person did it.
SWEPT_BY = "claude-opus-5 (Anthropic)"

# Upstream Bitext intents that by construction are a change to an order the customer
# already placed. Used instead of matching on ticket text: the Bitext intent is a
# property of the dataset, so selecting on it cannot smuggle in my own reading.
LIVE_ORDER_CHANGE_INTENTS = frozenset({"cancel_order", "change_order"})

# Brief v2 §4: "Adding items is the exception and stays `low`."
ADDITION = re.compile(r"\badd(?:ing|s)?\b", re.IGNORECASE)

# Brief v2 §4: "The ask must presuppose a live order." Every Bitext order-change ticket
# should name one; this is the guard that proves it rather than assuming it.
NAMES_AN_ORDER = re.compile(r"\b(order|purchase)\b", re.IGNORECASE)


def _clean(text: str) -> str:
    return " ".join(text.split())


def out_of_scope_contradiction(ticket: dict) -> tuple[dict, str] | None:
    """Brief v2 change 3: the escalation reason needs the matching intent."""
    labels = ticket["labels"]
    if "out_of_scope" not in labels["escalation_reasons"]:
        return None
    if labels["intent"] == "out_of_scope":
        return None
    reasons = [r for r in labels["escalation_reasons"] if r != "out_of_scope"]
    note = (
        f"Escalated `out_of_scope` while the intent is `{labels['intent']}`; brief v2 §5 "
        f"makes the reason available only when the intent is `out_of_scope` too. Intent "
        f"kept, escalation reason dropped."
    )
    return {"escalate": bool(reasons), "escalation_reasons": reasons}, note


def pre_dispatch_window(ticket: dict) -> tuple[dict, str] | None:
    """Brief v2 change 4: a change to a live order before dispatch is `high`."""
    if ticket.get("bitext_intent") not in LIVE_ORDER_CHANGE_INTENTS:
        return None
    if ticket["labels"]["urgency"] == "high":
        return None
    text = ticket["text"]
    if ADDITION.search(text):
        return None  # additions stay low; missing the window costs a second order
    if not NAMES_AN_ORDER.search(text):
        return None  # no live order presupposed, so no window to close
    note = (
        f"Upstream intent `{ticket['bitext_intent']}`: a change to a live order that has "
        f"to take effect before dispatch, which brief v2 §4 makes `high`. Not an "
        f"addition, and the ticket names an order."
    )
    return {"urgency": "high"}, note


RULES = {
    "out_of_scope_contradiction": (out_of_scope_contradiction, "v2 change 3 (D-008)"),
    "pre_dispatch_window": (pre_dispatch_window, "v2 change 4 (D-009)"),
}


def sweep_ticket(ticket: dict) -> list[dict]:
    """Every change the rules make to one ticket. Usually zero or one."""
    changes = []
    for pattern, (rule, brief_change) in RULES.items():
        hit = rule(ticket)
        if hit is None:
            continue
        patch, note = hit
        was = {k: ticket["labels"][k] for k in patch}
        changes.append(
            {
                "id": ticket["id"],
                "pattern": pattern,
                "brief_change": brief_change,
                "was": was,
                "now": patch,
                "note": note,
                "text": _clean(ticket["text"]),
                # A ticket the review pass already looked at is being changed because
                # the brief moved under it, not because the review was wrong. Called
                # out so that case can be counted separately.
                "previously_reviewed": bool(ticket.get("reviewed")),
            }
        )
        ticket["labels"].update(patch)
    return changes


FIELD_TO_PROVENANCE = {
    "intent": "intent",
    "urgency": "urgency",
    "escalate": "escalate",
    "escalation_reasons": "escalate",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Print what would change.")
    group.add_argument("--apply", action="store_true", help="Write the changes.")
    args = parser.parse_args()

    version = brief_version()
    splits = {}
    for split in ("dev", "test"):
        path = EVAL / f"{split}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} not found. Run: make data")
        splits[split] = [
            json.loads(line) for line in path.read_text().splitlines() if line.strip()
        ]

    all_changes: list[dict] = []
    for split, tickets in splits.items():
        for ticket in tickets:
            for change in sweep_ticket(ticket):
                change["split"] = split
                all_changes.append(change)
                if not args.apply:
                    continue
                for field in change["now"]:
                    ticket["label_provenance"][FIELD_TO_PROVENANCE[field]] = "rule_sweep"
                ticket["sweep"] = {
                    "pattern": change["pattern"],
                    "brief_version": version,
                    "brief_change": change["brief_change"],
                    "by": SWEPT_BY,
                    "note": change["note"],
                    "was": change["was"],
                }

    by_pattern: dict[str, int] = {}
    for change in all_changes:
        by_pattern[change["pattern"]] = by_pattern.get(change["pattern"], 0) + 1

    verb = "Would change" if args.dry_run else "Changed"
    print(f"Sweeping {sum(len(v) for v in splits.values())} tickets against brief {version}.\n")
    for pattern in RULES:
        hits = [c for c in all_changes if c["pattern"] == pattern]
        print(f"## {pattern} -- {RULES[pattern][1]}: {len(hits)} ticket(s)\n")
        for change in hits:
            was = ", ".join(f"{k}={v!r}" for k, v in change["was"].items())
            now = ", ".join(f"{k}={v!r}" for k, v in change["now"].items())
            flag = "  [was already reviewed]" if change["previously_reviewed"] else ""
            print(f"  {change['id']} [{change['split']}]{flag}")
            print(f"      {was}  ->  {now}")
            print(f"      {change['text'][:110]}")
        print()
    already = sum(1 for c in all_changes if c["previously_reviewed"])
    print(
        f"{verb} {len(all_changes)} label(s) across {len({c['id'] for c in all_changes})} "
        f"ticket(s): {by_pattern}. {already} of them had already been through the review "
        f"pass and are changing because the brief moved, not because the review was wrong."
    )

    if args.dry_run:
        print("\nDry run: nothing written. Re-run with --apply.")
        return 0

    for split, tickets in splits.items():
        with (EVAL / f"{split}.jsonl").open("w") as fh:
            for ticket in tickets:
                fh.write(json.dumps(ticket, ensure_ascii=False) + "\n")

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    record = {
        "at": datetime.now(UTC).isoformat(timespec="seconds"),
        "brief_version": version,
        "by": SWEPT_BY,
        "is_a_human_pass": False,
        "what_this_is": (
            "A mechanical application of two rules from brief v2 to every ticket they "
            "match. It is a consistency mechanism, not a check: it finds only the errors "
            "its rules describe, and a swept ticket is not `reviewed`."
        ),
        "rules": {k: v[1] for k, v in RULES.items()},
        "counts": by_pattern,
        "changes": all_changes,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    dest = RESULTS / f"{stamp}_sweep_brief_{version}.json"
    dest.write_text(json.dumps(record, indent=2, ensure_ascii=False))
    print(f"\nWrote {dest.relative_to(REPO_ROOT)}")
    print("Swept tickets are NOT marked `reviewed`. Re-measure with a fresh random block.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
