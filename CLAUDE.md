# CLAUDE.md — working rules for this repo

These rules come from the project owner and persist across sessions.

## Process
- Work in **PHASES**. Stop after each phase, summarize what was done and why in a
  few lines, and **wait for explicit approval** before starting the next phase.
- Before writing code for a phase, confirm the plan or flag anything that looks wrong.
- The owner must be able to explain **every** choice in an interview. No unexplained
  magic numbers, no "because the library does it that way".
- Commit at the end of each phase with a clear message.

## DECISIONS.md
Every time something is chosen (algorithm, parameter, schema, library, data transform),
append an entry to `DECISIONS.md` with exactly three parts:
- **Decision** — what was chosen.
- **Alternatives considered** — what else was on the table.
- **Why** — the reasoning, including the experiment or measurement if there was one.

## Code style
- Simple and readable over clever.
- Small, well-named functions. A function should fit on a screen.
- Prefer the standard library unless a dependency clearly pays for itself.
- Tests with pytest; test behaviour, not implementation details.

## Hard requirements (from the assignment)
1. Corpus of 3–5 public-domain texts that share passages, committed to the repo.
2. Find EXACT and NEAR-match passages between **every** document pair, with
   character offsets in both texts and a similarity score.
3. Store documents, parallels, and review status. **Re-runs must not create duplicates.**
4. UI: filterable list of parallels + side-by-side view with matches highlighted.
5. Additional features of the owner's choice, each justified in the README.
6. Starts with **one** command: `docker compose up`.
7. No paid APIs and **no network access at runtime**.
8. README covering: how to run, schema, algorithm, limitations, AI-assistance disclosure.

## Phase plan (7 phases, from the owner's original brief)
1. Corpus — KJV Gospels from Gutenberg #10, `corpus/SOURCES.md`. ✅
2. Algorithm — seed-and-extend over word n-grams; n ∈ {3,4,5,6} experiment;
   toy-example unit tests. ✅
3. Database — documents / runs / parallels, upsert that never overwrites
   status/note; run-twice test. ✅
4. API + UI — startup pipeline + "Re-run" button; filtered/sorted/paginated list;
   side-by-side detail with highlight, review buttons, note, prev/next. ✅
5. Docker — `docker compose up` from a fresh clone builds, analyzes, serves on
   :8000; verified from a clean state. ✅
6. Additional features — owner picked: word diff, pair matrix, keyboard
   shortcuts, CSV export (DECISIONS 6.x). Thresholds-in-UI not built. ✅
   Candidates from the brief: word-level diff inside near matches; keyboard
   shortcuts (j/k/a/r); CSV export of approved parallels; document-pair matrix of
   parallel counts; adjustable thresholds in the UI.
7. README — Overview, How to run, Corpus, Algorithm (with toy example), Schema,
   Idempotency, Design decisions (summary of DECISIONS.md), Additional features +
   why, Limitations & future work (Smith-Waterman refinement, MinHash/LSH,
   embeddings for paraphrase, offsets shifting when params change), AI-assistance
   disclosure. ✅

Where the implementation went beyond or departed from the brief, it is recorded in
DECISIONS.md — notably 2.5 (overlap de-duplication, not in the brief's steps),
2.6 (n=3 instead of the suggested 5), 2.7 (doc-frequency filter, built but off),
3.5/4.6 (stale-row tracking + banner), 4.1 (skip-if-unchanged at startup),
5.1 (PYTHONUNBUFFERED).

## Stack (fixed)
Python 3.12 · FastAPI · SQLite on a Docker volume · rapidfuzz (or difflib) ·
plain HTML + vanilla JS + CSS served by FastAPI, no build step ·
one Dockerfile + docker-compose.yml, single service · pytest.
