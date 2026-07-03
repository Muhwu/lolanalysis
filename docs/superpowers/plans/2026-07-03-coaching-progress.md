# Coaching Progress View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A "Coaching progress" view showing WR/KDA/CS-min per period between user-entered coaching sessions, combined across both accounts, champion filter defaulting to Gwen.

**Architecture:** New `coaching_sessions` table + helpers in `server/db.py`; `stats._filtered_base` gains multi-puuid support and a new `progress_segments()`; three session endpoints + one progress endpoint in `server/app.py`; frontend gets a view switcher and a progress pane in the existing `static/` files.

**Tech Stack:** unchanged (Python 3.12, FastAPI, sqlite3, vanilla JS, pytest).

## Global Constraints

- Segment boundaries: session_date at **00:00 UTC**; session-day games belong to the *after* segment.
- Baseline = 30 days before first session. Final segment = last session → now.
- Progress aggregates **all tracked players**; top-lane only; remakes (<300 s) excluded.
- Champion default in UI: Gwen (fallback All). Sessions are global, `session_date` unique ISO date.
- First session 2026-06-28 inserted at delivery (one-off, not in schema code).

---

### Task 1: DB — coaching_sessions table + helpers

**Files:** Modify `server/db.py` (SCHEMA + helpers). Test `tests/test_db.py`.

**Produces:** `add_session(conn, session_date: str, note: str = "") -> int` (raises `sqlite3.IntegrityError` on duplicate date), `list_sessions(conn) -> list[Row]` (date ascending), `delete_session(conn, session_id) -> bool`.

- [ ] Failing tests: add/list ordering, duplicate date raises, delete returns True/False, note default ''. Verify FAIL → implement (`CREATE TABLE IF NOT EXISTS coaching_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, session_date TEXT NOT NULL UNIQUE, note TEXT NOT NULL DEFAULT '', created_at_ms INTEGER)`) → PASS → commit.

### Task 2: stats.progress_segments + multi-puuid base

**Files:** Modify `server/stats.py`. Test `tests/test_stats.py`.

**Produces:** `_filtered_base` accepts `puuid: str | list[str]`; `progress_segments(conn, puuids: list[str], sessions: list[dict], champion=None, queues=None, now_ms=None, baseline_days=30) -> list[dict]` — sessions as `[{"session_date": "YYYY-MM-DD", "note": str}]` sorted ascending; returns segments `[{label, from_ms, to_ms, note, games, wins, winrate, kda, cs_min, gold_min, dmg_min, ...}]`: baseline, one per consecutive pair, final "since last". Empty-game segments included with `games: 0`.

- [ ] Failing tests: single session → 2 segments (baseline + since); boundaries at UTC midnight (game 1 ms before boundary in baseline, at boundary in next); two sessions → 3 segments; union across two puuids; champion filter; zero-game segment present; no sessions → []. Verify FAIL → implement → PASS → commit.

### Task 3: API — session CRUD + progress endpoint

**Files:** Modify `server/app.py`. Test `tests/test_app.py`.

**Produces:** `GET /api/sessions`; `POST /api/sessions` (json `{date, note?}`; 400 invalid date, 409 duplicate); `DELETE /api/sessions/{id}` (404 missing); `GET /api/stats/progress?champion=&queue=` (all tracked puuids; no puuid param).

- [ ] Failing tests: CRUD round trip; 400/409/404; progress returns segments with expected labels after POSTing a session. Verify FAIL → implement → PASS → commit.

### Task 4: Frontend — view switcher + progress pane

**Files:** Modify `static/index.html`, `static/app.js`, `static/style.css`.

- [ ] Add header view switcher (Overview | Coaching progress); progress `<section>` hidden by default containing: champion+queue selects, segment table target, session manager (list + date/note add form). Overview sections and account tabs hide when progress active.
- [ ] app.js: `loadProgress()` fetches `/api/sessions` + `/api/stats/progress`; render segment rows (period label + dates, note, games, W–L, WR bar, KDA, CS/min, gold/min) with ↑/↓ deltas vs previous segment on WR/KDA/CS-min (`--good-text`/`--critical` colored, only when both segments have games); champion select defaults to Gwen when present; add/delete session wired with refresh + `confirm()` on delete.
- [ ] Verify: pytest suite green; screenshot check with real data.

### Task 5: Deliver — insert first session + docs

- [ ] Insert session 2026-06-28 into `data/lol.sqlite` via `db.add_session`.
- [ ] README: coaching progress section (assumptions: combined accounts, boundary semantics). CLAUDE.md: new endpoints + progress_segments note.
- [ ] Full pytest + screenshot of progress view with real data → commit.
