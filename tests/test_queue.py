"""No-API-key checks for the Phase 4 review queue: the approve/edit/reject decision logic
and the storage layer's round-trip and aggregation. Not a Flask test -- `decide_status` is
deliberately a pure function so this doesn't need one."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from triage.queue_app import decide_status
from triage.queue_db import (
    SCHEMA,
    dump_packages,
    get_package,
    get_review,
    package_ids,
    reset_reviews,
    save_review,
    save_spot_check,
    seed_if_empty,
    stats,
    upsert_package,
)


def test_decide_status_approve_as_is():
    assert decide_status("approve", "ignored", "the reply") == ("approved", "the reply")


def test_decide_status_edit_approve_unchanged_counts_as_approved():
    assert decide_status("edit_approve", "the reply", "the reply") == ("approved", "the reply")


def test_decide_status_edit_approve_changed_counts_as_edited():
    assert decide_status("edit_approve", "a different reply", "the reply") == ("edited", "a different reply")


def test_decide_status_reject():
    assert decide_status("reject", "x", "the reply") == ("rejected", None)


def test_decide_status_unknown_action_raises():
    try:
        decide_status("bogus", "x", "y")
        assert False, "expected ValueError"
    except ValueError:
        pass


def _memory_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def _package(ticket_id: str, handled_by: str) -> dict:
    return {
        "id": ticket_id, "split": "dev", "ticket_text": "text", "intent": "product_issue",
        "urgency": "high", "confidence": 0.9, "escalation_reasons": ["product_safety"],
        "rationale": "why", "handled_by": handled_by, "order_facts": "none",
        "policy_docs": ["product_safety.md"], "handover_note": "note" if handled_by == "human" else None,
        "suggested_reply": "suggested text", "generated_at": "2026-09-21T00:00:00Z",
    }


def test_upsert_and_get_package_round_trips_json_fields():
    conn = _memory_conn()
    upsert_package(conn, _package("hl-1", "human"))
    pkg = get_package(conn, "hl-1")
    assert pkg["escalation_reasons"] == ["product_safety"]
    assert pkg["policy_docs"] == ["product_safety.md"]


def test_save_review_upsert_overwrites():
    conn = _memory_conn()
    upsert_package(conn, _package("hl-1", "human"))
    save_review(conn, "hl-1", "approved", "suggested text", "", "t1")
    save_review(conn, "hl-1", "edited", "changed text", "note", "t2")
    review = get_review(conn, "hl-1")
    assert review["status"] == "edited" and review["final_reply_text"] == "changed text"


def test_stats_aggregation():
    conn = _memory_conn()
    upsert_package(conn, _package("hl-1", "human"))
    upsert_package(conn, _package("hl-2", "human"))
    upsert_package(conn, _package("hl-3", "self"))
    save_review(conn, "hl-1", "approved", "x", "", "t1")
    save_review(conn, "hl-2", "rejected", None, "no good", "t2")
    save_spot_check(conn, "hl-3", flagged=True, notes="check this", checked_at="t3")

    s = stats(conn)
    assert s["human_total"] == 2
    assert s["human_reviewed"] == 2
    assert s["human_pending"] == 0
    assert s["approved_as_is"] == 1
    assert s["rejected"] == 1
    assert s["acceptance_rate_of_reviewed"] == 0.5
    assert s["self_total"] == 1
    assert s["self_spot_checked"] == 1
    assert s["self_spot_checked_flagged"] == 1
    assert s["self_flag_rate_of_checked"] == 1.0


def test_seed_if_empty_loads_from_json_and_is_a_noop_when_already_populated(tmp_path):
    seed_path = tmp_path / "seed_packages.json"
    seed_path.write_text(json.dumps([_package("hl-1", "human"), _package("hl-2", "self")]))

    conn = _memory_conn()
    assert seed_if_empty(conn, seed_path) == 2
    assert package_ids(conn) == {"hl-1", "hl-2"}

    # Already populated (e.g. a real `make queue-data` run) -- seeding must not overwrite it.
    upsert_package(conn, _package("hl-3", "self"))
    assert seed_if_empty(conn, seed_path) == 0
    assert "hl-3" in package_ids(conn)


def test_seed_if_empty_missing_file_is_a_noop():
    conn = _memory_conn()
    assert seed_if_empty(conn, Path("/does/not/exist.json")) == 0
    assert package_ids(conn) == set()


def test_dump_packages_round_trips_and_omits_reviews():
    conn = _memory_conn()
    upsert_package(conn, _package("hl-1", "human"))
    save_review(conn, "hl-1", "approved", "x", "", "t1")

    dumped = dump_packages(conn)
    assert len(dumped) == 1
    assert dumped[0]["id"] == "hl-1"
    assert "status" not in dumped[0]  # review fields never leak into the demo seed


def test_reset_reviews_clears_visitor_state_not_packages():
    conn = _memory_conn()
    upsert_package(conn, _package("hl-1", "human"))
    save_review(conn, "hl-1", "approved", "x", "", "t1")

    reset_reviews(conn)
    assert get_review(conn, "hl-1") is None
    assert get_package(conn, "hl-1") is not None
