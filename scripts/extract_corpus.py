"""Extract the four Gospels from Project Gutenberg eBook #10 (KJV Bible).

Run once, at development time, to produce the committed files in `corpus/`.
The application itself never needs this script and never touches the network.

    python scripts/extract_corpus.py                 # download the source
    python scripts/extract_corpus.py path/to/pg10.txt  # use a local copy

Each gospel is written as one verse per line, in the form `chapter:verse text`.
See DECISIONS.md ("Corpus normalisation") for why.
"""

from __future__ import annotations

import re
import sys
import urllib.request
from pathlib import Path

SOURCE_URL = "https://www.gutenberg.org/cache/epub/10/pg10.txt"
CORPUS_DIR = Path(__file__).resolve().parent.parent / "corpus"

GUTENBERG_START = "*** START OF THE PROJECT GUTENBERG EBOOK"
GUTENBERG_END = "*** END OF THE PROJECT GUTENBERG EBOOK"

# (slug, heading that opens the book, heading that closes it, expected chapters)
GOSPELS = [
    ("matthew", "The Gospel According to Saint Matthew", "The Gospel According to Saint Mark", 28),
    ("mark", "The Gospel According to Saint Mark", "The Gospel According to Saint Luke", 16),
    ("luke", "The Gospel According to Saint Luke", "The Gospel According to Saint John", 24),
    ("john", "The Gospel According to Saint John", "The Acts of the Apostles", 21),
]

VERSE_MARKER = re.compile(r"(\d+):(\d+)\s+")


def load_source(argv: list[str]) -> str:
    """Return the raw eBook text, from a local path if given or else by download."""
    if argv:
        return Path(argv[0]).read_text(encoding="utf-8")
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL, timeout=120) as response:
        return response.read().decode("utf-8")


def strip_gutenberg_wrapper(raw: str) -> str:
    """Drop Project Gutenberg's header and licence footer."""
    start = raw.index("\n", raw.index(GUTENBERG_START)) + 1
    end = raw.index(GUTENBERG_END)
    return raw[start:end]


def extract_book(body: str, opening_heading: str, closing_heading: str) -> str:
    """Return the raw text of one book, located between two headings.

    Each heading appears twice in the eBook: once in the table of contents and
    once above the book itself. `rindex` picks the second, real occurrence.
    """
    start = body.rindex(opening_heading) + len(opening_heading)
    end = body.rindex(closing_heading)
    if end <= start:
        raise ValueError(f"{closing_heading!r} does not follow {opening_heading!r}")
    return body[start:end]


def split_into_verses(book_text: str) -> list[tuple[int, int, str]]:
    """Split a book into (chapter, verse, text) triples.

    The source wraps lines at ~72 characters and runs verses together inside
    paragraphs, so each verse's text is rejoined on single spaces.
    """
    markers = list(VERSE_MARKER.finditer(book_text))
    if not markers:
        raise ValueError("no verse markers found")

    verses = []
    for current, following in zip(markers, markers[1:] + [None]):
        stop = following.start() if following else len(book_text)
        text = " ".join(book_text[current.end():stop].split())
        verses.append((int(current.group(1)), int(current.group(2)), text))
    return verses


def check_verses_are_in_order(verses: list[tuple[int, int, str]], expected_chapters: int) -> None:
    """Fail loudly if the markers are not a clean, gapless chapter:verse sequence.

    This is what guards against the regex matching something that is not a verse
    marker, which would silently corrupt every character offset downstream.
    """
    previous_chapter, previous_verse = 1, 0
    for chapter, verse, text in verses:
        if chapter == previous_chapter:
            expected = (chapter, previous_verse + 1)  # next verse in this chapter
        else:
            expected = (previous_chapter + 1, 1)  # first verse of the next chapter
        if (chapter, verse) != expected:
            raise ValueError(f"expected verse {expected[0]}:{expected[1]}, found {chapter}:{verse}")
        if not text:
            raise ValueError(f"verse {chapter}:{verse} is empty")
        previous_chapter, previous_verse = chapter, verse

    if previous_chapter != expected_chapters:
        raise ValueError(f"expected {expected_chapters} chapters, found {previous_chapter}")


def render(verses: list[tuple[int, int, str]]) -> str:
    """Render verses as one `chapter:verse text` line each."""
    return "".join(f"{chapter}:{verse} {text}\n" for chapter, verse, text in verses)


def main() -> None:
    body = strip_gutenberg_wrapper(load_source(sys.argv[1:]))
    CORPUS_DIR.mkdir(exist_ok=True)

    for slug, opening, closing, expected_chapters in GOSPELS:
        verses = split_into_verses(extract_book(body, opening, closing))
        check_verses_are_in_order(verses, expected_chapters)
        text = render(verses)
        (CORPUS_DIR / f"{slug}.txt").write_text(text, encoding="utf-8", newline="\n")
        print(
            f"{slug:8} {verses[-1][0]:3} chapters  {len(verses):5} verses  "
            f"{len(text):7} chars  -> corpus/{slug}.txt"
        )


if __name__ == "__main__":
    main()
