# Decisions

A running log. Every choice that could reasonably have gone another way gets an
entry: **Decision**, **Alternatives considered**, **Why**. Newest phase last.

---

## Phase 1 — Corpus

### 1.1 Corpus: the four KJV Gospels from Project Gutenberg eBook #10

**Decision.** Use Matthew, Mark, Luke and John in the King James Version, extracted
from Project Gutenberg eBook #10 (*The King James Version of the Bible*), as four
documents: `corpus/matthew.txt`, `mark.txt`, `luke.txt`, `john.txt`.

**Alternatives considered.**
- *Multiple English translations of one Gospel* (e.g. KJV vs. Douay-Rheims Matthew).
  Near-total overlap.
- *Shakespeare quartos vs. folio*, or *Plutarch vs. Shakespeare's Roman plays*.
- *Multiple editions of one novel* (e.g. the 1818 and 1831 *Frankenstein*).
- *Wikipedia-style forked articles* — not reliably public domain, and not a fixed corpus.

**Why.** The assignment needs documents that share passages *and* a way to tell whether
the detector is right. The synoptic Gospels give three graded degrees of overlap in one
corpus: passages that are word-for-word identical, passages that are clearly the same
material reworded, and passages unique to one book. That range is what separates an
*exact* match from a *near* match, which is precisely what has to be demonstrated.
John supplies something the alternatives do not: a built-in **control**. It shares far
less with the other three, so if the pipeline reports comparable numbers of parallels
for the John pairs as for Matthew–Luke, the parameters are wrong. A corpus of near-
identical translations would have made every pair look the same and hidden that signal.
Overlap confirmed before committing: Matthew 8:20 and Luke 9:58 share "the Son of man
hath not where to lay his head" verbatim; Matthew 3:17, Mark 1:11 and Luke 3:22 carry
the baptism declaration in three slightly different wordings; "Verily, verily" occurs
25 times in John and never in the other three.
Size (~80–140 KB each) is large enough that performance matters and small enough to
analyse in seconds, which keeps `docker compose up` a single fast command.

### 1.2 Corpus normalisation: one verse per line, verse markers kept in the text

**Decision.** Store each Gospel as one verse per line in the form `chapter:verse text`,
with whitespace inside a verse collapsed to single spaces. The `1:1`-style markers stay
**in** the stored text. All character offsets this project produces refer to these
committed files.

**Alternatives considered.**
- *Keep the Gutenberg bytes verbatim.* Source is hard-wrapped at ~72 characters, runs
  several verses together inside one paragraph, and inserts blank lines at irregular
  intervals.
- *Strip the verse markers entirely* and store continuous prose.
- *Strip the markers from the text but keep a separate offset→verse mapping table.*

**Why.** Three things had to be true at once: the text must read well in a two-column
side-by-side view, offsets must be stable and explainable, and a researcher must be able
to cite what they are looking at.

Verbatim bytes fail the first: at 72 characters hard-wrapped, two columns side by side
either scroll horizontally or break mid-sentence at arbitrary points. Collapsing to one
verse per line lets the browser reflow the text to whatever column width is available.

Keeping the markers in the text is the cheap option that buys the most. A researcher
reviewing a parallel wants to know it is Matthew 5:3, not "character 8,432". Because the
markers live in the text itself, that reference comes for free in every snippet and in
the side-by-side view, with no second table to keep in sync and no risk of a mapping
drifting out of step with the content. The cost is one line in the tokenizer: tokens
matching `\d+:\d+` are skipped so verse numbers never enter an n-gram and never create
a spurious match between two unrelated verses that happen to share a number. A matched
passage that spans a verse boundary will include the marker inside its highlighted span,
which is correct and in fact useful.

The separate mapping table is the more "normalised" design and was rejected as more
machinery than the problem justifies — it adds a table, a join and a class of bug
(stale mapping) in exchange for cosmetics.

Offsets being relative to the committed files, not the Gutenberg original, is the
consequence of normalising at all. It is recorded in `corpus/SOURCES.md` and will be
stated in the README, along with the checksums of both the source file and the
extracted files, so any offset can be reproduced exactly.

### 1.3 Extraction is a committed script, not a one-off manual edit

**Decision.** `scripts/extract_corpus.py` performs the whole extraction and is committed.
It accepts a local copy of the source file or downloads it. It runs at **development
time only**; the application never touches the network.

