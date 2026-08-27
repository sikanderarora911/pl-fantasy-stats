"""Map a manager's FPL squad to our enriched player data and suggest transfers.

A transfer suggestion pairs a player you own with a better-scoring, affordable replacement in
the same position. "Better" uses ``differential_score`` from :mod:`insights` (quality × average
fixture ease over the horizon), so suggestions favour in-form players with a kind run of games.

Budget note: the public FPL API does not expose a player's *selling* price, so we approximate it
with their current price. That is exact unless the player's price has moved since you bought them.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def build_squad(rec_df: pd.DataFrame, picks: list[dict[str, Any]]) -> pd.DataFrame:
    """Return the manager's 15 players (rows from ``rec_df``) tagged with role/bench flags."""
    by_id = {p["element"]: p for p in picks}
    squad = rec_df[rec_df["id"].isin(by_id)].copy()
    squad["is_captain"] = squad["id"].map(lambda i: by_id[i]["is_captain"])
    squad["is_vice"] = squad["id"].map(lambda i: by_id[i]["is_vice_captain"])
    squad["on_bench"] = squad["id"].map(lambda i: by_id[i]["position"] > 11)
    # Preserve the manager's ordering (1..15).
    squad["squad_pos"] = squad["id"].map(lambda i: by_id[i]["position"])
    return squad.sort_values("squad_pos")


def suggest_transfers(
    rec_df: pd.DataFrame,
    squad: pd.DataFrame,
    bank: float,
    n: int = 5,
    min_minutes: int = 60,
    score_col: str = "differential_score",
) -> pd.DataFrame:
    """Best single-transfer upgrades: for each owned player, the top affordable replacement.

    Returns a table of OUT → IN swaps ranked by score improvement. Each swap is costed
    independently against ``bank`` + the sold player's price, so combining several may exceed
    your budget — treat them as a ranked menu, not a simultaneous plan.
    """
    owned_ids = set(squad["id"])
    rows: list[dict[str, Any]] = []

    for _, p in squad.iterrows():
        budget = bank + p["price"]
        pool = rec_df[
            (rec_df["position"] == p["position"])
            & (~rec_df["id"].isin(owned_ids))
            & (rec_df["price"] <= budget + 1e-9)
            & (rec_df["availability"] == "Available")
            & (rec_df["minutes"] >= min_minutes)
        ]
        if pool.empty:
            continue
        best = pool.sort_values(score_col, ascending=False).iloc[0]
        improvement = round(float(best[score_col]) - float(p[score_col]), 2)
        if improvement <= 0:
            continue
        rows.append(
            {
                "out": p["player"], "out_team": p["team"], "position": p["position"],
                "out_score": round(float(p[score_col]), 2),
                "in": best["player"], "in_team": best["team"],
                "in_next": best["next_opp"], "in_score": round(float(best[score_col]), 2),
                "improvement": improvement,
                "cost": round(float(best["price"]) - float(p["price"]), 1),
            }
        )

    cols = ["out", "out_team", "position", "out_score", "in", "in_team",
            "in_next", "in_score", "improvement", "cost"]
    if not rows:
        return pd.DataFrame(columns=cols)
    res = pd.DataFrame(rows).sort_values("improvement", ascending=False)
    # Keep the highest-improvement swap per player, so the menu shows distinct OUTs and INs.
    res = res.drop_duplicates("out").drop_duplicates("in")
    return res.head(n)
