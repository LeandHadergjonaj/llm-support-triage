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
from pathlib import Path

from triage.llm import REPO_ROOT

EVAL = REPO_ROOT / "data" / "eval"
DEST = REPO_ROOT / "data" / "review" / "label_review_sample.csv"
SMOKE_EVAL = REPO_ROOT / "data" / "smoke"
SMOKE_DEST = SMOKE_EVAL / "label_review_sample.csv"

COLUMNS = [
    "id",
    "split",
    "ticket_text",
    "drafted_intent",
    "drafted_urgency",
    "drafted_escalate",
    "drafted_escalation_reasons",
    "why_selected",
    "in_random_block",
    "drafter_note",
    "CORRECTED_intent",
    "CORRECTED_urgency",
    "CORRECTED_escalate",
    "CORRECTED_escalation_reasons",
    "reviewer_note",
]


def load_all(eval_dir: Path) -> list[dict]:
    rows = []
    for split in ("dev", "test"):
        path = eval_dir / f"{split}.jsonl"
        if not path.exists():
            raise SystemExit(f"{path} not found. Run: make data")
        for line in path.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                row["_split"] = split
                rows.append(row)
    return rows


RANDOM_CONTROL = "random control"


def select(
    rows: list[dict], n: int, seed: int, random_controls: int
) -> list[tuple[dict, str, bool]]:
    """Pick the review sample. Returns (ticket, why_selected, in_random_block).

    Two jobs that pull in different directions, so they are drawn separately:

    Targeted picks answer "are the labels wrong where we most suspect them" -- drafter
    disagreements, self-flagged uncertainty, escalations, hard cases. Their error rate is
    biased upwards by construction and says nothing about the set as a whole.

    The random block answers "how wrong is the label set overall". For that it has to be
    a uniform draw over every ticket, so it is sampled from all of them with its own
    random stream -- not from what the targeted picks left behind, which would exclude
    the most suspicious tickets and bias the estimate down. A ticket can therefore be in
    both: it is listed once, keeping its targeted reason, with `in_random_block` true.
    Counting errors over exactly the flagged rows gives the unbiased estimate.

    Drawing the two independently also means adding random controls later cannot displace
    a targeted pick already under review.
    """
    picked: dict[str, tuple[dict, str]] = {}
    targeted_budget = max(0, n - random_controls)

    rng = random.Random(seed)

    def take(candidates: list[dict], reason: str, quota: int) -> None:
        """Fill up to `quota` from `candidates`, never exceeding the targeted budget."""
        pool = [r for r in candidates if r["id"] not in picked]
        rng.shuffle(pool)
        for row in pool[: min(quota, targeted_budget - len(picked))]:
            picked[row["id"]] = (row, reason)

    take([r for r in rows if r.get("intent_disagreement")],
         "drafter disagreed with Bitext intent", 8)
    take([r for r in rows if r.get("drafter_uncertain")], "drafter flagged uncertain", 8)
    take([r for r in rows if r["labels"]["escalate"]], "escalation (rare, high-leverage)", 7)
    take([r for r in rows if r["hard_case"]], "authored hard case", 4)

    # Separate stream, so the size of this block never perturbs the picks above.
    block = random.Random(seed + 1000).sample(rows, min(random_controls, len(rows)))
    in_block = {r["id"] for r in block}
    for row in block:
        picked.setdefault(row["id"], (row, RANDOM_CONTROL))

    return sorted(
        ((row, reason, row["id"] in in_block) for row, reason in picked.values()),
        key=lambda triple: triple[0]["id"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", type=int, default=42)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--random-controls",
        type=int,
        default=15,
        metavar="N",
        help=(
            "Reserve this many purely random tickets. These are the only ones that "
            "estimate the label error rate of the set as a whole; the targeted picks "
            "are chosen for being suspicious and overstate it."
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Export from the throwaway set in data/smoke/ instead of the eval set.",
    )
    args = parser.parse_args()

    eval_dir, dest = (SMOKE_EVAL, SMOKE_DEST) if args.smoke else (EVAL, DEST)
    rows_all = load_all(eval_dir)
    selected = select(rows_all, args.n, args.seed, args.random_controls)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row, reason, in_block in selected:
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
                    "in_random_block": str(in_block).lower(),
                    "drafter_note": row.get("drafter_note", ""),
                    "CORRECTED_intent": "",
                    "CORRECTED_urgency": "",
                    "CORRECTED_escalate": "",
                    "CORRECTED_escalation_reasons": "",
                    "reviewer_note": "",
                }
            )

    counts: dict[str, int] = {}
    for _, reason, _ in selected:
        counts[reason] = counts.get(reason, 0) + 1
    block = sum(1 for _, _, in_block in selected if in_block)
    print(f"Wrote {dest.relative_to(REPO_ROOT)} ({len(selected)} tickets)")
    for reason, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:2d}  {reason}")
    print(
        f"\n  {block} of them are the random block (in_random_block=true) -- a uniform "
        f"draw over all {len(rows_all)} tickets.\n  That block, and only that block, "
        f"estimates the label error rate of the set as a whole."
    )
    flag = " --smoke" if args.smoke else ""
    print(
        "\nFill only the CORRECTED_* columns where the draft is wrong; leave them blank "
        f"where it is right.\nThen run: .venv/bin/python -m triage.import_review{flag}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
