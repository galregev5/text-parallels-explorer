# Corpus sources

## What is here

The four canonical Gospels in the King James Version (KJV), one file per book:

| File | Book | Chapters | Verses | Characters |
|------|------|---------:|-------:|-----------:|
| `matthew.txt` | The Gospel According to Saint Matthew | 28 | 1071 | 130,319 |
| `mark.txt`    | The Gospel According to Saint Mark    | 16 |  678 |  82,670 |
| `luke.txt`    | The Gospel According to Saint Luke    | 24 | 1151 | 140,891 |
| `john.txt`    | The Gospel According to Saint John    | 21 |  879 | 102,680 |

## Source

- **Work:** *The King James Version of the Bible*
- **Source:** Project Gutenberg eBook **#10** — <https://www.gutenberg.org/ebooks/10>
- **Plain-text file used:** <https://www.gutenberg.org/cache/epub/10/pg10.txt>
- **Release date:** 1 August 1989 · **most recently updated:** 29 October 2024
- **Retrieved:** 8 November 2026
- **SHA-256 of the retrieved source file:** `0204adaed1f25700aa854218cae63c7172228c41088f335e99167a071eed83c0`

The Gospels were extracted from that single file by `scripts/extract_corpus.py`,
which is committed so the corpus is reproducible. The script runs at development
time only — the application never downloads anything.

## Copyright status

The KJV text (1611, 1769 revision) long predates any applicable copyright term and
is in the **public domain in the United States**. Project Gutenberg distributes it
on that basis.

Two honest caveats, stated because the claim deserves precision:

1. Project Gutenberg's own licence applies to its *header, footer and trademark*,
   not to the underlying public-domain text. Those wrappers have been removed from
   these files (see `strip_gutenberg_wrapper` in the extraction script), and the
   "Project Gutenberg" trademark is not used in them. Under PG's terms that makes
   these files plain public-domain text, freely redistributable.
2. In the **United Kingdom** the KJV is covered by a perpetual Crown copyright
   administered through letters patent (Cambridge University Press). This does not
   affect use in the US, and does not affect this project's use of the text, but it
   is why "public domain" is qualified by jurisdiction rather than stated flatly.

## Why these four texts

The assignment asks for 3–5 public-domain texts that **share passages**. The Gospels
are close to an ideal test corpus for a parallel detector:

- **Matthew, Mark and Luke** (the "synoptic" Gospels) share a large amount of
  material, some word-for-word identical and some reworded — exactly the mix of
  *exact* and *near* matches the algorithm has to tell apart. Their overlap is the
  most studied text-reuse problem in the humanities, so results can be sanity-checked
  against well-known passages.
- **John** overlaps the other three far less, so it acts as a **control**: a detector
  that reports as many parallels for John as for the synoptics is miscalibrated.
  (Concretely: the phrase "Verily, verily" occurs 25 times in John and never in the
  other three.)
- All four are a convenient size: ~80–140 KB each, large enough for performance to be
  a real consideration, small enough to analyse in seconds.

## Normalisation applied

The source wraps lines at ~72 characters, runs several verses together inside a
paragraph, and inserts blank lines at irregular intervals. Each file here is
renormalised to **one verse per line**, in the form `chapter:verse text`, with
whitespace inside a verse collapsed to single spaces.

All character offsets produced by this project refer to **these committed files**,
not to the original Project Gutenberg file. See `DECISIONS.md`
("Corpus normalisation") for the alternatives considered and the reasoning.

## Checksums of the extracted files

| File | SHA-256 |
|------|---------|
| `corpus/matthew.txt` | `1d1083028f0b536e74bfadcbe8b8fefae6daa82ea7a2a540c0521455736af9de` |
| `corpus/mark.txt` | `b5e916096c5ea19df4fa9f7542d6a258e02afde231ad5abdff131d00358c622d` |
| `corpus/luke.txt` | `b48d53f6a555e8b9c2bd2622a4e59e26cc50ebd9344cdeeb80cbced479930d83` |
| `corpus/john.txt` | `d2529bc1ddb09f1ea6aeba8c6036b6974ccf8a89895673c2845e4e185dffae7f` |
