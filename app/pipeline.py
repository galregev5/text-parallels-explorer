"""Tie the algorithm to storage: run it over a whole corpus, idempotently.

This is the function Phase 4 calls on container start and from the "re-run
analysis" button. It is tested directly here in Phase 3 because the
assignment's own acceptance test for idempotency -- run it twice, get the
same row count, keep a status set in between -- needs the two layers wired
together to mean anything.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from datetime import UTC, datetime
from itertools import combinations

from app.algorithm import Params, build_ngram_index, find_parallels, to_char_span, tokenize
from app.db import create_run, hash_content, upsert_document, upsert_parallel


def run_pipeline(
    conn: sqlite3.Connection,
    documents: list[tuple[str, str, str]],  # (slug, title, content)
    params: Params = Params(),
    force: bool = False,
) -> dict:
    """Upsert `documents`, then find and store parallels for every pair.

    Unless `force` is true, the analysis itself is skipped -- no new `runs`
    row, no re-chaining -- when nothing that could change the result has
    changed: every document's content hash still matches what is stored, and
    `params` is identical to the most recent run's. This is what makes
    "on container start, run the pipeline" cheap to do on every restart (the
    common case), while `force=True` is what the "re-run analysis" button
    uses to mean what it says regardless. See DECISIONS.md ("Phase 4 --
    skip-if-unchanged is an extension of Phase 3's run_pipeline, not a new
    function") for why this is not two functions with duplicated logic.

    The whole run -- every document upsert and every parallel upsert -- commits
    as one transaction: a crash or error partway through leaves the database
    exactly as it was before the run started, never a half-written one that
    could be mistaken for a smaller but complete run.

    Returns {"run_id": int, "ran": bool, "total_parallels": int}. When `ran`
    is False, `run_id` is the pre-existing run that already covers this
    corpus and these params.
    """
    with conn:
        any_document_changed = False
        doc_ids = {}
        for slug, title, content in documents:
            existing_hash = conn.execute(
                "SELECT content_hash FROM documents WHERE slug = ?", (slug,)
            ).fetchone()
            if existing_hash is None or existing_hash["content_hash"] != hash_content(content):
                any_document_changed = True
            doc_ids[slug] = upsert_document(conn, slug, title, content)

        params_json = json.dumps(dataclasses.asdict(params), sort_keys=True)
        previous_run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        nothing_changed = (
            not force
            and not any_document_changed
            and previous_run is not None
            and previous_run["params_json"] == params_json
        )
        if nothing_changed:
            total = conn.execute("SELECT COUNT(*) AS n FROM parallels").fetchone()["n"]
            return {"run_id": previous_run["id"], "ran": False, "total_parallels": total}

        run_id = create_run(conn, started_at=datetime.now(UTC).isoformat(), params_json=params_json)

        tokens = {slug: tokenize(content) for slug, _, content in documents}
        ngram_indexes = {slug: build_ngram_index(tokens[slug], params.ngram_size) for slug, _, _ in documents}

        for (slug_a, _, _), (slug_b, _, _) in combinations(documents, 2):
            parallels = find_parallels(
                tokens[slug_a],
                tokens[slug_b],
                params,
                index_a=ngram_indexes[slug_a],
                index_b=ngram_indexes[slug_b],
            )
            for parallel in parallels:
                # Stored offsets are CHARACTER positions (per the assignment's
                # requirement), not the token indices the algorithm works in.
                a_start, a_end = to_char_span(tokens[slug_a], parallel.a_token_start, parallel.a_token_end)
                b_start, b_end = to_char_span(tokens[slug_b], parallel.b_token_start, parallel.b_token_end)
                upsert_parallel(
                    conn,
                    doc_ids[slug_a],
                    doc_ids[slug_b],
                    a_start,
                    a_end,
                    b_start,
                    b_end,
                    parallel.score,
                    parallel.match_type,
                    run_id,
                )

        total = conn.execute("SELECT COUNT(*) AS n FROM parallels").fetchone()["n"]

    return {"run_id": run_id, "ran": True, "total_parallels": total}
