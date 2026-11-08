"""Load the committed corpus files as documents."""

from __future__ import annotations

from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"

# (slug, display title), in a fixed order so doc_a/doc_b pairing is stable.
DOCUMENTS = [
    ("matthew", "The Gospel According to Saint Matthew"),
    ("mark", "The Gospel According to Saint Mark"),
    ("luke", "The Gospel According to Saint Luke"),
    ("john", "The Gospel According to Saint John"),
]


def load_corpus() -> dict[str, str]:
    """Return {slug: full text} for every document in `corpus/`."""
    return {slug: (CORPUS_DIR / f"{slug}.txt").read_text(encoding="utf-8") for slug, _ in DOCUMENTS}
