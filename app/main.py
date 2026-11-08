"""FastAPI application: run the pipeline once at startup, serve the API
under /api, and serve the static UI for everything else.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.config import DB_PATH
from app.corpus import DOCUMENTS, load_corpus
from app.db import connect
from app.pipeline import run_pipeline

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = connect(DB_PATH)
    try:
        corpus = load_corpus()
        documents = [(slug, title, corpus[slug]) for slug, title in DOCUMENTS]
        # force=False: skip the analysis (no new run, no re-chaining) when
        # the corpus and parameters are exactly what the last run already
        # covered -- the common case on every ordinary restart. See
        # DECISIONS.md ("Phase 4 -- skip-if-unchanged...").
        result = run_pipeline(conn, documents)
        verb = "ran" if result["ran"] else "skipped (nothing changed)"
        print(f"[startup] analysis {verb}: run_id={result['run_id']} total_parallels={result['total_parallels']}")
    finally:
        conn.close()
    yield


app = FastAPI(title="Text Parallels Explorer", lifespan=lifespan)
app.include_router(api_router, prefix="/api")

# Mounted last and at "/": FastAPI matches routes in order, so /api/* above
# is tried first and this only ever serves what /api/* did not claim.
# html=True serves index.html at "/" and lets e.g. /detail.html resolve
# without the extension.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
