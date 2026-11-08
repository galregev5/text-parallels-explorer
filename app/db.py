"""SQLite storage: schema setup and the idempotent upsert functions.

See `app/schema.sql` for the schema itself and DECISIONS.md ("Phase 3 --
Database") for why. The one rule every write function here follows: an upsert
either inserts a brand-new row, or updates exactly the columns that a re-run
is allowed to change -- never `status` or `note`, which belong to the
researcher doing the review.

None of these functions call `conn.commit()`. The caller controls the
transaction boundary -- `app/pipeline.py`'s `run_pipeline` wraps a whole run
in one `with conn:` block so it commits or rolls back atomically; a caller
using these functions directly (as the tests do) must commit (or use
`with conn:`) itself before the changes are durable.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection to the SQLite file at `db_path`, creating the schema
    if it does not exist yet. `db_path` may be ":memory:" for a throwaway
    in-process database (used by the test suite).
    """
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL lets a read (the UI, serving a page) proceed while a write (a
    # "re-run analysis" pass) is in progress, instead of blocking on it.
    # Harmless for the tests' :memory: connections, where it is a no-op.
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def upsert_document(conn: sqlite3.Connection, slug: str, title: str, content: str) -> int:
    """Insert a document, or update it if its slug already exists but its
    content changed. A matching, unchanged row is left untouched (no write).

    Returns the document's id either way.
    """
    content_hash = hash_content(content)
    existing = conn.execute("SELECT id, content_hash FROM documents WHERE slug = ?", (slug,)).fetchone()

    if existing is None:
        cursor = conn.execute(
            "INSERT INTO documents (slug, title, content, content_hash) VALUES (?, ?, ?, ?)",
            (slug, title, content, content_hash),
        )
        return cursor.lastrowid

    if existing["content_hash"] != content_hash:
        conn.execute(
            "UPDATE documents SET title = ?, content = ?, content_hash = ? WHERE id = ?",
            (title, content, content_hash, existing["id"]),
        )
    return existing["id"]


def create_run(conn: sqlite3.Connection, started_at: str, params_json: str) -> int:
    """Record one analysis run and return its id."""
    cursor = conn.execute(
        "INSERT INTO runs (started_at, params_json) VALUES (?, ?)",
        (started_at, params_json),
    )
    return cursor.lastrowid


def upsert_parallel(
    conn: sqlite3.Connection,
    doc_a_id: int,
    doc_b_id: int,
    a_start: int,
    a_end: int,
    b_start: int,
    b_end: int,
    score: float,
    match_type: str,
    run_id: int,
) -> None:
    """Insert a parallel, or refresh its score/type/run if it already exists.

    `doc_a_id`/`doc_b_id` and the matching offset pairs are reordered here so
    that doc_a_id < doc_b_id always holds in storage (see DECISIONS.md,
    "Canonical pair ordering is enforced in the database layer, not trusted
    from the caller") -- callers do not need to pre-sort their document pairs.

    `status` and `note` are deliberately absent from the UPDATE: SQLite's
    upsert only touches the columns named in the SET clause, so a status or
    note the researcher already set survives any number of re-runs untouched.
    """
    if doc_a_id > doc_b_id:
        doc_a_id, doc_b_id = doc_b_id, doc_a_id
        a_start, a_end, b_start, b_end = b_start, b_end, a_start, a_end

    conn.execute(
        """
        INSERT INTO parallels
            (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end, score, match_type, last_seen_run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end)
        DO UPDATE SET score = excluded.score,
                      match_type = excluded.match_type,
                      last_seen_run_id = excluded.last_seen_run_id
        """,
        (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end, score, match_type, run_id),
    )
