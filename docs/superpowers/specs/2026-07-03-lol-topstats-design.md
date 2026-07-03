# LoL Top-Lane Stats App — Design

**Date:** 2026-07-03
**Status:** Approved with assumptions (user AFK during clarification; assumptions flagged in README)

## Purpose

A local web app that crawls Riot API match history for two accounts
(**PlayerOne#EUW**, **PlayerTwo#EUW**), stores it in SQLite, and shows
top-lane matchup winrates and related statistics with filters.

## Requirements

- Crawl full ranked match history (Solo 420 + Flex 440 by default) for both accounts.
- Show winrate per top-lane matchup (opponent champion), plus supporting stats:
  games, W/L, KDA, CS/min, gold/min, damage/min, avg game length.
- Filters: account, date range (1w / 2w / 1m / 3m / 6m / 1y / all / custom),
  champion played, queue, minimum games.
- Group/bucket matchups by lane opponent's **current** solo-queue rank tier
  (Riot API has no historical rank; documented limitation). Show own current
  rank per account.
- SQLite storage, incremental resumable crawler, rate-limit aware
  (dev key: 20 req/1s, 100 req/2min; expires every 24 h).
- Startup scripts, README, CLAUDE.md, tests (TDD where plausible).

## Decisions & assumptions (made autonomously)

1. **Rank grouping = lane opponent's current rank.** One cached
   `league-v4 entries by-puuid` call per opposing player. Schema keeps a
   `player_ranks` table so avg-lobby-rank could be added later.
2. **Queues**: 420 + 440 crawled by default; `--queues` flag for more.
3. **Stack**: Python 3.12, FastAPI + uvicorn, stdlib `sqlite3`, vanilla
   HTML/CSS/JS frontend (no build step), pytest.
4. **API key**: read from `.env` in project root; setup script copies
   `RIOT_API_KEY` from `../lolmeta/.env` if missing. 403 responses surface
   a "dev key expired — refresh at developer.riotgames.com" message.

## Architecture

```
lolanalysis/
  server/
    riot_client.py   # Riot HTTP client + token-bucket rate limiter
    db.py            # schema, connection, upsert helpers
    crawler.py       # incremental crawl + rank enrichment
    stats.py         # SQL aggregation for matchup/summary stats
    app.py           # FastAPI app: JSON API + static files
  static/            # index.html, app.js, style.css
  tests/             # pytest: stats, rate limiter, crawler parsing, db
  crawl.py           # CLI entry: python crawl.py [--limit N] [--queues ...]
  run.sh, setup.sh
  data/lol.sqlite    # created at runtime (gitignored)
```

### Data flow

1. `crawl.py` → resolves Riot IDs → puuid (account-v1, europe routing).
2. Pages `match-v5` match-id lists per queue (newest first, `startTime`
   watermark for incremental runs); fetches details for unseen ids.
3. Stores match + all 10 participants (champion, teamPosition, win, KDA,
   CS, gold, damage, etc.).
4. Enrichment: for matches where a tracked player played TOP, fetch lane
   opponent's current rank (cached in `player_ranks`, TTL 7 days).
5. FastAPI reads SQLite; frontend fetches `/api/stats/matchups` etc. with
   filter query params.

### Schema (SQLite)

- `players(puuid PK, game_name, tag_line, region, is_tracked, solo_tier, solo_division, solo_lp, rank_fetched_at)`
- `matches(match_id PK, queue_id, game_creation_ms, game_duration_s, game_version, crawled_at)`
- `participants(match_id, puuid, riot_id_name, champion_name, team_id, team_position, win, kills, deaths, assists, cs, gold_earned, damage_to_champions, PRIMARY KEY(match_id, puuid))`
- `player_ranks(puuid PK, solo_tier, solo_division, solo_lp, fetched_at)`
- `crawl_state(puuid, queue_id, newest_ms, oldest_ms, complete)` — resume watermarks

### API endpoints

- `GET /api/players` — tracked accounts + current ranks + match counts
- `GET /api/stats/matchups?puuid&from&to&champion&queue&rank_tier&min_games`
- `GET /api/stats/summary?...` — overall WR, games, per-champion breakdown
- `GET /api/filters?puuid` — available champions/queues/rank tiers for dropdowns
- `POST /api/crawl` + `GET /api/crawl/status` — trigger/watch incremental crawl from the UI

### Error handling

- 429 → sleep `Retry-After`, retry; proactive token-bucket limiter stays under limits.
- 403 → abort with "API key expired" message (surfaced in UI crawl status).
- Crawler is idempotent: `INSERT OR IGNORE`, watermark resume; safe to kill anytime.

### Testing

- TDD for `stats.py` (fixture SQLite with synthetic matches: date ranges,
  champion filters, rank buckets, remakes).
- Unit tests for rate limiter (fake clock), match-JSON → row parsing,
  matchup-opponent pairing (edge: no TOP opponent / position mismatch).
- Live smoke test: `python crawl.py --limit 5` before full crawl.

## Out of scope (YAGNI)

- Historical rank reconstruction, timeline data (CS@10 etc.), other lanes'
  matchup views (data is stored for all lanes; UI focuses on TOP), auth,
  deployment.
