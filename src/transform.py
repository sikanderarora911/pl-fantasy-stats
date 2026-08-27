"""Turn the raw FPL ``bootstrap-static`` payload into a tidy players DataFrame.

The heavy lifting is joining human-readable team/position labels onto each player and
computing the derived metrics that drive fantasy decisions (price in £m, points-per-£m
value, availability). FPL delivers several numeric-looking fields (``form``,
``points_per_game``, ``selected_by_percent``, the expected-goals family, ``ict_index``)
as **strings**, so those are explicitly coerced to float.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

# FPL ``status`` code -> human label.
STATUS_LABELS = {
    "a": "Available",
    "d": "Doubtful",
    "i": "Injured",
    "s": "Suspended",
    "u": "Unavailable",
    "n": "Not eligible",
}

# Fields FPL returns as strings that we want as floats.
_STRING_FLOAT_FIELDS = [
    "form",
    "points_per_game",
    "selected_by_percent",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "ict_index",
]

# Stable, display-ordered column set.
DISPLAY_COLUMNS = [
    "player",
    "team",
    "position",
    "price",
    "total_points",
    "form",
    "points_per_game",
    "value",
    "minutes",
    "goals_scored",
    "assists",
    "clean_sheets",
    "bonus",
    "expected_goals",
    "expected_assists",
    "expected_goal_involvements",
    "ict_index",
    "selected_by_percent",
    "price_change",
    "net_transfers_event",
    "expected_change",
    "availability",
    "chance_of_playing_next_round",
    "news",
    "news_added",
]

# Net-transfer thresholds (this gameweek) for the momentum-based price-change estimate.
# These are heuristic: real FPL price moves depend on a proprietary daily target, but net
# transfers are the honest public proxy for direction.
_RISE_THRESHOLD = 75_000
_FALL_THRESHOLD = -75_000


def _predict_price_move(net_transfers: int) -> str:
    """Momentum-based estimate of the next price move from this week's net transfers."""
    if net_transfers >= _RISE_THRESHOLD:
        return "▲ Rising"
    if net_transfers <= _FALL_THRESHOLD:
        return "▼ Falling"
    return "– Stable"


def build_players_df(bootstrap: dict[str, Any]) -> pd.DataFrame:
    """Flatten ``bootstrap['elements']`` into a tidy, decision-ready DataFrame."""
    teams = {t["id"]: t for t in bootstrap["teams"]}
    positions = {p["id"]: p["singular_name_short"] for p in bootstrap["element_types"]}

    df = pd.DataFrame(bootstrap["elements"])

    # Human-readable labels.
    df["player"] = df["web_name"]
    df["team"] = df["team"].map(lambda tid: teams.get(tid, {}).get("short_name", "?"))
    df["position"] = df["element_type"].map(positions).fillna("?")

    # String -> float coercion for the numeric-as-text fields.
    for col in _STRING_FLOAT_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    # Derived metrics.
    df["price"] = df["now_cost"] / 10.0  # now_cost is in tenths of a £m
    df["value"] = (df["total_points"] / df["price"]).round(1)  # points per £m

    # Price movement: realised change since season start, plus a momentum-based estimate
    # of the next move driven by this gameweek's net transfers.
    df["price_change"] = df["cost_change_start"] / 10.0  # £m since season start
    df["net_transfers_event"] = df["transfers_in_event"] - df["transfers_out_event"]
    df["expected_change"] = df["net_transfers_event"].map(_predict_price_move)

    # Availability + official injury/rotation news.
    df["availability"] = df["status"].map(STATUS_LABELS).fillna(df["status"])
    df["news"] = df["news"].fillna("").astype(str)
    # Parse the news timestamp for display/sorting; NaT when there is no news.
    df["news_added"] = pd.to_datetime(df["news_added"], errors="coerce", utc=True)

    return df[DISPLAY_COLUMNS].copy()
