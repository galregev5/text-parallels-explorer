"""Find exact and near-match textual parallels between two documents.

The approach is classic seed-and-extend, the same family of algorithm used by
plagiarism detectors and bioinformatics sequence aligners (a simplified,
un-gapped cousin of BLAST):

1. Tokenize each document into words, keeping each word's (start, end)
   character offsets in the ORIGINAL text.
2. Normalize tokens (lowercase, strip punctuation) for comparison.
3. Index each document's word n-grams ("seeds").
4. For a pair of documents, a seed shared by both is a point of alignment.
   Seeds that sit close together on the same "diagonal" (the token-offset
   difference between the two documents) are chained into a candidate passage.
5. Candidates are filtered by minimum length, de-duplicated, and scored.

See DECISIONS.md ("Phase 2 — Algorithm") for why this approach and these
parameters, including the n in {3,4,5,6} experiment that picked the default.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

# A run of Unicode letters, with an optional internal apostrophe-joined run
# (so "camel's" / "camel’s" tokenizes as one word: "camel" + "'s").
# Deliberately letter-only, not \w: \w also matches digits, so this excludes
# the "12:3"-style verse markers embedded in the corpus text (see corpus/
# SOURCES.md and DECISIONS.md 1.5) without a separate marker-skipping rule.
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’][^\W\d_]+)*")

# Characters stripped when normalizing a token for comparison.
_APOSTROPHES = "'’"


@dataclass(frozen=True)
class Token:
    """A single word, with its position in the original text."""

    normalized: str  # lowercase, punctuation-stripped
    start: int  # char offset in the original text, inclusive
    end: int  # char offset in the original text, exclusive


@dataclass(frozen=True)
class Parallel:
    """One matched passage between two documents, in token-index terms."""

    a_token_start: int
    a_token_end: int  # exclusive
    b_token_start: int
    b_token_end: int  # exclusive
    score: float  # 0.0-1.0 token-level similarity
    match_type: str  # "exact" or "near"


@dataclass(frozen=True)
class Params:
    """Parameters governing the algorithm. See DECISIONS.md for the chosen values."""

    ngram_size: int = 3
    gap_tolerance: int = 4  # max token gap when chaining seeds on a diagonal
    min_passage_tokens: int = 8
    max_ngram_document_frequency: int = 3  # drop seeds this common or commoner (opt-in: only
    # applied when a `document_freq` map is actually passed in; off by default -- see DECISIONS.md


def tokenize(text: str) -> list[Token]:
    """Split text into normalized words with their original character spans."""
    tokens = []
    for match in _WORD_RE.finditer(text):
        raw = match.group()
        normalized = raw.translate({ord(c): None for c in _APOSTROPHES}).lower()
        tokens.append(Token(normalized, match.start(), match.end()))
    return tokens


def build_ngram_index(tokens: list[Token], n: int) -> dict[tuple[str, ...], list[int]]:
    """Map each word n-gram to the token indices where it starts.

    An n-gram is the tuple of n consecutive tokens' normalized forms. The
    index lets `find_seeds` look up, for any n-gram, every position it starts
    at in this document.
    """
    index: dict[tuple[str, ...], list[int]] = {}
    for i in range(len(tokens) - n + 1):
        ngram = tuple(t.normalized for t in tokens[i : i + n])
        index.setdefault(ngram, []).append(i)
    return index


def document_frequency(indexes: list[dict[tuple[str, ...], list[int]]]) -> dict[tuple[str, ...], int]:
    """Count, across a corpus, how many documents each n-gram appears in at all.

    Used to drop common formulaic phrases ("and it came to pass") from seeding
    before they flood the results with matches that are not meaningful
    parallels. See DECISIONS.md ("Formula filtering").
    """
    frequency: dict[tuple[str, ...], int] = {}
    for index in indexes:
        for ngram in index:
            frequency[ngram] = frequency.get(ngram, 0) + 1
    return frequency


def find_seeds(
    index_a: dict[tuple[str, ...], list[int]],
    index_b: dict[tuple[str, ...], list[int]],
    corpus_frequency: dict[tuple[str, ...], int] | None = None,
    max_document_frequency: int = 3,
) -> list[tuple[int, int]]:
    """Return (token_index_in_a, token_index_in_b) pairs for every shared n-gram.

    Each pair is a "seed": a point where the two documents are known to align.
    N-grams that occur in more than `max_document_frequency` documents in the
    corpus (per `corpus_frequency`, see `document_frequency`) are skipped as
    too common to indicate a real parallel.

    Iterates `index_a` directly rather than `set(index_a) & set(index_b)`: Python
    randomizes string hashing per process, so a set's iteration order is not
    reproducible across runs, while a dict's is (insertion order). Re-running the
    pipeline must produce the same seed order -- and so the same tie-breaking in
    `select_non_redundant` -- every time; see DECISIONS.md ("Deterministic seed
    and selection order").
    """
    seeds = []
    for ngram in index_a:
        if ngram not in index_b:
            continue
        if corpus_frequency is not None and corpus_frequency.get(ngram, 0) > max_document_frequency:
            continue
        for i in index_a[ngram]:
            for j in index_b[ngram]:
                seeds.append((i, j))
    return seeds


def chain_seeds(seeds: list[tuple[int, int]], ngram_size: int, gap_tolerance: int) -> list[tuple[int, int, int, int]]:
    """Chain nearby seeds on the same diagonal into candidate passages.

    Two seeds lie on the same "diagonal" if token_index_in_b - token_index_in_a
    is equal for both: that means the aligned material has not shifted between
    the two documents, i.e. no words were inserted or deleted between the
    seeds (small substitutions within a seed's own n-gram are allowed, since a
    "near" n-gram still will not match exactly and so will not seed at all --
    chaining only joins exact n-gram matches that happen to be nearby).

    Seeds on one diagonal, sorted by position, are grouped into a chain as
    long as consecutive seeds are no more than `gap_tolerance` tokens apart;
    a bigger gap starts a new chain. Each chain becomes one candidate passage
    spanning from its first seed's start to its last seed's end.

    Returns (a_token_start, a_token_end, b_token_start, b_token_end) tuples,
    with ends exclusive.
    """
    seeds_by_diagonal: dict[int, list[tuple[int, int]]] = {}
    for i, j in seeds:
        seeds_by_diagonal.setdefault(j - i, []).append((i, j))

    candidates = []
    for diagonal_seeds in seeds_by_diagonal.values():
        diagonal_seeds.sort()
        chain_start = diagonal_seeds[0]
        chain_end = diagonal_seeds[0]
        for seed in diagonal_seeds[1:]:
            if seed[0] - chain_end[0] <= gap_tolerance:
                chain_end = seed
            else:
                candidates.append(_candidate_from_chain(chain_start, chain_end, ngram_size))
                chain_start = chain_end = seed
        candidates.append(_candidate_from_chain(chain_start, chain_end, ngram_size))
    return candidates


def _candidate_from_chain(
    first_seed: tuple[int, int], last_seed: tuple[int, int], ngram_size: int
) -> tuple[int, int, int, int]:
    a_start, b_start = first_seed
    a_end, b_end = last_seed[0] + ngram_size, last_seed[1] + ngram_size
    return a_start, a_end, b_start, b_end


def score_passage(tokens_a: list[Token], tokens_b: list[Token]) -> tuple[float, str]:
    """Score a candidate passage's similarity and classify it exact or near.

    The score is a token-level similarity ratio (0-1): the normalized token
    sequences are joined into single strings and compared with rapidfuzz's
    Levenshtein-based ratio, so insertions/deletions/substitutions of whole
    words are penalized once each rather than character-by-character.
    "exact" means the normalized token sequences are identical (case and
    punctuation ignored, but no word added, removed, or substituted);
    anything else that passes the caller's threshold is "near".
    """
    normalized_a = [t.normalized for t in tokens_a]
    normalized_b = [t.normalized for t in tokens_b]
    if normalized_a == normalized_b:
        return 1.0, "exact"
    ratio = fuzz.ratio(" ".join(normalized_a), " ".join(normalized_b)) / 100.0
    return ratio, "near"


def select_non_redundant(
    candidates: list[tuple[tuple[int, int, int, int], float, str]],
) -> list[tuple[tuple[int, int, int, int], float, str]]:
    """Drop candidates that are redundant restatements of an already-kept one.

    Seed chaining can produce several overlapping chains for the same
    underlying shared passage (e.g. one chain starting one token later than
    another, covering almost the same span). Processing candidates
    best-first (by score * length), a later candidate is dropped only if it
    overlaps an already-kept candidate on BOTH sides -- i.e. it describes
    materially the same region of both documents.

    Overlapping on only one side is kept: that is a legitimate one-to-many
    match, such as one Gospel passage that parallels two different passages
    in another Gospel (the same material quoted twice). See DECISIONS.md
    ("Selecting non-redundant passages").
    """
    # Primary key is score * length, descending; the candidate's own range is a
    # secondary key purely to break ties deterministically (so a tie's winner
    # does not depend on the input order, which upstream seed-finding does not
    # guarantee -- see `find_seeds`). Negating both achieves "descending" on a
    # single ascending sort without `reverse=True` flipping the tiebreaker too.
    ranked = sorted(candidates, key=lambda c: (-(c[1] * (c[0][1] - c[0][0])), c[0]))
    kept: list[tuple[tuple[int, int, int, int], float, str]] = []
    for candidate in ranked:
        (a_start, a_end, b_start, b_end), _, _ = candidate
        is_redundant = any(
            _ranges_overlap(a_start, a_end, kept_range[0], kept_range[1])
            and _ranges_overlap(b_start, b_end, kept_range[2], kept_range[3])
            for kept_range, _, _ in kept
        )
        if not is_redundant:
            kept.append(candidate)
    return kept


def _ranges_overlap(start_1: int, end_1: int, start_2: int, end_2: int) -> bool:
    return start_1 < end_2 and start_2 < end_1


def find_parallels(
    tokens_a: list[Token],
    tokens_b: list[Token],
    params: Params,
    index_a: dict[tuple[str, ...], list[int]] | None = None,
    index_b: dict[tuple[str, ...], list[int]] | None = None,
    document_freq: dict[tuple[str, ...], int] | None = None,
) -> list[Parallel]:
    """Run the full pipeline for one document pair and return its parallels.

    `index_a`/`index_b` may be precomputed and reused across pairs (as the
    corpus pipeline does); if omitted they are built here.
    """
    index_a = index_a if index_a is not None else build_ngram_index(tokens_a, params.ngram_size)
    index_b = index_b if index_b is not None else build_ngram_index(tokens_b, params.ngram_size)

    seeds = find_seeds(index_a, index_b, document_freq, params.max_ngram_document_frequency)
    chains = chain_seeds(seeds, params.ngram_size, params.gap_tolerance)

    scored = []
    for a_start, a_end, b_start, b_end in chains:
        if (a_end - a_start) < params.min_passage_tokens or (b_end - b_start) < params.min_passage_tokens:
            continue
        score, match_type = score_passage(tokens_a[a_start:a_end], tokens_b[b_start:b_end])
        scored.append(((a_start, a_end, b_start, b_end), score, match_type))

    kept = select_non_redundant(scored)
    return [
        Parallel(a_start, a_end, b_start, b_end, score, match_type)
        for (a_start, a_end, b_start, b_end), score, match_type in kept
    ]


def to_char_span(tokens: list[Token], token_start: int, token_end: int) -> tuple[int, int]:
    """Convert a [token_start, token_end) range to [char_start, char_end) in the original text."""
    return tokens[token_start].start, tokens[token_end - 1].end
