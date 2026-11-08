"""Unit tests for app/algorithm.py, built on small, hand-checkable examples."""

from app.algorithm import (
    Params,
    chain_seeds,
    document_frequency,
    find_parallels,
    find_seeds,
    select_non_redundant,
    to_char_span,
    tokenize,
)


# --- tokenize --------------------------------------------------------------


def test_tokenize_offsets_round_trip_to_the_original_text():
    text = "1:1 The book of Abraham's generation."
    tokens = tokenize(text)
    # every token's span, read back from the ORIGINAL text, is the raw word
    raw_words = [text[t.start : t.end] for t in tokens]
    assert raw_words == ["The", "book", "of", "Abraham's", "generation"]


def test_tokenize_normalizes_case_and_apostrophe():
    tokens = tokenize("Abraham's")
    assert len(tokens) == 1
    assert tokens[0].normalized == "abrahams"


def test_tokenize_handles_curly_apostrophe_like_the_real_corpus():
    # The corpus uses U+2019, never ASCII '. See DECISIONS.md 1.5.
    tokens = tokenize("camel’s hair")
    assert [t.normalized for t in tokens] == ["camels", "hair"]


def test_tokenize_skips_verse_markers_entirely():
    # "1:1" must not produce a "1" token on either side of the colon: it is
    # not a word, and if it tokenized, "1" could spuriously seed-match "1"
    # from an unrelated verse marker elsewhere in the corpus.
    tokens = tokenize("1:1 The book of the generation. 2:3 More text.")
    assert tokens[0].normalized == "the"
    assert all(t.normalized not in ("1", "2", "3") for t in tokens)


# --- seed finding and chaining ----------------------------------------------


def test_find_seeds_returns_every_shared_ngram_position():
    tokens_a = tokenize("the quick brown fox jumps")
    tokens_b = tokenize("a quick brown fox ran")
    from app.algorithm import build_ngram_index

    index_a = build_ngram_index(tokens_a, n=3)
    index_b = build_ngram_index(tokens_b, n=3)
    seeds = find_seeds(index_a, index_b)
    # "quick brown fox" is the only shared 3-gram, at position 1 in both.
    assert seeds == [(1, 1)]


def test_find_seeds_drops_ngrams_above_the_document_frequency_cutoff():
    from app.algorithm import build_ngram_index

    tokens_a = tokenize("and it came to pass that he went")
    tokens_b = tokenize("and it came to pass that she stayed")
    index_a = build_ngram_index(tokens_a, n=3)
    index_b = build_ngram_index(tokens_b, n=3)

    # Pretend "and it came" occurs in many documents corpus-wide.
    common_ngram = ("and", "it", "came")
    freq = document_frequency([index_a, index_b])
    freq[common_ngram] = 50

    seeds_unfiltered = find_seeds(index_a, index_b, freq, max_document_frequency=100)
    seeds_filtered = find_seeds(index_a, index_b, freq, max_document_frequency=3)
    assert common_ngram in {tuple(w.normalized for w in [tokens_a[i], tokens_a[i + 1], tokens_a[i + 2]]) for i, _ in seeds_unfiltered}
    assert len(seeds_filtered) < len(seeds_unfiltered)


def test_chain_seeds_bridges_a_small_gap_on_the_same_diagonal():
    # Seeds at token positions 0 and 5, same diagonal (0), gap of 5.
    seeds = [(0, 0), (5, 5)]
    chains = chain_seeds(seeds, ngram_size=3, gap_tolerance=5)
    assert chains == [(0, 8, 0, 8)]  # merged into one chain


def test_chain_seeds_splits_on_too_large_a_gap():
    seeds = [(0, 0), (10, 10)]
    chains = chain_seeds(seeds, ngram_size=3, gap_tolerance=4)
    assert sorted(chains) == [(0, 3, 0, 3), (10, 13, 10, 13)]


