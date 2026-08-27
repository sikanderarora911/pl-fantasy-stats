"""Unit tests for squad mapping and transfer suggestions — pure logic, no network."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.myteam import build_squad, suggest_transfers  # noqa: E402


def _rec() -> pd.DataFrame:
    # id 1 owned weak DEF; id 2 a strong affordable DEF upgrade; id 3 too expensive; id 4 owned OK MID.
    return pd.DataFrame(
        [
            {"id": 1, "player": "WeakDef", "team": "AAA", "position": "DEF", "price": 4.5,
             "availability": "Available", "minutes": 90, "next_opp": "X (H)",
             "differential_score": 2.0},
            {"id": 2, "player": "GoodDef", "team": "BBB", "position": "DEF", "price": 5.0,
             "availability": "Available", "minutes": 90, "next_opp": "Y (A)",
             "differential_score": 9.0},
            {"id": 3, "player": "PriceyDef", "team": "CCC", "position": "DEF", "price": 8.0,
             "availability": "Available", "minutes": 90, "next_opp": "Z (H)",
             "differential_score": 12.0},
            {"id": 4, "player": "MidOwned", "team": "AAA", "position": "MID", "price": 7.0,
             "availability": "Available", "minutes": 90, "next_opp": "X (H)",
             "differential_score": 6.0},
        ]
    )


def _picks(ids):
    return [{"element": i, "position": pos, "is_captain": False,
             "is_vice_captain": False} for pos, i in enumerate(ids, start=1)]


def test_build_squad_maps_owned_players():
    squad = build_squad(_rec(), _picks([1, 4]))
    assert set(squad["id"]) == {1, 4}
    assert list(squad["squad_pos"]) == [1, 2]  # ordering preserved


def test_suggest_upgrade_within_budget():
    # Own WeakDef (4.5), bank 0.6 -> budget 5.1 covers GoodDef (5.0) but not PriceyDef (8.0).
    squad = build_squad(_rec(), _picks([1, 4]))
    sug = suggest_transfers(_rec(), squad, bank=0.6, n=5, min_minutes=60)
    row = sug[sug["out"] == "WeakDef"].iloc[0]
    assert row["in"] == "GoodDef"                # affordable upgrade chosen, not the pricey one
    assert row["improvement"] == 7.0             # 9.0 - 2.0
    assert row["cost"] == 0.5                     # 5.0 - 4.5


def test_no_suggestion_when_budget_too_low():
    # Bank 0.0 -> budget 4.5, cannot afford GoodDef (5.0); WeakDef has no upgrade.
    squad = build_squad(_rec(), _picks([1]))
    sug = suggest_transfers(_rec(), squad, bank=0.0, n=5, min_minutes=60)
    assert sug.empty


def test_owned_players_excluded_as_targets():
    # If GoodDef is already owned, it can't be suggested as an incoming transfer.
    squad = build_squad(_rec(), _picks([1, 2]))
    sug = suggest_transfers(_rec(), squad, bank=5.0, n=5, min_minutes=60)
    assert "GoodDef" not in list(sug["in"])
