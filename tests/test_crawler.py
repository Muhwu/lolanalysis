import pytest

from server import db
from server.crawler import Crawler

TRACKED_PUUID = "tracked-1"


def match_json(match_id, creation_ms, queue_id=420, tracked_pos="TOP",
               opp_puuid="opp-1", opp_pos="TOP", duration_s=1800):
    """Minimal-but-valid match-v5 JSON with 10 participants."""
    positions = ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
    participants = []
    for i, pos in enumerate(positions):
        puuid = TRACKED_PUUID if pos == tracked_pos else f"ally-{i}"
        participants.append({
            "puuid": puuid, "riotIdGameName": f"A{i}", "championName": "Garen",
            "teamId": 100, "teamPosition": pos, "win": True,
            "kills": 1, "deaths": 1, "assists": 1,
            "totalMinionsKilled": 100, "neutralMinionsKilled": 0,
            "goldEarned": 10000, "totalDamageDealtToChampions": 10000,
        })
    for i, pos in enumerate(positions):
        puuid = opp_puuid if pos == opp_pos else f"enemy-{i}"
        participants.append({
            "puuid": puuid, "riotIdGameName": f"E{i}", "championName": "Darius",
            "teamId": 200, "teamPosition": pos, "win": False,
            "kills": 1, "deaths": 1, "assists": 1,
            "totalMinionsKilled": 100, "neutralMinionsKilled": 0,
            "goldEarned": 10000, "totalDamageDealtToChampions": 10000,
        })
    return {
        "metadata": {"matchId": match_id, "participants": [p["puuid"] for p in participants]},
        "info": {
            "gameCreation": creation_ms, "gameDuration": duration_s,
            "gameVersion": "14.1.1", "queueId": queue_id,
            "participants": participants,
        },
    }


class FakeClient:
    def __init__(self, matches):
        # matches: list of match JSON, any order; served newest-first like Riot
        self.matches = {m["metadata"]["matchId"]: m for m in matches}
        self.detail_calls = 0
        self.league_calls = []
        self.ranks = {}  # puuid -> list of league entries

    def get_account(self, game_name, tag_line):
        return {"puuid": TRACKED_PUUID, "gameName": game_name, "tagLine": tag_line}

    def get_match_ids(self, puuid, queue=None, start=0, count=100, start_time=None, end_time=None):
        ms = [
            m for m in self.matches.values()
            if m["info"]["queueId"] == queue
            and (start_time is None or m["info"]["gameCreation"] >= start_time * 1000)
        ]
        ms.sort(key=lambda m: -m["info"]["gameCreation"])
        ids = [m["metadata"]["matchId"] for m in ms]
        return ids[start:start + count]

    def get_match(self, match_id):
        self.detail_calls += 1
        return self.matches[match_id]

    def get_league_entries(self, puuid):
        self.league_calls.append(puuid)
        return self.ranks.get(puuid, [])


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.sqlite")
    yield c
    c.close()


def make_crawler(client, conn, now_ms=1_800_000_000_000):
    return Crawler(client, conn, now_ms=lambda: now_ms)


def test_crawl_inserts_matches_and_participants(conn):
    client = FakeClient([
        match_json("EUW1_1", 1_700_000_000_000),
        match_json("EUW1_2", 1_700_000_100_000),
    ])
    result = make_crawler(client, conn).crawl_player("PlayerOne", "EUW", queues=(420,))
    assert result["new_matches"] == 2
    assert conn.execute("SELECT COUNT(*) c FROM matches").fetchone()["c"] == 2
    assert conn.execute("SELECT COUNT(*) c FROM participants").fetchone()["c"] == 20
    player = conn.execute("SELECT * FROM players WHERE puuid=?", (TRACKED_PUUID,)).fetchone()
    assert player["is_tracked"] == 1
    assert player["game_name"] == "PlayerOne"


def test_second_crawl_is_incremental_and_fetches_no_details(conn):
    client = FakeClient([
        match_json("EUW1_1", 1_700_000_000_000),
        match_json("EUW1_2", 1_700_000_100_000),
    ])
    crawler = make_crawler(client, conn)
    crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    client.detail_calls = 0
    result = crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    assert client.detail_calls == 0
    assert result["new_matches"] == 0
    # a match played after the first crawl gets picked up
    client.matches["EUW1_3"] = match_json("EUW1_3", 1_700_000_200_000)
    result = crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    assert result["new_matches"] == 1


def test_limit_caps_new_detail_fetches_and_leaves_incomplete(conn):
    client = FakeClient([
        match_json(f"EUW1_{i}", 1_700_000_000_000 + i * 1000) for i in range(5)
    ])
    crawler = make_crawler(client, conn)
    result = crawler.crawl_player("PlayerOne", "EUW", queues=(420,), limit=2)
    assert result["new_matches"] == 2
    _, complete = db.get_crawl_watermark(conn, TRACKED_PUUID, 420)
    assert complete is False
    # next run without limit picks up the remaining 3
    result = crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    assert result["new_matches"] == 3
    _, complete = db.get_crawl_watermark(conn, TRACKED_PUUID, 420)
    assert complete is True


def test_enrich_ranks_fetches_top_lane_opponents(conn):
    client = FakeClient([
        match_json("EUW1_1", 1_700_000_000_000, opp_puuid="opp-A"),
        match_json("EUW1_2", 1_700_000_100_000, opp_puuid="opp-B"),
    ])
    client.ranks["opp-A"] = [
        {"queueType": "RANKED_FLEX_SR", "tier": "SILVER", "rank": "I", "leaguePoints": 10},
        {"queueType": "RANKED_SOLO_5x5", "tier": "GOLD", "rank": "III", "leaguePoints": 42},
    ]
    crawler = make_crawler(client, conn)
    crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    n = crawler.enrich_ranks()
    assert n == 2
    assert sorted(client.league_calls) == ["opp-A", "opp-B"]
    row = db.get_player_rank(conn, "opp-A")
    assert (row["solo_tier"], row["solo_division"], row["solo_lp"]) == ("GOLD", "III", 42)
    # opp-B had no solo entry -> stored as unranked
    assert db.get_player_rank(conn, "opp-B")["solo_tier"] is None


def test_enrich_ranks_skips_fresh_entries(conn):
    client = FakeClient([match_json("EUW1_1", 1_700_000_000_000, opp_puuid="opp-A")])
    now = 1_800_000_000_000
    crawler = make_crawler(client, conn, now_ms=now)
    crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    db.set_player_rank(conn, "opp-A", "GOLD", "I", 1, fetched_at_ms=now - 1000)  # fresh
    assert crawler.enrich_ranks() == 0
    db.set_player_rank(conn, "opp-A", "GOLD", "I", 1, fetched_at_ms=now - 8 * 86_400_000)  # stale
    assert crawler.enrich_ranks() == 1


def test_refresh_tracked_ranks_updates_players_table(conn):
    client = FakeClient([match_json("EUW1_1", 1_700_000_000_000)])
    client.ranks[TRACKED_PUUID] = [
        {"queueType": "RANKED_SOLO_5x5", "tier": "DIAMOND", "rank": "IV", "leaguePoints": 12},
    ]
    crawler = make_crawler(client, conn)
    crawler.crawl_player("PlayerOne", "EUW", queues=(420,))
    crawler.refresh_tracked_ranks()
    row = conn.execute("SELECT * FROM players WHERE puuid=?", (TRACKED_PUUID,)).fetchone()
    assert (row["solo_tier"], row["solo_division"], row["solo_lp"]) == ("DIAMOND", "IV", 12)
