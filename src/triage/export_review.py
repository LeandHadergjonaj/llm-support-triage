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
REVIEW_DIR = REPO_ROOT / "data" / "review"
DEST = REVIEW_DIR / "label_review_sample.csv"
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


def round_dest(round_no: int, smoke: bool) -> Path:
    """Where round N's CSV lives. Round 1 keeps its original filename."""
    base = SMOKE_EVAL if smoke else REVIEW_DIR
    if round_no == 1:
        return SMOKE_DEST if smoke else DEST
    return base / f"label_review_round{round_no}.csv"


def fresh_block(rows: list[dict], n: int, seed: int) -> list[tuple[dict, str, bool]]:
    """A later round's random block: a uniform draw over the NOT-YET-REVIEWED tickets.

    Round 1's block was drawn over all 252 and its tickets have since been corrected, so
    re-drawing over the whole set would measure a mixture of a checked stratum and an
    unchecked one -- and would mostly measure me agreeing with myself on the tickets I
    already read. Drawing from the unreviewed remainder instead gives a clean estimate of
    one well-defined population: the part of the label set nobody has looked at.

    Tickets the rule sweep touched are deliberately left in the pool. The sweep applied a
    rule without re-reading anything, so it is not a check, and a block that excluded its
    tickets could not catch it being wrong.
    """
    pool = [r for r in rows if not r.get("reviewed")]
    if n > len(pool):
        raise SystemExit(f"Asked for {n} but only {len(pool)} tickets are unreviewed.")
    shuffled = list(pool)
    random.Random(seed).shuffle(shuffled)
    return sorted(
        ((row, RANDOM_CONTROL, True) for row in shuffled[:n]),
        key=lambda triple: triple[0]["id"],
    )


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
    rows: list[dict],
    n: int,
    seed: int,
    random_controls: int,
    pinned: dict[str, tuple[str, bool]] | None = None,
) -> list[tuple[dict, str, bool]]:
    """Pick the review sample. Returns (ticket, why_selected, in_random_block).

    Two jobs that pull in different directions, so they are drawn separately:

    Targeted picks answer "are the labels wrong where we most suspect them" -- drafter
    disagreements, self-flagged uncertainty, escalations, hard cases. Their error rate is
    biased upwards by construction and says nothing about the set as a whole.

    The random block answers "how wrong is the label set overall". For that it has to be
    a uniform draw over every ticket, so it is sampled from all of them with its own
    random stream -- not from what the targeted picks left behind, which would exclude
    the most suspicious tickets and bias the estimate down. A ticket can be in both: it
    is listed once, keeping its targeted reason, with `in_random_block` true. Counting
    errors over exactly the flagged rows gives the unbiased estimate.

    `pinned` carries the previous export's rows, so re-exporting never pulls a ticket out
    from under a reviewer. Growing the block therefore tops the existing one up rather
    than redrawing it, and that keeps the block uniform: a ticket already in is in, and
    every ticket not already in has the same chance of being drawn in the top-up, so
    every ticket ends up with the same inclusion probability of `random_controls` / N.
    """
    pinned = pinned or {}
    picked: dict[str, tuple[dict, str]] = {}
    by_id = {r["id"]: r for r in rows}
    targeted_budget = max(0, n - random_controls)

    # Whatever the reviewer already has stays, with the reason it was given.
    block_ids: set[str] = set()
    for ticket_id, (reason, was_in_block) in pinned.items():
        if ticket_id not in by_id:
            continue  # the eval set was rebuilt and this ticket is gone
        picked[ticket_id] = (by_id[ticket_id], reason)
        if was_in_block:
            block_ids.add(ticket_id)

    rng = random.Random(seed)

    def take(candidates: list[dict], reason: str, quota: int) -> None:
        """Fill up to `quota` from `candidates`, never exceeding the targeted budget."""
        pool = [r for r in candidates if r["id"] not in picked]
        rng.shuffle(pool)
        already = sum(1 for _, why in picked.values() if why == reason)
        room = min(quota - already, targeted_budget - len(picked))
        for row in pool[:max(0, room)]:
            picked[row["id"]] = (row, reason)

    take([r for r in rows if r.get("intent_disagreement")],
         "drafter disagreed with Bitext intent", 8)
    take([r for r in rows if r.get("drafter_uncertain")], "drafter flagged uncertain", 8)
    take([r for r in rows if r["labels"]["escalate"]], "escalation (rare, high-leverage)", 7)
    take([r for r in rows if r["hard_case"]], "authored hard case", 4)

    # Top the random block up along one fixed shuffle. A prefix is nested in k, so
    # raising the block later keeps everything already in it; random.sample is not, and
    # would silently swap tickets out.
    shuffled = list(rows)
    random.Random(seed + 1000).shuffle(shuffled)
    for row in shuffled:
        if len(block_ids) >= min(random_controls, len(rows)):
            break
        block_ids.add(row["id"])
    for ticket_id in block_ids:
        picked.setdefault(ticket_id, (by_id[ticket_id], RANDOM_CONTROL))

    return sorted(
        ((row, reason, row["id"] in block_ids) for row, reason in picked.values()),
        key=lambda triple: triple[0]["id"],
    )


