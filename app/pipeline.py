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
from app.db import create_run, upsert_document, upsert_parallel


def run_pipeline(
    conn: sqlite3.Connection,
    documents: list[tuple[str, str, str]],  # (slug, title, content)
    params: Params = Params(),
) -> int:
    """Upsert `documents`, then find and store parallels for every pair.

    The whole run -- every document upsert and every parallel upsert -- commits
    as one transaction: a crash or error partway through leaves the database
    exactly as it was before the run started, never a half-written one that
    could be mistaken for a smaller but complete run.

    Returns the new run's id.
    """
    with conn:
        doc_ids = {slug: upsert_document(conn, slug, title, content) for slug, title, content in documents}
        run_id = create_run(
            conn,
            started_at=datetime.now(UTC).isoformat(),
            params_json=json.dumps(dataclasses.asdict(params), sort_keys=True),
        )

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

    return run_id