**Alternatives considered.**
- *Download and hand-trim the files*, committing only the results.
- *Download at container startup.*
- *Commit the whole 4.5 MB eBook* and slice it at runtime.

**Why.** A committed script makes the corpus reproducible and makes the normalisation
auditable — the exact transform applied to the text is readable in the repo rather than
being lost in a shell history. Hand-trimming leaves no record of what was done.
Downloading at startup is ruled out directly by the requirement that nothing needs the
network at runtime, and would make `docker compose up` depend on gutenberg.org being
reachable. Committing the full eBook would put 4.5 MB of Old Testament in the repo to
use 10% of it, and would push the trimming logic into the application, where it does
not belong.

### 1.4 The extractor validates the verse sequence and fails loudly

**Decision.** After splitting a book, assert that chapter/verse numbers form a gapless
sequence starting at 1:1, that no verse is empty, and that the final chapter number
matches the known chapter count (28/16/24/21). Any deviation raises.

**Alternatives considered.**
- *No validation* — trust the regex.
- *Check only the total verse count* against a published figure.

**Why.** Everything downstream is character offsets into these files. If the
`(\d+):(\d+)` pattern ever matched something that was not a verse marker — a number in
the prose, a stray artefact in a future revision of the eBook — the files would be
silently wrong and every offset, score and highlight in the application would be wrong
with them, in a way that looks plausible and is miserable to debug. The sequence check
is a few lines and makes that failure mode loud and immediate instead. It also pinned
the extraction as correct on the first run: the resulting verse counts (1071 / 678 /
1151 / 879) match the canonical KJV counts for the four Gospels exactly, which is
stronger evidence than a total-count check and was obtained for free.

### 1.5 Noted for Phase 2: the corpus uses U+2019, not ASCII `'`

**Observation, not yet a decision.** The source uses the curly right single quotation
mark `U+2019` for every possessive apostrophe — 166 occurrences across the four files
(`child’s`, `camel’s`, `righteousness’ sake`) — and the ASCII apostrophe `U+0027`
appears **zero** times in any file. Line endings are LF throughout, with no CR bytes.

**Why it is recorded here.** Token normalisation in Phase 2 must strip punctuation in a
**Unicode-aware** way. The obvious implementation is the wrong one:

    "Jesus’".strip(string.punctuation)  -> "Jesus’"   # string.punctuation is ASCII-only
    re.sub(r"[^\w\s]", "", "Jesus’")    -> "Jesus"    # correct

Because the usage is perfectly consistent there is no mixed-form hazard — nothing will
fail to match `Jesus'` against `Jesus’`, since the former never occurs. The risk is
narrower: an ASCII-only strip would leave the apostrophe attached to the token, so
`camel’s` would normalise to `camel’s` rather than `camels`, and the n-grams containing
it would still match each other consistently. The real cost would be silent and small —
a handful of passage boundaries off by a token — which is exactly the kind of bug that
does not announce itself. Decided in Phase 2 against a test case built from a real
possessive from the corpus.

### 1.6 `.gitattributes` pins line endings; the corpus is marked `-text`

**Decision.** Commit a `.gitattributes` with `* text=auto eol=lf` as the default, plus
`corpus/*.txt -text` to disable end-of-line translation for the corpus entirely.

**Alternatives considered.**
- *Nothing* — rely on contributors having `core.autocrlf=false`.
- *`* text=auto eol=lf` alone*, without the corpus exception.
- *Ask the pipeline to normalise line endings when it loads a document.*

**Why.** This was found, not foreseen. Staging the corpus on the development machine
produced `warning: LF will be replaced by CRLF the next time Git touches it` for every
file — `core.autocrlf` is `true`, which is the default for Git for Windows.

The consequence would have been severe and silent. A fresh clone on Windows would check
the corpus out with CRLF line endings, adding one byte per preceding line. Every
character offset in the database is an index into these files, so an offset computed on
Linux would point at the wrong character on Windows, drifting further the deeper into
the file it sits — by the end of Luke, a 1,151-line file, the drift is over a thousand
characters. The SHA-256 sums published in `corpus/SOURCES.md` would not verify either,
which is the opposite of the reproducibility those checksums exist to provide.

Relying on contributor configuration is not a fix; the whole point is that
`docker compose up` works from a fresh clone on a machine whose settings are unknown.
`eol=lf` alone would have been *sufficient* in practice, but `-text` is stronger and
says the right thing: these files are not to be interpreted or transformed, they are
fixed data whose exact bytes are part of the project's contract. Normalising at load
time was rejected because it treats a repository-hygiene problem as an application
problem, and would leave the committed checksums still failing to verify.

