# Coaching Session Titles, Markdown Notes & Export — Design

**Date:** 2026-07-03
**Status:** Approved with assumption (user AFK on export question; single-file
Markdown export chosen — the recommended option)

## Purpose

Coaching sessions grow from a date + short label into editable records with a
**title** and **full notes written in Markdown**, viewable expanded in the UI
and exportable as one Markdown document (e.g. to share with the coach).

## Requirements

1. Rename the existing `note` field to `title` (it already behaves as one);
   add a `notes` TEXT field for long-form Markdown.
   Existing databases migrate automatically on connect
   (`ALTER TABLE ... RENAME COLUMN`, `ADD COLUMN`).
2. Sessions are editable: title and notes (date stays fixed; delete + re-add
   covers corrections).
3. In the Coaching progress view, each session row expands to show the notes
   rendered from Markdown. Rendering uses a **vendored `marked.min.js`**
   (committed into `static/vendor/`, no runtime CDN dependency).
4. Export: one Markdown document of all sessions, newest first — heading per
   session (`## <date> — <title>`) followed by its raw notes. Served by the
   API; Download button in the UI.
5. Segment labels/notes in the progress table keep using the title.

## Components

### DB (`server/db.py`)
- Schema (new installs): `coaching_sessions(id, session_date UNIQUE, title
  TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '', created_at_ms)`.
- `_migrate(conn)` run in `connect()`: if `coaching_sessions.note` exists →
  rename to `title`; if `notes` column missing → add it.
- `add_session(conn, session_date, title="", notes="") -> int`
- `update_session(conn, session_id, title=None, notes=None) -> bool`
  (None = leave unchanged; returns False when id missing)
- `list_sessions(conn)` unchanged (now returns title + notes).

### Stats (`server/stats.py`)
- `progress_segments` reads `title` instead of `note` from session dicts
  (returned segment key stays `note` to avoid touching the rendering
  contract — it carries the title text).

### API (`server/app.py`)
- `POST /api/sessions` body `{date, title?, notes?}` (was `note`).
- `PATCH /api/sessions/{id}` body `{title?, notes?}` → 404 if missing.
- `GET /api/sessions/export.md` → `text/markdown; charset=utf-8` with
  `Content-Disposition: attachment; filename=coaching-sessions.md`.
  Document: `# Coaching sessions` + per session (newest first)
  `## <session_date> — <title or "Session">` + blank line + notes (raw).
  **Route must be declared before `/api/sessions/{id}`-style matching is
  irrelevant (different methods) but before the static mount as usual.**
- `GET /api/sessions` unchanged shape (now includes `title`, `notes`).

### Frontend (`static/`)
- `static/vendor/marked.min.js` vendored, loaded via `<script>` before app.js.
- Session list becomes cards: header row = date, title, buttons
  **expand/collapse**, **edit**, **delete**; expanded body shows
  `marked.parse(notes)` inside a `.md-body` container (styled: headings,
  lists, code, blockquote — modest CSS).
- Edit mode swaps the card body for title input + notes textarea +
  Save/Cancel; Save → PATCH → reload sessions (and progress table, since
  titles appear there).
- Add form: date + title (placeholder updated); notes are added via Edit
  after creation.
- **Export** button (link to `/api/sessions/export.md`) next to the
  "Coaching sessions" heading.
- If `marked` failed to load (file missing), expanded notes fall back to
  escaped plain text in `<pre>`.

## Error handling
- PATCH with neither title nor notes → 400. Unknown id → 404.
- Export with zero sessions → valid document with just the H1.

## Testing
- db: migration from old schema (build a db with `note` column, connect,
  verify rename + `notes` added, data preserved); update_session round trip.
- API: POST with title/notes, PATCH round trip + 404/400, export content
  (headings order, markdown body, content-type).
- Frontend: screenshot check (expanded markdown notes render).

## Out of scope (YAGNI)
- Per-session export files, editing session dates, markdown preview while
  typing, HTML sanitization (single-user local app, own content).
