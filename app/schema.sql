-- Schema for the Text Parallels Explorer. See DECISIONS.md ("Phase 3 -- Database")
-- for why each constraint is here, not just what it says.

PRAGMA foreign_keys = ON;

-- One row per corpus document. Upserted by slug (see app/db.py upsert_document):
-- content_hash lets a re-run detect that a document's text actually changed
-- without re-hashing it elsewhere, and avoids a write when it has not.
CREATE TABLE IF NOT EXISTS documents (
    id            INTEGER PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,
    title         TEXT NOT NULL,
    content       TEXT NOT NULL,
    content_hash  TEXT NOT NULL
);

-- One row per analysis run: which parameters produced the parallels that
-- reference it via last_seen_run_id. params_json is the algorithm's Params
-- dataclass, serialized, so a run is self-describing without a join.
CREATE TABLE IF NOT EXISTS runs (
    id          INTEGER PRIMARY KEY,
    started_at  TEXT NOT NULL,
    params_json TEXT NOT NULL
);

-- One row per matched passage between two documents. doc_a_id < doc_b_id always
-- (enforced below, not just promised by the application) so a pair is never
-- stored both ways around. The UNIQUE constraint is the whole idempotency
-- mechanism: re-running the pipeline with the same parameters recomputes the
-- same (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end) key and upserts the
-- same row instead of inserting a duplicate (see app/db.py upsert_parallel).
-- status and note are deliberately NOT part of that upsert's SET clause, so a
-- researcher's review is never overwritten by a re-run.
CREATE TABLE IF NOT EXISTS parallels (
    id               INTEGER PRIMARY KEY,
    doc_a_id         INTEGER NOT NULL REFERENCES documents(id),
    doc_b_id         INTEGER NOT NULL REFERENCES documents(id),
    a_start          INTEGER NOT NULL,
    a_end            INTEGER NOT NULL,
    b_start          INTEGER NOT NULL,
    b_end            INTEGER NOT NULL,
    score            REAL NOT NULL,
    match_type       TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    note             TEXT,
    last_seen_run_id INTEGER NOT NULL REFERENCES runs(id),
    UNIQUE (doc_a_id, doc_b_id, a_start, a_end, b_start, b_end),
    CHECK (doc_a_id < doc_b_id),
    CHECK (a_start < a_end),
    CHECK (b_start < b_end),
    CHECK (score >= 0.0 AND score <= 1.0),
    CHECK (match_type IN ('exact', 'near')),
    CHECK (status IN ('pending', 'approved', 'rejected'))
);

-- Phase 4's list view filters/sorts by pair, status and score; last_seen_run_id
-- is how it will tell "from the latest run" apart from stale leftovers. Adding
-- these now costs nothing and they are schema, not query logic, so they belong
-- here rather than waiting on the Phase 4 API that will actually use them.
CREATE INDEX IF NOT EXISTS idx_parallels_pair ON parallels(doc_a_id, doc_b_id);
CREATE INDEX IF NOT EXISTS idx_parallels_status ON parallels(status);
CREATE INDEX IF NOT EXISTS idx_parallels_score ON parallels(score);
CREATE INDEX IF NOT EXISTS idx_parallels_last_seen_run ON parallels(last_seen_run_id);
