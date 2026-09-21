"""Export a sample of tickets for a human to check and correct.

The reference labels are model-drafted. This is the mechanism for fixing that. The
sample is deliberately NOT random: it is weighted towards the tickets where a drafting
error would do the most damage to the eval --

  - everything the drafter flagged as uncertain
  - every ticket where the drafter's blind intent disagreed with the Bitext mapping
  - escalations, which are rare and therefore individually high-leverage
  - hard cases, which have no upstream label to fall back on

Edit the CSV in place, then run `import_review.py` to fold the corrections back in.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys

from triage.llm import REPO_ROOT

EVAL = REPO_ROOT / "data" / "eval"
DEST = REPO_ROOT / "data" / "review" / "label_review_sample.csv"

COLUMNS = [
    "id",
    "split",
    "ticket_text",
    "drafted_intent",
    "drafted_urgency",
    "drafted_escalate",
    "drafted_escalation_reasons",
    "why_selected",
    "drafter_note",
    "CORRECTED_intent",
    "CORRECTED_urgency",
    "CORRECTED_escalate",
    "CORRECTED_escalation_reasons",
    "reviewer_note",
]


def load_all() -> list[dict]:
    rows = []
    for split in ("dev", "test"):
        path = EVAL / f"{split}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} not found. Run: make data")
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_split"] = split
                rows.append(row)
    return rows


def select(rows: list[dict], n: int, seed: int) -> list[tuple[dict, str]]:
    rng = random.Random(seed)
    picked: dict[str, tuple[dict, str]] = {}

    def take(candidates: list[dict], reason: str, quota: int) -> None:
        """Fill up to `quota` from `candidates`, never exceeding the overall budget."""
        pool = [r for r in candidates if r["id"] not in picked]
        rng.shuffle(pool)
        for row in pool[: min(quota, n - len(picked))]:
            picked[row["id"]] = (row, reason)

    # Priority order. Controls come last and only fill whatever budget is left, so a
    # targeted pick is never displaced by a random one.
    take([r for r in rows if r.get("intent_disagreement")], "drafter disagreed with Bitext intent", 8)
    take([r for r in rows if r.get("drafter_uncertain")], "drafter flagged uncertain", 8)
    take([r for r in rows if r["labels"]["escalate"]], "escalation (rare, high-leverage)", 7)
    take([r for r in rows if r["hard_case"]], "authored hard case", 4)
    take([r for r in rows if not r["labels"]["escalate"] and not r["hard_case"]], "random control", n)

    return sorted(picked.values(), key=lambda pair: pair[0]["id"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", type=int, default=30)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    selected = select(load_all(), args.n, args.seed)
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with DEST.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row, reason in selected:
            labels = row["labels"]
            writer.writerow(
                {
                    "id": row["id"],
                    "split": row["_split"],
                    "ticket_text": row["text"],
                    "drafted_intent": labels["intent"],
                    "drafted_urgency": labels["urgency"],
                    "drafted_escalate": str(labels["escalate"]).lower(),
                    "drafted_escalation_reasons": "|".join(labels["escalation_reasons"]),
                    "why_selected": reason,
                    "drafter_note": row.get("drafter_note", ""),
                    "CORRECTED_intent": "",
                    "CORRECTED_urgency": "",
                    "CORRECTED_escalate": "",
                    "CORRECTED_escalation_reasons": "",
                    "reviewer_note": "",
                }
            )

    counts: dict[str, int] = {}
    for _, reason in selected:
        counts[reason] = counts.get(reason, 0) + 1
    print(f"Wrote {DEST.relative_to(REPO_ROOT)} ({len(selected)} tickets)")
    for reason, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:2d}  {reason}")
    print(
        "\nFill only the CORRECTED_* columns where the draft is wrong; leave them blank "
        "where it is right.\nThen run: .venv/bin/python -m triage.import_review"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
