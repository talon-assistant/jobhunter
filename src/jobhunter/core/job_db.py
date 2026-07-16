"""SQLite database for job applications, timeline events, and search URLs."""

from __future__ import annotations

import logging
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    position TEXT NOT NULL,
    location TEXT DEFAULT '',
    source TEXT DEFAULT '',
    url TEXT DEFAULT '',
    date_found TEXT NOT NULL,
    status TEXT DEFAULT 'new',
    fit_score INTEGER DEFAULT 0,
    fit_analysis TEXT DEFAULT '',
    jd_text TEXT DEFAULT '',
    jd_embedding BLOB,
    notes TEXT DEFAULT '',
    follow_up_date TEXT,
    resume_path TEXT DEFAULT '',
    cover_letter_path TEXT DEFAULT '',
    date_applied TEXT,
    date_modified TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER NOT NULL REFERENCES applications(id) ON DELETE CASCADE,
    event_date TEXT NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS search_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    board TEXT NOT NULL,
    url TEXT NOT NULL,
    label TEXT DEFAULT '',
    enabled INTEGER DEFAULT 1,
    last_scraped TEXT
);

CREATE INDEX IF NOT EXISTS idx_app_status ON applications(status);
CREATE INDEX IF NOT EXISTS idx_app_company ON applications(company);
CREATE INDEX IF NOT EXISTS idx_app_fit ON applications(fit_score);
CREATE INDEX IF NOT EXISTS idx_events_app ON events(application_id);
"""

_VALID_STATUSES = {"new", "reviewing", "applied", "interviewing", "offer", "rejected", "withdrawn", "archived"}

_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new":          {"reviewing", "applied", "withdrawn", "archived"},
    "reviewing":    {"applied", "withdrawn", "archived"},
    "applied":      {"interviewing", "offer", "rejected", "withdrawn"},
    "interviewing": {"offer", "rejected", "withdrawn"},
    "offer":        {"rejected", "withdrawn"},
    "rejected":     {"archived"},
    "withdrawn":    {"archived"},
    "archived":     set(),
}


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _today_iso() -> str:
    return date.today().isoformat()


class JobDB:
    """Data access layer for the job tracker database."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Applications CRUD
    # ------------------------------------------------------------------

    def add_application(
        self,
        company: str,
        position: str,
        *,
        location: str = "",
        source: str = "",
        url: str = "",
        jd_text: str = "",
        jd_embedding: bytes | None = None,
        fit_score: int = 0,
        fit_analysis: str = "",
        notes: str = "",
        status: str = "new",
    ) -> int:
        """Insert a new application and log a 'found' event. Returns the row id."""
        now = _now_iso()
        cur = self._conn.execute(
            """INSERT INTO applications
               (company, position, location, source, url, date_found,
                status, fit_score, fit_analysis, jd_text, jd_embedding,
                notes, date_modified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (company, position, location, source, url, _today_iso(),
             status, fit_score, fit_analysis, jd_text, jd_embedding,
             notes, now),
        )
        self._conn.commit()
        app_id = cur.lastrowid
        self.add_event(app_id, "found", f"Found on {source}" if source else "Added manually")
        return app_id

    def update_application(self, app_id: int, **fields: Any) -> bool:
        """Update one or more fields on an application."""
        if not fields:
            return False

        # Validate status transitions
        if "status" in fields:
            current = self.get_application(app_id)
            if current:
                old_status = current["status"]
                new_status = fields["status"]
                if new_status not in _VALID_STATUSES:
                    raise ValueError(f"Invalid status: {new_status}")
                allowed = _STATUS_TRANSITIONS.get(old_status, set())
                if new_status != old_status and new_status not in allowed:
                    raise ValueError(
                        f"Cannot transition from '{old_status}' to '{new_status}'. "
                        f"Allowed: {allowed}"
                    )
                if new_status != old_status:
                    self.add_event(app_id, "status_change", f"{old_status} -> {new_status}")

        # Auto-set date_applied
        if fields.get("status") == "applied" and "date_applied" not in fields:
            fields["date_applied"] = _today_iso()

        fields["date_modified"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [app_id]
        cur = self._conn.execute(
            f"UPDATE applications SET {set_clause} WHERE id = ?", values
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_application(self, app_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM applications WHERE id = ?", (app_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_applications(
        self,
        *,
        status: str | None = None,
        source: str | None = None,
        min_score: int = 0,
        search: str = "",
        include_archived: bool = False,
    ) -> list[dict]:
        """List applications with optional filters."""
        clauses = []
        params: list[Any] = []

        if status and status != "archived":
            clauses.append("status = ?")
            params.append(status)

        if not include_archived and status != "archived":
            clauses.append("status != 'archived'")

        if status == "archived":
            clauses.append("status = 'archived'")

        if source:
            clauses.append("source = ?")
            params.append(source)

        if min_score > 0:
            clauses.append("fit_score >= ?")
            params.append(min_score)

        if search:
            clauses.append("(company LIKE ? OR position LIKE ? OR location LIKE ?)")
            pattern = f"%{search}%"
            params.extend([pattern, pattern, pattern])

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM applications {where} ORDER BY fit_score DESC, date_found DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_application(self, app_id: int) -> bool:
        """Hard delete an application and its events."""
        cur = self._conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def url_exists(self, url: str) -> int | None:
        """Check if a job URL (bare, before ?) already exists. Returns app_id or None."""
        bare = url.split("?")[0]
        row = self._conn.execute(
            "SELECT id FROM applications WHERE url LIKE ? LIMIT 1",
            (f"{bare}%",),
        ).fetchone()
        return row["id"] if row else None

    # ------------------------------------------------------------------
    # Timeline Events
    # ------------------------------------------------------------------

    def add_event(
        self, application_id: int, event_type: str, description: str = ""
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO events (application_id, event_date, event_type, description) VALUES (?, ?, ?, ?)",
            (application_id, _now_iso(), event_type, description),
        )
        self._conn.commit()
        return cur.lastrowid

    def get_events(self, application_id: int) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE application_id = ? ORDER BY event_date ASC",
            (application_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Follow-ups
    # ------------------------------------------------------------------

    def get_overdue_followups(self) -> list[dict]:
        """Return applications with follow_up_date <= today and status not terminal."""
        rows = self._conn.execute(
            """SELECT * FROM applications
               WHERE follow_up_date IS NOT NULL
                 AND follow_up_date <= ?
                 AND status NOT IN ('rejected', 'withdrawn', 'archived')
               ORDER BY follow_up_date ASC""",
            (_today_iso(),),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_upcoming_followups(self, days: int = 7) -> list[dict]:
        """Return applications with follow_up_date within the next N days."""
        from datetime import timedelta
        cutoff = (date.today() + timedelta(days=days)).isoformat()
        rows = self._conn.execute(
            """SELECT * FROM applications
               WHERE follow_up_date IS NOT NULL
                 AND follow_up_date > ?
                 AND follow_up_date <= ?
                 AND status NOT IN ('rejected', 'withdrawn', 'archived')
               ORDER BY follow_up_date ASC""",
            (_today_iso(), cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, int]:
        """Return counts by status (excluding archived)."""
        rows = self._conn.execute(
            "SELECT status, COUNT(*) as cnt FROM applications WHERE status != 'archived' GROUP BY status"
        ).fetchall()
        return {r["status"]: r["cnt"] for r in rows}

    def count_since(self, since_date: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM applications WHERE date_found >= ?",
            (since_date,),
        ).fetchone()
        return row["cnt"] if row else 0

    def get_focus_counts(self, *, high_fit_threshold: int = 60) -> dict[str, int]:
        """Counts that drive the dashboard's daily focus line."""
        from datetime import timedelta

        def _count(sql: str, params: tuple = ()) -> int:
            row = self._conn.execute(sql, params).fetchone()
            return row["cnt"] if row else 0

        week_ago = (date.today() - timedelta(days=7)).isoformat()
        return {
            "overdue_followups": len(self.get_overdue_followups()),
            "high_fit_new": _count(
                "SELECT COUNT(*) as cnt FROM applications WHERE status = 'new' AND fit_score >= ?",
                (high_fit_threshold,),
            ),
            "in_flight": _count(
                "SELECT COUNT(*) as cnt FROM applications WHERE status IN ('applied', 'interviewing')"
            ),
            "offers": _count(
                "SELECT COUNT(*) as cnt FROM applications WHERE status = 'offer'"
            ),
            "added_this_week": self.count_since(week_ago),
            "total": _count("SELECT COUNT(*) as cnt FROM applications"),
        }

    # ------------------------------------------------------------------
    # Search URLs
    # ------------------------------------------------------------------

    def add_search_url(self, board: str, url: str, label: str = "") -> int:
        cur = self._conn.execute(
            "INSERT INTO search_urls (board, url, label) VALUES (?, ?, ?)",
            (board, url, label),
        )
        self._conn.commit()
        return cur.lastrowid

    def list_search_urls(self, *, enabled_only: bool = False) -> list[dict]:
        where = "WHERE enabled = 1" if enabled_only else ""
        rows = self._conn.execute(
            f"SELECT * FROM search_urls {where} ORDER BY board, id"
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_search_url(self, url_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM search_urls WHERE id = ?", (url_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def toggle_search_url(self, url_id: int, enabled: bool) -> bool:
        cur = self._conn.execute(
            "UPDATE search_urls SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, url_id),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def update_search_url_scraped(self, url_id: int) -> None:
        self._conn.execute(
            "UPDATE search_urls SET last_scraped = ? WHERE id = ?",
            (_now_iso(), url_id),
        )
        self._conn.commit()
