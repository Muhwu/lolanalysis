# Session Titles, Markdown Notes & Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sessions get an editable title + full Markdown notes (expandable, rendered client-side) and a one-file Markdown export.

**Architecture:** Schema migration in `db.connect` (note→title rename, notes column added); `update_session` helper; PATCH + export endpoints; vendored `marked.min.js`; expandable/editable session cards in the frontend.

**Tech Stack:** unchanged + vendored marked.js (no runtime CDN).

## Global Constraints

- Existing dbs migrate automatically on `connect()`; data preserved.
- Export document: `# Coaching sessions`, sessions **newest first**, each `## <session_date> — <title or "Session">` + raw notes; `text/markdown; charset=utf-8`, attachment filename `coaching-sessions.md`.
- Progress segments carry the **title** in their existing `note` key (rendering contract unchanged).
- Markdown rendered client-side with `static/vendor/marked.min.js`; `<pre>` fallback when lib missing.

---

### Task 1: DB migration + title/notes helpers

**Files:** Modify `server/db.py`; test `tests/test_db.py`.

**Produces:** new-install schema has `title`/`notes` columns; `_migrate(conn)` renames `note`→`title` and adds `notes` on legacy dbs; `add_session(conn, session_date, title="", notes="") -> int`; `update_session(conn, session_id, title=None, notes=None) -> bool` (None = unchanged; False if id missing).

- [ ] Failing tests: fresh schema has title+notes; legacy db (hand-created with `note` col + one row) migrates preserving data; add_session stores notes; update_session partial updates + missing id False. Existing session tests updated note→title. FAIL → implement → PASS → commit.

### Task 2: stats reads title

**Files:** Modify `server/stats.py` (`progress_segments` uses `s["title"]`); update `tests/test_stats.py` `sessions()` helper to emit `title`.

- [ ] Update tests to title; run (fails on old key) → change `ordered[i]["note"]`→`["title"]` accesses → PASS → commit.

### Task 3: API — POST title/notes, PATCH, export.md

**Files:** Modify `server/app.py`; test `tests/test_app.py`.

**Produces:** `POST /api/sessions {date, title?, notes?}`; `PATCH /api/sessions/{id} {title?, notes?}` (400 when both absent, 404 unknown id); `GET /api/sessions/export.md` (headers + document per Global Constraints).

- [ ] Failing tests: POST stores title+notes (visible in GET); PATCH round trip, 400, 404; export: content-type, disposition, `## 2026-07-05 — b` before `## 2026-06-28 — a`, notes body present, empty-db export = just H1. FAIL → implement → PASS → commit.

### Task 4: Frontend — vendor marked, expandable/editable cards, export button

**Files:** Create `static/vendor/marked.min.js` (download once from https://cdn.jsdelivr.net/npm/marked/marked.min.js and commit); modify `static/index.html` (script tag before app.js; Export button beside "Coaching sessions" h2; title field in add form), `static/app.js` (renderSessions → cards with expand/edit/delete; edit = title input + notes textarea + Save/Cancel → PATCH → loadProgress; expand renders `marked.parse(notes)` into `.md-body`, `<pre>` fallback), `static/style.css` (.session-card, .md-body typography).

- [ ] Implement; pytest suite green; screenshot: expanded session showing rendered Markdown (add sample notes to session 1 via PATCH for the check), edit mode, export link fetch returns markdown.

### Task 5: Docs

- [ ] README coaching section: titles, Markdown notes, export. CLAUDE.md: PATCH/export endpoints, migration note, vendored marked. Commit.
