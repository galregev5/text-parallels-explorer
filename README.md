# Text Parallels Explorer

Finds passages that two documents share, word-for-word ("exact") or with small wording
changes ("near"), stores them with character offsets and a similarity score, and gives a
researcher a UI to review them: a filterable list, a side-by-side view with the match and
its differing words highlighted, approve/reject with notes, and CSV export.

The corpus is the four Gospels in the King James Version. Matthew, Mark and Luke share a
great deal of material, some identical and some reworded; John shares little with them
and acts as a **control** for the detector.

Every choice below is recorded in more depth, with the alternatives and the evidence, in
[`DECISIONS.md`](DECISIONS.md). Section numbers like (2.6) refer to entries there.

---

## How to run

```sh
docker compose up
```

Then open <http://localhost:8000>. The first start builds the image, analyzes the corpus
(under a second) and serves the app. The startup log says what happened:

```
[startup] analysis ran: run_id=1 total_parallels=659
```

On later starts with the same corpus and parameters it says `analysis skipped (nothing
changed)` and keeps everything as it was (4.1).

- **Data** lives in the named Docker volume `data` (`/app/data/app.db`), so review status
  survives `docker compose down` / `up` and image rebuilds. `docker compose down -v`
  deletes it and starts fresh.
- **No network is needed at runtime.** The corpus is committed; nothing is downloaded. The
  image was verified to run with `--network none`.
- **Tests** (72, pytest) run inside the container:
  `docker compose run --rm web python -m pytest -q`
- **Without Docker** (Python 3.12): `pip install -r requirements.txt`, then
  `uvicorn app.main:app` (the database goes to `data/app.db`; override with
  `DATABASE_PATH`).
- **Parameter experiment:** `python scripts/run_experiment.py` reproduces the sweep
  used to choose the algorithm's parameters (snapshot in
  `docs/experiment_phase2_output.txt`).

## Using it

- **List page.** The document-pair matrix at the top shows how many parallels each pair
  has (click a cell to filter to that pair). Below it: filters for pair, type, status,
  score range, text search and "latest run only"; sorting; pagination. "Re-run analysis"
  forces a fresh run. "Export approved (CSV)" downloads the approved parallels matching
  the other filters.
- **Detail page.** Both full documents side by side, the matched passage highlighted in
  yellow and scrolled into view, the words that differ highlighted in orange. Approve /
  Reject / Pending, a note, and previous/next within the same filtered list.
  **Keyboard:** `j`/`k` next/previous, `a` approve, `r` reject, `p` pending.

## Corpus

| File | Book | Verses | Characters |
|------|------|-------:|-----------:|
| `corpus/matthew.txt` | Matthew | 1071 | 130,319 |
| `corpus/mark.txt` | Mark | 678 | 82,670 |
| `corpus/luke.txt` | Luke | 1151 | 140,891 |
| `corpus/john.txt` | John | 879 | 102,680 |

Source: Project Gutenberg eBook #10, *The King James Version of the Bible*; public domain.
`scripts/extract_corpus.py` extracts the four books reproducibly (checking chapter and
verse sequences and failing loudly on any gap), and `corpus/SOURCES.md` gives the source
URL, retrieval date, copyright note and SHA-256 sums of the files (1.1–1.4).

Each file is one verse per line as `chapter:verse text`. The verse markers stay in the
text so a researcher can cite what they see; the tokenizer never treats them as words
(2.2). `.gitattributes` marks the corpus `-text` so line endings are never translated on
checkout: every stored offset is an index into these exact bytes (1.6).

**Why the Gospels.** They give three degrees of overlap in one corpus: identical
passages, reworded passages, and material unique to one book. That range is what
separates exact from near matches. John gives a built-in sanity check: if the detector
finds as much between John and Luke as between Matthew and Luke, it is miscalibrated.
On the final parameters the synoptic pairs have 154–244 parallels each; every John pair
has 4–9.

## Algorithm

Seed-and-extend over word n-grams (`app/algorithm.py`), the same family as BLAST and
plagiarism detectors (2.1):

