"""No-API-key checks for the Phase 4 review queue: the approve/edit/reject decision logic
and the storage layer's round-trip and aggregation. Not a Flask test -- `decide_status` is
deliberately a pure function so this doesn't need one."""

from __future__ import annotations

import sqlite3

from triage.queue_app import decide_status
from triage.queue_db import (
    SCHEMA,
    get_package,
    get_review,
    save_review,
    save_spot_check,
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
