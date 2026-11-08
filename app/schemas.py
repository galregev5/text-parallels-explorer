"""Pydantic request/response models for the API. Kept separate from the DB
layer so a row's storage shape (SQLite columns) and its wire shape (nested
JSON) can differ without tangling the two together.
"""

from __future__ import annotations

import sqlite3
import textwrap
from typing import Literal

from pydantic import BaseModel

SNIPPET_LENGTH = 160


def snippet(text: str, length: int = SNIPPET_LENGTH) -> str:
    """Collapse whitespace (the corpus has embedded newlines) and shorten."""
    return textwrap.shorten(" ".join(text.split()), width=length, placeholder="...")


class DocumentOut(BaseModel):
    id: int
    slug: str
    title: str


class DocumentDetailOut(DocumentOut):
    content: str


class ParallelListItemOut(BaseModel):
    id: int
    doc_a: DocumentOut
    doc_b: DocumentOut
    a_start: int
    a_end: int
    b_start: int
    b_end: int
    score: float
    match_type: str
    status: str
    note: str | None
    snippet_a: str
    snippet_b: str
    is_stale: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row, latest_run_id: int) -> ParallelListItemOut:
        return cls(
            id=row["id"],
            doc_a=DocumentOut(id=row["doc_a_id"], slug=row["doc_a_slug"], title=row["doc_a_title"]),
            doc_b=DocumentOut(id=row["doc_b_id"], slug=row["doc_b_slug"], title=row["doc_b_title"]),
            a_start=row["a_start"],
            a_end=row["a_end"],
            b_start=row["b_start"],
            b_end=row["b_end"],
            score=row["score"],
            match_type=row["match_type"],
            status=row["status"],
            note=row["note"],
            snippet_a=snippet(row["text_a"]),
            snippet_b=snippet(row["text_b"]),
            is_stale=row["last_seen_run_id"] != latest_run_id,
        )


class ParallelListOut(BaseModel):
    items: list[ParallelListItemOut]
    total: int
    stale_count: int


class ParallelDetailOut(BaseModel):
    id: int
    doc_a: DocumentDetailOut
    doc_b: DocumentDetailOut
    a_start: int
    a_end: int
    b_start: int
    b_end: int
    score: float
    match_type: str
    status: str
    note: str | None
    is_stale: bool
    prev_id: int | None
    next_id: int | None


class ParallelUpdateIn(BaseModel):
    # Validated here (a 422 with a clear message) rather than left to the
    # schema's CHECK constraint to reject as an opaque 500.
    status: Literal["pending", "approved", "rejected"] | None = None
    note: str | None = None


class RerunOut(BaseModel):
    run_id: int
    ran: bool
    total_parallels: int
    stale_count: int