1. **Tokenize** each document into words, keeping each word's `(start, end)` character
   offsets in the *original* text. A word is a run of Unicode letters, optionally joined
   by an apostrophe (straight or curly). Digits are not letters, so verse markers like
   `15:18` are never tokens (2.2).
2. **Normalize** each token for comparison: lowercase, apostrophes removed.
3. **Index** each document's word n-grams (n = 3).
4. **Seeds.** For each document pair (all 6 pairs, stored with the lower document id
   first), every n-gram the two documents share, at every pair of positions, is a seed.
5. **Chain** seeds that lie on the same *diagonal* (same token offset between the two
   documents) and are at most `gap_tolerance` = 4 tokens apart. Same diagonal means any
   gap is a substitution, not an insertion (2.3).
6. **Filter** chains shorter than `min_passage_tokens` = 8 on either side.
7. **De-duplicate.** Keep candidates best-first; drop one only if it overlaps an already
   kept one on *both* sides. One-sided overlap is kept because it is a real one-to-many
   match, e.g. Matthew quotes Psalm 118:26 twice and John once (2.5).
8. **Score and classify.** "exact" if the normalized token sequences are identical
   (so case and punctuation differences still count as exact), otherwise "near" (2.4).
   The score is `rapidfuzz.fuzz.ratio` over the normalized tokens joined into one string:
   a 0–1 character-level similarity of the normalized text (exact matches are 1.0). Note
   it is character-level, not word-level: a substitution sharing letters costs less than
   one that does not (7.1).
9. **Output** per parallel: document pair, character offsets in both documents
   (token spans mapped back through step 1), score, type.

### Toy example (from the tests)

```
A: The quick brown fox jumps over the lazy dog near the river.
B: The quick brown fox leaps over the lazy dog near the river.
```

- 12 tokens each. Shared 3-grams (seeds), as (position in A, position in B):
  `(0,0) (1,1) (5,5) (6,6) (7,7) (8,8) (9,9)`. The 3-grams containing token 4
  (`jumps`/`leaps`) are missing.
- All seeds are on diagonal 0, and the gap between seed 1 and seed 5 is 4 ≤
  `gap_tolerance`, so they chain into one passage: tokens 0–12 on both sides.
- 12 ≥ 8 tokens, so it passes the filter. The token sequences differ, so it is **near**,
  score 0.948, at characters 0–58 in both texts.
- The word diff (below) marks characters 20–25 on each side: `jumps` / `leaps`.

### Choosing the parameters by experiment

`scripts/run_experiment.py` swept n ∈ {3, 4, 5, 6}, then `gap_tolerance` and
`min_passage_tokens` around the chosen n, printing counts and sample matches for every
pair (2.6):

