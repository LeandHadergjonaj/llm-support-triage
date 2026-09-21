"""The human review queue: a small Flask app an agent works from.

    .venv/bin/python -m triage.queue_app

Two workflows, per the Phase 4 brief:

1. **The queue** (`/`, `/ticket/<id>`) -- every `human`-routed package, shown as a
   ready-to-act bundle: the ticket, why it was escalated, the verified order facts, the
   relevant policy document(s), and a suggested reply. The agent approves it as-is, edits
   it and approves the edit, or rejects it with a note. Nothing is ever sent to a real
   customer -- "approve" only records a decision in `reviews`.
2. **Spot-check** (`/spotcheck`, `/spotcheck/<id>`) -- every `self`-routed ticket, i.e. one
   the system already "sent" on its own, browsable read-only with a flag/notes field, so a
   client could audit the automated replies before trusting them.

`/stats` reports the numbers the phase asked for: how often a draft is accepted unchanged
vs. edited vs. rejected, and the spot-check flag rate. All of it reads straight from
`queue_db` -- this file is routing and templates only.
"""

from __future__ import annotations

from datetime import UTC, datetime

from flask import Flask, abort, redirect, render_template_string, request, url_for

from triage.llm import REPO_ROOT
from triage.queue_db import (
    connect,
    get_package,
    get_review,
    get_spot_check,
    list_packages,
    save_review,
    save_spot_check,
    stats,
)

app = Flask(__name__)


def decide_status(action: str, reply_text: str, suggested_reply: str) -> tuple[str, str | None]:
    """Pure decision logic for a review action -- kept separate from the route so it is
    testable with no Flask app or database. Returns (status, final_reply_text)."""
    if action == "approve":
        return "approved", suggested_reply
    if action == "edit_approve":
        edited = reply_text.strip() != suggested_reply.strip()
        return ("edited", reply_text) if edited else ("approved", reply_text)
    if action == "reject":
        return "rejected", None
    raise ValueError(f"Unknown action {action!r}")

BASE = """
<!doctype html><html><head><meta charset="utf-8">
<title>Hearth & Loom -- review queue</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 900px; margin: 2rem auto; color: #1a1a1a; }
nav a { margin-right: 1.5rem; }
.pill { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 1rem; font-size: 0.8rem; }
.pill.high { background: #fde2e1; } .pill.normal { background: #fff3cd; } .pill.low { background: #e2f0d9; }
.pill.human { background: #e0e7ff; } .pill.self { background: #f0f0f0; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
td, th { border-bottom: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }
textarea { width: 100%; font-family: inherit; font-size: 0.95rem; }
.box { background: #f7f7f7; border: 1px solid #ddd; border-radius: 6px; padding: 1rem; margin: 1rem 0; }
.muted { color: #666; font-size: 0.9rem; }
button { padding: 0.5rem 1rem; margin-right: 0.5rem; cursor: pointer; }
.diff { background: #fffbe6; border-left: 3px solid #e8b923; padding: 0.5rem 1rem; }
</style></head><body>
<nav><a href="/">Queue</a><a href="/spotcheck">Spot-check</a><a href="/stats">Stats</a></nav>
<hr>
{{ body|safe }}
</body></html>
"""


def render(body_template: str, **ctx) -> str:
    body = render_template_string(body_template, **ctx)
    return render_template_string(BASE, body=body)


