# LoL Top-Lane Stats App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Local web app that crawls Riot match history for PlayerOne#EUW and PlayerTwo#EUW into SQLite and shows filterable top-lane matchup winrates.

**Architecture:** Python package `server/` (riot client + rate limiter, sqlite layer, crawler, stats SQL, FastAPI app) + vanilla-JS `static/` frontend + `crawl.py` CLI. Crawler is incremental/idempotent; stats are computed by SQL at request time.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, httpx, stdlib sqlite3, pytest.

## Global Constraints

- Accounts: PlayerOne#EUW, PlayerTwo#EUW; platform `euw1`, regional routing `europe`.
- Default queues crawled: 420 (Ranked Solo), 440 (Ranked Flex).
- Rate limits (dev key): 20 req/1 s AND 100 req/2 min; obey 429 Retry-After; 403 → raise `ApiKeyExpiredError`.
- `RIOT_API_KEY` from `.env` in project root (fallback: copy from `../lolmeta/.env` in setup.sh).
- Matches with `game_duration_s < 300` (remakes) are excluded from all stats.
- DB file: `data/lol.sqlite` (gitignored). All timestamps stored as ms epoch (Riot convention).
- Rank grouping = lane opponent's current solo rank (`player_ranks`, TTL 7 days).

---

### Task 1: Scaffolding + config

**Files:** Create `server/__init__.py`, `server/config.py`, `tests/test_config.py`, `requirements.txt`, `.gitignore`, `setup.sh`, `run.sh`.

**Produces:** `config.load_config(root: Path|None) -> Config` with fields `riot_api_key: str`, `db_path: Path`, `accounts: list[tuple[str,str]]` (from `ACCOUNTS` env or default `[("PlayerOne","EUW"),("PlayerTwo","EUW")]`). Reads `.env` (simple KEY=VALUE parser, no dependency).

- [ ] Write failing tests: parse `.env`, default accounts, missing key → `ConfigError`.
- [ ] Run pytest → FAIL. Implement `config.py`. Run → PASS.
- [ ] Write `requirements.txt` (fastapi, uvicorn, httpx, pytest), `.gitignore` (data/, .venv/, .env, __pycache__), `setup.sh` (create .venv, pip install, copy RIOT_API_KEY from ../lolmeta/.env if no .env), `run.sh` (exec .venv uvicorn server.app:app --port 8321).
- [ ] Create venv, install deps, full pytest PASS. Commit.

### Task 2: DB layer

**Files:** Create `server/db.py`, `tests/test_db.py`.

**Produces:**
- `connect(db_path) -> sqlite3.Connection` (row_factory=Row, creates schema, WAL).
- `upsert_player(conn, puuid, game_name, tag_line, is_tracked)`
- `insert_match(conn, match_row: dict, participant_rows: list[dict]) -> bool` (False if already present; single transaction)
- `has_match(conn, match_id) -> bool`
- `set_player_rank(conn, puuid, tier, division, lp, fetched_at_ms)` / `get_player_rank(conn, puuid) -> Row|None`
- `get_crawl_watermark(conn, puuid, queue_id) -> (newest_ms|None, complete: bool)` / `set_crawl_watermark(...)`

Schema exactly as in the spec (players, matches, participants, player_ranks, crawl_state).

- [ ] Failing tests: schema creates, insert_match idempotent, rank round-trip, watermark round-trip. Implement. PASS. Commit.

### Task 3: Rate limiter + Riot client

**Files:** Create `server/riot_client.py`, `tests/test_riot_client.py`.

**Produces:**
- `RateLimiter(limits=[(20,1.0),(100,120.0)], clock=time.monotonic, sleep=time.sleep)` with `.acquire()` — sliding-window; test with fake clock (no real sleeping).
- `RiotClient(api_key, limiter=None, transport=None)` (httpx.Client with optional mock transport) methods:
  - `get_account(game_name, tag_line) -> dict` (puuid, gameName, tagLine)
  - `get_match_ids(puuid, queue, start, count, start_time=None, end_time=None) -> list[str]`
  - `get_match(match_id) -> dict`
  - `get_league_entries(puuid) -> list[dict]` (euw1 host)
- Errors: 403 → `ApiKeyExpiredError`; 429 → sleep Retry-After then retry (max 5); 404 on account → `NotFoundError`; other 5xx → retry 3× with backoff.

- [ ] Failing tests: limiter window math with fake clock; client URL/paths/header via `httpx.MockTransport`; 429 retry; 403 raises. Implement. PASS. Commit.

### Task 4: Match parsing

**Files:** Create `server/parsing.py`, `tests/test_parsing.py`, `tests/fixtures/match_sample.json` (hand-built realistic match-v5 JSON, 10 participants).

**Produces:** `parse_match(match_json) -> (match_row: dict, participant_rows: list[dict])` mapping:
`metadata.matchId→match_id`, `info.queueId→queue_id`, `info.gameCreation→game_creation_ms`, `info.gameDuration→game_duration_s`, `info.gameVersion→game_version`; participant: `puuid, riotIdGameName→riot_id_name, championName→champion_name, teamId→team_id, teamPosition→team_position, win (int), kills, deaths, assists, totalMinionsKilled+neutralMinionsKilled→cs, goldEarned→gold_earned, totalDamageDealtToChampions→damage_to_champions`.

