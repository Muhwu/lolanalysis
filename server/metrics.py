"""Registry of coaching metrics extracted from match-v5 payloads.

The registry drives the participant_metrics DDL, payload parsing, SQL
aggregation and the metadata the frontend uses for labels/grouping/deltas.

agg kinds:
  avg      — AVG(col)
  pct01    — 100 * AVG(col)          (0..1 ratios and 0/1 flags)
  per_min  — 60 * SUM(col) / SUM(duration of rows where col present)
  pct_time — 100 * SUM(col) / SUM(duration of rows where col present)

direction: 1 = higher is better, -1 = lower is better, 0 = neutral.
"""


def _metric(key, label, group, field, source="challenges", agg="avg",
            direction=1, decimals=1, suffix=""):
    return {"key": key, "label": label, "group": group, "field": field,
            "source": source, "agg": agg, "direction": direction,
            "decimals": decimals, "suffix": suffix}


METRICS = [
    # --- Laning ---
    _metric("cs_at_10", "CS @ 10 min", "Laning", "laneMinionsFirst10Minutes"),
    _metric("lane_adv_early", "Ahead in lane @ ~7 min", "Laning",
            "earlyLaningPhaseGoldExpAdvantage", agg="pct01", decimals=0, suffix="%"),
    _metric("lane_adv_late", "Ahead in lane @ ~14 min", "Laning",
            "laningPhaseGoldExpAdvantage", agg="pct01", decimals=0, suffix="%"),
    _metric("max_cs_lead", "Max CS lead on opponent", "Laning",
            "maxCsAdvantageOnLaneOpponent"),
    _metric("max_level_lead", "Max level lead on opponent", "Laning",
            "maxLevelLeadLaneOpponent", decimals=2),
    _metric("plates", "Turret plates taken", "Laning", "turretPlatesTaken", decimals=2),
    _metric("solo_kills", "Solo kills", "Laning", "soloKills", decimals=2),
    _metric("early_takedowns", "Takedowns before ~15 min", "Laning",
            "takedownsFirstXMinutes", decimals=2),
    # --- Damage & fighting ---
    _metric("team_dmg_pct", "Share of team's damage", "Damage & fighting",
            "teamDamagePercentage", agg="pct01", suffix="%"),
    _metric("kill_participation", "Kill participation", "Damage & fighting",
            "killParticipation", agg="pct01", decimals=0, suffix="%"),
    _metric("dmg_taken_team_pct", "Share of team's damage taken", "Damage & fighting",
            "damageTakenOnTeamPercentage", agg="pct01", direction=0, suffix="%"),
    _metric("skillshots_dodged", "Skillshots dodged", "Damage & fighting",
            "skillshotsDodged"),
    _metric("self_mitigated", "Damage self-mitigated / min", "Damage & fighting",
            "damageSelfMitigated", source="participant", agg="per_min", decimals=0),
    # --- Objectives & map ---
    _metric("turret_takedowns", "Turret takedowns", "Objectives & map",
            "turretTakedowns", decimals=2),
    _metric("turret_damage", "Damage to turrets", "Objectives & map",
            "damageDealtToTurrets", source="participant", decimals=0),
    _metric("tp_takedowns", "Teleport takedowns", "Objectives & map",
            "teleportTakedowns", decimals=2),
    _metric("herald_takedowns", "Rift Herald takedowns", "Objectives & map",
            "riftHeraldTakedowns", decimals=2),
    # --- Vision & survival ---
    _metric("vision_per_min", "Vision score / min", "Vision & survival",
            "visionScorePerMinute", decimals=2),
    _metric("vision_adv", "Vision advantage vs opponent", "Vision & survival",
            "visionScoreAdvantageLaneOpponent", decimals=2),
    _metric("control_wards", "Control wards placed", "Vision & survival",
            "controlWardsPlaced", decimals=2),
    _metric("ward_takedowns", "Ward takedowns", "Vision & survival",
            "wardTakedowns", decimals=2),
    _metric("time_dead", "Time dead (% of game)", "Vision & survival",
            "totalTimeSpentDead", source="participant", agg="pct_time",
            direction=-1, suffix="%"),
]

GROUPS = ["Laning", "Damage & fighting", "Objectives & map", "Vision & survival"]


def metric_keys():
    return [m["key"] for m in METRICS]


def parse_metrics(match_json, puuid):
    """Extract raw metric values for one participant. None if puuid absent."""
    participant = next(
        (p for p in match_json["info"]["participants"] if p["puuid"] == puuid), None)
    if participant is None:
        return None
    challenges = participant.get("challenges") or {}
    values = {"has_challenges": int(bool(challenges))}
    for m in METRICS:
        if m["source"] == "participant":
            values[m["key"]] = participant.get(m["field"])
        else:
            values[m["key"]] = challenges.get(m["field"])
    return values
