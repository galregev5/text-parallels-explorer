"""Idempotency tests for app/pipeline.py -- the assignment's own acceptance
test ("run the pipeline twice -> same row count; a status set between runs
is preserved") plus the staleness case that motivated `last_seen_run_id`,
plus Phase 4's skip-if-unchanged / force extension.
"""

from app.algorithm import Params
from app.corpus import DOCUMENTS, load_corpus
from app.db import connect
from app.pipeline import run_pipeline

# Two short documents sharing one passage with a single substituted word --
# the same toy shape the algorithm's own tests use, kept tiny and explicit
# here so a test failure is easy to read, not because the mechanism differs
# from the real corpus.
TOY_PARAMS = Params(ngram_size=3, gap_tolerance=4, min_passage_tokens=4, max_ngram_document_frequency=100)
TOY_DOCS = [
    ("a", "Document A", "The quick brown fox jumps over the lazy dog today."),
    ("b", "Document B", "The quick brown fox leaps over the lazy dog today."),
]


def parallel_count(conn) -> int:
    return conn.execute("SELECT COUNT(*) AS n FROM parallels").fetchone()["n"]


# --- re-running the algorithm itself is idempotent (force=True) -------------


def test_forcing_the_pipeline_twice_does_not_duplicate_rows():
    conn = connect(":memory:")
    first = run_pipeline(conn, TOY_DOCS, TOY_PARAMS, force=True)
    assert first["ran"] is True
    assert first["total_parallels"] > 0

    second = run_pipeline(conn, TOY_DOCS, TOY_PARAMS, force=True)

    assert second["ran"] is True
    assert second["total_parallels"] == first["total_parallels"]
    assert parallel_count(conn) == first["total_parallels"]


def test_a_status_set_between_forced_runs_survives_a_rerun():
    conn = connect(":memory:")
    run_pipeline(conn, TOY_DOCS, TOY_PARAMS, force=True)

    conn.execute("UPDATE parallels SET status = 'approved', note = 'reviewed' WHERE id = 1")

    second = run_pipeline(conn, TOY_DOCS, TOY_PARAMS, force=True)

    row = conn.execute("SELECT * FROM parallels WHERE id = 1").fetchone()
    assert row["status"] == "approved"
    assert row["note"] == "reviewed"
    assert row["last_seen_run_id"] == second["run_id"]  # score/run were still refreshed


def test_changing_params_adds_rows_without_touching_the_old_ones():
    conn = connect(":memory:")
    first = run_pipeline(conn, TOY_DOCS, TOY_PARAMS, force=True)
    conn.execute("UPDATE parallels SET status = 'rejected' WHERE id = 1")

    stricter_params = Params(
        ngram_size=TOY_PARAMS.ngram_size,
        gap_tolerance=TOY_PARAMS.gap_tolerance,
        min_passage_tokens=100,  # nothing in this toy corpus is this long
        max_ngram_document_frequency=TOY_PARAMS.max_ngram_document_frequency,
    )
    second = run_pipeline(conn, TOY_DOCS, stricter_params, force=True)

    # The old row is untouched -- not revisited by the second run at all --
    # so it is now identifiable as stale: its last_seen_run_id lags behind
    # the latest run.
    old_row = conn.execute("SELECT * FROM parallels WHERE id = 1").fetchone()
    assert old_row["status"] == "rejected"
    assert old_row["last_seen_run_id"] == first["run_id"]
    assert old_row["last_seen_run_id"] != second["run_id"]

    # And the stricter run found nothing new to add.
    assert conn.execute(
        "SELECT COUNT(*) AS n FROM parallels WHERE last_seen_run_id = ?", (second["run_id"],)
    ).fetchone()["n"] == 0


def test_running_the_pipeline_twice_on_the_real_corpus_does_not_duplicate_rows():
    # The literal acceptance test from the assignment, on the actual corpus
    # and the actual chosen defaults -- not just the toy shape above.
    corpus = load_corpus()
    documents = [(slug, title, corpus[slug]) for slug, title in DOCUMENTS]

    conn = connect(":memory:")
    first = run_pipeline(conn, documents, force=True)  # Params() defaults
    assert first["total_parallels"] > 0

    second = run_pipeline(conn, documents, force=True)

    assert second["total_parallels"] == first["total_parallels"]


# --- skip-if-unchanged (the container-start case) ----------------------------


def test_an_unforced_rerun_with_nothing_changed_is_skipped():
    conn = connect(":memory:")
    first = run_pipeline(conn, TOY_DOCS, TOY_PARAMS)
    assert first["ran"] is True

    second = run_pipeline(conn, TOY_DOCS, TOY_PARAMS)  # force=False, nothing changed

    assert second["ran"] is False
    assert second["run_id"] == first["run_id"]  # no new run row was created
    assert second["total_parallels"] == first["total_parallels"]
    # Confirms no new row was actually created, not just that the returned
    # id happens to match.
    assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"] == 1


def test_an_unforced_rerun_with_changed_params_still_runs():
    conn = connect(":memory:")
    run_pipeline(conn, TOY_DOCS, TOY_PARAMS)

    different_params = Params(
        ngram_size=TOY_PARAMS.ngram_size + 1,
        gap_tolerance=TOY_PARAMS.gap_tolerance,
        min_passage_tokens=TOY_PARAMS.min_passage_tokens,
        max_ngram_document_frequency=TOY_PARAMS.max_ngram_document_frequency,
    )
    second = run_pipeline(conn, TOY_DOCS, different_params)  # force=False

    assert second["ran"] is True
    assert conn.execute("SELECT COUNT(*) AS n FROM runs").fetchone()["n"] == 2


def test_an_unforced_rerun_with_changed_document_content_still_runs():
    conn = connect(":memory:")
    run_pipeline(conn, TOY_DOCS, TOY_PARAMS)

    changed_docs = [TOY_DOCS[0], ("b", "Document B", TOY_DOCS[1][2] + " Extra sentence here.")]
    second = run_pipeline(conn, changed_docs, TOY_PARAMS)  # force=False

    assert second["ran"] is True