Verified after staging: all four blobs in the index hash to exactly the values published
in `corpus/SOURCES.md`, and contain zero CR bytes.

---

## Phase 2 — Algorithm

### 2.1 Approach: seed-and-extend over word n-grams

**Decision.** Find parallels by (1) tokenizing both documents into words with
character offsets, (2) indexing each document's word n-grams, (3) treating a
shared n-gram as a "seed", (4) chaining seeds that sit close together on the same
diagonal (the token-position offset between the two documents) into candidate
passages, (5) filtering short candidates, (6) de-duplicating overlapping candidates,
(7) scoring what remains and classifying it exact/near. This is the algorithm the
assignment specifies; implemented in `app/algorithm.py`.

**Alternatives considered.**
- *Full pairwise sequence alignment* (Smith-Waterman / Needleman-Wunsch at the
  character or token level) between every document pair.
- *MinHash / LSH* for approximate near-duplicate detection.
- *Sentence-embedding similarity* (cosine similarity over a sentence encoder).

**Why.** Full alignment is O(len_a x len_b) per pair; for four ~100K-character
documents that is workable here but would not scale, and the assignment explicitly
lists it as a documented *future-work* refinement rather than the baseline. MinHash/LSH
targets near-duplicate whole-document detection at corpus scale (millions of documents)
and is overkill, and loses exact character offsets along the way, which requirement 2
needs directly. Embeddings would catch paraphrase but not exact character offsets
either, needs a model artifact at runtime, and is exactly the kind of dependency the
"no paid APIs, no network" constraint is pushing against. Seed-and-extend is the
standard answer to "share exact sequences, with some latitude for divergence,
between two sequences" (it is a simplified cousin of BLAST), runs in time roughly
proportional to the amount of actual *shared* material rather than the product of the
two lengths, and keeps every step traceable to a concrete token position -- which
matters for an interview where every choice has to be explained.

### 2.2 Tokenizer: letter-run regex, which also disposes of verse markers for free

**Decision.** The word pattern is a maximal run of Unicode letters, optionally
continued across one internal apostrophe (straight or curly). Normalization is
lowercase + "drop any apostrophe". Everything the pattern does not match
(punctuation, whitespace, and digits) is simply not a token.

**Alternatives considered.**
- `\w+` (what most people reach for first).
- Split on whitespace, then `strip(string.punctuation)` each chunk.
- Explicitly detect and skip verse markers (chapter:verse) as a separate pass before tokenizing.

**Why.** `\w` matches digits, so it would tokenize the verse markers (the "1" and "1"
in "1:1") as words, and two unrelated verses that happen to both start with, say,
chapter 3 would then spuriously share a token. `string.punctuation` is ASCII-only, and
the corpus's 166 possessive apostrophes are all the Unicode curly quote (see
`corpus/SOURCES.md` and decision 1.5), which `strip(string.punctuation)` does not
touch -- confirmed directly: a curly-quoted word stripped with `string.punctuation`
comes back unchanged. The letter-run regex sidesteps both problems in one line: by
excluding digits from the character class, verse markers are never tokenized at all,
with no separate marker-detection pass needed; and the character class is
Unicode-aware by construction, so it strips the curly apostrophe correctly without
special-casing it. Verified directly in `tests/test_algorithm.py`
(`test_tokenize_skips_verse_markers_entirely`,
`test_tokenize_handles_curly_apostrophe_like_the_real_corpus`).

### 2.3 Chaining rule: same diagonal, gap <= gap_tolerance tokens

**Decision.** Two seeds chain together only if the token-index offset between
document A and document B is identical for both (same "diagonal") and their start
positions in document A are no more than `gap_tolerance` tokens apart.

**Alternatives considered.** Chain by char-offset proximity instead of token-index
proximity; allow chaining across different diagonals within some tolerance (to model
small insertions/deletions inside the gap, not just substitutions).

**Why.** "Same diagonal" is what makes a gap a *substitution* (same number of words on
both sides, so nothing was inserted or deleted) rather than noise -- two seeds on
different diagonals are seeing different amounts of text in between, which this
simple model does not try to align. Token-index gap, not char-offset gap, matches the
assignment's own framing ("gap tolerance ... e.g. <= 4 tokens") and is robust to KJV's
variable word lengths. Allowing cross-diagonal chaining would let the chain silently
swallow an insertion/deletion, which is a real phenomenon in the corpus (Mark 10:19
numbers its list of commandments differently than Luke 18:20) but is out of scope for
a seed-and-extend prototype; it is noted as future work (gapped alignment /
Smith-Waterman) rather than hacked in here.

