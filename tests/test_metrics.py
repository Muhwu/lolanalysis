from server.metrics import METRICS, metric_keys, parse_metrics


def sample_match(puuid="p1", challenges=True):
    participant = {
        "puuid": puuid,
        "damageSelfMitigated": 25320,
        "damageDealtToTurrets": 8353,
        "totalTimeSpentDead": 259,
    }
    if challenges:
        participant["challenges"] = {
            "laneMinionsFirst10Minutes": 87,
            "earlyLaningPhaseGoldExpAdvantage": 1,
            "laningPhaseGoldExpAdvantage": 0,
            "maxCsAdvantageOnLaneOpponent": 95,
            "maxLevelLeadLaneOpponent": 2,
            "turretPlatesTaken": 10,
            "soloKills": 2,
            "takedownsFirstXMinutes": 3,
            "teamDamagePercentage": 0.187,
            "killParticipation": 0.242,
            "damageTakenOnTeamPercentage": 0.161,
            "skillshotsDodged": 63,
            "turretTakedowns": 2,
            "teleportTakedowns": 1,
            "riftHeraldTakedowns": 0,
            "visionScorePerMinute": 0.674,
            "visionScoreAdvantageLaneOpponent": -0.439,
            "controlWardsPlaced": 0,
            "wardTakedowns": 2,
        }
    return {"info": {"participants": [participant]}}


def test_registry_shape():
    assert len(METRICS) >= 20
    groups = {m["group"] for m in METRICS}
    assert groups == {"Laning", "Damage & fighting", "Objectives & map", "Vision & survival"}
    for m in METRICS:
        assert m["agg"] in ("avg", "pct01", "per_min", "pct_time")
        assert m["direction"] in (1, -1, 0)
    assert len(metric_keys()) == len(set(metric_keys()))


def test_parse_metrics_extracts_all_fields():
    values = parse_metrics(sample_match(), "p1")
    assert values["has_challenges"] == 1
    assert values["cs_at_10"] == 87
    assert values["lane_adv_early"] == 1
    assert values["lane_adv_late"] == 0
    assert values["team_dmg_pct"] == 0.187
    assert values["self_mitigated"] == 25320   # participant-level source
    assert values["turret_damage"] == 8353
    assert values["time_dead"] == 259
    assert values["vision_adv"] == -0.439
    assert set(values) == set(metric_keys()) | {"has_challenges"}


def test_parse_metrics_without_challenges_gives_nulls_for_challenge_fields():
    values = parse_metrics(sample_match(challenges=False), "p1")
    assert values["has_challenges"] == 0
    assert values["cs_at_10"] is None
    assert values["self_mitigated"] == 25320  # participant fields still present


def test_parse_metrics_unknown_puuid_returns_none():
    assert parse_metrics(sample_match(), "other") is None
