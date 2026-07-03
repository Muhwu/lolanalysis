"""Riot API client with a sliding-window rate limiter.

Dev-key limits: 20 requests / 1 s and 100 requests / 2 min. Keys expire
every 24 h; a 403 raises ApiKeyExpiredError with a hint to refresh.
"""
import time
from collections import deque
from urllib.parse import quote

import httpx

REGIONAL_HOST = "https://europe.api.riotgames.com"  # account-v1, match-v5
PLATFORM_HOST = "https://euw1.api.riotgames.com"    # league-v4

DEV_KEY_LIMITS = [(20, 1.0), (100, 120.0)]


class RiotApiError(Exception):
    pass


class ApiKeyExpiredError(RiotApiError):
    pass


class NotFoundError(RiotApiError):
    pass


class RateLimiter:
    """Sliding-window limiter over one or more (max_requests, window_s) limits."""

    def __init__(self, limits=DEV_KEY_LIMITS, clock=time.monotonic, sleep=time.sleep):
        self.limits = limits
        self.clock = clock
        self.sleep = sleep
        self._history = [deque() for _ in limits]

    def acquire(self):
        while True:
            now = self.clock()
            wait = 0.0
            for (max_req, window), history in zip(self.limits, self._history):
                while history and history[0] <= now - window:
                    history.popleft()
                if len(history) >= max_req:
                    wait = max(wait, history[0] + window - now)
            if wait <= 0:
                break
            self.sleep(wait)
        now = self.clock()
        for history in self._history:
            history.append(now)


class RiotClient:
    MAX_429_RETRIES = 5
    MAX_5XX_RETRIES = 3

    def __init__(self, api_key, limiter=None, transport=None):
        self.limiter = limiter if limiter is not None else RateLimiter()
        self._http = httpx.Client(
            headers={"X-Riot-Token": api_key},
            timeout=15.0,
            transport=transport,
        )

    def _get(self, url, params=None):
        attempts_429 = 0
        attempts_5xx = 0
        while True:
            self.limiter.acquire()
            response = self._http.get(url, params=params)
            if response.status_code == 200:
                return response.json()
            if response.status_code in (401, 403):
                raise ApiKeyExpiredError(
                    "Riot API returned 403 — the dev key has likely expired. "
                    "Refresh it at https://developer.riotgames.com and update .env"
                )
            if response.status_code == 404:
                raise NotFoundError(url)
            if response.status_code == 429:
                attempts_429 += 1
                if attempts_429 > self.MAX_429_RETRIES:
                    raise RiotApiError(f"Rate limited too many times: {url}")
                retry_after = int(response.headers.get("Retry-After", "10"))
                self.limiter.sleep(retry_after)
                continue
            if response.status_code >= 500:
                attempts_5xx += 1
                if attempts_5xx > self.MAX_5XX_RETRIES:
                    raise RiotApiError(f"Server error {response.status_code}: {url}")
                self.limiter.sleep(2 * attempts_5xx)
                continue
            raise RiotApiError(f"Unexpected status {response.status_code}: {url}")

    def get_account(self, game_name, tag_line):
        url = (
            f"{REGIONAL_HOST}/riot/account/v1/accounts/by-riot-id/"
            f"{quote(game_name)}/{quote(tag_line)}"
        )
        return self._get(url)

    def get_match_ids(self, puuid, queue=None, start=0, count=100, start_time=None, end_time=None):
        params = {"start": start, "count": count}
        if queue is not None:
            params["queue"] = queue
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time
        url = f"{REGIONAL_HOST}/lol/match/v5/matches/by-puuid/{puuid}/ids"
        return self._get(url, params=params)

    def get_match(self, match_id):
        return self._get(f"{REGIONAL_HOST}/lol/match/v5/matches/{match_id}")

    def get_league_entries(self, puuid):
        return self._get(f"{PLATFORM_HOST}/lol/league/v4/entries/by-puuid/{puuid}")
