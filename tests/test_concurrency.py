"""Concurrent requests through the REAL per-request connection dependency.

The other API tests override `get_conn` with one shared in-memory connection,
and TestClient serializes requests, so neither can reproduce this: FastAPI
runs a sync generator dependency in one thread-pool thread and the route
handler in another, so under concurrent requests a connection opened by
`get_conn` is used from a different thread than the one that opened it.
Found in Phase 6, when the list page started loading the list and the
matrix in parallel (DECISIONS.md 6.5). Hence a real uvicorn server here.
"""

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
import uvicorn

import app.api
from app.db import connect
from app.main import app as fastapi_app
from app.pipeline import run_pipeline
from tests.test_api import TOY_DOCS, TOY_PARAMS


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def base_url(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    conn = connect(db_path)
    run_pipeline(conn, TOY_DOCS, TOY_PARAMS, force=True)
    conn.close()
    monkeypatch.setattr(app.api, "DB_PATH", str(db_path))

    port = _free_port()
    # lifespan="off": the startup pipeline would analyze the real corpus into
    # the real DB_PATH; this test brings its own small database instead.
    server = uvicorn.Server(uvicorn.Config(fastapi_app, port=port, lifespan="off", log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_concurrent_requests_through_the_real_connection_dependency_all_succeed(base_url):
    paths = ["/api/parallels", "/api/matrix", "/api/documents", "/api/export.csv"] * 25
    with httpx.Client(base_url=base_url) as http, ThreadPoolExecutor(max_workers=16) as pool:
        statuses = list(pool.map(lambda path: http.get(path).status_code, paths))
    assert statuses.count(200) == len(paths), f"non-200 responses: {[s for s in statuses if s != 200]}"
