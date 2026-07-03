# lolanalysis — LoL Top Lane Stats

A small local web app that crawls the Riot API match history for any number of
League of Legends accounts into a SQLite database and shows **top-lane matchup
winrates** (plus KDA, CS/min, gold/min, damage/min), filterable by date range,
own champion, queue, and opponent rank — plus a **coaching progress** view that
tracks your improvement between coaching sessions.

## Local setup

Requirements: Python 3.11+ on Linux/macOS/WSL.

```bash
git clone <this repo> && cd lolanalysis
./setup.sh              # creates .venv, installs deps, creates .env from .env.example
```

Then edit `.env`:

```ini
RIOT_API_KEY=RGAPI-...              # from https://developer.riotgames.com
ACCOUNTS=YourName#EUW, Smurf#EUW    # comma-separated Riot IDs, any number
```

And run:

```bash
./crawl.sh --limit 5    # tiny test batch first — confirms the API key works
./crawl.sh              # full incremental crawl (see rate limits below)
./run.sh                # web UI at http://localhost:8321
```

Re-run `./crawl.sh` any time (or click **Update data** in the UI) to pull new
games — the crawler is incremental and safe to interrupt/resume.

The app is EUW-flavoured by default (`euw1` platform, `europe` regional
routing); for other regions change `PLATFORM_HOST`/`REGIONAL_HOST` in
`server/riot_client.py`.

## ⚠ Riot dev keys expire every 24 h

The key in `.env` is a development key. When it expires, crawls fail with a
clear "API key expired" message. Fix: grab a fresh key at
<https://developer.riotgames.com> and update the `RIOT_API_KEY=` line in `.env`
(already-crawled data is unaffected; browsing the UI needs no key).

Dev-key rate limits (20 req/s, 100 req/2 min) are respected automatically, so a
full first crawl of a large history takes roughly 2 minutes per ~100 matches.

## What you get

- **Matchup table** — per opponent champion: games, W–L, winrate bar (50 %
  reference tick), KDA, CS/min, gold/min, damage/min, average game length.
- **Grouped by opponent rank** — same table bucketed by rank tier.
- **Summary tiles** — games, winrate, KDA, CS/min, current solo rank.
- **My champions** — performance per champion you played.
- **Recent games** — last 20 top-lane games with results and matchups.
- **Filters** — period presets (7d/14d/30d/90d/180d/1y/all/custom dates),
  my champion, queue (Ranked Solo / Flex), opponent rank tier, min games.

## Coaching progress view

The **Coaching progress** tab (or `#progress` in the URL) tracks improvement
between coaching sessions: a *Baseline* segment (30 days before your first
session), one segment per gap between sessions, and *Since last session* —
each with games, winrate, KDA, CS/min, gold/min, DMG/min and ▲/▼ deltas
against the previous segment. Add sessions (date + optional title) and delete
them in the same view.

Each segment row expands (▸) to list the individual games played in that
span — date, account, champion, lane opponent and their rank, result, K/D/A,
CS/min, game length.

Each session has a **title** and full **notes in Markdown** — expand a session
(▸) to read the rendered notes, click *edit* to change title/notes, and use
**Export all (.md)** to download every session as one Markdown document
(newest first) for sharing with your coach.

Notes:
- Progress stats combine **all tracked accounts** (coaching applies to you,
  not the account), top lane only, remakes excluded.
- The champion filter defaults to **Gwen**; queue filter available.
- A session's date boundary is midnight UTC — games played on the session day
  count toward the *after* segment.

## Design decisions & known limitations

1. **"Group by rank" = lane opponent's *current* solo-queue rank.** The Riot
   API stores no historical rank, so a Gold opponent who has since climbed to
   Plat counts as Plat. Ranks are cached 7 days (`player_ranks` table). The
   schema stores all participants, so switching to op.gg-style "average lobby
   rank" is possible later (needs ~10× more rank lookups).
2. **Queues crawled: 420 (Ranked Solo) + 440 (Ranked Flex)** by default.
   Add more: `./crawl.sh --queues 420 440 400 490`.
3. **Remakes (< 5 min) are excluded** from all statistics.
4. **Matchup = enemy participant with teamPosition TOP** in games where the
   tracked player is TOP; games where Riot's position data has no enemy TOP
   appear in summary totals but not the matchup table.

## Architecture

```
crawl.py            CLI crawler (also triggered from the UI)
server/
  config.py         .env loading, accounts, paths
  riot_client.py    Riot HTTP client + sliding-window rate limiter
  parsing.py        match-v5 JSON -> db rows
  crawler.py        incremental crawl (watermarks), rank enrichment
  db.py             sqlite schema + helpers (data/lol.sqlite, WAL)
  stats.py          SQL aggregation: matchups, summaries, progress, filters
  app.py            FastAPI JSON API + serves static/
static/             vanilla HTML/JS/CSS frontend (no build step)
tests/              pytest suite (offline, no API key needed)
```

### API examples

```bash
curl 'localhost:8321/api/players'
curl 'localhost:8321/api/stats/matchups?puuid=<PUUID>&range=30d&min_games=2'
curl 'localhost:8321/api/stats/matchups_by_rank?puuid=<PUUID>&champion=Kled'
curl 'localhost:8321/api/stats/summary?puuid=<PUUID>&from=2026-01-01&to=2026-06-30'
curl 'localhost:8321/api/stats/progress?champion=Gwen'
curl 'localhost:8321/api/sessions/export.md'
```

## Development

```bash
.venv/bin/python -m pytest tests/ -q     # run tests (no network or key needed)
```

See `CLAUDE.md` for architecture notes and gotchas, and
`docs/superpowers/` for design specs and implementation plans.