@app.route("/")
def queue():
    with connect() as conn:
        packages = list_packages(conn, "human")
        rows = [(p, get_review(conn, p["id"])) for p in packages]
    pending = [(p, r) for p, r in rows if r is None]
    done = [(p, r) for p, r in rows if r is not None]
    return render(
        """
        <h1>Human review queue</h1>
        <p class="muted">{{ pending|length }} pending, {{ done|length }} reviewed.</p>
        <h2>Pending</h2>
        <table><tr><th>Ticket</th><th>Intent</th><th>Urgency</th><th>Escalated for</th></tr>
        {% for p, _ in pending %}
        <tr>
          <td><a href="{{ url_for('ticket', ticket_id=p['id']) }}">{{ p['id'] }}</a></td>
          <td>{{ p['intent'] }}</td>
          <td><span class="pill {{ p['urgency'] }}">{{ p['urgency'] }}</span></td>
          <td>{{ p['escalation_reasons']|join(', ') or 'low confidence' }}</td>
        </tr>
        {% endfor %}
        </table>
        <h2>Reviewed</h2>
        <table><tr><th>Ticket</th><th>Decision</th><th>Reviewed</th></tr>
        {% for p, r in done %}
        <tr>
          <td><a href="{{ url_for('ticket', ticket_id=p['id']) }}">{{ p['id'] }}</a></td>
          <td>{{ r['status'] }}</td>
          <td class="muted">{{ r['reviewed_at'] }}</td>
        </tr>
        {% endfor %}
        </table>
        """,
        pending=pending, done=done,
    )


@app.route("/ticket/<ticket_id>")
def ticket(ticket_id: str):
    with connect() as conn:
        pkg = get_package(conn, ticket_id)
        if pkg is None or pkg["handled_by"] != "human":
            abort(404)
        review = get_review(conn, ticket_id)
    return render(
        """
        <p><a href="/">&larr; back to queue</a></p>
        <h1>{{ p['id'] }}</h1>
        <p><span class="pill {{ p['urgency'] }}">{{ p['urgency'] }}</span>
           <span class="pill human">escalated: {{ p['escalation_reasons']|join(', ') or 'low confidence' }}</span></p>

        <div class="box"><b>Ticket</b><p>{{ p['ticket_text'] }}</p></div>
        <div class="box"><b>Why escalated</b>
          <p>{{ p['rationale'] }}</p>
          <p class="muted">router confidence {{ '%.2f'|format(p['confidence']) }}</p>
        </div>
        <div class="box"><b>Order facts (verified database lookup)</b>
          <pre>{{ p['order_facts'] }}</pre>
        </div>
        <div class="box"><b>Relevant policy</b>
          {% for doc in p['policy_docs'] %}
          <p><a href="{{ url_for('policy_doc', name=doc) }}" target="_blank">{{ doc }}</a></p>
          {% else %}<p class="muted">No specific document mapped for this intent.</p>
          {% endfor %}
        </div>
        <div class="box"><b>Handover note (from the router's escalation)</b>
          <p style="white-space: pre-wrap">{{ p['handover_note'] }}</p>
        </div>

        {% if review %}
        <div class="box diff">
          <b>Reviewed: {{ review['status'] }}</b> ({{ review['reviewed_at'] }})
          {% if review['final_reply_text'] %}<pre>{{ review['final_reply_text'] }}</pre>{% endif %}
          {% if review['reviewer_notes'] %}<p class="muted">Note: {{ review['reviewer_notes'] }}</p>{% endif %}
        </div>
        {% else %}
        <form method="post" action="{{ url_for('decide', ticket_id=p['id']) }}">
          <b>Suggested reply (edit below if needed)</b>
          <textarea name="reply_text" rows="8">{{ p['suggested_reply'] }}</textarea>
          <p><b>Notes</b> (required for reject)</p>
          <textarea name="notes" rows="2"></textarea>
          <p>
            <button name="action" value="approve">Approve as-is</button>
            <button name="action" value="edit_approve">Save edit &amp; approve</button>
            <button name="action" value="reject">Reject</button>
          </p>
        </form>
        {% endif %}
        """,
        p=pkg, review=review,
    )


