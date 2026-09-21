"""Storage for the Phase 4 human review queue: SQLite, one file, no server.

Two kinds of row:

- `packages` -- built once by `triage.build_queue_data` from the Phase 3b answerer
  candidates (`results/*_answerer_v1_{dev,test}_candidates.jsonl`). Read-only from the
  app's point of view; rebuilding is a separate, budgeted step, not something a page view
  triggers.
- `reviews` / `spot_checks` -- written by the agent through `queue_app`. This is the data
  the phase asked for: how often a draft is accepted as-is vs. edited vs. rejected, and
  which self-handled replies a human has spot-checked.

SQLite over anything fancier because a single support agent working a queue is a
single-writer workload; nothing here needs a server process. It is also a normal
Postgres-compatible schema (plain tables, no SQLite-only types) so Phase 5's "avoid
choices that make deployment hard" is satisfied by not doing anything clever, not by
avoiding a real database.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "queue" / "queue.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS packages (
    id TEXT PRIMARY KEY,
    split TEXT NOT NULL,
    ticket_text TEXT NOT NULL,
    intent TEXT NOT NULL,
    urgency TEXT NOT NULL,
    confidence REAL NOT NULL,
    escalation_reasons TEXT NOT NULL,  -- JSON list
    rationale TEXT NOT NULL,
    handled_by TEXT NOT NULL CHECK (handled_by IN ('self', 'human')),
    order_facts TEXT NOT NULL,
    policy_docs TEXT NOT NULL,         -- JSON list of docs/knowledge_base/*.md filenames
    handover_note TEXT,                -- human tickets only
    suggested_reply TEXT NOT NULL,
    generated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    ticket_id TEXT PRIMARY KEY REFERENCES packages(id),
    status TEXT NOT NULL CHECK (status IN ('approved', 'edited', 'rejected')),
    final_reply_text TEXT,
    reviewer_notes TEXT,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS spot_checks (
    ticket_id TEXT PRIMARY KEY REFERENCES packages(id),
    flagged INTEGER NOT NULL,
    notes TEXT,
    checked_at TEXT NOT NULL
);
"""


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_to_package(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["escalation_reasons"] = json.loads(d["escalation_reasons"])
    d["policy_docs"] = json.loads(d["policy_docs"])
    return d


def upsert_package(conn: sqlite3.Connection, pkg: dict) -> None:
    conn.execute(
        """INSERT INTO packages
               (id, split, ticket_text, intent, urgency, confidence, escalation_reasons,
                rationale, handled_by, order_facts, policy_docs, handover_note,
                suggested_reply, generated_at)
           VALUES (:id, :split, :ticket_text, :intent, :urgency, :confidence,
                   :escalation_reasons, :rationale, :handled_by, :order_facts,
                   :policy_docs, :handover_note, :suggested_reply, :generated_at)
           ON CONFLICT(id) DO UPDATE SET
                split=excluded.split, ticket_text=excluded.ticket_text,
                intent=excluded.intent, urgency=excluded.urgency,
                confidence=excluded.confidence, escalation_reasons=excluded.escalation_reasons,
                rationale=excluded.rationale, handled_by=excluded.handled_by,
                order_facts=excluded.order_facts, policy_docs=excluded.policy_docs,
                handover_note=excluded.handover_note, suggested_reply=excluded.suggested_reply,
                generated_at=excluded.generated_at""",
        {**pkg, "escalation_reasons": json.dumps(pkg["escalation_reasons"]),
         "policy_docs": json.dumps(pkg["policy_docs"])},
    )


def package_ids(conn: sqlite3.Connection) -> set[str]:
    return {r["id"] for r in conn.execute("SELECT id FROM packages")}


def get_package(conn: sqlite3.Connection, ticket_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM packages WHERE id = ?", (ticket_id,)).fetchone()
    return _row_to_package(row) if row else None


def list_packages(conn: sqlite3.Connection, handled_by: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM packages WHERE handled_by = ? ORDER BY id", (handled_by,)
    ).fetchall()
    return [_row_to_package(r) for r in rows]


def get_review(conn: sqlite3.Connection, ticket_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM reviews WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def save_review(
    conn: sqlite3.Connection, ticket_id: str, status: str, final_reply_text: str | None,
    reviewer_notes: str, reviewed_at: str,
) -> None:
    conn.execute(
        """INSERT INTO reviews (ticket_id, status, final_reply_text, reviewer_notes, reviewed_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(ticket_id) DO UPDATE SET
                status=excluded.status, final_reply_text=excluded.final_reply_text,
                reviewer_notes=excluded.reviewer_notes, reviewed_at=excluded.reviewed_at""",
        (ticket_id, status, final_reply_text, reviewer_notes, reviewed_at),
    )


def get_spot_check(conn: sqlite3.Connection, ticket_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM spot_checks WHERE ticket_id = ?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def save_spot_check(
    conn: sqlite3.Connection, ticket_id: str, flagged: bool, notes: str, checked_at: str
) -> None:
    conn.execute(
        """INSERT INTO spot_checks (ticket_id, flagged, notes, checked_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ticket_id) DO UPDATE SET
                flagged=excluded.flagged, notes=excluded.notes, checked_at=excluded.checked_at""",
        (ticket_id, int(flagged), notes, checked_at),
    )


def stats(conn: sqlite3.Connection) -> dict:
    human_total = conn.execute("SELECT COUNT(*) FROM packages WHERE handled_by='human'").fetchone()[0]
    self_total = conn.execute("SELECT COUNT(*) FROM packages WHERE handled_by='self'").fetchone()[0]
    by_status = dict(
        conn.execute("SELECT status, COUNT(*) FROM reviews GROUP BY status").fetchall()
    )
    reviewed = sum(by_status.values())
    spot_total = conn.execute("SELECT COUNT(*) FROM spot_checks").fetchone()[0]
    spot_flagged = conn.execute("SELECT COUNT(*) FROM spot_checks WHERE flagged=1").fetchone()[0]

    def rate(n: int, d: int) -> float | None:
        return round(n / d, 4) if d else None

    return {
        "human_total": human_total,
        "human_reviewed": reviewed,
        "human_pending": human_total - reviewed,
        "approved_as_is": by_status.get("approved", 0),
        "edited_then_approved": by_status.get("edited", 0),
        "rejected": by_status.get("rejected", 0),
        "acceptance_rate_of_reviewed": rate(by_status.get("approved", 0), reviewed),
        "edit_rate_of_reviewed": rate(by_status.get("edited", 0), reviewed),
        "rejection_rate_of_reviewed": rate(by_status.get("rejected", 0), reviewed),
        "self_total": self_total,
        "self_spot_checked": spot_total,
        "self_spot_checked_flagged": spot_flagged,
        "self_flag_rate_of_checked": rate(spot_flagged, spot_total),
    }
