"""Experiment: sweep algorithm parameters over the real corpus and inspect results.

Run with no arguments for the full report used to choose the defaults recorded
in DECISIONS.md ("Phase 2 — Algorithm"):

    python scripts/run_experiment.py

What it prints, per n in {3, 4, 5, 6}, for every document pair:
  - how many candidate passages come out of chaining, before any filtering
  - how many survive the minimum-length filter
  - how many survive de-duplication (the final count)
  - the exact/near split and the score distribution
  - 10 sample matches
and, once, a measurement of the "common formula" problem (step 2 of the three
flagged issues) and how much the document-frequency filter (step 1) helps,
using Matthew-John -- the least-overlapping pair -- as the sensitive case.
"""

from __future__ import annotations

import statistics
import sys
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.algorithm import (  # noqa: E402
    Params,
    build_ngram_index,
    chain_seeds,
    document_frequency,
    find_parallels,
    find_seeds,
    score_passage,
    select_non_redundant,
    to_char_span,
    tokenize,
)
from app.corpus import DOCUMENTS, load_corpus  # noqa: E402


def snippet(text: str, start: int, end: int, context: int = 0) -> str:
    s = " ".join(text[max(0, start - context) : min(len(text), end + context)].split())
    return s if len(s) <= 100 else s[:97] + "..."


def run_pair(slug_a, text_a, tokens_a, slug_b, text_b, tokens_b, params: Params, verbose: bool):
    index_a = build_ngram_index(tokens_a, params.ngram_size)
    index_b = build_ngram_index(tokens_b, params.ngram_size)
    seeds = find_seeds(index_a, index_b)
    chains = chain_seeds(seeds, params.ngram_size, params.gap_tolerance)

    long_enough = [
        c for c in chains
        if (c[1] - c[0]) >= params.min_passage_tokens and (c[3] - c[2]) >= params.min_passage_tokens
    ]
    scored = []
    for a_start, a_end, b_start, b_end in long_enough:
        score, match_type = score_passage(tokens_a[a_start:a_end], tokens_b[b_start:b_end])
        scored.append(((a_start, a_end, b_start, b_end), score, match_type))
    kept = select_non_redundant(scored)

    if verbose:
        exact = sum(1 for _, _, t in kept if t == "exact")
        scores = [s for _, s, _ in kept]
        print(
            f"  {slug_a:8} x {slug_b:8}  chains={len(chains):5}  "
            f"min_len_ok={len(long_enough):5}  final={len(kept):4}  "
            f"exact={exact:4}  near={len(kept) - exact:4}  "
            f"score_mean={statistics.mean(scores):.2f}" if scores else
            f"  {slug_a:8} x {slug_b:8}  chains={len(chains):5}  min_len_ok={len(long_enough):5}  final=0"
        )
    return kept


def print_samples(slug_a, text_a, tokens_a, slug_b, text_b, tokens_b, kept, n=10):
    ranked = sorted(kept, key=lambda c: c[1], reverse=True)
    print(f"\n  -- sample matches, {slug_a} x {slug_b} (highest score first, up to {n}) --")
    for (a_start, a_end, b_start, b_end), score, match_type in ranked[:n]:
        ca_start, ca_end = to_char_span(tokens_a, a_start, a_end)
        cb_start, cb_end = to_char_span(tokens_b, b_start, b_end)
        print(f"    [{match_type:5} {score:.2f}] {slug_a}: {snippet(text_a, ca_start, ca_end)!r}")
        print(f"                     {slug_b}: {snippet(text_b, cb_start, cb_end)!r}")


def sweep_ngram_size():
    corpus = load_corpus()
    tokens = {slug: tokenize(text) for slug, text in corpus.items()}
    slugs = [slug for slug, _ in DOCUMENTS]

    for n in (3, 4, 5, 6):
        print(f"\n{'=' * 90}\nn-gram size = {n}  (gap_tolerance=4, min_passage_tokens=8, no document-frequency filter)\n{'=' * 90}")
        params = Params(ngram_size=n, gap_tolerance=4, min_passage_tokens=8, max_ngram_document_frequency=10**9)
        all_kept = {}
        for slug_a, slug_b in combinations(slugs, 2):
            kept = run_pair(slug_a, corpus[slug_a], tokens[slug_a], slug_b, corpus[slug_b], tokens[slug_b], params, verbose=True)
            all_kept[(slug_a, slug_b)] = kept

        # Samples only for the default n, to keep output readable.
        if n == 3:
            for (slug_a, slug_b), kept in all_kept.items():
                print_samples(slug_a, corpus[slug_a], tokens[slug_a], slug_b, corpus[slug_b], tokens[slug_b], kept)


