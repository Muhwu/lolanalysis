# Matchup Rune Pages — Design

**Date:** 2026-07-14
**Status:** Proposal — not implemented

## Purpose

A third **"Runes"** tab in the matchup expansion (next to Overview / Games)
where you author the rune pages you intend to play against a given champion.
This is authored content — "essentially notes" — not an import of the rune
pages from crawled games (explicitly out of scope for now; the schema below
leaves room for imports later).

## The season problem (main design driver)

Riot reworks runes between seasons: keystones and minors get added, removed,
reworked or moved between trees, and the stat-shard rows have changed shape
before. A page authored today may reference runes that no longer exist next
season. Three requirements fall out of this:

1. **Pages must stay readable forever**, even when a rune they reference has
   been removed from current game data.
2. **Every page carries the season it was authored for**; the UI leads with
   current-season pages and clearly marks older ones as outdated.
3. **Rune metadata is a versioned input, not a lookup we depend on** — the
   current-season data file is needed only while *editing*, never for
   *display* of existing pages.

## Data model

```sql
CREATE TABLE IF NOT EXISTS matchup_runes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    opp_champion TEXT NOT NULL,
    my_champion TEXT,              -- optional: page can be pick-specific
    season TEXT NOT NULL,          -- e.g. 'S16'; from runes.json at save time
    title TEXT NOT NULL DEFAULT '',
    page TEXT,                     -- JSON snapshot, see below (NULL = text-only page)
    notes TEXT NOT NULL DEFAULT '',-- Markdown: the "why", tweaks, matchup nuances
    created_at_ms INTEGER,
    updated_at_ms INTEGER
);
```

`page` is a **self-contained JSON snapshot** resolved at save time — this is
the season-proofing. Rather than storing bare rune ids that need a live
lookup, the editor resolves every selection to `{id, name, icon, slot}` and
stores the result:

```json
{
  "primary":   {"style": {"id": 8400, "name": "Resolve", "icon": "..."},
                "keystone": {"id": 8437, "name": "Grasp of the Undying", "icon": "..."},
                "minors": [{...}, {...}, {...}]},
  "secondary": {"style": {"id": 8000, "name": "Precision", "icon": "..."},
                "minors": [{...}, {...}]},
  "shards":    [{"id": 5008, "name": "Adaptive Force"}, {...}, {...}]
}
```

Rendering always reads the snapshot, so a page whose keystone was deleted in
a later season still displays exactly what was authored. No migrations, no
dangling foreign keys into rune metadata, and old seasons of `runes.json`
never need to be kept around.

## Rune metadata: `static/runes.json`

Vendored snapshot of DDragon `runesReforged.json` for the current patch,
maintained exactly like `static/champions.json` (regenerate on new patches;
document the fetch in CLAUDE.md). Two additions DDragon doesn't provide:

- `"season": "S16"` — derived from the patch major version (16.x → S16);
  stamped into new pages and used to decide which pages are "current".
- `"shards": [...]` — the stat-shard rows, embedded manually (they're tiny
  and not in runesReforged.json).

Only ever one file: old pages don't need old metadata thanks to snapshots.
Rune icons render from the DDragon CDN like champion icons (client already
has the version + graceful offline fallback to text).

## API

- `GET  /api/matchups/runes?opp_champion=X` — pages vs X, newest first,
  current season first.
- `POST /api/matchups/runes` — create (validates structure against
  `runes.json`, stamps `season` + snapshot server-side).
- `PUT  /api/matchups/runes/{id}` — edit title/notes always; edit picks only
  while `season` == current (older pages are read-only, see UI).
- `DELETE /api/matchups/runes/{id}`
- `GET  /api/runes/meta` — serves the vendored file to the editor.

Follows the matchup-notes pattern (champion validated against
`CHAMPION_IDS`; global rather than per-account). The hide-my-rank middleware
is irrelevant here (no rank data).

## UI

Third tab in the matchup expansion: **Runes**.

- **List**: one card per page — title, season badge, optional my-champion
  chip, compact page render (keystone icon prominent, then minors row by
  row, shards as small text), Markdown notes underneath. Current-season
  pages listed first; older seasons collapsed under
  *"Previous seasons (n)"* with an amber `S15 — outdated` badge.
- **Editor** (new page / edit current-season page): primary tree → keystone
  → 3 minors (one per row), secondary tree (≠ primary) → 2 minors from
  different rows, 3 stat shards; plus title, optional my-champion, notes.
  Constraints enforced in the picker so invalid pages can't be authored.
- **Old-season pages are read-only** with one action:
  **"Copy to S16"** — duplicates the page into the current season, carrying
  over every pick whose id still exists and flagging vanished slots
  ("*Lethal Tempo no longer exists — pick a replacement*"). Explicit,
  user-driven migration; nothing is ever silently rewritten.

## Phasing

1. **Phase 1 — text-first (one sitting):** table + CRUD + list UI with
   season badges and read-only-when-old, but the "page" is just
   title + Markdown notes (`page` stays NULL). Users write
   "Grasp / Demolish / Second Wind / Overgrowth + PTA…" as text. Delivers
   the *"essentially as notes"* ask with full season handling.
2. **Phase 2 — structured pages:** vendored `runes.json`, the slot editor,
   snapshot rendering, and "Copy to S16". Purely additive (fills the
   `page` column); no schema break, text-only pages keep working.

## Open questions

1. Are per-my-champion pages wanted, or is one set of pages per opponent
   enough? (Schema supports both; UI could hide the field initially.)
2. Are stat shards worth including, or noise?
3. Should the Runes tab also appear for champions you have 0 games against
   (e.g. prep for a champion you haven't met yet)? Currently the matchup
   list only shows champions you've faced — a small "prep page" search box
   on the Matchups view could cover this later.
