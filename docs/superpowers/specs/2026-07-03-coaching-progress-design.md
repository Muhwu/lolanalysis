# Coaching Progress View — Design

**Date:** 2026-07-03
**Status:** Approved with assumptions (user AFK; recommended options taken, flagged below)

## Purpose

Track improvement between weekly coaching sessions (first: 2026-06-28).
A separate "Coaching progress" view shows winrate, KDA, and CS/min for the
periods between consecutive sessions, so week-over-week improvement is visible.
The existing overview stays unchanged.

## Decisions (assumptions taken while user was AFK)

1. **Account scope: combined.** Progress aggregates games from all tracked
   accounts (coaching applies to the player, not the account).
2. **Session record: date + optional note** (e.g. "wave management").
3. **Segments: baseline + between + current.**
   - *Baseline*: the 30 days before the first session.
   - One segment per gap between consecutive sessions.
   - *Since last session*: last session date → now.
   - Boundary semantics: a session's date converts to **00:00 UTC**; games on
     the session day count toward the segment *after* the session.
4. **Champion filter defaults to Gwen** (falls back to All if no Gwen games);
   queue filter available, defaults to All. Top-lane games only, remakes
   excluded — same rules as the rest of the app.
5. The first session (2026-06-28) is inserted as part of delivery; further
   sessions are added through the UI.

## Components

### DB (`server/db.py`)
- New table: `coaching_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_date TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  created_at_ms INTEGER)` (`session_date` = ISO `YYYY-MM-DD`, unique).
- Helpers: `add_session(conn, date, note) -> id`,
  `list_sessions(conn) -> [Row]` (date asc), `delete_session(conn, id)`.
- Table added via existing `SCHEMA` script (CREATE TABLE IF NOT EXISTS —
  existing dbs pick it up on next connect).

### Stats (`server/stats.py`)
- `_filtered_base` gains multi-puuid support: `puuid` param accepts a list
  (SQL `IN`); existing single-puuid callers unchanged.
- New `progress_segments(conn, puuids, session_rows, champion=None,
  queues=None, now_ms=None, baseline_days=30) -> list[dict]`:
  each dict = `{label, from_ms, to_ms, note, games, wins, winrate, kills,
  deaths, assists, kda, cs_min, gold_min, dmg_min, avg_duration_s}`.
  Segments with 0 games still appear (stats None) so gaps are visible.
  With no sessions, returns [].

### API (`server/app.py`)
- `GET /api/sessions` → `[{id, session_date, note}]`
- `POST /api/sessions` body `{date: "YYYY-MM-DD", note?: str}` → 400 on bad
  date, 409 on duplicate date.
- `DELETE /api/sessions/{id}` → 404 if missing.
- `GET /api/stats/progress?champion=&queue=` → segments over **all tracked
  players' puuids** (no puuid param).

### Frontend (`static/`)
- Header view switcher: **Overview | Coaching progress** (account tabs hidden
  in progress view since it's combined).
- Progress view: champion select (default Gwen when available), queue select,
  segment table — rows: Baseline, S1 → S2 (dates + note), …, "Since last
  session (date)"; columns: period, games, W–L, winrate bar, KDA, CS/min,
  gold/min, with small ↑/↓ delta vs the previous segment on winrate, KDA,
  CS/min (green/red text, sign included).
- Session manager under the table: list of sessions (date, note, delete
  button with confirm) + add form (date input + note input + button).
  Changes refresh the segment table.

## Error handling
- Duplicate/invalid session dates rejected at the API with a message shown
  in the UI.
- Delete requires a `confirm()`.

## Testing
- TDD: db session helpers; `progress_segments` (segment boundaries, baseline,
  multi-account union, champion/queue filters, empty segments, no sessions);
  API CRUD incl. 400/409/404 and progress endpoint shape.
- Screenshot check of the new view with real data.

## Out of scope (YAGNI)
- Editing sessions (delete + re-add covers it), per-session goals, charts
  beyond the segment table, session-time-of-day precision.