- [ ] Failing tests with fixture: field mapping, cs sum, 10 rows. Implement. PASS. Commit.

### Task 5: Crawler

**Files:** Create `server/crawler.py`, `tests/test_crawler.py` (FakeClient).

**Produces:**
- `Crawler(client, conn, status_cb=None)`
- `.crawl_player(game_name, tag_line, queues=(420,440), limit=None) -> dict` (counts) — resolve puuid, upsert tracked player; per queue: page match ids 100 at a time using `start_time = newest watermark - 1h` for incremental; fetch+parse+insert unseen matches; update watermarks; `limit` caps *new* match fetches (for test batches).
- `.enrich_ranks(max_players=None) -> int` — find puuids of TOP-lane opponents of tracked players lacking fresh rank (7-day TTL), call `get_league_entries`, store solo-queue entry (tier NULL if unranked).
- `.refresh_tracked_ranks()` — update tracked players' own solo rank in `players`.
- Module-level crawl status dict updated via `status_cb` (used by API later).

- [ ] Failing tests: crawl inserts matches; second crawl fetches 0 details (idempotent + watermark); limit respected; enrich_ranks stores opponent ranks and respects TTL. Implement. PASS. Commit.

### Task 6: Stats queries

**Files:** Create `server/stats.py`, `tests/test_stats.py` (fixture db builder helper `make_match(...)` in test file).

**Produces (all take `conn`, `puuid`, and filters `from_ms=None, to_ms=None, champion=None, queues=None, rank_tier=None, min_games=1`):**
- `matchups(...) -> list[dict]`: one row per opponent champion (tracked player TOP vs enemy TOP): `opp_champion, games, wins, winrate, kills, deaths, assists, kda, cs_min, gold_min, dmg_min, avg_duration_s` — sorted games desc.
- `matchups_by_rank(...) -> list[dict]`: same + `rank_tier` bucket (opponent's rank from `player_ranks`, 'UNKNOWN' if absent).
- `summary(...) -> dict`: games, wins, winrate, kda, plus `by_champion: list` (own champion breakdown, TOP only) and `recent: list` (last 20 top-lane games w/ result, matchup, kda, date).
- `filter_options(conn, puuid) -> dict`: champions played (TOP), queues present, rank tiers present.
- Remakes (<300 s) excluded everywhere; opponent = enemy-team participant with `team_position='TOP'` (skip match if none).

- [ ] Failing tests (TDD, most important module): winrate math; date-range filter; own-champion filter; queue filter; rank bucket incl. UNKNOWN; remake exclusion; no-opponent skip; min_games. Implement. PASS. Commit.

### Task 7: FastAPI app

**Files:** Create `server/app.py`, `tests/test_app.py` (TestClient, temp db via dependency override / env `LOL_DB_PATH`).

**Produces:** endpoints from spec — `/api/players`, `/api/stats/matchups`, `/api/stats/matchups_by_rank`, `/api/stats/summary`, `/api/filters`, `POST /api/crawl` (background thread, one at a time), `/api/crawl/status`; serves `static/` at `/`. Date filters accepted as `from`/`to` ISO dates or `range=7d|14d|30d|90d|180d|365d|all`.

- [ ] Failing tests: players endpoint, matchups endpoint with filters, range parsing, crawl status shape, 409 if crawl already running. Implement. PASS. Commit.

### Task 8: Frontend

**Files:** Create `static/index.html`, `static/app.js`, `static/style.css`.

Single page: account tabs, filter bar (date-range preset buttons + custom dates, my-champion select, queue select, rank-tier select, min-games), summary cards (games/WR/KDA + own rank), matchup table (opponent champ icon via Data Dragon CDN, games, W-L, winrate bar, KDA, CS/min, gold/min, dmg/min), optional rank-grouped view toggle, per-own-champion table, recent games list, "Update data" button wired to `/api/crawl` + status polling. Follow dataviz skill for the winrate bars/colors (load it before writing this task's code).

- [ ] Build page; manual check via `run.sh` + fetch of `/` and API endpoints (curl) since no browser tests. Commit.

### Task 9: CLI + live smoke test

**Files:** Create `crawl.py` (argparse: `--limit N`, `--queues 420 440`, `--accounts "Name#TAG" ...`, `--skip-ranks`; prints progress; runs crawl then enrich_ranks then refresh_tracked_ranks).

- [ ] `python crawl.py --limit 5` live against Riot API → verify rows in sqlite (both accounts, matches, participants, ranks). Fix issues. Commit.

### Task 10: Docs + full crawl

**Files:** Create `README.md`, `CLAUDE.md`.

- [ ] README: what it is, setup (key expiry warning!), usage, design decisions/assumptions made autonomously (rank grouping semantics), architecture map, API examples.
- [ ] CLAUDE.md: commands (setup/run/test/crawl), architecture pointers, rate-limit and dev-key gotchas, schema summary, testing conventions.
- [ ] Commit. Kick off full crawl in background; verify stats render with real data (curl API + check counts). Report results.