@app.route("/ticket/<ticket_id>/decide", methods=["POST"])
def decide(ticket_id: str):
    action = request.form["action"]
    reply_text = request.form.get("reply_text", "")
    notes = request.form.get("notes", "")

    with connect() as conn:
        pkg = get_package(conn, ticket_id)
        if pkg is None:
            abort(404)
        if action == "reject" and not notes.strip():
            abort(400, "A note is required to reject a draft.")
        try:
            status, final = decide_status(action, reply_text, pkg["suggested_reply"])
        except ValueError as exc:
            abort(400, str(exc))

        save_review(conn, ticket_id, status, final, notes, datetime.now(UTC).isoformat(timespec="seconds"))
    return redirect(url_for("ticket", ticket_id=ticket_id))


@app.route("/policy/<name>")
def policy_doc(name: str):
    path = REPO_ROOT / "docs" / "knowledge_base" / name
    if not path.is_file() or path.parent != REPO_ROOT / "docs" / "knowledge_base":
        abort(404)
    return f"<pre>{path.read_text()}</pre>"


@app.route("/spotcheck")
def spotcheck_list():
    with connect() as conn:
        packages = list_packages(conn, "self")
        rows = [(p, get_spot_check(conn, p["id"])) for p in packages]
    return render(
        """
        <h1>Spot-check: replies the system sent on its own</h1>
        <p class="muted">{{ rows|length }} self-handled tickets.
           {{ rows|selectattr('1')|list|length }} checked.</p>
        <table><tr><th>Ticket</th><th>Intent</th><th>Checked</th><th>Flagged</th></tr>
        {% for p, sc in rows %}
        <tr>
          <td><a href="{{ url_for('spotcheck_detail', ticket_id=p['id']) }}">{{ p['id'] }}</a></td>
          <td>{{ p['intent'] }}</td>
          <td>{{ 'yes' if sc else 'no' }}</td>
          <td>{{ 'FLAGGED' if sc and sc['flagged'] else '' }}</td>
        </tr>
        {% endfor %}
        </table>
        """,
        rows=rows,
    )


@app.route("/spotcheck/<ticket_id>")
def spotcheck_detail(ticket_id: str):
    with connect() as conn:
        pkg = get_package(conn, ticket_id)
        if pkg is None or pkg["handled_by"] != "self":
            abort(404)
        sc = get_spot_check(conn, ticket_id)
    return render(
        """
        <p><a href="/spotcheck">&larr; back</a></p>
        <h1>{{ p['id'] }} (self-handled)</h1>
        <div class="box"><b>Ticket</b><p>{{ p['ticket_text'] }}</p></div>
        <div class="box"><b>Order facts</b><pre>{{ p['order_facts'] }}</pre></div>
        <div class="box"><b>Reply sent</b><p style="white-space: pre-wrap">{{ p['suggested_reply'] }}</p></div>
        <form method="post" action="{{ url_for('spotcheck_save', ticket_id=p['id']) }}">
          <label><input type="checkbox" name="flagged" {{ 'checked' if sc and sc['flagged'] }}> Flag this reply</label>
          <textarea name="notes" rows="2">{{ sc['notes'] if sc else '' }}</textarea>
          <p><button type="submit">Save</button></p>
        </form>
        {% if sc %}<p class="muted">Last checked {{ sc['checked_at'] }}</p>{% endif %}
        """,
        p=pkg, sc=sc,
    )


@app.route("/spotcheck/<ticket_id>/save", methods=["POST"])
def spotcheck_save(ticket_id: str):
    flagged = "flagged" in request.form
    notes = request.form.get("notes", "")
    with connect() as conn:
        if get_package(conn, ticket_id) is None:
            abort(404)
        save_spot_check(conn, ticket_id, flagged, notes, datetime.now(UTC).isoformat(timespec="seconds"))
    return redirect(url_for("spotcheck_detail", ticket_id=ticket_id))


@app.route("/stats")
def stats_page():
    with connect() as conn:
        s = stats(conn)
    return render(
        """
        <h1>Queue stats</h1>
        <table>
        {% for k, v in s.items() %}
        <tr><td>{{ k }}</td><td>{{ v }}</td></tr>
        {% endfor %}
        </table>
        """,
        s=s,
    )


if __name__ == "__main__":
    app.run(debug=True, port=5050)
