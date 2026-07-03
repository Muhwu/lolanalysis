import json

import httpx
import pytest

from server.riot_client import (
    ApiKeyExpiredError,
    NotFoundError,
    RateLimiter,
    RiotClient,
)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


# ---------- RateLimiter ----------

def test_limiter_allows_burst_within_limit():
    clock = FakeClock()
    rl = RateLimiter(limits=[(20, 1.0)], clock=clock.time, sleep=clock.sleep)
    for _ in range(20):
        rl.acquire()
    assert clock.slept == []


def test_limiter_sleeps_when_short_window_exhausted():
    clock = FakeClock()
    rl = RateLimiter(limits=[(20, 1.0)], clock=clock.time, sleep=clock.sleep)
    for _ in range(20):
        rl.acquire()
    rl.acquire()  # 21st within the same second must wait
    assert len(clock.slept) == 1
    assert clock.slept[0] > 0


def test_limiter_enforces_long_window():
    clock = FakeClock()
    rl = RateLimiter(limits=[(20, 1.0), (100, 120.0)], clock=clock.time, sleep=clock.sleep)
    for i in range(100):
        rl.acquire()
        clock.now = (i + 1) * 1.0  # spread out: never trips 20/1s
    total_slept_before = sum(clock.slept)
    rl.acquire()  # 101st within 120s window
    assert sum(clock.slept) > total_slept_before


def test_limiter_window_expires():
    clock = FakeClock()
    rl = RateLimiter(limits=[(2, 1.0)], clock=clock.time, sleep=clock.sleep)
    rl.acquire()
    rl.acquire()
    clock.now = 2.0
    rl.acquire()  # old window expired, no sleep
    assert clock.slept == []


# ---------- RiotClient ----------

def make_client(handler, limiter=None):
    transport = httpx.MockTransport(handler)
    return RiotClient("RGAPI-test", limiter=limiter, transport=transport)


def test_get_account_hits_europe_route_with_token_header():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["token"] = request.headers.get("X-Riot-Token")
        return httpx.Response(200, json={"puuid": "abc", "gameName": "PlayerOne", "tagLine": "EUW"})

    client = make_client(handler)
    account = client.get_account("PlayerOne", "EUW")
    assert account["puuid"] == "abc"
    assert seen["url"] == "https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/PlayerOne/EUW"
    assert seen["token"] == "RGAPI-test"


def test_get_account_encodes_unicode_names():
    seen = {}

    def handler(request):
        seen["path"] = request.url.raw_path.decode()
        return httpx.Response(200, json={"puuid": "x"})

    make_client(handler).get_account("Ünï cödé", "EUW")
    assert "%C3%9Cn%C3%AF%20c%C3%B6d%C3%A9" in seen["path"]


def test_get_match_ids_passes_params():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=["EUW1_1", "EUW1_2"])

    ids = make_client(handler).get_match_ids("abc", queue=420, start=0, count=100, start_time=1700000000)
    assert ids == ["EUW1_1", "EUW1_2"]
    assert "matches/by-puuid/abc/ids" in seen["url"]
    assert "queue=420" in seen["url"]
    assert "count=100" in seen["url"]
    assert "startTime=1700000000" in seen["url"]


def test_get_league_entries_uses_platform_host():
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        return httpx.Response(200, json=[{"queueType": "RANKED_SOLO_5x5", "tier": "GOLD"}])

    entries = make_client(handler).get_league_entries("abc")
    assert entries[0]["tier"] == "GOLD"
    assert seen["url"].startswith("https://euw1.api.riotgames.com/lol/league/v4/entries/by-puuid/abc")


def test_403_raises_api_key_expired():
    def handler(request):
        return httpx.Response(403, json={"status": {"message": "Forbidden"}})

    with pytest.raises(ApiKeyExpiredError):
        make_client(handler).get_account("PlayerOne", "EUW")


def test_404_raises_not_found():
    def handler(request):
        return httpx.Response(404, json={"status": {"message": "not found"}})

    with pytest.raises(NotFoundError):
        make_client(handler).get_account("Nobody", "EUW")


def test_429_sleeps_retry_after_then_retries():
    calls = {"n": 0}
    clock = FakeClock()
    limiter = RateLimiter(limits=[(1000, 1.0)], clock=clock.time, sleep=clock.sleep)

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={})
        return httpx.Response(200, json={"puuid": "abc"})

    client = make_client(handler, limiter=limiter)
    account = client.get_account("PlayerOne", "EUW")
    assert account["puuid"] == "abc"
    assert calls["n"] == 2
    assert 3 in clock.slept


def test_5xx_retries_then_succeeds():
    calls = {"n": 0}
    clock = FakeClock()
    limiter = RateLimiter(limits=[(1000, 1.0)], clock=clock.time, sleep=clock.sleep)

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={})
        return httpx.Response(200, json={"puuid": "abc"})

    account = make_client(handler, limiter=limiter).get_account("PlayerOne", "EUW")
    assert account["puuid"] == "abc"
    assert calls["n"] == 3
