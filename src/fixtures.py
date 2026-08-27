"""Build a fixture-difficulty ticker from the FPL fixtures + teams data.

The ticker is the classic FDR grid: one row per team, one column per upcoming gameweek, each
cell showing the opponent and venue (H/A) coloured by FPL's difficulty rating (1=easiest …
5=hardest). Blank gameweeks show "–"; double gameweeks join both fixtures with "+".
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# FDR rating -> (background, text) colours, following the familiar green→red scale.
FDR_COLORS = {
    1: ("#1a9850", "#ffffff"),
    2: ("#66bd63", "#ffffff"),
    3: ("#8f8f8f", "#ffffff"),
    4: ("#f46d43", "#ffffff"),
    5: ("#d73027", "#ffffff"),
}
_BLANK = ("#20232a", "#8a8a8a")  # neutral for blank gameweeks


def build_ticker(
    fixtures: list[dict[str, Any]],
    teams: list[dict[str, Any]],
    start_gw: int,
    horizon: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """Return (display_df, difficulty_df, avg_difficulty).

    * ``display_df``   — team × gameweek grid of "OPP (H)" strings (index = team short name).
    * ``difficulty_df``— same shape, mean FDR per cell (NaN for blank gameweeks); used for colour.
    * ``avg_difficulty`` — per-team mean FDR across the horizon, for "easiest first" sorting.
    """
    team_short = {t["id"]: t["short_name"] for t in teams}
    gws = list(range(start_gw, start_gw + horizon))
    gw_labels = [f"GW{g}" for g in gws]

    display: dict[str, list[str]] = {}
    difficulty: dict[str, list[float]] = {}

    for tid, short in team_short.items():
        cells, diffs = [], []
        for gw in gws:
            legs = []  # (opponent_short, venue, fdr) for each fixture this team has in this GW
            for fx in fixtures:
                if fx.get("event") != gw:
                    continue
                if fx["team_h"] == tid:
                    legs.append((team_short.get(fx["team_a"], "?"), "H", fx["team_h_difficulty"]))
                elif fx["team_a"] == tid:
                    legs.append((team_short.get(fx["team_h"], "?"), "A", fx["team_a_difficulty"]))
            if not legs:
                cells.append("–")
                diffs.append(float("nan"))
            else:
                cells.append(" + ".join(f"{opp} ({venue})" for opp, venue, _ in legs))
                diffs.append(sum(fdr for *_, fdr in legs) / len(legs))
        display[short] = cells
        difficulty[short] = diffs

    display_df = pd.DataFrame.from_dict(display, orient="index", columns=gw_labels)
    difficulty_df = pd.DataFrame.from_dict(difficulty, orient="index", columns=gw_labels)
    avg_difficulty = difficulty_df.mean(axis=1, skipna=True).round(2)

    display_df.index.name = "Team"
    difficulty_df.index.name = "Team"
    return display_df, difficulty_df, avg_difficulty


def color_for(fdr: float) -> tuple[str, str]:
    """Background/text colour for a (possibly fractional) FDR value; neutral for NaN."""
    if pd.isna(fdr):
        return _BLANK
    return FDR_COLORS[int(round(fdr))]
