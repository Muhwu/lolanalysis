"""SQLite storage layer. All timestamps are ms epoch (Riot convention)."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    puuid TEXT PRIMARY KEY,
    game_name TEXT,
    tag_line TEXT,
    is_tracked INTEGER NOT NULL DEFAULT 0,
    solo_tier TEXT,
    solo_division TEXT,
    solo_lp INTEGER,
    rank_fetched_at_ms INTEGER
);

CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    queue_id INTEGER NOT NULL,
    game_creation_ms INTEGER NOT NULL,
    game_duration_s INTEGER NOT NULL,
    game_version TEXT,
    crawled_at_ms INTEGER
);

CREATE TABLE IF NOT EXISTS participants (
    match_id TEXT NOT NULL,
    puuid TEXT NOT NULL,
    riot_id_name TEXT,
    champion_name TEXT NOT NULL,
    team_id INTEGER NOT NULL,
    team_position TEXT,
    win INTEGER NOT NULL,
    kills INTEGER NOT NULL,
    deaths INTEGER NOT NULL,
    assists INTEGER NOT NULL,
    cs INTEGER NOT NULL,
    gold_earned INTEGER NOT NULL,
    damage_to_champions INTEGER NOT NULL,
    PRIMARY KEY (match_id, puuid)
);
CREATE INDEX IF NOT EXISTS idx_participants_puuid ON participants(puuid);

CREATE TABLE IF NOT EXISTS player_ranks (
    puuid TEXT PRIMARY KEY,
    solo_tier TEXT,
    solo_division TEXT,
    solo_lp INTEGER,
    fetched_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS coaching_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_date TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at_ms INTEGER
);

CREATE TABLE IF NOT EXISTS crawl_state (
    puuid TEXT NOT NULL,
    queue_id INTEGER NOT NULL,
    newest_ms INTEGER,
    complete INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (puuid, queue_id)
);
"""


def connect(db_path) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _migrate(conn)
    conn.executescript(SCHEMA)
    return conn


def _migrate(conn):
    """In-place upgrades for schema changes on existing databases."""
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(coaching_sessions)")}
    if not columns:
        return  # table doesn't exist yet; SCHEMA will create the current shape
    if "note" in columns and "title" not in columns:
        conn.execute("ALTER TABLE coaching_sessions RENAME COLUMN note TO title")
    if "notes" not in columns:
        conn.execute("ALTER TABLE coaching_sessions ADD COLUMN notes TEXT NOT NULL DEFAULT ''")
    conn.commit()


def has_match(conn, match_id: str) -> bool:
    return conn.execute("SELECT 1 FROM matches WHERE match_id=?", (match_id,)).fetchone() is not None


def insert_match(conn, match_row: dict, participant_rows: list) -> bool:
    """Insert a match with its participants in one transaction.

    Returns False (no-op) if the match is already stored.
    """
    if has_match(conn, match_row["match_id"]):
        return False
    with conn:
        conn.execute(
            """INSERT INTO matches
               (match_id, queue_id, game_creation_ms, game_duration_s, game_version, crawled_at_ms)
               VALUES (:match_id, :queue_id, :game_creation_ms, :game_duration_s, :game_version,
                       CAST(strftime('%s','now') AS INTEGER) * 1000)""",
            match_row,
        )
        conn.executemany(
            """INSERT INTO participants
               (match_id, puuid, riot_id_name, champion_name, team_id, team_position,
                win, kills, deaths, assists, cs, gold_earned, damage_to_champions)
               VALUES (:match_id, :puuid, :riot_id_name, :champion_name, :team_id, :team_position,
                       :win, :kills, :deaths, :assists, :cs, :gold_earned, :damage_to_champions)""",
            [{**p, "match_id": match_row["match_id"]} for p in participant_rows],
        )
    return True


def upsert_player(conn, puuid, game_name, tag_line, is_tracked=False):
    with conn:
        conn.execute(
            """INSERT INTO players (puuid, game_name, tag_line, is_tracked)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(puuid) DO UPDATE SET
                 game_name=excluded.game_name,
                 tag_line=excluded.tag_line,
                 is_tracked=MAX(players.is_tracked, excluded.is_tracked)""",
            (puuid, game_name, tag_line, int(is_tracked)),
        )


def set_player_rank(conn, puuid, tier, division, lp, fetched_at_ms):
    with conn:
        conn.execute(
            """INSERT INTO player_ranks (puuid, solo_tier, solo_division, solo_lp, fetched_at_ms)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(puuid) DO UPDATE SET
                 solo_tier=excluded.solo_tier,
                 solo_division=excluded.solo_division,
                 solo_lp=excluded.solo_lp,
                 fetched_at_ms=excluded.fetched_at_ms""",
            (puuid, tier, division, lp, fetched_at_ms),
        )


def get_player_rank(conn, puuid):
    return conn.execute("SELECT * FROM player_ranks WHERE puuid=?", (puuid,)).fetchone()


def add_session(conn, session_date, title="", notes=""):
    with conn:
        cursor = conn.execute(
            """INSERT INTO coaching_sessions (session_date, title, notes, created_at_ms)
               VALUES (?, ?, ?, CAST(strftime('%s','now') AS INTEGER) * 1000)""",
            (session_date, title, notes),
        )
    return cursor.lastrowid


def update_session(conn, session_id, title=None, notes=None):
    """Update the given fields (None = leave unchanged). False if id missing."""
    sets, params = [], []
    if title is not None:
        sets.append("title=?")
        params.append(title)
    if notes is not None:
        sets.append("notes=?")
        params.append(notes)
    if not sets:
        return False
    with conn:
        cursor = conn.execute(
            f"UPDATE coaching_sessions SET {', '.join(sets)} WHERE id=?",
            (*params, session_id),
        )
    return cursor.rowcount > 0


def list_sessions(conn):
    return conn.execute(
        "SELECT * FROM coaching_sessions ORDER BY session_date"
    ).fetchall()


def delete_session(conn, session_id):
    with conn:
        cursor = conn.execute("DELETE FROM coaching_sessions WHERE id=?", (session_id,))
    return cursor.rowcount > 0


def get_crawl_watermark(conn, puuid, queue_id):
    row = conn.execute(
        "SELECT newest_ms, complete FROM crawl_state WHERE puuid=? AND queue_id=?",
        (puuid, queue_id),
    ).fetchone()
    if row is None:
        return (None, False)
    return (row["newest_ms"], bool(row["complete"]))


def set_crawl_watermark(conn, puuid, queue_id, newest_ms, complete):
    with conn:
        conn.execute(
            """INSERT INTO crawl_state (puuid, queue_id, newest_ms, complete)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(puuid, queue_id) DO UPDATE SET
                 newest_ms=excluded.newest_ms,
                 complete=excluded.complete""",
            (puuid, queue_id, newest_ms, int(complete)),
        )
