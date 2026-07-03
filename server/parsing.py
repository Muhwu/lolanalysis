"""Map raw match-v5 JSON to database rows."""


def parse_match(match_json: dict):
    info = match_json["info"]
    match_row = {
        "match_id": match_json["metadata"]["matchId"],
        "queue_id": info["queueId"],
        "game_creation_ms": info["gameCreation"],
        "game_duration_s": info["gameDuration"],
        "game_version": info.get("gameVersion", ""),
    }
    participant_rows = []
    for p in info["participants"]:
        participant_rows.append(
            {
                "puuid": p["puuid"],
                "riot_id_name": p.get("riotIdGameName") or p.get("summonerName") or "",
                "champion_name": p["championName"],
                "team_id": p["teamId"],
                "team_position": p.get("teamPosition") or "",
                "win": int(bool(p["win"])),
                "kills": p.get("kills", 0),
                "deaths": p.get("deaths", 0),
                "assists": p.get("assists", 0),
                "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                "gold_earned": p.get("goldEarned", 0),
                "damage_to_champions": p.get("totalDamageDealtToChampions", 0),
            }
        )
    return match_row, participant_rows
