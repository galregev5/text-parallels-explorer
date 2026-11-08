"""Word-level diff: which words differ inside a matched passage."""

from app.diff import word_diff


def _texts(content, spans):
    return [content[start:end] for start, end in spans]


def test_a_substituted_word_is_marked_on_both_sides():
    a = "The quick brown fox jumps over the lazy dog."
    b = "The quick brown fox leaps over the lazy dog."
    spans_a, spans_b = word_diff(a, 0, len(a), b, 0, len(b))
    assert _texts(a, spans_a) == ["jumps"]
    assert _texts(b, spans_b) == ["leaps"]


def test_an_inserted_word_is_marked_only_on_the_side_that_has_it():
    a = "and he went up into a mountain to pray"
    b = "and he went up into a high mountain to pray"
    spans_a, spans_b = word_diff(a, 0, len(a), b, 0, len(b))
    assert spans_a == []
    assert _texts(b, spans_b) == ["high"]


def test_an_exact_match_has_no_differences_even_with_different_case_and_punctuation():
    a = "Blessed is he that cometh, in the name of the Lord."
    b = "blessed is he that cometh in the name of the Lord;"
    assert word_diff(a, 0, len(a), b, 0, len(b)) == ([], [])


def test_spans_are_offsets_into_the_full_document_not_the_passage():
    prefix_a, prefix_b = "Unrelated opening text. ", "Something else first, longer. "
    passage_a, passage_b = "the lazy dog sleeps", "the lazy cat sleeps"
    a, b = prefix_a + passage_a, prefix_b + passage_b
    spans_a, spans_b = word_diff(a, len(prefix_a), len(a), b, len(prefix_b), len(b))
    assert _texts(a, spans_a) == ["dog"]
    assert _texts(b, spans_b) == ["cat"]


def test_a_multi_word_replacement_is_one_span_covering_the_words_between():
    a = "he said unto them, Go ye into the village"
    b = "he spake to them saying, Go ye into the village"
    spans_a, spans_b = word_diff(a, 0, len(a), b, 0, len(b))
    assert _texts(a, spans_a) == ["said unto"]
    assert _texts(b, spans_b) == ["spake to", "saying"]
