"""SQLite database for the resume bullet library."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from jobhunter.core.embeddings import (
    bytes_to_vec,
    cosine_similarity,
    embed_text,
    vec_to_bytes,
)

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bullets (
    bullet_id INTEGER PRIMARY KEY AUTOINCREMENT,
    section TEXT NOT NULL,
    role TEXT DEFAULT '',
    text TEXT NOT NULL,
    source_file TEXT DEFAULT '',
    date_added TEXT NOT NULL,
    date_modified TEXT NOT NULL,
    embedding BLOB,
    priority TEXT DEFAULT 'normal',
    times_selected INTEGER DEFAULT 0,
    last_selected TEXT
);

CREATE TABLE IF NOT EXISTS section_caps (
    section TEXT PRIMARY KEY,
    cap INTEGER NOT NULL DEFAULT 4
);

CREATE INDEX IF NOT EXISTS idx_bullet_section ON bullets(section);
CREATE INDEX IF NOT EXISTS idx_bullet_role ON bullets(role);
"""


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class ResumeDB:
    """Data access layer for the resume bullet library."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Bullet CRUD
    # ------------------------------------------------------------------

    def add_bullet(
        self,
        section: str,
        text: str,
        *,
        role: str = "",
        source_file: str = "",
        priority: str = "normal",
        auto_embed: bool = True,
    ) -> int:
        """Insert a new bullet. Returns bullet_id."""
        now = _now_iso()
        embedding = vec_to_bytes(embed_text(text)) if auto_embed else None
        cur = self._conn.execute(
            """INSERT INTO bullets
               (section, role, text, source_file, date_added, date_modified,
                embedding, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (section, role, text, source_file, now, now, embedding, priority),
        )
        self._conn.commit()
        return cur.lastrowid

    def update_bullet(self, bullet_id: int, **fields: Any) -> bool:
        """Update fields on a bullet. Re-embeds if text changes."""
        if not fields:
            return False

        if "text" in fields:
            fields["embedding"] = vec_to_bytes(embed_text(fields["text"]))

        fields["date_modified"] = _now_iso()
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [bullet_id]
        cur = self._conn.execute(
            f"UPDATE bullets SET {set_clause} WHERE bullet_id = ?", values
        )
        self._conn.commit()
        return cur.rowcount > 0

    def delete_bullet(self, bullet_id: int) -> bool:
        cur = self._conn.execute(
            "DELETE FROM bullets WHERE bullet_id = ?", (bullet_id,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_bullet(self, bullet_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM bullets WHERE bullet_id = ?", (bullet_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_bullets(
        self,
        *,
        section: str | None = None,
        role: str | None = None,
    ) -> list[dict]:
        clauses = []
        params: list[Any] = []
        if section:
            clauses.append("section = ?")
            params.append(section)
        if role:
            clauses.append("role = ?")
            params.append(role)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM bullets {where} ORDER BY section, role, bullet_id",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def increment_selected(self, bullet_id: int) -> None:
        """Increment usage counter when a bullet is picked by the selector."""
        self._conn.execute(
            "UPDATE bullets SET times_selected = times_selected + 1, last_selected = ? WHERE bullet_id = ?",
            (_now_iso(), bullet_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Section Caps
    # ------------------------------------------------------------------

    def get_section_cap(self, section: str, default: int = 4) -> int:
        """Return the bullet cap for a section."""
        row = self._conn.execute(
            "SELECT cap FROM section_caps WHERE section = ?", (section,)
        ).fetchone()
        return row["cap"] if row else default

    def set_section_cap(self, section: str, cap: int) -> None:
        """Set or update the bullet cap for a section."""
        self._conn.execute(
            "INSERT INTO section_caps (section, cap) VALUES (?, ?) "
            "ON CONFLICT(section) DO UPDATE SET cap = excluded.cap",
            (section, cap),
        )
        self._conn.commit()

    def get_all_caps(self, default: int = 4) -> dict[str, int]:
        """Return caps for all sections (fills in default for unconfigured ones)."""
        sections = self.get_sections()
        rows = self._conn.execute("SELECT section, cap FROM section_caps").fetchall()
        configured = {r["section"]: r["cap"] for r in rows}
        return {s: configured.get(s, default) for s in sections}

    # ------------------------------------------------------------------
    # Sections & Roles
    # ------------------------------------------------------------------

    def get_sections(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT DISTINCT section FROM bullets ORDER BY section"
        ).fetchall()
        return [r["section"] for r in rows]

    def get_roles(self, section: str | None = None) -> list[str]:
        if section:
            rows = self._conn.execute(
                "SELECT DISTINCT role FROM bullets WHERE section = ? AND role != '' ORDER BY role",
                (section,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT DISTINCT role FROM bullets WHERE role != '' ORDER BY role"
            ).fetchall()
        return [r["role"] for r in rows]

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def find_duplicates(
        self, text: str, *, threshold: float = 0.92
    ) -> list[tuple[dict, float]]:
        """Find existing bullets similar to *text*.

        Returns list of (bullet_dict, similarity_score) pairs above threshold,
        sorted by similarity descending.
        """
        query_vec = embed_text(text)
        all_bullets = self.list_bullets()
        results = []

        for b in all_bullets:
            if not b["embedding"]:
                continue
            stored_vec = bytes_to_vec(b["embedding"])
            sim = cosine_similarity(query_vec, stored_vec)
            if sim >= threshold:
                results.append((b, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Bulk Operations
    # ------------------------------------------------------------------

    def bulk_embed(self) -> int:
        """Compute and store embeddings for all bullets that lack one."""
        rows = self._conn.execute(
            "SELECT bullet_id, text FROM bullets WHERE embedding IS NULL"
        ).fetchall()
        if not rows:
            return 0

        log.info("Embedding %d bullets...", len(rows))
        for row in rows:
            vec = embed_text(row["text"])
            self._conn.execute(
                "UPDATE bullets SET embedding = ? WHERE bullet_id = ?",
                (vec_to_bytes(vec), row["bullet_id"]),
            )
        self._conn.commit()
        log.info("Embedded %d bullets", len(rows))
        return len(rows)

    # ------------------------------------------------------------------
    # Markdown Export/Import
    # ------------------------------------------------------------------

    def export_markdown(self, output_path: str | Path) -> None:
        """Export the bullet library to a markdown file.

        Format matches what ResumeSelector expects::

            ## Section Name

            *Role description*

            - Bullet text here
            - Another bullet
        """
        sections = self.get_sections()
        lines: list[str] = []

        for section in sections:
            lines.append(f"## {section}\n")
            roles = self.get_roles(section)

            if roles:
                for role in roles:
                    lines.append(f"*{role}*\n")
                    bullets = self.list_bullets(section=section, role=role)
                    for b in bullets:
                        lines.append(f"- {b['text']}")
                    lines.append("")
            else:
                bullets = self.list_bullets(section=section)
                for b in bullets:
                    lines.append(f"- {b['text']}")
                lines.append("")

        Path(output_path).write_text("\n".join(lines), encoding="utf-8")
        log.info("Exported %d sections to %s", len(sections), output_path)

    def import_from_markdown(
        self, md_path: str | Path, *, source_file: str = ""
    ) -> int:
        """Import bullets from a markdown file. Returns count of bullets added."""
        text = Path(md_path).read_text(encoding="utf-8")
        count = 0
        current_section = ""
        current_role = ""

        for line in text.splitlines():
            stripped = line.strip()

            if stripped.startswith("## "):
                current_section = stripped[3:].strip()
                current_role = ""
                continue

            if stripped.startswith("*") and stripped.endswith("*") and not stripped.startswith("- "):
                current_role = stripped.strip("*").strip()
                continue

            if stripped.startswith("- ") and current_section:
                bullet_text = stripped[2:].strip()
                if bullet_text:
                    # Check for near-duplicates before adding
                    dupes = self.find_duplicates(bullet_text, threshold=0.95)
                    if not dupes:
                        self.add_bullet(
                            current_section,
                            bullet_text,
                            role=current_role,
                            source_file=source_file or str(md_path),
                        )
                        count += 1

        log.info("Imported %d bullets from %s", count, md_path)
        return count

    def total_bullets(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) as cnt FROM bullets").fetchone()
        return row["cnt"] if row else 0