- **n = 3, not the suggested 5.** At n = 4, 5 and 6 the results are identical and contain
  *zero* near matches: if the substituted word is near either end of a shared passage,
  no n-word window of untouched context is left to seed from, and the whole passage is
  lost. n = 3 finds the same exact matches plus 166 near matches (scores 0.84–0.99), every
  one inspected a genuine substitution (*tombs*/*sepulchres*, *multitude*/*people*,
  *raiment*/*clothes*), and adds no near matches to the John control pairs.
- **gap_tolerance = 4.** At 2, no near match survives. At 8 and 16, chains bridge across
  sentence boundaries and even between different episodes.
- **min_passage_tokens = 8.** Lowering it from 6 to 5 jumps the count from 1,852 to
  7,176, the extra matches almost all stock KJV phrases ("And he said unto them") rather
  than parallels. At 8 the weakest kept
  match is still a real substitution.
- A filter dropping n-grams common across the corpus was built and measured but left off:
  with only four documents it also removed a genuine Old Testament quotation (2.7).

## Schema

SQLite, standard library `sqlite3`, no ORM (3.1). Full DDL with comments in
[`app/schema.sql`](app/schema.sql).

```
documents(id, slug UNIQUE, title, content, content_hash)
runs(id, started_at, params_json)
parallels(id, doc_a_id → documents, doc_b_id → documents,
          a_start, a_end, b_start, b_end,          -- character offsets, end exclusive
          score, match_type, status DEFAULT 'pending', note,
          last_seen_run_id → runs,
          UNIQUE(doc_a_id, doc_b_id, a_start, a_end, b_start, b_end),
          CHECK(doc_a_id < doc_b_id), CHECK(a_start < a_end), CHECK(b_start < b_end),
          CHECK(score BETWEEN 0 AND 1), CHECK(match_type IN ('exact','near')),
          CHECK(status IN ('pending','approved','rejected')))
```

- `doc_a_id < doc_b_id` is enforced by the database, not just by the code, so a pair is
  never stored both ways round (3.3).
- `runs.params_json` records which parameters produced the results;
  `parallels.last_seen_run_id` records the latest run that found each row.
- Indexes on pair, status, score and `last_seen_run_id` serve the list filters.

## Idempotency

Re-runs never create duplicates and never overwrite a researcher's review (3.4):

1. The `UNIQUE` key on `(doc_a_id, doc_b_id, a_start, a_end, b_start, b_end)` means the
   same passage always maps to the same row.
2. Parallels are written with
   `INSERT ... ON CONFLICT(...) DO UPDATE SET score=..., match_type=..., last_seen_run_id=...`.
3. `status` and `note` are simply not in that `SET` list, so SQLite leaves them as they are.

Documents are upserted by slug; an unchanged `content_hash` means no write (3.7). A whole
run is one transaction, so a crash never leaves a half-applied run (3.6). At startup the
analysis is skipped entirely when the corpus hashes and parameters match the latest run;
the Re-run button always runs (4.1).

Tested directly: running the pipeline twice gives the same row count, a status and note
set between runs survive, and the Docker volume keeps review status across
`down`/`up`.

**When parameters change**, passages can come out with different offsets, so they become
new rows. Old rows are never deleted: their `last_seen_run_id` falls behind the latest run
and they become *stale*. The list page shows a banner with the stale count and a "latest
run only" filter, and stale rows are badged (3.5, 4.6). Nothing is lost, and a reviewed row
keeps its decision.

## Design decisions (summary of DECISIONS.md)

- **Corpus:** KJV Gospels for graded overlap plus a control; one verse per line with
  markers kept; corpus bytes pinned by `.gitattributes` and SHA-256 (1.1–1.6).
- **Algorithm:** seed-and-extend because it keeps exact offsets and every step is
  traceable, unlike MinHash or embeddings (2.1); letter-only tokenizer (2.2); same-diagonal
  chaining (2.3); exact = identical normalized tokens (2.4); both-sides overlap
  de-duplication, a step added beyond the brief (2.5); n = 3, gap 4, min length 8 by
  experiment (2.6); corpus-frequency filter built but off (2.7); deterministic ordering so
  re-runs produce identical rows (2.9).
- **Storage:** stdlib `sqlite3`, schema in a `.sql` file, pair order enforced by `CHECK`,
  idempotency by three plain rules, stale rows kept rather than deleted, one transaction
  per run (3.1–3.7).
- **API/UI:** skip-if-unchanged at startup (4.1); one connection per request (4.2, with
  the Phase 6 correction in 6.5); researcher-owned and pipeline-owned writes kept in
  separate functions (4.3); snippets and search read only the matched span via `SUBSTR`
  (4.4); prev/next computed over the same filtered, sorted set as the list (4.5);
  stale-row banner (4.6). Plain HTML, vanilla JS and CSS served by FastAPI; no build step.
- **Docker:** one service, analysis at container start (not build time) so results land on
  the volume, `PYTHONUNBUFFERED` so the startup log appears (5.1).
- **Bugs found by verification and fixed:** concurrent requests failed because FastAPI
  runs the connection dependency and the handler on different threads (6.5); the scoring
  docstring overstated what the score measures (7.1).

## Additional features and why

| Feature | Why |
|---|---|
| **Word-level diff inside near matches** | A score of 0.91 doesn't tell the reviewer *what* changed; highlighting the differing words makes each near match reviewable at a glance. It diffs the same normalized tokens the scorer compared (`difflib`, stdlib), so case or punctuation alone never shows as a change, matching how exact/near is decided. Computed server-side and unit-tested (6.1). |
| **Document-pair matrix** | A one-screen overview of the whole analysis, and the clearest view of the control: John's 4–9 parallels per pair against the synoptics' 154–244. Counts the latest run only so stale rows don't inflate it; clicking a cell filters the list (6.2). |
| **Keyboard shortcuts** (`j`/`k`/`a`/`r`/`p`) | Reviewing hundreds of parallels is the core repetitive task, and moving the mouse between Approve and Next is the bottleneck. The shortcuts reuse the existing buttons and save logic. No auto-advance, so the reviewer sees each decision land before moving on (6.3). |
| **CSV export of approved parallels** | The review's output, in a form a researcher can take into a spreadsheet or another tool: offsets, score, type, status, note and both passages' text. Honors the list's other filters. UTF-8 with a byte-order mark so Excel shows the corpus's curly apostrophes correctly (6.4). |

Not built: **adjustable thresholds in the UI.** Changing parameters moves offsets and
creates stale rows, so a one-click control would scatter review work across parameter
sets; see the last limitation below.

## Limitations and future work

- **Insertions and deletions split passages.** Chaining requires the same diagonal, so a
  word added on one side ends the chain. A passage with an insertion appears as two
  parallels, or one if the other half is too short. *Future:* a gapped alignment such as
  Smith-Waterman, run only inside the regions seeds identify, to join and refine them.
- **Paraphrase is invisible.** A passage needs at least one shared 3-word sequence, and
  8 tokens of mostly-shared text, to be found at all. Retellings in different words are
  missed. *Future:* sentence embeddings, which would need a local model to keep the
  no-network rule.
- **The score is character-level** (7.1), by choice: a plural or spelling variant
  ("village"/"villages", 0.989) scores higher than a different word ("village"/"city",
  0.894), so real wording changes surface first when sorting by score. The cost is that
  the score cannot be read as "share of words that match" (both would be 0.900 there).
- **Scale.** Every document pair is compared, which grows with the square of the number of
  documents, and each pair builds its seed list in memory. Fine for four books; a large
  corpus would want *MinHash/LSH* to pick candidate pairs and a streaming chain step. The
  detail page's prev/next also loads the filtered id list in Python (4.5).
- **Stock phrases.** `min_passage_tokens = 8` removes most KJV stock phrases, but a long
  one shared by chance could still match. The corpus-frequency filter (2.7) becomes useful
  with a larger, more varied corpus.
- **Greedy de-duplication** is an approximation, not an optimal cover; no failure was seen
  in this corpus's output (2.5).
- **Highlighted spans include verse markers** that fall between matched words (e.g.
  `15:18`), because a span runs from the first matched word's start to the last one's end
  in the original text.
- **Offsets shift when parameters change.** A passage found under new parameters is a new
  row; the review on the old row does not carry over, it is only kept and marked stale.
  *Future:* carry status over to a new row that overlaps a reviewed stale row on both
  sides, with the researcher confirming.
- **Single-user tool.** No authentication; last write wins on status and notes.

## AI assistance disclosure

This project was built with an AI coding assistant, Anthropic's Claude (Claude Code),
working in phases under my direction:

- **Mine:** the assignment brief, the phase plan, the algorithm design (seed-and-extend
  with the steps above), the schema and idempotency rules, the stack, the choice of
  corpus, the selection of additional features, and the review and approval of each phase
  before the next began.
- **The assistant's:** writing the code, tests, scripts and documentation; running the
  parameter experiment and reporting the results; verifying each phase (including in
  Docker and in a browser); and recording each decision with its alternatives in
  `DECISIONS.md`. Where it went beyond or departed from the brief, it says so there: for
  example the both-sides de-duplication step (2.5), choosing n = 3 over the suggested 5
  (2.6), and the stale-row handling (3.5, 4.6).
- The two bugs listed under Design decisions were found by the assistant's own
  verification and fixed with regression tests or corrected documentation.

No AI is used at runtime: the app uses no paid APIs, models or network.