def test_chain_seeds_separates_different_diagonals():
    # (0,0) and (1,2) are on different diagonals (0 vs 1): one text has an
    # extra word inserted relative to the other, so they must not merge.
    seeds = [(0, 0), (1, 2)]
    chains = chain_seeds(seeds, ngram_size=2, gap_tolerance=4)
    assert sorted(chains) == [(0, 2, 0, 2), (1, 3, 2, 4)]


# --- end-to-end on the toy example from the assignment ----------------------


TOY_PARAMS = Params(ngram_size=3, gap_tolerance=4, min_passage_tokens=4, max_ngram_document_frequency=100)


def test_identical_sentences_are_an_exact_match():
    text = "The quick brown fox jumps over the lazy dog today."
    tokens = tokenize(text)
    parallels = find_parallels(tokens, tokens, TOY_PARAMS)
    assert len(parallels) == 1
    assert parallels[0].score == 1.0
    assert parallels[0].match_type == "exact"


def test_one_substituted_word_is_a_near_match_not_exact():
    # The toy example the assignment asks for: two sentences differing by
    # exactly one substituted word ("jumps" -> "leaps").
    text_a = "The quick brown fox jumps over the lazy dog today."
    text_b = "The quick brown fox leaps over the lazy dog today."
    tokens_a, tokens_b = tokenize(text_a), tokenize(text_b)

    parallels = find_parallels(tokens_a, tokens_b, TOY_PARAMS)

    assert len(parallels) == 1
    parallel = parallels[0]
    assert parallel.match_type == "near"
    assert 0.0 < parallel.score < 1.0
    # the gap tolerance must bridge over the one substituted word, so the
    # matched span covers the whole sentence on both sides, not just the
    # parts before or after the substitution.
    assert (parallel.a_token_end - parallel.a_token_start) == len(tokens_a)
    assert (parallel.b_token_end - parallel.b_token_start) == len(tokens_b)

    # the char span, read back from the original text, is the full sentence
    # (minus the trailing period, which is not a word token).
    char_start, char_end = to_char_span(tokens_a, parallel.a_token_start, parallel.a_token_end)
    assert text_a[char_start:char_end] == text_a.rstrip(".")


def test_unrelated_sentences_produce_no_parallel():
    tokens_a = tokenize("The quick brown fox jumps over the lazy dog today.")
    tokens_b = tokenize("Distant galaxies spin slowly through the endless void.")
    assert find_parallels(tokens_a, tokens_b, TOY_PARAMS) == []


def test_min_passage_length_filters_out_short_matches():
    # Only "brown fox" (2 words) is shared -- below any reasonable minimum.
    tokens_a = tokenize("A brown fox ran away quickly today.")
    tokens_b = tokenize("Some brown fox stayed home instead.")
    strict_params = Params(ngram_size=2, gap_tolerance=4, min_passage_tokens=4, max_ngram_document_frequency=100)
    assert find_parallels(tokens_a, tokens_b, strict_params) == []


# --- de-duplication / one-to-many ------------------------------------------


def test_select_non_redundant_drops_a_candidate_overlapping_on_both_sides():
    # Two near-identical chains for the same underlying region (one token
    # shorter on each side) -- a seed-chaining artifact, not two real matches.
    candidates = [
        ((0, 10, 0, 10), 0.95, "near"),
        ((1, 9, 1, 9), 0.90, "near"),  # nested inside the first on BOTH sides
    ]
    kept = select_non_redundant(candidates)
    assert kept == [((0, 10, 0, 10), 0.95, "near")]


def test_select_non_redundant_keeps_legitimate_one_to_many_matches():
    # One passage in document B genuinely parallels two different passages
    # in document A (the same material quoted twice, as in the Gospels).
    # The A-ranges are disjoint; the B-range is the same for both.
    candidates = [
        ((0, 10, 100, 110), 0.95, "near"),  # A[0:10]  <-> B[100:110]
        ((50, 60, 100, 110), 0.90, "near"),  # A[50:60] <-> B[100:110] (same B span)
    ]
    kept = select_non_redundant(candidates)
    assert len(kept) == 2
