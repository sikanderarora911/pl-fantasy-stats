"""Captain and differential recommendations.

Combines each player's form, scoring rate and underlying threat (xGI) with how easy their
upcoming fixture is (from the FDR ticker). Two scores are produced:

* ``captain_score``      — weighted by the *next* gameweek's fixture ease (you captain for one GW).
* ``differential_score`` — weighted by the *average* fixture ease over the horizon (you hold a
  differential for a run), and only meaningful for low-owned players.

Both use the same underlying-quality blend so they stay comparable:
    quality = 0.6·form + 0.4·points_per_game + 0.5·xGI
and a fixture-ease multiplier centred on 1.0 for an average (FDR 3) fixture:
    ease = (6 − FDR) / 3   → FDR1≈1.67 (easy) … FDR3=1.0 … FDR5≈0.33 (hard)
Blank gameweeks (no fixture) get ease 0, dropping non-players out of the rankings.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from .fixtures import build_ticker


def _quality(df: pd.DataFrame) -> pd.Series:
    return 0.6 * df["form"] + 0.4 * df["points_per_game"] + 0.5 * df["expected_goal_involvements"]


def build_recommendations(
    players_df: pd.DataFrame,
    fixtures: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    start_gw: int,
    horizon: int = 3,
) -> pd.DataFrame:
    """Return the players DataFrame enriched with next fixture, FDRs and the two scores."""
    display_df, difficulty_df, avg = build_ticker(fixtures, teams, start_gw, horizon)
    next_col = difficulty_df.columns[0]

    df = players_df.copy()
    df["next_opp"] = df["team"].map(display_df[next_col])
    df["next_fdr"] = df["team"].map(difficulty_df[next_col])
    df["avg_fdr"] = df["team"].map(avg)

    quality = _quality(df)
    ease_next = ((6 - df["next_fdr"]) / 3.0).fillna(0.0)
    ease_avg = ((6 - df["avg_fdr"]) / 3.0).fillna(0.0)

    df["captain_score"] = (quality * ease_next).round(2)
    df["differential_score"] = (quality * ease_avg).round(2)
    return df


def top_captains(rec_df: pd.DataFrame, n: int = 10, min_minutes: int = 60) -> pd.DataFrame:
    """Best captain options for the next gameweek: available, playing, favourable fixture."""
    d = rec_df[
        (rec_df["availability"] == "Available")
        & (rec_df["minutes"] >= min_minutes)
        & (rec_df["captain_score"] > 0)
    ]
    return d.sort_values("captain_score", ascending=False).head(n)


def top_differentials(
    rec_df: pd.DataFrame, max_ownership: float = 10.0, n: int = 10, min_minutes: int = 60
) -> pd.DataFrame:
    """In-form, low-owned players with a good fixture run — rank-gaining differentials."""
    d = rec_df[
        (rec_df["availability"] == "Available")
        & (rec_df["minutes"] >= min_minutes)
        & (rec_df["selected_by_percent"] <= max_ownership)
        & (rec_df["differential_score"] > 0)
    ]
    return d.sort_values("differential_score", ascending=False).head(n)
