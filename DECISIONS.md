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
