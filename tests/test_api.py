"""API tests, through the real FastAPI app.

Every test overrides the `get_conn` dependency with an in-memory connection
it controls, rather than letting requests hit `app.config.DB_PATH` (the real
`data/app.db`) -- `get_conn` opens its own connection per request independent
of the app's startup lifespan, so skipping the lifespan alone is not enough
to keep a test from touching real project data. This was confirmed directly
before writing these tests: a plain request through an un-started TestClient
still created `data/app.db` on disk.
"""

import pytest
from fastapi.testclient import TestClient

from app.algorithm import Params
from app.api import get_conn
from app.db import connect
from app.main import app
from app.pipeline import run_pipeline

TOY_PARAMS = Params(ngram_size=3, gap_tolerance=4, min_passage_tokens=4, max_ngram_document_frequency=100)
# Two separate matched regions, deliberately: a word substitution (-> one
# "near" match) and, separated by an insertion that breaks the chaining
# diagonal, a byte-identical sentence (-> one "exact" match). Needed so
# filter/pagination tests below have both a match_type to filter FOR and
# one to filter AGAINST, and more than one row to paginate over. Verified
# directly against app.algorithm before writing these tests.
TOY_DOCS = [
    (
        "a",
        "Document A",
        "The quick brown fox jumps over the lazy dog today near the river bank. "
        "Many sailors love the quiet harbor at dawn.",
    ),
    (
        "b",
        "Document B",
        "The quick brown fox leaps over the lazy dog today near the river bank. "
        "Indeed truly however nevertheless. "
        "Many sailors love the quiet harbor at dawn.",
    ),
]


@pytest.fixture
def conn():
    # check_same_thread=False: TestClient dispatches each request through a
    # thread pool, so this one shared connection is used from more than one
    # thread across a test's several requests -- never concurrently, just
    # sequentially, which is what the override is for (see app/db.py).
    connection = connect(":memory:", check_same_thread=False)
    run_pipeline(connection, TOY_DOCS, TOY_PARAMS, force=True)
    yield connection
    connection.close()


@pytest.fixture
def client(conn):
    def override_get_conn():
        yield conn
        conn.commit()

    app.dependency_overrides[get_conn] = override_get_conn
    yield TestClient(app)  # no `with`: the app's startup lifespan never runs
    app.dependency_overrides.clear()


# --- documents ---------------------------------------------------------------


