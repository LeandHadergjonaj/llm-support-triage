"""Build the evaluation set: sample, fill placeholders, draft labels, split.

Stages, each cached on disk so a re-run does not re-pay for label drafting:

  1. sample   Bitext rows -> stratified sample -> placeholders filled  (deterministic)
  2. label    every ticket -> model-drafted urgency / escalation       (costs money)
  3. split    stratified dev / test -> data/eval/{dev,test}.jsonl       (deterministic)

Intent for Bitext-sourced tickets comes from the deterministic mapping in taxonomy.py,
not from the model. The model is asked for an intent anyway, blind, and disagreements
are recorded on the ticket as a label-quality signal.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from triage.labeler import labeler_json_schema, labeler_system, labeler_user
from triage.llm import DEFAULT_MODEL, REPO_ROOT, Usage, call_json, get_client
from triage.taxonomy import BITEXT_INTENT_TO_CATEGORY

DATA = REPO_ROOT / "data"
RAW_CSV = DATA / "raw" / "bitext_customer_support.csv"
HARD_CASES = DATA / "hard_cases.jsonl"
EVAL = DATA / "eval"
SAMPLED = EVAL / "_sampled.jsonl"
DRAFTED = EVAL / "_drafted.jsonl"

SEED = 20260921
PER_CATEGORY = 24  # 9 Bitext-backed categories -> 216, plus 36 authored hard cases
DEV_FRACTION = 0.60

# --- Stage 1: sample and fill ----------------------------------------------

CITIES = ["Leeds", "Bristol", "Glasgow", "Norwich", "Cardiff", "Sheffield", "Brighton"]
COUNTRIES = ["the United Kingdom", "England", "Scotland", "Wales"]
NAMES = [
    "Marta Lindqvist", "Dev Raina", "Aoife Brennan", "Tom Okafor",
    "Priya Shah", "Callum Reid", "Noor Haddad", "Ellen Whitcombe",
]
ACCOUNT_WORDS = ["standard", "premium"]


def _money(rng: random.Random) -> str:
    """Refund amounts, deliberately straddling the £100 escalation threshold.

    Without this the threshold rule is untestable: the upstream placeholder carries no
    value at all. Roughly a third land within £20 of the boundary, which is where the
    rule is hardest to apply.
    """
    bucket = rng.random()
    if bucket < 0.35:
        value = rng.uniform(12, 80)
    elif bucket < 0.65:
        value = rng.uniform(80, 125)
    else:
        value = rng.uniform(125, 850)
    return f"{value:.2f}" if rng.random() < 0.4 else str(int(round(value)))


def fill_placeholders(text: str, rng: random.Random) -> str:
    """Replace {{Placeholder}} tokens with plausible Hearth & Loom values.

    Each occurrence is filled independently, except Order Number which is held constant
    within a ticket so a single ticket does not reference two different orders.
    """
    order_number = str(rng.randint(46000, 53000))

    def sub(match: re.Match[str]) -> str:
        key = match.group(1)
        return {
            "Order Number": order_number,
            "Invoice Number": str(rng.randint(80000, 89999)),
            "Person Name": rng.choice(NAMES),
            "Account Type": rng.choice(ACCOUNT_WORDS),
            "Account Category": rng.choice(ACCOUNT_WORDS),
            "Currency Symbol": "£",
            "Refund Amount": _money(rng),
            "Delivery City": rng.choice(CITIES),
            "Delivery Country": rng.choice(COUNTRIES),
        }.get(key, match.group(0))

    return re.sub(r"\{\{(.*?)\}\}", sub, text)


def _order_pool(rows: list[dict], quota: int, rng: random.Random) -> list[dict]:
    """Shuffle an intent's rows, front-loading ones that state a money amount.

    Only `track_refund` and `get_refund` carry the {{Refund Amount}} placeholder, and
    only in a minority of rows, so an unweighted sample yields two or three tickets with
    a figure in them across the whole set -- too few to say anything about the £100
    escalation threshold. Up to half of each intent's quota is therefore drawn from
    money-bearing rows where they exist. This is a deliberate departure from the upstream
    distribution, made so the rule is measurable; it is recorded in data/README.md.
    """
    with_money = [r for r in rows if "{{Refund Amount}}" in r["instruction"]]
    without = [r for r in rows if "{{Refund Amount}}" not in r["instruction"]]
    if not with_money:
        pool = rows[:]
        rng.shuffle(pool)
        return pool
    rng.shuffle(with_money)
    rng.shuffle(without)
    head = with_money[: quota // 2]
    tail = with_money[quota // 2 :] + without
    rng.shuffle(tail)
    return head + tail


def stage_sample() -> list[dict]:
    """Stratified sample by target category, spread evenly over source intents."""
    import csv

    if not RAW_CSV.exists():
        raise SystemExit(
            f"{RAW_CSV} not found. Run: .venv/bin/python scripts/fetch_dataset.py"
        )

    rng = random.Random(SEED)
    by_intent: dict[str, list[dict]] = defaultdict(list)
    with RAW_CSV.open(newline="") as fh:
        for row in csv.DictReader(fh):
            if row["intent"] in BITEXT_INTENT_TO_CATEGORY:
                by_intent[row["intent"]].append(row)

    by_category: dict[str, list[str]] = defaultdict(list)
    for intent, category in BITEXT_INTENT_TO_CATEGORY.items():
        by_category[category].append(intent)

    tickets: list[dict] = []
    seen_text: set[str] = set()
    for category in sorted(by_category):
        intents = sorted(by_category[category])
        # Spread PER_CATEGORY over the source intents as evenly as the count allows.
        quotas = [PER_CATEGORY // len(intents)] * len(intents)
        for i in range(PER_CATEGORY % len(intents)):
            quotas[i] += 1
        for intent, quota in zip(intents, quotas, strict=True):
            pool = _order_pool(by_intent[intent], quota, rng)
            taken = 0
            for row in pool:
                if taken >= quota:
                    break
                text = fill_placeholders(row["instruction"].strip(), rng)
                if text.lower() in seen_text:
                    continue
                seen_text.add(text.lower())
                taken += 1
                tickets.append(
                    {
                        "text": text,
                        "source": "bitext",
                        "hard_case": False,
                        "hard_case_kind": None,
                        "author_note": None,
                        "bitext_intent": intent,
                        "bitext_flags": row["flags"],
                        "mapped_intent": category,
                    }
                )

    for row in (json.loads(line) for line in HARD_CASES.read_text().splitlines() if line.strip()):
        tickets.append(
            {
                "text": row["text"],
                "source": "authored_hard_case",
                "hard_case": True,
                "hard_case_kind": row["kind"],
                "author_note": row["author_note"],
                "bitext_intent": None,
                "bitext_flags": None,
                "mapped_intent": None,
            }
        )

    rng.shuffle(tickets)
    for i, ticket in enumerate(tickets, start=1):
        ticket["id"] = f"hl-{i:04d}"
    return tickets


# --- Stage 2: draft labels --------------------------------------------------


def stage_label(tickets: list[dict], model: str, workers: int) -> tuple[list[dict], Usage]:
    client = get_client()
    system = labeler_system()
    schema = labeler_json_schema()
    total = Usage()

    def one(ticket: dict) -> dict:
        draft, usage = call_json(
            client,
            model=model,
            system=system,
            user=labeler_user(ticket["text"]),
            json_schema=schema,
        )
        return {**ticket, "draft": draft, "_usage": usage}

    done = 0
    labelled: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for result in pool.map(one, tickets):
            total.add(result.pop("_usage"))
            labelled.append(result)
            done += 1
            if done % 25 == 0 or done == len(tickets):
                print(f"  drafted {done}/{len(tickets)}", flush=True)
    labelled.sort(key=lambda t: t["id"])
    return labelled, total


def assemble(labelled: list[dict]) -> list[dict]:
    """Turn drafts into final tickets, deciding which intent is authoritative."""
    out = []
    for row in labelled:
        draft = row["draft"]
        if row["source"] == "bitext":
            intent = row["mapped_intent"]
            intent_provenance = "bitext_mapped"
        else:
            intent = draft["intent"]
            intent_provenance = "model_drafted"

        escalate = bool(draft["escalate"])
        reasons = sorted(set(draft["escalation_reasons"])) if escalate else []

        out.append(
            {
                "id": row["id"],
                "text": row["text"],
                "source": row["source"],
                "hard_case": row["hard_case"],
                "hard_case_kind": row["hard_case_kind"],
                "labels": {
                    "intent": intent,
                    "urgency": draft["urgency"],
                    "escalate": escalate,
                    "escalation_reasons": reasons,
                },
                "label_provenance": {
                    "intent": intent_provenance,
                    "urgency": "model_drafted",
                    "escalate": "model_drafted",
                },
                "human_reviewed": False,
                "review_note": None,
                "bitext_intent": row["bitext_intent"],
                "bitext_flags": row["bitext_flags"],
                # Signals for the review pass, not labels.
                "drafter_uncertain": bool(draft["uncertain"]),
                "drafter_note": draft["note"],
                "drafter_intent_blind": draft["intent"],
                "intent_disagreement": (
                    row["source"] == "bitext" and draft["intent"] != row["mapped_intent"]
                ),
                "author_note": row["author_note"],
            }
        )
    return out


# --- Stage 3: split ---------------------------------------------------------


def stage_split(tickets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Stratify on the strata known before labelling: category for Bitext rows, kind
    for authored ones. Stratifying on drafted labels would bake drafting error into
    the split."""
    rng = random.Random(SEED + 1)
    strata: dict[str, list[dict]] = defaultdict(list)
    for ticket in tickets:
        key = ticket["hard_case_kind"] if ticket["hard_case"] else ticket["labels"]["intent"]
        strata[f"{ticket['source']}:{key}"].append(ticket)

    dev: list[dict] = []
    test: list[dict] = []
    for key in sorted(strata):
        group = strata[key][:]
        rng.shuffle(group)
        cut = round(len(group) * DEV_FRACTION)
        dev.extend(group[:cut])
        test.extend(group[cut:])
    dev.sort(key=lambda t: t["id"])
    test.sort(key=lambda t: t["id"])
    return dev, test


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--relabel",
        action="store_true",
        help="Re-draft labels even if a cached draft exists (costs money).",
    )
    args = parser.parse_args()

    print("Stage 1: sampling")
    tickets = stage_sample()
    write_jsonl(SAMPLED, tickets)
    print(f"  {len(tickets)} tickets -> {SAMPLED.relative_to(REPO_ROOT)}")

    if DRAFTED.exists() and not args.relabel:
        print(f"Stage 2: reusing cached drafts ({DRAFTED.relative_to(REPO_ROOT)})")
        labelled = [json.loads(line) for line in DRAFTED.read_text().splitlines() if line.strip()]
        if {t["id"] for t in labelled} != {t["id"] for t in tickets}:
            raise SystemExit("Cached drafts do not match the current sample. Re-run --relabel.")
    else:
        print(f"Stage 2: drafting labels with {args.model} (this costs money)")
        labelled, usage = stage_label(tickets, args.model, args.workers)
        write_jsonl(DRAFTED, labelled)
        print(f"  drafting usage: {json.dumps(usage.summary(args.model))}")

    final = assemble(labelled)

    print("Stage 3: splitting")
    dev, test = stage_split(final)
    write_jsonl(EVAL / "dev.jsonl", dev)
    write_jsonl(EVAL / "test.jsonl", test)
    print(f"  dev  {len(dev):4d} -> data/eval/dev.jsonl")
    print(f"  test {len(test):4d} -> data/eval/test.jsonl")

    uncertain = sum(1 for t in final if t["drafter_uncertain"])
    disagree = sum(1 for t in final if t["intent_disagreement"])
    bitext_n = sum(1 for t in final if t["source"] == "bitext")
    print(
        f"\nLabel-quality signals: drafter flagged {uncertain}/{len(final)} uncertain; "
        f"drafter's blind intent disagreed with the Bitext mapping on {disagree}/{bitext_n}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
