"""Word-level diff inside a matched passage: which words differ between the
two sides, as character spans in each ORIGINAL document.

Compares the same normalized tokens the algorithm itself compares (lowercase,
punctuation stripped -- `app.algorithm.tokenize`), so a difference shown here
is exactly a difference the scorer saw: case or punctuation alone never shows
up as a change, consistent with such a passage being classified "exact".
"""

from __future__ import annotations

from difflib import SequenceMatcher

from app.algorithm import Token, tokenize

Span = tuple[int, int]  # [start, end) character offsets in the full document


def word_diff(content_a: str, a_start: int, a_end: int, content_b: str, b_start: int, b_end: int) -> tuple[list[Span], list[Span]]:
    """Return (changed spans in A, changed spans in B) for one parallel.

    A word substituted shows on both sides; a word only one side has shows
    on that side only. An exact match returns two empty lists.
    """
    tokens_a = _tokens_in(content_a, a_start, a_end)
    tokens_b = _tokens_in(content_b, b_start, b_end)
    # autojunk=False: difflib's "popular element" heuristic would otherwise
    # treat frequent words like "the" as junk in passages over 200 tokens and
    # produce a misleading diff. These passages are short; no speedup needed.
    matcher = SequenceMatcher(
        a=[t.normalized for t in tokens_a], b=[t.normalized for t in tokens_b], autojunk=False
    )

    spans_a: list[Span] = []
    spans_b: list[Span] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:  # "replace" or "delete": words in A not matched in B
            spans_a.append((tokens_a[i1].start, tokens_a[i2 - 1].end))
        if j2 > j1:  # "replace" or "insert": words in B not matched in A
            spans_b.append((tokens_b[j1].start, tokens_b[j2 - 1].end))
    return spans_a, spans_b


def _tokens_in(content: str, start: int, end: int) -> list[Token]:
    """Tokenize content[start:end], with offsets shifted back to the full document."""
    return [Token(t.normalized, t.start + start, t.end + start) for t in tokenize(content[start:end])]
