"""Unit tests for build_players_df — mapping and derived metrics, no network."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.transform import build_players_df  # noqa: E402


def _fixture() -> dict:
    return {
        "teams": [
            {"id": 1, "name": "Arsenal", "short_name": "ARS"},
            {"id": 2, "name": "Chelsea", "short_name": "CHE"},
        ],
        "element_types": [
            {"id": 1, "singular_name_short": "GKP"},
            {"id": 3, "singular_name_short": "MID"},
        ],
        "elements": [
            {
                "id": 1,
                "web_name": "Raya", "team": 1, "element_type": 1, "now_cost": 60,
                "total_points": 30, "form": "6.0", "points_per_game": "5.0",
                "selected_by_percent": "38.2", "minutes": 900, "goals_scored": 0,
                "assists": 0, "clean_sheets": 4, "bonus": 3, "expected_goals": "0.00",
                "expected_goals_per_90": "0.00",
                "expected_assists": "0.10", "expected_goal_involvements": "0.10",
                "ict_index": "12.3", "status": "a", "chance_of_playing_next_round": None,
                "news": "", "news_added": None,
                "cost_change_start": 2, "transfers_in_event": 200000, "transfers_out_event": 20000,
            },
            {
                "id": 2,
                "web_name": "Palmer", "team": 2, "element_type": 3, "now_cost": 105,
                "total_points": 42, "form": "7.5", "points_per_game": "7.0",
                "selected_by_percent": "55.1", "minutes": 810, "goals_scored": 5,
                "assists": 3, "clean_sheets": 2, "bonus": 6, "expected_goals": "3.20",
                "expected_goals_per_90": "0.36",
                "expected_assists": "2.10", "expected_goal_involvements": "5.30",
                "ict_index": "88.0", "status": "d", "chance_of_playing_next_round": 75,
                "news": "Knock - 75% chance of playing", "news_added": "2026-08-25T09:30:00Z",
                "cost_change_start": -1, "transfers_in_event": 10000, "transfers_out_event": 150000,
            },
        ],
    }


def test_labels_and_positions():
    df = build_players_df(_fixture())
    raya = df.set_index("player").loc["Raya"]
    palmer = df.set_index("player").loc["Palmer"]
    assert raya["team"] == "ARS"
    assert raya["position"] == "GKP"
    assert palmer["team"] == "CHE"
    assert palmer["position"] == "MID"


def test_price_and_value():
    df = build_players_df(_fixture()).set_index("player")
    # now_cost 60 -> £6.0m; 30 pts / 6.0 = 5.0 value
    assert df.loc["Raya", "price"] == 6.0
    assert df.loc["Raya", "value"] == 5.0
    # now_cost 105 -> £10.5m; 42 / 10.5 = 4.0
    assert df.loc["Palmer", "price"] == 10.5
    assert df.loc["Palmer", "value"] == 4.0


def test_string_float_coercion():
    df = build_players_df(_fixture()).set_index("player")
    assert isinstance(df.loc["Palmer", "form"].item(), float)
    assert df.loc["Palmer", "form"] == 7.5
    assert df.loc["Palmer", "selected_by_percent"] == 55.1
    assert df.loc["Palmer", "expected_goal_involvements"] == 5.30


def test_availability_mapping():
    df = build_players_df(_fixture()).set_index("player")
    assert df.loc["Raya", "availability"] == "Available"
    assert df.loc["Palmer", "availability"] == "Doubtful"


def test_news_fields():
    import pandas as pd

    df = build_players_df(_fixture()).set_index("player")
    # No news -> empty string, NaT timestamp.
    assert df.loc["Raya", "news"] == ""
    assert pd.isna(df.loc["Raya", "news_added"])
    # Has news -> text preserved and timestamp parsed.
    assert "Knock" in df.loc["Palmer", "news"]
    assert df.loc["Palmer", "news_added"] == pd.Timestamp("2026-08-25T09:30:00Z")


def test_price_change_and_prediction():
    df = build_players_df(_fixture()).set_index("player")
    # cost_change_start 2 -> +£0.2m; net transfers +180k -> Rising
    assert df.loc["Raya", "price_change"] == 0.2
    assert df.loc["Raya", "net_transfers_event"] == 180000
    assert df.loc["Raya", "expected_change"] == "▲ Rising"
    # cost_change_start -1 -> -£0.1m; net transfers -140k -> Falling
    assert df.loc["Palmer", "price_change"] == -0.1
    assert df.loc["Palmer", "net_transfers_event"] == -140000
    assert df.loc["Palmer", "expected_change"] == "▼ Falling"
