# Expandable Segment Game Lists — Design

**Date:** 2026-07-03
**Status:** Approved with assumptions (presented and proceeded; user actively
iterating but AFK on prior question rounds)

## Purpose

In the Coaching progress view, each time segment (Baseline, between-sessions,
Since-last) expands to list the individual games played in that span with
per-game stats and lane opponents.

## Components

### Stats (`server/stats.py`)
- `_BASE` additionally selects `me.puuid AS my_puuid` (needed to attribute
  games to an account in combined views).
- `games_in_range(conn, puuids, from_ms=None, to_ms=None, champion=None,
  queues=None) -> list[dict]`: one row per top-lane game of any tracked puuid
  in `[from_ms, to_ms]` (caller passes `to_ms-1` for half-open segment ends,
  same as `progress_segments`); fields: `match_id, game_creation_ms,
  game_duration_s, queue_id, my_puuid, my_champion, opp_champion, rank_tier,
  win, kills, deaths, assists, cs`; newest first; remakes excluded;
  `require_opponent=False` (games without an enemy TOP still listed,
  `opp_champion` null).

### API (`server/app.py`)
- `GET /api/stats/games?from_ms=&to_ms=&champion=&queue=` — integer ms bounds
  (optional), filters as elsewhere; runs over all tracked puuids; response
  rows include `account` (the tracked player's game_name) resolved from the
  players table.

### Frontend (`static/`)
- Segment rows get the same ▸/▾ toggle pattern as session cards (button in
  the Period cell). Expanding inserts a full-width sub-row
  (`<tr class="games-row"><td colspan="8">` containing an inner table:
  Date, Account, Me, Opponent, Opp. rank, Result (W/L pill), K/D/A, CS/min,
  Length. CS/min computed client-side (`cs * 60 / game_duration_s`).
- Games fetched on first expand per segment (`from_ms`/`to_ms` of the
  segment + current champion/queue filters), cached in a Map keyed by
  `from_ms:to_ms`; cache cleared whenever loadProgress re-renders (filters
  or data changed). Expanded-state persists across re-renders in the same
  Map-holding module state.
- Empty span → "No games in this period."

## Error handling
- Invalid from_ms/to_ms (non-integer) → 400.

## Testing
- stats: rows within bounds only; newest first; multi-account union +
  my_puuid attribution; champion filter; remake excluded; no-opponent game
  listed with null opp_champion.
- API: shape incl. account name; bounds filtering; 400 on bad from_ms.
- Screenshot check of an expanded segment.

## Out of scope (YAGNI)
- Pagination (segments are week-sized), per-game deep links to match pages,
  overview-table expansion.