### 2.4 Classification: "exact" iff normalized token sequences are identical

**Decision.** A kept passage is "exact" if the two normalized token lists compare
equal element-for-element; otherwise "near". The similarity score is
`rapidfuzz.fuzz.ratio` over the two normalized token sequences joined with spaces,
scaled to 0-1.

**Alternatives considered.** Classify by score threshold (e.g. score == 1.0 is
"exact"); score with `difflib.SequenceMatcher` instead of rapidfuzz.

**Why.** Classifying by score threshold would make "exact" mean "happens to score
1.0", which is a roundabout way of saying the same thing the direct list comparison
says plainly, and risks floating-point score computations landing at 0.999999 for
something that is actually identical. A direct equality check is the simpler, more
honest statement of what "exact" means, and the docstring + test
(`test_identical_sentences_are_an_exact_match`) are unambiguous about it. Because
normalization already drops case and punctuation, "exact" at the word level does NOT
require identical punctuation or verse-numbering -- borne out in the real corpus:
several of the highest-scoring Matthew-Luke matches differ only in punctuation
("adultery, Do not kill, Do" vs. "adultery; Do not kill, Do") and both correctly
register as exact. rapidfuzz was chosen over `difflib` because it is already a
project dependency (the assignment lists it first) and is substantially faster in C;
for a corpus this size either would have worked.

### 2.5 Selecting non-redundant passages: drop only same-region duplicates

**Decision.** After scoring, rank candidates by score times passage length and keep a
candidate only if it does not overlap an already-kept candidate on BOTH sides
(document A range AND document B range). Overlapping on only one side is kept.

**Alternatives considered.** No selection step at all (take every candidate that
passes the length filter). Drop a candidate if it overlaps a kept one on EITHER
side. Keep only the single best candidate per document-pair region, picked by some
clustering of overlapping ranges.

**Why.** This step did not exist in the assignment's numbered steps and was flagged
before writing code: seed chaining on a long shared passage produces many
overlapping chains for the *same* underlying parallel (one starting a token later
than another, covering nearly the same span), and without de-duplication those would
all land in the database as separate rows. "Overlap on both sides" is the right test
because a genuine ONE-TO-MANY match -- one Gospel passage that parallels two
*different* passages elsewhere, because the second Gospel repeats itself -- overlaps
the first kept candidate on only one side (document B, say) while the other side
(document A) is a disjoint region; "overlap on either side" would incorrectly merge
that into one entry and silently lose a real match. This was not a hypothetical
concern: it is exactly what the real corpus does. Matthew quotes Psalm 118:26
("Blessed is he that cometh in the name of the Lord") at BOTH Matthew 21:9 (the
triumphal entry) and Matthew 23:39 (the lament over Jerusalem), and John 12:13 quotes
it once. Running the pipeline on Matthew x John produces two separate kept matches,
each pairing John's one occurrence against a different Matthew verse -- confirmed by
inspecting the actual output, not just a synthetic test (a synthetic version of the
same case is also covered directly in
`test_select_non_redundant_keeps_legitimate_one_to_many_matches`). The documented
limitation: this rule is a greedy approximation, not an optimal set cover, and a
pathological case -- a chain that drifts on one side only due to indel noise near a
substitution -- could in principle be kept alongside something that is really the same
match. No case like that was found by eye in this corpus's actual output.

### 2.6 Parameter experiment on the real corpus (n, gap_tolerance, min_passage_tokens)

**Decision.** Defaults: `ngram_size = 3`, `gap_tolerance = 4`,
`min_passage_tokens = 8`, document-frequency filtering OFF by default (see 2.7).
Reproduce with `python scripts/run_experiment.py`; a snapshot of its output is saved
at `docs/experiment_phase2_output.txt`.

**Alternatives considered.** The assignment suggests `n = 5` as the default; `n` was
swept over `{3, 4, 5, 6}` as instructed, with `gap_tolerance = 4` and
`min_passage_tokens = 8` held at the assignment's own suggested values, then each of
those two was swept independently around n=3 to check they still hold.