def measure_formula_flood_and_filter():
    """At the chosen n=3: does the document-frequency filter help or hurt?"""
    print(f"\n{'=' * 90}\nDocument-frequency filter at n=3: Matthew x John\n{'=' * 90}")
    corpus = load_corpus()
    tokens_a, tokens_b = tokenize(corpus["matthew"]), tokenize(corpus["john"])
    all_tokens = {slug: tokenize(text) for slug, text in corpus.items()}
    n = 3

    index_a = build_ngram_index(tokens_a, n)
    index_b = build_ngram_index(tokens_b, n)
    all_indexes = [build_ngram_index(all_tokens[slug], n) for slug, _ in DOCUMENTS]
    freq = document_frequency(all_indexes)

    for label, corpus_freq, cutoff in [("no filter", None, 0), ("max_document_frequency=3", freq, 3)]:
        seeds = find_seeds(index_a, index_b, corpus_freq, cutoff)
        chains = chain_seeds(seeds, n, gap_tolerance=4)
        long_enough = [c for c in chains if (c[1] - c[0]) >= 8 and (c[3] - c[2]) >= 8]
        scored = [
            ((a, ae, b, be), *score_passage(tokens_a[a:ae], tokens_b[b:be]))
            for a, ae, b, be in long_enough
        ]
        kept = select_non_redundant(scored)
        print(f"  {label:28}  seeds={len(seeds):6}  chains={len(chains):4}  final={len(kept):4}")

    print("\n  Most corpus-wide-frequent 3-grams (every document frequency value possible here is 1-4):")
    for ngram, count in sorted(freq.items(), key=lambda kv: -kv[1])[:10]:
        print(f"    {count}x  {' '.join(ngram)!r}")


def sweep_gap_tolerance_and_min_length():
    """At the chosen n=3: how far can gap_tolerance and min_passage_tokens move
    before the output stops looking clean? Prints the single worst-scoring
    (lowest-score) kept match at each setting, since that is where a bad
    parameter choice shows up first.
    """
    corpus = load_corpus()
    tokens = {slug: tokenize(text) for slug, text in corpus.items()}
    pairs = list(combinations([slug for slug, _ in DOCUMENTS], 2))

    def run(n, gap, min_len):
        total_final, total_near, lowest, worst = 0, 0, 2.0, None
        for a, b in pairs:
            ta, tb = tokens[a], tokens[b]
            ia, ib = build_ngram_index(ta, n), build_ngram_index(tb, n)
            seeds = find_seeds(ia, ib)
            chains = chain_seeds(seeds, n, gap)
            long_enough = [c for c in chains if (c[1] - c[0]) >= min_len and (c[3] - c[2]) >= min_len]
            scored = [((s, e, s2, e2), *score_passage(ta[s:e], tb[s2:e2])) for s, e, s2, e2 in long_enough]
            kept = select_non_redundant(scored)
            total_final += len(kept)
            total_near += sum(1 for _, _, t in kept if t == "near")
            for rng, score, mtype in kept:
                if score <= lowest:
                    lowest, worst = score, (a, b, rng, score, mtype)
        return total_final, total_near, lowest, worst

    print(f"\n{'=' * 90}\ngap_tolerance sweep (n=3, min_passage_tokens=8) -- worst kept match at each setting\n{'=' * 90}")
    for gap in (2, 4, 8, 16):
        final, near, lowest, (a, b, (s, e, s2, e2), score, mtype) = run(3, gap, 8)
        ca, cb = to_char_span(tokens[a], s, e), to_char_span(tokens[b], s2, e2)
        print(f"  gap={gap:3}  final={final:4}  near={near:3}  lowest_score={lowest:.2f}  ({a}-{b}, {mtype})")
        print(f"    {a}: {corpus[a][ca[0]:ca[1]]!r}")
        print(f"    {b}: {corpus[b][cb[0]:cb[1]]!r}")

    print(f"\n{'=' * 90}\nmin_passage_tokens sweep (n=3, gap_tolerance=4)\n{'=' * 90}")
    for min_len in (5, 6, 8, 10, 12):
        final, near, lowest, _ = run(3, 4, min_len)
        print(f"  min_len={min_len:3}  final={final:4}  near={near:3}  lowest_score={lowest:.2f}")


if __name__ == "__main__":
    sweep_ngram_size()
    measure_formula_flood_and_filter()
    sweep_gap_tolerance_and_min_length()
