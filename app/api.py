"""The HTTP API: documents, parallels (list/detail/update), and re-run.

Every route gets its own SQLite connection via `get_conn` (opened per request,
closed at the end) rather than sharing one connection across requests --
sqlite3 connections are not safe to use from more than the thread that
created them, and FastAPI runs sync routes in a thread pool, so a single
shared connection would be a concurrency bug waiting to happen. SQLite
handles multiple connections to the same file natively; this is the standard
pattern, not a workaround. The dependency commits once on a clean exit (the
same "caller controls the transaction boundary" convention `app/db.py`
documents) and rolls back on an exception.
"""

from __future__ import annotations

import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import DB_PATH
from app.corpus import DOCUMENTS, load_corpus
from app.db import connect, get_document, latest_run, list_documents, update_review
from app.pipeline import run_pipeline
from app.queries import FROM_CLAUSE, DEFAULT_SORT, ParallelFilters, count_parallels, list_parallels, ordered_ids, stale_count
from app.schemas import (
    DocumentDetailOut,
    DocumentOut,
    ParallelDetailOut,
    ParallelListItemOut,
    ParallelListOut,
    ParallelUpdateIn,
    RerunOut,
)

router = APIRouter()


def get_conn():
    conn = connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parallel_filters(
    doc: int | None = Query(None, description="either side of the pair is this document id"),
    doc_a: int | None = Query(None, description="with doc_b, this exact pair, in either order"),
    doc_b: int | None = Query(None),
    match_type: Literal["exact", "near"] | None = Query(None),
    status: Literal["pending", "approved", "rejected"] | None = Query(None),
    min_score: float | None = Query(None, ge=0.0, le=1.0),
    max_score: float | None = Query(None, ge=0.0, le=1.0),
    q: str | None = Query(None, description="case-insensitive text search within the matched passage"),
    latest_only: bool = Query(False, description="only rows the most recent run touched"),
) -> ParallelFilters:
    return ParallelFilters(
        doc=doc, doc_a=doc_a, doc_b=doc_b, match_type=match_type, status=status,
        min_score=min_score, max_score=max_score, q=q, latest_only=latest_only,
    )


def _latest_run_id(conn: sqlite3.Connection) -> int | None:
    row = latest_run(conn)
    return row["id"] if row is not None else None


def _fetch_parallel_row(conn: sqlite3.Connection, parallel_id: int) -> sqlite3.Row | None:
    return conn.execute(
        f"""
        SELECT p.*,
               da.slug AS doc_a_slug, da.title AS doc_a_title, da.content AS doc_a_content,
               db.slug AS doc_b_slug, db.title AS doc_b_title, db.content AS doc_b_content
        {FROM_CLAUSE}
        WHERE p.id = ?
        """,
        (parallel_id,),
    ).fetchone()


# --- documents ----------------------------------------------------------


@router.get("/documents", response_model=list[DocumentOut])
def api_list_documents(conn: sqlite3.Connection = Depends(get_conn)):
    return [DocumentOut(id=row["id"], slug=row["slug"], title=row["title"]) for row in list_documents(conn)]


@router.get("/documents/{doc_id}", response_model=DocumentDetailOut)
def api_get_document(doc_id: int, conn: sqlite3.Connection = Depends(get_conn)):
    row = get_document(conn, doc_id)
    if row is None:
        raise HTTPException(404, "document not found")
    return DocumentDetailOut(id=row["id"], slug=row["slug"], title=row["title"], content=row["content"])


# --- parallels: list, detail, update -------------------------------------


@router.get("/parallels", response_model=ParallelListOut)
def api_list_parallels(
    filters: ParallelFilters = Depends(parallel_filters),
    sort: str = Query(DEFAULT_SORT),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_conn),
):
    latest_id = _latest_run_id(conn)
    items = [
        ParallelListItemOut.from_row(row, latest_id)
        for row in list_parallels(conn, filters, sort=sort, limit=limit, offset=offset)
    ]
    return ParallelListOut(items=items, total=count_parallels(conn, filters), stale_count=stale_count(conn))


@router.get("/parallels/{parallel_id}", response_model=ParallelDetailOut)
def api_get_parallel(
    parallel_id: int,
    filters: ParallelFilters = Depends(parallel_filters),
    sort: str = Query(DEFAULT_SORT),
    conn: sqlite3.Connection = Depends(get_conn),
):
    row = _fetch_parallel_row(conn, parallel_id)
    if row is None:
        raise HTTPException(404, "parallel not found")

    # Prev/next within the SAME filtered, sorted set the list page is
    # showing (the filters/sort are passed through from the list page's own
    # URL) -- not within the whole table. If the current id falls outside
    # that set (e.g. a filter changed after navigating here), there is no
    # context to navigate within, so both come back None rather than
    # guessing at a global order the page was never showing.
    ids = ordered_ids(conn, filters, sort=sort)
    prev_id = next_id = None
    if parallel_id in ids:
        index = ids.index(parallel_id)
        prev_id = ids[index - 1] if index > 0 else None
        next_id = ids[index + 1] if index < len(ids) - 1 else None

    latest_id = _latest_run_id(conn)
    return ParallelDetailOut(
        id=row["id"],
        doc_a=DocumentDetailOut(id=row["doc_a_id"], slug=row["doc_a_slug"], title=row["doc_a_title"], content=row["doc_a_content"]),
        doc_b=DocumentDetailOut(id=row["doc_b_id"], slug=row["doc_b_slug"], title=row["doc_b_title"], content=row["doc_b_content"]),
        a_start=row["a_start"], a_end=row["a_end"], b_start=row["b_start"], b_end=row["b_end"],
        score=row["score"], match_type=row["match_type"], status=row["status"], note=row["note"],
        is_stale=row["last_seen_run_id"] != latest_id,
        prev_id=prev_id, next_id=next_id,
    )


@router.patch("/parallels/{parallel_id}", response_model=ParallelListItemOut)
def api_update_parallel(
    parallel_id: int,
    body: ParallelUpdateIn,
    conn: sqlite3.Connection = Depends(get_conn),
):
    found = update_review(conn, parallel_id, status=body.status, note=body.note)
    if not found:
        raise HTTPException(404, "parallel not found")

    row = conn.execute(
        f"""
        SELECT p.*,
               da.slug AS doc_a_slug, da.title AS doc_a_title,
               db.slug AS doc_b_slug, db.title AS doc_b_title,
               SUBSTR(da.content, p.a_start + 1, p.a_end - p.a_start) AS text_a,
               SUBSTR(db.content, p.b_start + 1, p.b_end - p.b_start) AS text_b
        {FROM_CLAUSE}
        WHERE p.id = ?
        """,
        (parallel_id,),
    ).fetchone()
    return ParallelListItemOut.from_row(row, _latest_run_id(conn))


# --- re-run ----------------------------------------------------------------


@router.post("/rerun", response_model=RerunOut)
def api_rerun(conn: sqlite3.Connection = Depends(get_conn)):
    corpus = load_corpus()
    documents = [(slug, title, corpus[slug]) for slug, title in DOCUMENTS]
    result = run_pipeline(conn, documents, force=True)  # the button always means it
    return RerunOut(
        run_id=result["run_id"],
        ran=result["ran"],
        total_parallels=result["total_parallels"],
        stale_count=stale_count(conn),
    )