**Why -- the n sweep, and why 3 was chosen over the suggested 5.** Holding
`gap_tolerance=4`, `min_passage_tokens=8` fixed, raw chain counts fall sharply as n
grows (Matthew x Mark: 16,363 chains at n=3 -> 4,529 at n=4 -> 1,556 at n=5 -> 575 at
n=6), because fewer short coincidental word-sequences repeat at higher n. But the
FINAL, filtered counts tell a different story: at n=4, 5 and 6 every document
pair's final count is *identical* (212/213/9/132/7/4 for the six pairs respectively)
and every single kept match is classified "exact" -- zero "near" matches survive
anywhere in the corpus at n>=4. At n=3, the same exact matches are still found, plus
166 additional near matches across the four non-control pairs (Matthew-Mark 63,
Matthew-Luke 66, Mark-Luke 34, Mark-John 3), with scores from 0.84 to 0.99, and
ZERO near matches in either control pair (Matthew-John, Luke-John) at any n --
meaning the control stayed clean while recall strictly improved. Inspecting the actual
matches recovered only at n=3 (not a sample -- every one of the lowest-scoring ones,
to stress-test the claim) shows them to be exactly the real one-word substitutions a
"near" match is supposed to catch: *raiment* / *clothes*, *come* / *entered*,
*multitude* / *people*, *Galilee* / *Nazareth*, *tombs* / *sepulchres*, *Master* /
*Lord*, *thine* / *thy*, *plenteous* / *great*, *considerest* / *perceivest* -- not one
looked like a coincidental or incoherent match. The mechanism: at n>=4, a seed needs n
consecutive identical words; when the one substituted word sits within n-1 tokens of
the start or end of an otherwise-shared passage, there may be no full n-word window of
undisturbed context left on that side to seed from at all, so the whole passage can
drop out of the results entirely rather than just losing a token or two at the edge --
this was traced concretely through the "come"/"entered" example in Mark 2:1 / Matthew
9:1. n=3 recovers these without any observed cost. THIS DIRECTLY CONTRADICTS AN
ASSUMPTION MADE WHEN PLANNING THE EXPERIMENT -- that smaller n would mainly
introduce noise from short coincidental overlaps -- which the data did not support:
every n=3-only match inspected was genuine, and the control pairs never produced a
false positive. The suggested default of 5 was therefore not adopted; n=3 is the
one evidence-backed choice. The trade-off accepted is purely computational
(far more raw seeds to chain before filtering), and it is not a real cost here: the
whole sweep over all 4 values of n across all 6 document pairs runs in well under a
second.

