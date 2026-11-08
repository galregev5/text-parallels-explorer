"""Unit tests for app/db.py: schema shape, and upsert idempotency/safety."""

import sqlite3

import pytest

from app.db import connect, create_run, upsert_document, upsert_parallel


@pytest.fixture
def conn():
    connection = connect(":memory:")
    yield connection
    connection.close()


def table_names(conn) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


# --- schema -----------------------------------------------------------------


def test_schema_creates_all_three_tables(conn):
    assert {"documents", "runs", "parallels"} <= table_names(conn)


def test_schema_rejects_an_unknown_match_type(conn):
    doc_a = upsert_document(conn, "a", "A", "text a")
    doc_b = upsert_document(conn, "b", "B", "text b")
    run_id = create_run(conn, "2025-01-01T00:00:00+00:00", "{}")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO parallels
               (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end, score, match_type, last_seen_run_id)
               VALUES (?, ?, 0, 10, 0, 10, 1.0, 'kinda-exact', ?)""",
            (doc_a, doc_b, run_id),
        )


def test_schema_rejects_doc_a_id_not_less_than_doc_b_id(conn):
    doc_a = upsert_document(conn, "a", "A", "text a")
    doc_b = upsert_document(conn, "b", "B", "text b")
    run_id = create_run(conn, "2025-01-01T00:00:00+00:00", "{}")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            """INSERT INTO parallels
               (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end, score, match_type, last_seen_run_id)
               VALUES (?, ?, 0, 10, 0, 10, 1.0, 'exact', ?)""",
            (max(doc_a, doc_b), min(doc_a, doc_b), run_id),
        )


# --- upsert_document ---------------------------------------------------------


def test_upsert_document_inserts_a_new_document(conn):
    doc_id = upsert_document(conn, "matthew", "Matthew", "In the beginning...")
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    assert row["slug"] == "matthew"
    assert row["content"] == "In the beginning..."
    assert len(row["content_hash"]) == 64  # sha256 hex digest


def test_upsert_document_is_a_no_op_when_content_is_unchanged(conn):
    first_id = upsert_document(conn, "matthew", "Matthew", "same content")
    second_id = upsert_document(conn, "matthew", "Matthew", "same content")
    assert first_id == second_id
    assert conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"] == 1


def test_upsert_document_updates_content_when_it_changes(conn):
    doc_id = upsert_document(conn, "matthew", "Matthew", "old content")
    same_id = upsert_document(conn, "matthew", "Matthew", "new content")
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    assert same_id == doc_id
    assert row["content"] == "new content"
    assert conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"] == 1


# --- upsert_parallel ----------------------------------------------------------


def two_documents(conn) -> tuple[int, int]:
    return upsert_document(conn, "a", "A", "text a"), upsert_document(conn, "b", "B", "text b")


def test_upsert_parallel_inserts_a_new_row(conn):
    doc_a, doc_b = two_documents(conn)
    run_id = create_run(conn, "2025-01-01T00:00:00+00:00", "{}")
    upsert_parallel(conn, doc_a, doc_b, 0, 10, 5, 15, 0.9, "near", run_id)
    row = conn.execute("SELECT * FROM parallels").fetchone()
    assert (row["doc_a_id"], row["doc_b_id"]) == (doc_a, doc_b)
    assert row["status"] == "pending"  # schema default
    assert row["note"] is None


def test_upsert_parallel_reorders_a_reversed_pair_to_canonical_order(conn):
    doc_a, doc_b = two_documents(conn)
    assert doc_a < doc_b
    run_id = create_run(conn, "2025-01-01T00:00:00+00:00", "{}")

    # The real a_start/a_end belong to doc_a and the real b_start/b_end to
    # doc_b. Call with the pair reversed (doc_b first, doc_a second) and its
    # matching offsets reversed too, exactly as a caller that has not sorted
    # its pair would.
    a_start, a_end, b_start, b_end = 0, 10, 5, 15
    upsert_parallel(conn, doc_b, doc_a, b_start, b_end, a_start, a_end, 0.9, "near", run_id)

    row = conn.execute("SELECT * FROM parallels").fetchone()
    assert (row["doc_a_id"], row["doc_b_id"]) == (doc_a, doc_b)
    # offsets must have swapped along with the documents, not stayed put
    assert (row["a_start"], row["a_end"]) == (a_start, a_end)
    assert (row["b_start"], row["b_end"]) == (b_start, b_end)


def test_upsert_parallel_is_idempotent_for_the_same_passage(conn):
    doc_a, doc_b = two_documents(conn)
    run_id = create_run(conn, "2025-01-01T00:00:00+00:00", "{}")
    upsert_parallel(conn, doc_a, doc_b, 0, 10, 5, 15, 0.9, "near", run_id)
    upsert_parallel(conn, doc_a, doc_b, 0, 10, 5, 15, 0.9, "near", run_id)
    assert conn.execute("SELECT COUNT(*) AS n FROM parallels").fetchone()["n"] == 1


def test_upsert_parallel_refreshes_score_and_run_but_never_status_or_note(conn):
    doc_a, doc_b = two_documents(conn)
    run_1 = create_run(conn, "2025-01-01T00:00:00+00:00", "{}")
    upsert_parallel(conn, doc_a, doc_b, 0, 10, 5, 15, 0.80, "near", run_1)

    conn.execute("UPDATE parallels SET status = 'approved', note = 'looks real' WHERE id = 1")

    run_2 = create_run(conn, "2025-01-02T00:00:00+00:00", "{}")
    upsert_parallel(conn, doc_a, doc_b, 0, 10, 5, 15, 0.95, "near", run_2)

    row = conn.execute("SELECT * FROM parallels").fetchone()
    assert conn.execute("SELECT COUNT(*) AS n FROM parallels").fetchone()["n"] == 1
    assert row["score"] == 0.95  # refreshed
    assert row["last_seen_run_id"] == run_2  # refreshed
    assert row["status"] == "approved"  # untouched
    assert row["note"] == "looks real"  # untouched


# --- file-backed persistence (the Docker-volume case) ------------------------


def test_data_persists_across_a_close_and_reconnect(tmp_path):
    db_path = tmp_path / "app.db"

    conn = connect(db_path)
    upsert_document(conn, "matthew", "Matthew", "some content")
    conn.commit()  # db.py functions never commit themselves -- the caller does
    conn.close()

    reopened = connect(db_path)
    row = reopened.execute("SELECT * FROM documents WHERE slug = 'matthew'").fetchone()
    reopened.close()

    assert row["content"] == "some content"
