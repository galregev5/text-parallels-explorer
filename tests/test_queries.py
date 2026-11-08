"""Unit tests for the pure WHERE-clause builder in app/queries.py -- the
part of the API's filtering that doesn't need a database to verify.
"""

from app.queries import ParallelFilters, build_where


def test_no_filters_matches_everything():
    where_sql, params = build_where(ParallelFilters())
    assert where_sql == "1 = 1"
    assert params == []


def test_doc_filter_matches_either_side():
    where_sql, params = build_where(ParallelFilters(doc=7))
    assert "doc_a_id = ?" in where_sql
    assert "doc_b_id = ?" in where_sql
    assert params == [7, 7]


def test_pair_filter_is_order_independent():
    # A caller who asks for the pair (5, 2) and one who asks for (2, 5) must
    # produce the identical query: storage is always canonical-ordered.
    forward = build_where(ParallelFilters(doc_a=2, doc_b=5))
    reversed_order = build_where(ParallelFilters(doc_a=5, doc_b=2))
    assert forward == reversed_order
    assert forward[1] == [2, 5]


def test_score_range_uses_inclusive_bounds():
    _, params = build_where(ParallelFilters(min_score=0.5, max_score=0.9))
    assert params == [0.5, 0.9]


def test_text_search_is_lowercased_for_case_insensitive_like():
    where_sql, params = build_where(ParallelFilters(q="Verily"))
    assert params == ["%verily%", "%verily%"]
    assert "LOWER(" in where_sql


def test_latest_only_adds_no_bound_parameters():
    where_sql, params = build_where(ParallelFilters(latest_only=True))
    assert "last_seen_run_id" in where_sql
    assert params == []  # the subquery has no placeholders of its own


def test_filters_combine_with_and():
    where_sql, params = build_where(ParallelFilters(match_type="near", status="pending", min_score=0.8))
    assert where_sql.count(" AND ") == 2
    assert params == ["near", "pending", 0.8]
