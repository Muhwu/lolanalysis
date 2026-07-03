import pytest

from server import db


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "test.sqlite")
    yield c
    c.close()


def make_participant(puuid="p1", **overrides):
    row = {
        "puuid": puuid,
        "riot_id_name": "Player" + puuid,
        "champion_name": "Garen",
        "team_id": 100,
        "team_position": "TOP",
        "win": 1,
        "kills": 5,
        "deaths": 2,
        "assists": 7,
        "cs": 200,
        "gold_earned": 12000,
        "damage_to_champions": 18000,
    }
    row.update(overrides)
    return row


def make_match(match_id="EUW1_1", **overrides):
    row = {
        "match_id": match_id,
        "queue_id": 420,
        "game_creation_ms": 1_700_000_000_000,
        "game_duration_s": 1800,
        "game_version": "14.1.1",
    }
    row.update(overrides)
    return row


def test_connect_creates_schema_and_parent_dir(tmp_path):
    c = db.connect(tmp_path / "sub" / "x.sqlite")
    tables = {
        r["name"]
        for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"players", "matches", "participants", "player_ranks", "crawl_state"} <= tables
    c.close()


def test_insert_match_stores_match_and_participants(conn):
    inserted = db.insert_match(conn, make_match(), [make_participant("a"), make_participant("b")])
    assert inserted is True
    assert db.has_match(conn, "EUW1_1")
    n = conn.execute("SELECT COUNT(*) AS n FROM participants").fetchone()["n"]
    assert n == 2


def test_insert_match_is_idempotent(conn):
    db.insert_match(conn, make_match(), [make_participant("a")])
    inserted = db.insert_match(conn, make_match(), [make_participant("a")])
    assert inserted is False
    n = conn.execute("SELECT COUNT(*) AS n FROM participants").fetchone()["n"]
    assert n == 1


def test_upsert_player_updates_name_keeps_tracked(conn):
    db.upsert_player(conn, "pu1", "Old", "EUW", is_tracked=True)
    db.upsert_player(conn, "pu1", "New", "EUW", is_tracked=False)
    row = conn.execute("SELECT * FROM players WHERE puuid='pu1'").fetchone()
    assert row["game_name"] == "New"
    assert row["is_tracked"] == 1  # once tracked, stays tracked


def test_player_rank_round_trip(conn):
    assert db.get_player_rank(conn, "pu1") is None
    db.set_player_rank(conn, "pu1", "GOLD", "II", 54, fetched_at_ms=1000)
    row = db.get_player_rank(conn, "pu1")
    assert (row["solo_tier"], row["solo_division"], row["solo_lp"]) == ("GOLD", "II", 54)
    db.set_player_rank(conn, "pu1", "PLATINUM", "IV", 1, fetched_at_ms=2000)
    assert db.get_player_rank(conn, "pu1")["solo_tier"] == "PLATINUM"


def test_unranked_player_rank_stored_as_null_tier(conn):
    db.set_player_rank(conn, "pu1", None, None, None, fetched_at_ms=1000)
    row = db.get_player_rank(conn, "pu1")
    assert row["solo_tier"] is None
    assert row["fetched_at_ms"] == 1000


def test_add_and_list_sessions_sorted_by_date(conn):
    db.add_session(conn, "2026-07-05", "split pushing")
    db.add_session(conn, "2026-06-28", "wave management", notes="# Focus\n- freeze near tower")
    sessions = db.list_sessions(conn)
    assert [s["session_date"] for s in sessions] == ["2026-06-28", "2026-07-05"]
    assert sessions[0]["title"] == "wave management"
    assert sessions[0]["notes"].startswith("# Focus")


def test_add_session_title_and_notes_default_empty(conn):
    session_id = db.add_session(conn, "2026-06-28")
    assert isinstance(session_id, int)
    row = db.list_sessions(conn)[0]
    assert row["title"] == ""
    assert row["notes"] == ""


def test_update_session_partial_updates(conn):
    session_id = db.add_session(conn, "2026-06-28", "old title", notes="old notes")
    assert db.update_session(conn, session_id, title="new title") is True
    row = db.list_sessions(conn)[0]
    assert row["title"] == "new title"
    assert row["notes"] == "old notes"
    assert db.update_session(conn, session_id, notes="new notes") is True
    row = db.list_sessions(conn)[0]
    assert row["title"] == "new title"
    assert row["notes"] == "new notes"


def test_update_session_missing_id_returns_false(conn):
    assert db.update_session(conn, 999, title="x") is False


def test_legacy_note_column_migrates_to_title_and_notes(tmp_path):
    import sqlite3
    path = tmp_path / "legacy.sqlite"
    legacy = sqlite3.connect(path)
    legacy.execute(
        """CREATE TABLE coaching_sessions (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               session_date TEXT NOT NULL UNIQUE,
               note TEXT NOT NULL DEFAULT '',
               created_at_ms INTEGER)"""
    )
    legacy.execute(
        "INSERT INTO coaching_sessions (session_date, note, created_at_ms) VALUES (?,?,?)",
        ("2026-06-28", "first coaching session", 123),
    )
    legacy.commit()
    legacy.close()
    conn = db.connect(path)
    row = db.list_sessions(conn)[0]
    assert row["title"] == "first coaching session"
    assert row["notes"] == ""
    assert row["session_date"] == "2026-06-28"
    conn.close()


def test_add_session_duplicate_date_raises(conn):
    import sqlite3
    db.add_session(conn, "2026-06-28")
    with pytest.raises(sqlite3.IntegrityError):
        db.add_session(conn, "2026-06-28")


def test_delete_session(conn):
    session_id = db.add_session(conn, "2026-06-28")
    assert db.delete_session(conn, session_id) is True
    assert db.list_sessions(conn) == []
    assert db.delete_session(conn, session_id) is False


def test_crawl_watermark_round_trip(conn):
    assert db.get_crawl_watermark(conn, "pu1", 420) == (None, False)
    db.set_crawl_watermark(conn, "pu1", 420, newest_ms=123, complete=False)
    assert db.get_crawl_watermark(conn, "pu1", 420) == (123, False)
    db.set_crawl_watermark(conn, "pu1", 420, newest_ms=456, complete=True)
    assert db.get_crawl_watermark(conn, "pu1", 420) == (456, True)
    # different queue independent
    assert db.get_crawl_watermark(conn, "pu1", 440) == (None, False)
