from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection(database_path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(database_path: Path) -> None:
    with get_connection(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                external_id TEXT,
                title TEXT NOT NULL,
                company TEXT,
                location TEXT,
                job_url TEXT NOT NULL UNIQUE,
                description TEXT,
                raw_text TEXT,
                contact_email TEXT,
                search_keyword TEXT,
                discovered_at TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                telegram_message_id INTEGER,
                applied_at TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS packets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL UNIQUE,
                resume_output_path TEXT,
                cover_letter_path TEXT,
                cover_letter_text TEXT,
                created_at TEXT NOT NULL,
                final_status TEXT NOT NULL DEFAULT 'draft',
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                event_type TEXT NOT NULL,
                event_value TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            );
            """
        )


def upsert_job(database_path: Path, job: dict[str, Any]) -> tuple[int, bool]:
    now = utc_now()
    with get_connection(database_path) as conn:
        existing = conn.execute(
            "SELECT id FROM jobs WHERE job_url = ?",
            (job["job_url"],),
        ).fetchone()

        if existing:
            conn.execute(
                """
                UPDATE jobs
                SET
                    title = ?,
                    company = COALESCE(?, company),
                    location = COALESCE(?, location),
                    description = COALESCE(?, description),
                    raw_text = COALESCE(?, raw_text),
                    contact_email = COALESCE(?, contact_email),
                    search_keyword = ?,
                    last_seen_at = ?
                WHERE id = ?
                """,
                (
                    job.get("title"),
                    job.get("company"),
                    job.get("location"),
                    job.get("description"),
                    job.get("raw_text"),
                    job.get("contact_email"),
                    job.get("search_keyword"),
                    now,
                    existing["id"],
                ),
            )
            return int(existing["id"]), False

        cursor = conn.execute(
            """
            INSERT INTO jobs (
                source,
                external_id,
                title,
                company,
                location,
                job_url,
                description,
                raw_text,
                contact_email,
                search_keyword,
                discovered_at,
                first_seen_at,
                last_seen_at,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.get("source"),
                job.get("external_id"),
                job.get("title"),
                job.get("company"),
                job.get("location"),
                job.get("job_url"),
                job.get("description"),
                job.get("raw_text"),
                job.get("contact_email"),
                job.get("search_keyword"),
                job.get("discovered_at", now),
                now,
                now,
                "new",
            ),
        )
        return int(cursor.lastrowid), True


def get_job(database_path: Path, job_id: int) -> sqlite3.Row | None:
    with get_connection(database_path) as conn:
        return conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()


def list_jobs(database_path: Path, status: str | None = None, limit: int = 20) -> list[sqlite3.Row]:
    query = "SELECT * FROM jobs"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with get_connection(database_path) as conn:
        return conn.execute(query, params).fetchall()


def update_job_status(database_path: Path, job_id: int, status: str, notes: str | None = None) -> None:
    with get_connection(database_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, notes = COALESCE(?, notes) WHERE id = ?",
            (status, notes, job_id),
        )


def set_job_message_id(database_path: Path, job_id: int, message_id: int) -> None:
    with get_connection(database_path) as conn:
        conn.execute(
            "UPDATE jobs SET telegram_message_id = ? WHERE id = ?",
            (message_id, job_id),
        )


def save_packet(
    database_path: Path,
    job_id: int,
    resume_output_path: str,
    cover_letter_path: str,
    cover_letter_text: str,
) -> None:
    with get_connection(database_path) as conn:
        existing = conn.execute("SELECT id FROM packets WHERE job_id = ?", (job_id,)).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE packets
                SET resume_output_path = ?, cover_letter_path = ?, cover_letter_text = ?, created_at = ?
                WHERE job_id = ?
                """,
                (resume_output_path, cover_letter_path, cover_letter_text, utc_now(), job_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO packets (job_id, resume_output_path, cover_letter_path, cover_letter_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (job_id, resume_output_path, cover_letter_path, cover_letter_text, utc_now()),
            )


def get_packet(database_path: Path, job_id: int) -> sqlite3.Row | None:
    with get_connection(database_path) as conn:
        return conn.execute("SELECT * FROM packets WHERE job_id = ?", (job_id,)).fetchone()


def update_packet_status(database_path: Path, job_id: int, final_status: str) -> None:
    with get_connection(database_path) as conn:
        conn.execute(
            "UPDATE packets SET final_status = ? WHERE job_id = ?",
            (final_status, job_id),
        )


def record_event(database_path: Path, event_type: str, event_value: str, job_id: int | None = None) -> None:
    with get_connection(database_path) as conn:
        conn.execute(
            "INSERT INTO events (job_id, event_type, event_value, created_at) VALUES (?, ?, ?, ?)",
            (job_id, event_type, event_value, utc_now()),
        )


def stats(database_path: Path) -> dict[str, int]:
    with get_connection(database_path) as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS total FROM jobs GROUP BY status"
        ).fetchall()
    payload = {row["status"]: int(row["total"]) for row in rows}
    return {
        "new": payload.get("new", 0),
        "saved": payload.get("saved", 0),
        "approved": payload.get("approved", 0),
        "trash": payload.get("trash", 0),
        "applied": payload.get("applied", 0),
        "manual_followup": payload.get("manual_followup", 0),
    }