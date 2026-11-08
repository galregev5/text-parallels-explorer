"""Build the WHERE/ORDER BY for listing parallels, shared by the paginated
list endpoint and the detail page's prev/next navigation -- both need to
agree on exactly the same filtered, sorted set, or "next" from a filtered
list could point at a row the filter would have excluded.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

FROM_CLAUSE = """
FROM parallels p
JOIN documents da ON da.id = p.doc_a_id
JOIN documents db ON db.id = p.doc_b_id
"""

# An explicit allow-list, not a user-supplied column name, so `sort` can
# never become a SQL-injection vector no matter what a client sends.
SORT_OPTIONS = {
    "score_desc": "p.score DESC, p.id ASC",
    "score_asc": "p.score ASC, p.id ASC",
    "id_desc": "p.id DESC",
    "id_asc": "p.id ASC",
}
DEFAULT_SORT = "score_desc"


@dataclass(frozen=True)
class ParallelFilters:
    doc: int | None = None  # either side of the pair is this document id
    doc_a: int | None = None  # this exact pair, in either stored order
    doc_b: int | None = None
    match_type: str | None = None  # "exact" | "near"
    status: str | None = None  # "pending" | "approved" | "rejected"
    min_score: float | None = None
    max_score: float | None = None
    q: str | None = None  # case-insensitive text search within the matched passage
    latest_only: bool = False  # only rows last touched by the most recent run


def build_where(filters: ParallelFilters) -> tuple[str, list]:
    """Return (sql_fragment, bound_params) for everything in `filters`."""
    clauses: list[str] = []
    params: list = []

    if filters.doc is not None:
        clauses.append("(p.doc_a_id = ? OR p.doc_b_id = ?)")
        params += [filters.doc, filters.doc]

    if filters.doc_a is not None and filters.doc_b is not None:
        low, high = sorted((filters.doc_a, filters.doc_b))
        clauses.append("(p.doc_a_id = ? AND p.doc_b_id = ?)")
        params += [low, high]

    if filters.match_type is not None:
        clauses.append("p.match_type = ?")
        params.append(filters.match_type)

    if filters.status is not None:
        clauses.append("p.status = ?")
        params.append(filters.status)

    if filters.min_score is not None:
        clauses.append("p.score >= ?")
        params.append(filters.min_score)

    if filters.max_score is not None:
        clauses.append("p.score <= ?")
        params.append(filters.max_score)

    if filters.q:
        term = f"%{filters.q.lower()}%"
        clauses.append(
            "(LOWER(SUBSTR(da.content, p.a_start + 1, p.a_end - p.a_start)) LIKE ?"
            " OR LOWER(SUBSTR(db.content, p.b_start + 1, p.b_end - p.b_start)) LIKE ?)"
        )
        params += [term, term]

    if filters.latest_only:
        clauses.append("p.last_seen_run_id = (SELECT MAX(id) FROM runs)")

    where_sql = " AND ".join(clauses) if clauses else "1 = 1"
    return where_sql, params


def count_parallels(conn: sqlite3.Connection, filters: ParallelFilters) -> int:
    where_sql, params = build_where(filters)
    row = conn.execute(f"SELECT COUNT(*) AS n {FROM_CLAUSE} WHERE {where_sql}", params).fetchone()
    return row["n"]


def list_parallels(
    conn: sqlite3.Connection,
    filters: ParallelFilters,
    sort: str = DEFAULT_SORT,
    limit: int = 50,
    offset: int = 0,
) -> list[sqlite3.Row]:
    where_sql, params = build_where(filters)
    order_sql = SORT_OPTIONS.get(sort, SORT_OPTIONS[DEFAULT_SORT])
    return conn.execute(
        f"""
        SELECT p.*,
               da.slug AS doc_a_slug, da.title AS doc_a_title,
               db.slug AS doc_b_slug, db.title AS doc_b_title,
               SUBSTR(da.content, p.a_start + 1, p.a_end - p.a_start) AS text_a,
               SUBSTR(db.content, p.b_start + 1, p.b_end - p.b_start) AS text_b
        {FROM_CLAUSE}
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()


def export_rows(conn: sqlite3.Connection, filters: ParallelFilters, sort: str = DEFAULT_SORT) -> list[sqlite3.Row]:
    """Every row in `filters`' set, in `sort` order, unpaginated -- for CSV export."""
    where_sql, params = build_where(filters)
    order_sql = SORT_OPTIONS.get(sort, SORT_OPTIONS[DEFAULT_SORT])
    return conn.execute(
        f"""
        SELECT p.*,
               da.slug AS doc_a_slug, db.slug AS doc_b_slug,
               SUBSTR(da.content, p.a_start + 1, p.a_end - p.a_start) AS text_a,
               SUBSTR(db.content, p.b_start + 1, p.b_end - p.b_start) AS text_b
        {FROM_CLAUSE}
        WHERE {where_sql}
        ORDER BY {order_sql}
        """,
        params,
    ).fetchall()


def pair_counts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Per document pair: parallel counts from the LATEST run only, by type and status.

    Latest run only: the matrix summarizes the current analysis. Stale rows
    from earlier parameter choices would inflate the counts without saying
    so; they already have their own banner and filter on the list page.
    """
    return conn.execute(
        """
        SELECT doc_a_id, doc_b_id,
               COUNT(*) AS total,
               SUM(match_type = 'exact') AS exact,
               SUM(match_type = 'near') AS near,
               SUM(status = 'approved') AS approved,
               SUM(status = 'rejected') AS rejected
        FROM parallels
        WHERE last_seen_run_id = (SELECT MAX(id) FROM runs)
        GROUP BY doc_a_id, doc_b_id
        """
    ).fetchall()


def ordered_ids(conn: sqlite3.Connection, filters: ParallelFilters, sort: str = DEFAULT_SORT) -> list[int]:
    """Every id in `filters`' set, in `sort` order -- for prev/next lookup.

    Fine at this corpus's scale (hundreds of rows, one cheap query); a corpus
    large enough for this to matter would want a windowed SQL query instead
    of an in-Python index lookup -- see README limitations.
    """
    where_sql, params = build_where(filters)
    order_sql = SORT_OPTIONS.get(sort, SORT_OPTIONS[DEFAULT_SORT])
    rows = conn.execute(f"SELECT p.id {FROM_CLAUSE} WHERE {where_sql} ORDER BY {order_sql}", params).fetchall()
    return [row["id"] for row in rows]


def stale_count(conn: sqlite3.Connection) -> int:
    """How many parallels were not touched by the most recent run."""
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM parallels WHERE last_seen_run_id != (SELECT MAX(id) FROM runs)"
    ).fetchone()
    return row["n"]