def test_list_documents(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    slugs = {doc["slug"] for doc in res.json()}
    assert slugs == {"a", "b"}


def test_get_document_includes_content(client):
    doc_id = client.get("/api/documents").json()[0]["id"]
    res = client.get(f"/api/documents/{doc_id}")
    assert res.status_code == 200
    assert "quick brown fox" in res.json()["content"]


def test_get_missing_document_is_404(client):
    assert client.get("/api/documents/9999").status_code == 404


# --- parallels: list ----------------------------------------------------------


def test_list_parallels_returns_items_and_total(client):
    res = client.get("/api/parallels")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 1
    assert len(body["items"]) == body["total"]  # small toy corpus fits on one page
    item = body["items"][0]
    assert {"id", "doc_a", "doc_b", "score", "match_type", "status", "snippet_a", "snippet_b"} <= item.keys()


def test_list_parallels_filters_by_match_type(client):
    res = client.get("/api/parallels?match_type=exact")
    assert res.status_code == 200
    assert all(item["match_type"] == "exact" for item in res.json()["items"])


def test_list_parallels_filters_by_min_score_excludes_the_near_match(client):
    res = client.get("/api/parallels?min_score=0.999")
    assert all(item["score"] >= 0.999 for item in res.json()["items"])
    # the toy corpus's one substitution scores below 1.0 -- confirm it is
    # actually excluded, not just that nothing violates the filter vacuously
    unfiltered = client.get("/api/parallels").json()
    assert any(item["score"] < 0.999 for item in unfiltered["items"])


def test_list_parallels_text_search_is_case_insensitive(client):
    res = client.get("/api/parallels?q=RIVER")
    assert res.status_code == 200
    assert len(res.json()["items"]) >= 1


def test_list_parallels_pagination(client):
    first_page = client.get("/api/parallels?limit=1&offset=0").json()
    second_page = client.get("/api/parallels?limit=1&offset=1").json()
    assert len(first_page["items"]) == 1
    assert first_page["items"][0]["id"] != second_page["items"][0]["id"]


def test_list_parallels_rejects_an_invalid_match_type(client):
    res = client.get("/api/parallels?match_type=not-a-type")
    assert res.status_code == 422  # validated before it ever reaches SQL


# --- parallels: detail and navigation ---------------------------------------


def test_get_parallel_detail_includes_full_document_content(client):
    item_id = client.get("/api/parallels").json()["items"][0]["id"]
    res = client.get(f"/api/parallels/{item_id}")
    assert res.status_code == 200
    body = res.json()
    assert body["doc_a"]["content"].startswith("The quick brown fox")
    assert body["a_start"] < body["a_end"] <= len(body["doc_a"]["content"])


def test_get_missing_parallel_is_404(client):
    assert client.get("/api/parallels/99999").status_code == 404


def test_prev_next_navigation_covers_the_whole_filtered_set_exactly_once(client):
    # Walk the whole list via `next_id`, starting from the first item in the
    # same sort order, and check it visits every id exactly once.
    ids_in_order = [item["id"] for item in client.get("/api/parallels?sort=id_asc").json()["items"]]

    visited = []
    current_id = ids_in_order[0]
    while current_id is not None:
        detail = client.get(f"/api/parallels/{current_id}?sort=id_asc").json()
        visited.append(current_id)
        assert detail["prev_id"] == (visited[-2] if len(visited) > 1 else None)
        current_id = detail["next_id"]

    assert visited == ids_in_order


def test_navigation_is_none_when_id_is_outside_the_given_filter(client):
    item_id = client.get("/api/parallels?match_type=exact").json()["items"][0]["id"]
    # Ask for this same id's detail, but under a filter that would exclude it.
    res = client.get(f"/api/parallels/{item_id}?match_type=near")
    body = res.json()
    assert body["prev_id"] is None
    assert body["next_id"] is None


# --- parallels: update (review) ----------------------------------------------


def test_patch_updates_status_and_note(client):
    item_id = client.get("/api/parallels").json()["items"][0]["id"]
    res = client.patch(f"/api/parallels/{item_id}", json={"status": "approved", "note": "looks real"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["note"] == "looks real"

    # and it is durable -- a fresh GET reflects it too
    refetched = client.get(f"/api/parallels/{item_id}").json()
    assert refetched["status"] == "approved"
    assert refetched["note"] == "looks real"


def test_patch_rejects_an_invalid_status(client):
    item_id = client.get("/api/parallels").json()["items"][0]["id"]
    res = client.patch(f"/api/parallels/{item_id}", json={"status": "maybe"})
    assert res.status_code == 422


def test_patch_missing_parallel_is_404(client):
    res = client.patch("/api/parallels/99999", json={"status": "approved"})
    assert res.status_code == 404


def test_patch_with_only_a_note_leaves_status_unchanged(client):
    item_id = client.get("/api/parallels").json()["items"][0]["id"]
    client.patch(f"/api/parallels/{item_id}", json={"status": "rejected"})
    res = client.patch(f"/api/parallels/{item_id}", json={"note": "just a note"})
    assert res.json()["status"] == "rejected"
    assert res.json()["note"] == "just a note"


# --- rerun --------------------------------------------------------------------


def test_rerun_endpoint_forces_a_run_even_if_unchanged(client, conn):
    first = client.post("/api/rerun").json()
    assert first["ran"] is True  # force=True always actually runs

    second = client.post("/api/rerun").json()
    assert second["ran"] is True
    assert second["total_parallels"] == first["total_parallels"]


# --- static UI --------------------------------------------------------------


def test_index_page_is_served(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "Text Parallels Explorer" in res.text


def test_detail_page_is_served(client):
    res = client.get("/detail.html")
    assert res.status_code == 200
    assert "reviewPanel" in res.text


def test_static_assets_are_served(client):
    for path in ("/style.css", "/app.js", "/list.js", "/detail.js"):
        res = client.get(path)
        assert res.status_code == 200, path


# --- Phase 6: word diff, matrix, CSV export ----------------------------------


def _parallel_by_type(client, match_type):
    return client.get("/api/parallels", params={"match_type": match_type}).json()["items"][0]


def test_detail_of_a_near_match_marks_the_substituted_word_on_each_side(client):
    item = _parallel_by_type(client, "near")
    data = client.get(f"/api/parallels/{item['id']}").json()
    words_a = [data["doc_a"]["content"][start:end] for start, end in data["diff_a"]]
    words_b = [data["doc_b"]["content"][start:end] for start, end in data["diff_b"]]
    assert words_a == ["jumps"]
    assert words_b == ["leaps"]


def test_detail_of_an_exact_match_has_no_diff(client):
    item = _parallel_by_type(client, "exact")
    data = client.get(f"/api/parallels/{item['id']}").json()
    assert data["diff_a"] == [] and data["diff_b"] == []


def test_matrix_counts_the_pair_by_type_and_status(client):
    near = _parallel_by_type(client, "near")
    client.patch(f"/api/parallels/{near['id']}", json={"status": "approved"})

    data = client.get("/api/matrix").json()
    assert {doc["slug"] for doc in data["documents"]} == {"a", "b"}
    assert len(data["pairs"]) == 1
    pair = data["pairs"][0]
    assert pair["doc_a_id"] < pair["doc_b_id"]
    assert (pair["total"], pair["exact"], pair["near"]) == (2, 1, 1)
    assert (pair["approved"], pair["rejected"]) == (1, 0)


def _read_csv(res):
    import csv
    import io

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    text = res.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def test_csv_export_of_approved_contains_only_approved_rows_with_their_text(client):
    near = _parallel_by_type(client, "near")
    client.patch(f"/api/parallels/{near['id']}", json={"status": "approved", "note": "a, \"quoted\" note"})

    rows = _read_csv(client.get("/api/export.csv", params={"status": "approved"}))
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == str(near["id"]) and row["status"] == "approved"
    assert row["note"] == 'a, "quoted" note'
    assert "jumps" in row["text_a"] and "leaps" in row["text_b"]


def test_csv_export_starts_with_a_byte_order_mark_for_excel(client):
    res = client.get("/api/export.csv")
    assert res.content.startswith(b"\xef\xbb\xbf")
    assert len(_read_csv(res)) == 2
