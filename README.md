# Text Parallels Explorer

Finds passages that two documents share, word-for-word ("exact") or with small wording
changes ("near"), stores them with character offsets and a similarity score, and gives a
researcher a UI to review them: a filterable list, a side-by-side view with the match
highlighted, approve/reject with notes, and CSV export.

**Corpus:** the four Gospels, King James Version (Project Gutenberg #10, public domain),
in `corpus/`. Matthew, Mark and Luke share a great deal of material, some identical and
some reworded; John shares little with them and acts as a **control**: the synoptic pairs
have 154–244 parallels each, every John pair has 4–9.

Each choice is recorded with its reasoning in [`DECISIONS.md`](DECISIONS.md).

## How to run

```sh
docker compose up
```

Open <http://localhost:8000>. The first start builds the image, analyzes the corpus
(under a second) and serves the app. Later starts with an unchanged corpus skip the
analysis and keep all review work.

- Data lives in the Docker volume `data`; `docker compose down -v` starts fresh.
- No network access at runtime: the corpus is committed and nothing is downloaded.
- Tests (72, pytest): `docker compose run --rm web python -m pytest -q`

## Algorithm

Seed-and-extend over word n-grams (`app/algorithm.py`), run on every document pair:

1. **Tokenize** into words, keeping each word's character offsets in the original text.
   A word is a run of letters, so verse markers like `15:18` are never tokens.
2. **Normalize** each token: lowercase, apostrophes removed.
3. **Seeds:** every 3-word sequence (n-gram) the two documents share.
4. **Chain** seeds on the same *diagonal* (same position offset between the two
   documents) that are at most 4 tokens apart. A gap on the same diagonal is a
   substituted word.
5. **Filter** passages shorter than 8 tokens.
6. **De-duplicate:** best candidates first; drop one that overlaps an already-kept
   passage in *both* documents (overlap on one side only is a real one-to-many match).
7. **Score and classify:** "exact" if the normalized words are identical, otherwise
   "near". The score (0–1) is `rapidfuzz.fuzz.ratio` on the normalized text.
8. **Output:** document pair, character offsets in both texts, score, type.

**Toy example (from the tests)**

```
A: The quick brown fox jumps over the lazy dog near the river.
B: The quick brown fox leaps over the lazy dog near the river.
```

Every 3-gram is shared except the three containing `jumps`/`leaps`. All seeds lie on one
diagonal with a gap of 4 ≤ 4, so they chain into one 12-token passage: **near**, score
0.948, characters 0–58 in both texts. The UI highlights `jumps` / `leaps` as the difference.

**Parameters were chosen by experiment** (`scripts/run_experiment.py`, output in
`docs/`):

- **n = 3.** With n = 4, 5 or 6 no near matches are found at all: a substituted word near
  the end of a passage leaves no full n-word window to seed from. n = 3 finds the same
  exact matches plus 166 near matches, each inspected and genuine
  (*tombs*/*sepulchres*, *raiment*/*clothes*), and none in the John control pairs.
- **Gap 4.** At 2 no near match survives; at 8+ chains bridge into unrelated episodes.
- **Minimum 8 tokens.** Shorter passages are dominated by stock phrases such as
  "And he said unto them".

## Schema

SQLite (stdlib `sqlite3`); full DDL in [`app/schema.sql`](app/schema.sql).

```
documents(id, slug UNIQUE, title, content, content_hash)
runs(id, started_at, params_json)
parallels(id, doc_a_id, doc_b_id, a_start, a_end, b_start, b_end,
          score, match_type, status DEFAULT 'pending', note, last_seen_run_id,
          UNIQUE(doc_a_id, doc_b_id, a_start, a_end, b_start, b_end),
          CHECK(doc_a_id < doc_b_id))
```

**Re-runs never create duplicates or overwrite a review:** the `UNIQUE` key maps the same
passage to the same row; parallels are written with `INSERT ... ON CONFLICT DO UPDATE`;
and `status`/`note` are not in that update, so a researcher's review is preserved. Each
run is a single transaction. Tested by running the pipeline twice and by restarting the
container.

## Features beyond the core

| Feature | Why |
|---|---|
| **Word-level diff** in near matches | A score alone doesn't say *what* changed; the differing words are highlighted. |
| **Document-pair matrix** | One-screen overview of the analysis; makes the John control visible; click to filter. |
| **Keyboard shortcuts** (`j`/`k` next/prev, `a`/`r`/`p` approve/reject/pending) | Reviewing hundreds of parallels is the core repetitive task. |
| **CSV export** of approved parallels | The review's output, ready for a spreadsheet. |

## Limitations

- **Inserted or deleted words split a passage** into two parallels, since chaining
  stays on one diagonal.
- **Paraphrase is not detected:** a passage needs shared 3-word sequences to be found.
- **Built for a small corpus:** every document pair is compared in memory.
- **Changing parameters can shift offsets**, creating new rows. Old rows are kept and
  marked stale (with a banner and filter in the UI), so no review is lost, but it does
  not carry over automatically.
- **Single user:** no authentication.

## AI assistance

Built with Anthropic's Claude (Claude Code) under my direction, phase by phase. I set the
plan, algorithm design, schema, corpus and features, and reviewed and approved each
phase; the assistant wrote the code, tests and documentation and ran the experiments. No
AI is used at runtime.