REVIEWER_COLUMNS = (
    "CORRECTED_intent",
    "CORRECTED_urgency",
    "CORRECTED_escalate",
    "CORRECTED_escalation_reasons",
    "reviewer_note",
)


def read_existing(dest: Path) -> dict[str, dict]:
    """Load a previous export, so re-exporting adds to it instead of replacing it.

    Without this, growing the sample overwrites the file and throws away anything the
    reviewer has already typed. The rows that come back here are pinned into the new
    selection and their CORRECTED_* values are carried over verbatim.
    """
    if not dest.exists():
        return {}
    with dest.open(newline="") as fh:
        return {row["id"]: row for row in csv.DictReader(fh)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-n", type=int, default=57)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--random-controls",
        type=int,
        default=30,
        metavar="N",
        help=(
            "Reserve this many purely random tickets. These are the only ones that "
            "estimate the label error rate of the set as a whole; the targeted picks "
            "are chosen for being suspicious and overstate it."
        ),
    )
    parser.add_argument(
        "--round",
        type=int,
        default=1,
        dest="round_no",
        metavar="N",
        help=(
            "Which review round this is. Round 1 is the original mixed sample and is "
            "pinned so re-exporting never drops a row. Round 2 and later draw a fresh "
            "random block from the tickets no round has reviewed yet, with no targeted "
            "picks -- their only job is to re-measure the error rate after a correction "
            "pass. Rounds are never pooled: they sample different populations."
        ),
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Export from the throwaway set in data/smoke/ instead of the eval set.",
    )
    args = parser.parse_args()

    eval_dir = SMOKE_EVAL if args.smoke else EVAL
    dest = round_dest(args.round_no, args.smoke)
    rows_all = load_all(eval_dir)
    existing = read_existing(dest)
    if args.round_no > 1:
        selected = fresh_block(rows_all, args.random_controls, args.seed + args.round_no)
    else:
        pinned = {
            ticket_id: (row.get("why_selected", RANDOM_CONTROL),
                        row.get("in_random_block", "false") == "true")
            for ticket_id, row in existing.items()
        }
        selected = select(rows_all, args.n, args.seed, args.random_controls, pinned)
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
                    # Anything the reviewer has already typed is carried over.
                    **{c: existing.get(row["id"], {}).get(c, "") for c in REVIEWER_COLUMNS},
                }
            )

    counts: dict[str, int] = {}
    for _, reason, _ in selected:
        counts[reason] = counts.get(reason, 0) + 1
    block = sum(1 for _, _, in_block in selected if in_block)
    print(f"Wrote {dest.relative_to(REPO_ROOT)} ({len(selected)} tickets, round {args.round_no})")
    for reason, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:2d}  {reason}")
    if args.round_no > 1:
        pool = sum(1 for r in rows_all if not r.get("reviewed"))
        print(
            f"\n  All {block} are a uniform draw over the {pool} tickets no round has "
            f"reviewed yet.\n  They estimate the error rate of that population -- not of "
            f"the whole set, part of\n  which has already been corrected, and not poolable "
            f"with round 1, which sampled\n  a different population at a different time."
        )
    else:
        print(
            f"\n  {block} of them are the random block (in_random_block=true) -- a uniform "
            f"draw over all {len(rows_all)} tickets.\n  That block, and only that block, "
            f"estimates the label error rate of the set as a whole."
        )
    flag = " --smoke" if args.smoke else ""
    rnd = f" --round {args.round_no}" if args.round_no > 1 else ""
    print(
        "\nFill only the CORRECTED_* columns where the draft is wrong; leave them blank "
        f"where it is right.\nThen run: .venv/bin/python -m triage.import_review{flag}{rnd}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