**Why -- gap_tolerance = 4 holds.** Swept {2, 4, 8, 16} at n=3, min_passage_tokens=8,
and inspected the single WORST-scoring kept match at each setting (the most likely
place a bad parameter shows up): at gap=2, chaining is so strict that zero near
matches survive at all (every kept match's score rounds to 1.00) -- recall is already
being lost. At gap=4, the worst kept match scores 0.84 and is a clean, legitimate
substitution (*tombs* / *sepulchres*, Matthew 23:29 / Luke 11:47). At gap=8, the
worst drops to 0.67 and is visibly wrong: "Do ye not yet understand, neither
remember the five loaves" chained against "do ye not remember? [verse marker] When I
brake the five loaves" -- bridging across what both texts punctuate as a sentence
boundary, joining material that does not read as one continuous thought. At gap=16 it
is worse still (0.57): the chain bridges two DIFFERENT healing episodes (Matthew
14:34's arrival at Gennesaret bridged into Luke 4:35's unrelated exorcism) purely
because both happen to continue with "And when the" nearby. gap=4 -- the assignment's
own suggested value -- sits right at the point where every inspected match is still
coherent and a larger value starts stitching together text that is not really parallel.

**Why -- min_passage_tokens = 8 holds, and is the real fix for the "formula flood"
risk flagged before this phase.** Swept {5, 6, 8, 10, 12} at n=3, gap=4. Final count
explodes from 1,852 at min_len=6 to 7,176 at min_len=5 -- a 3.9x jump far out
of proportion to the step size, the signature of a flood. Diffing the two result sets
directly: of the 6,517 matches that exist only at min_len=5, a sample of the
shortest confirms they are exactly the predicted problem -- recurring KJV narrative
formulae with no real parallel content: "And he said unto them", "the scribes and
the elders", "cried with a loud voice", "arose, and followed him, and". These are
boilerplate, not parallels, and the pre-registered concern about formula flood
(flagged before Phase 2 started) materializes specifically BELOW 8 tokens, not
above it. At min_len=8 the lowest-scoring surviving match is still a legitimate
substitution at 0.84; raising it further to 10 or 12 only trims genuine matches (final
count keeps falling smoothly, with no further quality cliff) without fixing anything
that was still broken. 8 -- again the assignment's own suggested value -- is the
cutoff right at the edge of the flood.

### 2.7 Document-frequency seed filtering: implemented, off by default

**Decision.** `find_seeds` accepts an optional per-n-gram corpus document-frequency
map and a cutoff, and drops seeds from n-grams that occur in more than that many
documents. The feature stays in the code (`app/algorithm.py`), available for a larger
corpus, but is NOT used in the chosen pipeline: `find_parallels` only applies it
if a frequency map is explicitly passed in, and it is not passed in by default.

**Alternatives considered.** Enable it by default at `max_document_frequency = 3`
(the value originally planned when this filter was proposed, before Phase 2, as the
mitigation for formula flood).

**Why.** Measured directly on Matthew x John at n=3: with no filter, 9 matches;
with the filter at cutoff 3, only 2. The filter did not just remove noise -- it
removed the one-to-many Psalm-quotation match described in 2.5 along with it, because
a direct Old Testament quotation repeated across the Gospels is, by construction, a
*common* n-gram corpus-wide, and this corpus only has four documents, so "document
frequency" takes just five possible values (0-4) and cannot distinguish "common
because it's a cross-Gospel quotation" (a real parallel) from "common because it's
narrative boilerplate" (not one). Meanwhile, `min_passage_tokens` (2.6) already
removes the boilerplate this filter was meant to catch, without that false-positive
cost, because formulae are short and genuine quotations and parallels, formulaic or
not, tend to be longer. The filter is kept available and documented, since a bigger,
more varied corpus (where a phrase's corpus-wide frequency is a less coarse, more
informative signal) is exactly the situation future work (see README limitations)
might reintroduce it for.

### 2.8 Unit tests use explicit small parameters, not the chosen defaults

**Decision.** `tests/test_algorithm.py`'s end-to-end tests construct their own small
`Params` rather than relying on `Params()`'s defaults.

**Why.** The toy sentences the assignment asks for ("two short sentences with one
substituted word") are ten words long; the production `min_passage_tokens=8` would
pass them only barely, and a future change to the chosen defaults (made for a
different corpus, say) should not silently break these tests or change what they are
demonstrating. Pinning the toy test's parameters keeps the test about the mechanism
(seed chaining bridges one substitution; equal normalized sequences are "exact",
unequal ones are "near") independent of whatever the production defaults happen to be.

### 2.9 Deterministic seed and selection order

**Decision.** `find_seeds` iterates `index_a`'s own key order (a plain dict, so
insertion order) filtered to keys also present in `index_b`, instead of
`set(index_a) & set(index_b)`. `select_non_redundant`'s sort key includes the
candidate's own range tuple as an explicit tiebreaker, instead of relying on
sort stability over whatever order the candidates happened to arrive in.

**Why.** Found while trying to reproduce the n-sweep output a second time to save
a clean snapshot for this file: running `scripts/run_experiment.py` twice gave
identical summary counts both times, but the printed *sample* matches came out in a
different order each run, even though the underlying match set was the same. The
cause: Python randomizes string hashing per process (`PYTHONHASHSEED`), so a `set`
built from string-tuple keys iterates in a different order every run, even though a
plain `dict`'s key order is just insertion order and is not affected. `find_seeds`
was building exactly such a set, so the order seeds were generated in -- and
therefore the order candidates were handed to `select_non_redundant` in, which
matters whenever two candidates tie exactly on `score * length` -- was not
reproducible. This is not merely cosmetic: when the Phase 3 database upserts a
passage by its `(doc_a, doc_b, a_start, a_end, b_start, b_end)` key, a non-deterministic
tie-break could, in principle, let two different runs settle on two different
*actual* boundaries for what is really the same redundant cluster, which would show
up as "re-running the pipeline changed a row" -- a direct violation of the Phase 3
"re-runs must not create duplicates" requirement. Fixed by removing the set
intersection (dict membership-testing `index_b` directly, in `index_a`'s own
deterministic order) and by adding the range tuple as an explicit secondary sort
key. Verified by running the full experiment script twice in two separate Python
processes with `PYTHONHASHSEED=random` (forcing a different seed each time) and
diffing: output is now byte-for-byte identical.
