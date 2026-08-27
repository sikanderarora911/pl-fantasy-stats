"""Unit tests for the fixture-difficulty ticker — pure logic, no network."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.fixtures import build_ticker, color_for  # noqa: E402

TEAMS = [
    {"id": 1, "short_name": "ARS"},
    {"id": 2, "short_name": "CHE"},
    {"id": 3, "short_name": "LIV"},
]

# GW1: ARS(h) v CHE(a); GW2: LIV(h) v ARS(a); (LIV blank in GW1, CHE blank in GW2)
FIXTURES = [
    {"event": 1, "team_h": 1, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 4},
    {"event": 2, "team_h": 3, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 5},
]


def test_home_away_and_difficulty():
    disp, diff, avg = build_ticker(FIXTURES, TEAMS, start_gw=1, horizon=2)
    # ARS: GW1 home vs CHE (fdr 2), GW2 away at LIV (fdr 5)
    assert disp.loc["ARS", "GW1"] == "CHE (H)"
    assert disp.loc["ARS", "GW2"] == "LIV (A)"
    assert diff.loc["ARS", "GW1"] == 2
    assert diff.loc["ARS", "GW2"] == 5
    # CHE: GW1 away at ARS (fdr 4), GW2 blank
    assert disp.loc["CHE", "GW1"] == "ARS (A)"
    assert disp.loc["CHE", "GW2"] == "–"
    assert pd.isna(diff.loc["CHE", "GW2"])


def test_average_difficulty_and_order():
    _, _, avg = build_ticker(FIXTURES, TEAMS, start_gw=1, horizon=2)
    # ARS avg = (2 + 5) / 2 = 3.5
    assert avg.loc["ARS"] == 3.5
    # CHE has one fixture (fdr 4) -> avg 4.0 over the non-blank gameweek
    assert avg.loc["CHE"] == 4.0
    # LIV has one fixture (fdr 3) -> avg 3.0
    assert avg.loc["LIV"] == 3.0
    # Easiest-first ordering puts LIV before CHE.
    order = list(avg.sort_values().index)
    assert order.index("LIV") < order.index("CHE")


def test_color_for():
    assert color_for(1)[0] != color_for(5)[0]      # distinct easy vs hard
    assert color_for(2.6) == color_for(3)          # fractional rounds to nearest bucket
    assert color_for(float("nan"))[0] == "#20232a"  # blank gameweek neutral
