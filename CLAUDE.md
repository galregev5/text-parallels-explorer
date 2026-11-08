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

## Stack (fixed)
Python 3.12 · FastAPI · SQLite on a Docker volume · rapidfuzz (or difflib) ·
plain HTML + vanilla JS + CSS served by FastAPI, no build step ·
one Dockerfile + docker-compose.yml, single service · pytest.
