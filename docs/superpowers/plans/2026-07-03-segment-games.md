# Expandable Segment Game Lists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Progress-view segments expand to list that span's games with per-game stats and lane opponents.

**Architecture:** `stats.games_in_range` (raw rows off the existing filtered base, plus `my_puuid` in `_BASE`); lazy `GET /api/stats/games` endpoint with ms bounds; frontend toggle per segment row inserting a colspan sub-row with an inner games table, cached per segment until filters change.

**Tech Stack:** unchanged.

## Global Constraints

- Same stat rules everywhere: top lane only, remakes (<300 s) excluded, combined tracked accounts, opponent = enemy TOP (may be absent → null).
- Segment ends are half-open: caller passes `to_ms - 1` (same convention as `progress_segments`).
- Games ordered newest first. Response rows carry `account` = tracked player's game_name.

---

### Task 1: stats.games_in_range

**Files:** Modify `server/stats.py` (`_BASE` + new fn); test `tests/test_stats.py`.

**Produces:** `games_in_range(conn, puuids, from_ms=None, to_ms=None, champion=None, queues=None) -> list[dict]` with keys `match_id, game_creation_ms, game_duration_s, queue_id, my_puuid, my_champion, opp_champion, rank_tier, win, kills, deaths, assists, cs`.

- [ ] Failing tests: bounds inclusion/exclusion; newest first; two-puuid union with correct `my_puuid`; champion filter; remake excluded; positionless-enemy game listed with `opp_champion` None. FAIL → add `me.puuid AS my_puuid` to `_BASE` select + implement fn (SELECT raw columns FROM filtered base ORDER BY game_creation_ms DESC) → PASS → commit.

### Task 2: /api/stats/games endpoint

**Files:** Modify `server/app.py`; test `tests/test_app.py`.

**Produces:** `GET /api/stats/games?from_ms=&to_ms=&champion=&queue=` → rows from Task 1 + `account` field; 400 for non-integer ms params (FastAPI `int | None` query types handle this → 422; accept 422 as the failure code and assert that).

- [ ] Failing tests: returns fixture games with `account == "PlayerOne"`; from_ms/to_ms filter; champion filter; bad from_ms → 422. FAIL → implement (tracked puuids + puuid→name map, `games_in_range`, `to_ms` passed through verbatim — client sends `to_ms-1`) → PASS → commit.

### Task 3: frontend expandable segments

**Files:** Modify `static/app.js` (toggle button in period cell; games sub-row; fetch+cache in `segmentGamesCache` Map keyed `from:to`, cleared in `loadProgress`; expanded-key Set), `static/style.css` (.games-row inner table, inset background).

- [ ] Implement render: inner table columns Date, Account, Me, Opponent, Opp. rank, Result (W/L pill), K/D/A, CS/min (`(cs*60/game_duration_s).toFixed(1)`), Length; champ icons reused; "No games in this period." empty state.
- [ ] pytest green; screenshot expanded segment with real data → commit.

### Task 4: docs

- [ ] README (expandable segments line) + CLAUDE.md (`games_in_range`, `/api/stats/games`). Commit.
