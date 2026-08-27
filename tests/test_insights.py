"""Unit tests for captain / differential recommendations — pure logic, no network."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.insights import build_recommendations, top_captains, top_differentials  # noqa: E402

TEAMS = [
    {"id": 1, "short_name": "ARS"},
    {"id": 2, "short_name": "CHE"},
]

# GW2: ARS(h, easy fdr 2) v CHE(a, hard fdr 5).
FIXTURES = [
    {"event": 2, "team_h": 1, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 5},
]


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # In-form ARS player, easy fixture, low owned -> strong captain + differential.
            {"player": "Saka", "team": "ARS", "position": "MID", "form": 8.0,
             "points_per_game": 6.0, "expected_goal_involvements": 1.0,
             "selected_by_percent": 8.0, "minutes": 90, "availability": "Available"},
            # In-form CHE player but hard fixture -> lower captain score.
            {"player": "Palmer", "team": "CHE", "position": "MID", "form": 8.0,
             "points_per_game": 6.0, "expected_goal_involvements": 1.0,
             "selected_by_percent": 55.0, "minutes": 90, "availability": "Available"},
            # Injured player -> excluded.
            {"player": "Injured", "team": "ARS", "position": "FWD", "form": 9.0,
             "points_per_game": 7.0, "expected_goal_involvements": 2.0,
             "selected_by_percent": 4.0, "minutes": 90, "availability": "Injured"},
        ]
    )


def test_fixture_ease_favours_easy_opponent():
    rec = build_recommendations(_players(), FIXTURES, TEAMS, start_gw=2, horizon=1).set_index("player")
    # Same quality, but Saka (FDR 2) should outscore Palmer (FDR 5).
    assert rec.loc["Saka", "captain_score"] > rec.loc["Palmer", "captain_score"]
    assert rec.loc["Saka", "next_opp"] == "CHE (H)"
    assert rec.loc["Saka", "next_fdr"] == 2


def test_top_captains_excludes_unavailable_and_ranks():
    rec = build_recommendations(_players(), FIXTURES, TEAMS, start_gw=2, horizon=1)
    caps = top_captains(rec, n=10, min_minutes=60)
    names = list(caps["player"])
    assert "Injured" not in names          # unavailable excluded
    assert names[0] == "Saka"              # best fixture ranks first


def test_differentials_respect_ownership_cap():
    rec = build_recommendations(_players(), FIXTURES, TEAMS, start_gw=2, horizon=1)
    diffs = top_differentials(rec, max_ownership=10.0, n=10, min_minutes=60)
    names = list(diffs["player"])
    assert "Saka" in names        # 8% owned, under cap
    assert "Palmer" not in names  # 55% owned, over cap
