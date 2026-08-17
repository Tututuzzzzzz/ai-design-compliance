"""SQLite persistence. One file, no server — the judge runs `docker compose up`."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    created_at    REAL NOT NULL,
    updated_at    REAL NOT NULL,
    status        TEXT NOT NULL,
    source        TEXT NOT NULL,
    label         TEXT,
    total         INTEGER NOT NULL DEFAULT 0,
    done          INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS designs (
    id          TEXT PRIMARY KEY,
    job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    created_at  REAL NOT NULL,
    status      TEXT NOT NULL,
    filename    TEXT NOT NULL,
    source      TEXT NOT NULL,
    source_ref  TEXT,
    path        TEXT,
    verdict     TEXT,
    confidence  INTEGER,
    niche       TEXT,
    report_json TEXT,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS idx_designs_job ON designs(job_id);
CREATE INDEX IF NOT EXISTS idx_designs_verdict ON designs(verdict);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    with _lock:
        conn = _connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def init_db() -> None:
    with tx() as conn:
        conn.executescript(SCHEMA)


# --------------------------------------------------------------------------
# Jobs
# --------------------------------------------------------------------------


def create_job(job_id: str, source: str, label: str, metadata: dict[str, Any]) -> None:
    now = time.time()
    with tx() as conn:
        conn.execute(
            "INSERT INTO jobs (id, created_at, updated_at, status, source, label, metadata_json)"
            " VALUES (?,?,?,?,?,?,?)",
            (job_id, now, now, "queued", source, label, json.dumps(metadata)),
        )


def set_job_total(job_id: str, total: int) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE jobs SET total=?, status='running', updated_at=? WHERE id=?",
            (total, time.time(), job_id),
        )


def bump_job(job_id: str, *, ok: bool) -> None:
    col = "done" if ok else "failed"
    with tx() as conn:
        conn.execute(
            f"UPDATE jobs SET {col}={col}+1, updated_at=? WHERE id=?", (time.time(), job_id)
        )
        row = conn.execute(
            "SELECT total, done, failed FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if row and row["done"] + row["failed"] >= row["total"] > 0:
            conn.execute("UPDATE jobs SET status='done' WHERE id=?", (job_id,))


def fail_job(job_id: str, message: str) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE jobs SET status='failed', updated_at=?,"
            " metadata_json=json_set(metadata_json,'$.error',?) WHERE id=?",
            (time.time(), message, job_id),
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with tx() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job_row(row) if row else None


def list_jobs(limit: int = 50) -> list[dict[str, Any]]:
    with tx() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [_job_row(r) for r in rows]


def _job_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["metadata"] = json.loads(d.pop("metadata_json") or "{}")
    return d


# --------------------------------------------------------------------------
# Designs
# --------------------------------------------------------------------------


def create_design(
    design_id: str,
    job_id: str,
    filename: str,
    source: str,
    source_ref: str | None,
    path: str | None,
) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO designs (id, job_id, created_at, status, filename, source, source_ref, path)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (design_id, job_id, time.time(), "queued", filename, source, source_ref, path),
        )


def mark_design_running(design_id: str) -> None:
    with tx() as conn:
        conn.execute("UPDATE designs SET status='running' WHERE id=?", (design_id,))


def save_report(design_id: str, report: dict[str, Any]) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE designs SET status='done', verdict=?, confidence=?, niche=?, report_json=?,"
            " error=NULL WHERE id=?",
            (
                report.get("verdict"),
                report.get("confidence"),
                (report.get("niche") or {}).get("primary"),
                json.dumps(report, ensure_ascii=False),
                design_id,
            ),
        )


def save_design_error(design_id: str, message: str) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE designs SET status='failed', error=? WHERE id=?", (message, design_id)
        )


def get_design(design_id: str) -> dict[str, Any] | None:
    with tx() as conn:
        row = conn.execute("SELECT * FROM designs WHERE id=?", (design_id,)).fetchone()
    return _design_row(row) if row else None


def list_designs(
    job_id: str | None = None,
    verdict: str | None = None,
    niche: str | None = None,
    category: str | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM designs WHERE 1=1"
    args: list[Any] = []
    if job_id:
        sql += " AND job_id=?"
        args.append(job_id)
    if verdict:
        sql += " AND verdict=?"
        args.append(verdict.upper())
    if niche:
        sql += " AND niche LIKE ?"
        args.append(f"%{niche}%")
    sql += " ORDER BY created_at ASC"

    with tx() as conn:
        rows = conn.execute(sql, args).fetchall()

    items = [_design_row(r) for r in rows]
    if category:
        items = [
            d
            for d in items
            if any(f.get("category") == category for f in (d.get("report") or {}).get("findings", []))
        ]
    return items


def _design_row(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    raw = d.pop("report_json", None)
    d["report"] = json.loads(raw) if raw else None
    return d


def job_stats(job_id: str) -> dict[str, int]:
    with tx() as conn:
        rows = conn.execute(
            "SELECT verdict, COUNT(*) c FROM designs WHERE job_id=? GROUP BY verdict", (job_id,)
        ).fetchall()
    stats = {"SAFE": 0, "RISKY": 0, "BLOCKED": 0, "FAILED": 0}
    for r in rows:
        key = r["verdict"] or "FAILED"
        stats[key] = stats.get(key, 0) + r["c"]
    return stats
