"""PL Fantasy Stats — a Streamlit app backed by the official FPL API.

Tabs: a player picker and a fixture-difficulty ticker.
Run with:  streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.fixtures import build_ticker, color_for
from src.fpl_client import (
    cache_mtime, fetch_bootstrap, fetch_entry, fetch_fixtures, fetch_picks, load_config,
)
from src.insights import build_recommendations, top_captains, top_differentials
from src.myteam import build_squad, suggest_transfers
from src.news_feed import attach_rumours, fetch_feed_items
from src.transform import build_players_df

st.set_page_config(page_title="PL Fantasy Stats", page_icon="⚽", layout="wide")

CFG = load_config()
TTL_SECONDS = int(CFG["cache"]["ttl_minutes"]) * 60

# Position display order.
POSITION_ORDER = ["GKP", "DEF", "MID", "FWD"]

# Human labels for the sort selectbox -> DataFrame column.
SORT_OPTIONS = {
    "Total points": "total_points",
    "Form": "form",
    "Value (pts/£m)": "value",
    "Price": "price",
    "xGI": "expected_goal_involvements",
    "xG per 90": "expected_goals_per_90",
    "ICT index": "ict_index",
    "Selected by %": "selected_by_percent",
    "Minutes": "minutes",
    "Net transfers (GW)": "net_transfers_event",
    "Price change (season)": "price_change",
}


@st.cache_data(ttl=TTL_SECONDS, show_spinner="Loading FPL data…")
def load_data(force_refresh: bool = False):
    bootstrap = fetch_bootstrap(force_refresh=force_refresh, cfg=CFG)
    df = build_players_df(bootstrap)
    # RSS transfer/team-news rumours, matched to players by surname.
    items = fetch_feed_items(force_refresh=force_refresh, cfg=CFG)
    df = attach_rumours(df, items, cfg=CFG)
    fixtures = fetch_fixtures(force_refresh=force_refresh, cfg=CFG)
    # Gameweek context.
    current = next((e for e in bootstrap["events"] if e.get("is_current")), None)
    upcoming = next((e for e in bootstrap["events"] if e.get("is_next")), None)
    # Latest gameweek whose squads are viewable (finished or in progress).
    played = [e["id"] for e in bootstrap["events"] if e.get("finished") or e.get("is_current")]
    meta = {
        "gameweek": current["id"] if current else (upcoming["id"] if upcoming else None),
        "gameweek_kind": "current" if current else ("upcoming" if upcoming else None),
        "next_gameweek": upcoming["id"] if upcoming else (current["id"] + 1 if current else 1),
        "picks_gw": max(played) if played else 1,
        "total_players": bootstrap.get("total_players"),
    }
    return df, meta, items, fixtures, bootstrap["teams"]


def format_refreshed() -> str:
    mtime = cache_mtime(CFG)
    if not mtime:
        return "not cached yet"
    return datetime.fromtimestamp(mtime).strftime("%d %b %Y, %H:%M")


# --- Header -----------------------------------------------------------------
df, meta, feed_items, fixtures, teams_raw = load_data()

left, right = st.columns([0.75, 0.25])
with left:
    st.title("⚽ PL Fantasy Stats")
    gw = meta.get("gameweek")
    if gw:
        st.caption(f"Gameweek {gw} ({meta['gameweek_kind']}) · latest official FPL data")
    else:
        st.caption("Latest official FPL data")
with right:
    st.write("")
    if st.button("🔄 Refresh data", use_container_width=True):
        fetch_bootstrap(force_refresh=True, cfg=CFG)
        fetch_feed_items(force_refresh=True, cfg=CFG)
        fetch_fixtures(force_refresh=True, cfg=CFG)
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Data refreshed: {format_refreshed()}")

tab_picker, tab_fixtures, tab_picks, tab_myteam = st.tabs(
    ["🎯 Player Picker", "📅 Fixture Difficulty", "⭐ Captains & Differentials", "🔁 My Team"]
)

# ============================================================================
# TAB 1 — Player Picker
# ============================================================================
with tab_picker:
    # Primary filters, inline on the page.
    f1, f2, f3 = st.columns([1, 1, 1])
    positions = [p for p in POSITION_ORDER if p in df["position"].unique()]
    sel_positions = f1.multiselect("Position", positions, default=positions,
                                   help="e.g. show only DEF")
    sel_teams = f2.multiselect("Team", sorted(df["team"].unique()), default=[],
                               help="Empty = all teams. e.g. pick AVL for Villa players")
    name_query = f3.text_input("Search player name")

    # Secondary filters + sorting, tucked away to keep the page clean.
    with st.expander("More filters & sorting"):
        e1, e2, e3 = st.columns([2, 1, 2])
        price_min, price_max = float(df["price"].min()), float(df["price"].max())
        sel_price = e1.slider(
            "Price (£m)", min_value=round(price_min, 1), max_value=round(price_max, 1),
            value=(round(price_min, 1), round(price_max, 1)), step=0.1,
        )
        max_minutes = int(df["minutes"].max()) if len(df) else 0
        min_minutes = e2.slider("Min. minutes", 0, max_minutes, 0, step=10)
        sort_label = e3.selectbox("Sort by", list(SORT_OPTIONS.keys()), index=0)
        sort_desc = e3.radio("Order", ["Descending", "Ascending"], index=0,
                             horizontal=True) == "Descending"
        t1, t2, t3 = st.columns(3)
        available_only = t1.toggle("Available only", value=False)
        flagged_only = t2.toggle("Flagged (injury/rotation) only", value=False)
        rumours_only = t3.toggle("Has press rumours only", value=False)

    mask = (
        df["position"].isin(sel_positions)
        & df["price"].between(sel_price[0], sel_price[1])
        & (df["minutes"] >= min_minutes)
    )
    if sel_teams:
        mask &= df["team"].isin(sel_teams)
    if available_only:
        mask &= df["availability"] == "Available"
    if flagged_only:
        mask &= df["news"].str.len() > 0
    if rumours_only:
        mask &= df["rumour_count"] > 0
    if name_query.strip():
        mask &= df["player"].str.contains(name_query.strip(), case=False, na=False)

    view = df[mask].sort_values(SORT_OPTIONS[sort_label], ascending=not sort_desc)

    # Headline metrics.
    if len(view):
        m1, m2, m3, m4 = st.columns(4)
        top_pts = view.loc[view["total_points"].idxmax()]
        best_val = view.loc[view["value"].idxmax()]
        top_form = view.loc[view["form"].idxmax()]
        m1.metric("Players shown", len(view))
        m2.metric("Top scorer", top_pts["player"], f"{int(top_pts['total_points'])} pts")
        m3.metric("Best value", best_val["player"], f"{best_val['value']} pts/£m")
        m4.metric("Hottest form", top_form["player"], f"{top_form['form']} form")
    else:
        st.info("No players match the current filters.")

    # Injury & rotation watch.
    flagged = view[view["news"].str.len() > 0].sort_values("news_added", ascending=False)
    with st.expander(f"🩹 Injury & rotation watch ({len(flagged)} flagged)", expanded=bool(flagged_only)):
        if len(flagged):
            st.caption("Official FPL team news — injuries, suspensions, doubts and transfers.")
            st.dataframe(
                flagged[["player", "team", "position", "availability",
                         "chance_of_playing_next_round", "news", "news_added"]],
                use_container_width=True, hide_index=True,
                column_config={
                    "player": "Player", "team": "Team", "position": "Pos",
                    "availability": "Status",
                    "chance_of_playing_next_round": st.column_config.NumberColumn("Play%", format="%d%%"),
                    "news": st.column_config.TextColumn("News", width="large"),
                    "news_added": st.column_config.DatetimeColumn("Updated", format="DD MMM, HH:mm"),
                },
            )
        else:
            st.write("No flagged players in the current filter.")

    # Transfer & press rumours.
    rumoured = view[view["rumour_count"] > 0][["player", "team", "position", "rumours"]]
    with st.expander(f"📰 Transfer & press rumours ({len(rumoured)} players mentioned)",
                     expanded=bool(rumours_only)):
        st.caption(
            "Headlines from public RSS feeds (BBC Sport, Sky Sports) keyword-matched to players "
            "by surname. Mentions, not confirmed facts — a shared surname can occasionally mismatch."
        )
        if len(rumoured):
            st.dataframe(
                rumoured, use_container_width=True, hide_index=True,
                column_config={
                    "player": "Player", "team": "Team", "position": "Pos",
                    "rumours": st.column_config.TextColumn("Headlines", width="large"),
                },
            )
        else:
            st.write("No players in the current filter are mentioned in recent headlines.")

        if feed_items:
            st.markdown("**Latest Premier League headlines**")
            headlines = pd.DataFrame(feed_items)[["title", "source", "published", "link"]]
            headlines["published"] = pd.to_datetime(headlines["published"], errors="coerce", utc=True)
            headlines = headlines.sort_values("published", ascending=False)
            st.dataframe(
                headlines, use_container_width=True, hide_index=True,
                column_config={
                    "title": st.column_config.TextColumn("Headline", width="large"),
                    "source": "Source",
                    "published": st.column_config.DatetimeColumn("Published", format="DD MMM, HH:mm"),
                    "link": st.column_config.LinkColumn("Link", display_text="open"),
                },
            )

    # Main player table.
    table_columns = [c for c in view.columns if c not in ("rumour_count", "id")]
    st.dataframe(
        view, use_container_width=True, hide_index=True, column_order=table_columns,
        column_config={
            "player": "Player", "team": "Team", "position": "Pos",
            "price": st.column_config.NumberColumn("Price", format="£%.1fm"),
            "total_points": st.column_config.NumberColumn("Pts"),
            "form": st.column_config.NumberColumn("Form", format="%.1f"),
            "points_per_game": st.column_config.NumberColumn("PPG", format="%.1f"),
            "value": st.column_config.NumberColumn("Value", format="%.1f", help="Points per £m"),
            "minutes": st.column_config.NumberColumn("Mins"),
            "goals_scored": st.column_config.NumberColumn("G"),
            "assists": st.column_config.NumberColumn("A"),
            "clean_sheets": st.column_config.NumberColumn("CS"),
            "bonus": st.column_config.NumberColumn("Bonus"),
            "expected_goals": st.column_config.NumberColumn("xG", format="%.2f"),
            "expected_goals_per_90": st.column_config.NumberColumn("xG/90", format="%.2f", help="Expected goals per 90 minutes"),
            "expected_assists": st.column_config.NumberColumn("xA", format="%.2f"),
            "expected_goal_involvements": st.column_config.NumberColumn("xGI", format="%.2f"),
            "ict_index": st.column_config.NumberColumn("ICT", format="%.1f"),
            "selected_by_percent": st.column_config.NumberColumn("Owned", format="%.1f%%"),
            "price_change": st.column_config.NumberColumn("Δ Price", format="£%+.1fm", help="Net price change since season start"),
            "net_transfers_event": st.column_config.NumberColumn("Net T/F", format="%d", help="Net transfers this gameweek (in − out) — drives price moves"),
            "expected_change": st.column_config.TextColumn("Exp. Δ", help="Momentum-based estimate of the next price move"),
            "availability": "Status",
            "chance_of_playing_next_round": st.column_config.NumberColumn("Play%", format="%d%%"),
            "news": st.column_config.TextColumn("News", width="medium"),
            "news_added": st.column_config.DatetimeColumn("News upd.", format="DD MMM, HH:mm"),
            "rumours": st.column_config.TextColumn("Press rumours", width="large", help="Headlines mentioning this player (RSS keyword match)"),
        },
    )

# ============================================================================
# TAB 2 — Fixture Difficulty
# ============================================================================
with tab_fixtures:
    st.subheader("Fixture Difficulty Ticker")
    st.caption(
        "Each team's upcoming opponents, coloured by FPL's Fixture Difficulty Rating "
        "(1 = easiest, 5 = hardest). H = home, A = away. Sorted by average difficulty so the "
        "best fixture runs sit at the top — useful for planning transfers and captaincy."
    )

    c1, c2 = st.columns([0.5, 0.5])
    horizon = c1.slider("Gameweeks ahead", min_value=1, max_value=19, value=6)
    easiest_first = c2.radio("Sort", ["Easiest first", "Hardest first"], index=0,
                             horizontal=True) == "Easiest first"

    start_gw = meta["next_gameweek"]
    # Don't request gameweeks past the end of the 38-GW season.
    horizon = max(1, min(horizon, 38 - start_gw + 1))
    display_df, difficulty_df, avg = build_ticker(fixtures, teams_raw, start_gw, horizon)

    order = avg.sort_values(ascending=easiest_first).index
    table = display_df.loc[order].copy()
    table.insert(0, "Avg FDR", avg.loc[order])

    # Build an aligned CSS grid to colour each cell by its difficulty.
    def _css(colors: tuple[str, str]) -> str:
        bg, fg = colors
        return f"background-color:{bg}; color:{fg}; text-align:center;"

    css = pd.DataFrame("", index=table.index, columns=table.columns)
    for team in order:
        css.loc[team, "Avg FDR"] = _css(color_for(avg.loc[team]))
        for col in difficulty_df.columns:
            css.loc[team, col] = _css(color_for(difficulty_df.loc[team, col]))

    styled = table.style.apply(lambda _: css, axis=None).format({"Avg FDR": "{:.2f}"})
    st.dataframe(styled, use_container_width=True, height=(len(table) + 1) * 35 + 3)

    # Colour legend.
    legend = " ".join(
        f"<span style='background:{color_for(i)[0]};color:{color_for(i)[1]};"
        f"padding:2px 8px;border-radius:4px;margin-right:4px;'>{i}</span>"
        for i in range(1, 6)
    )
    st.markdown(
        f"**FDR:** {legend} &nbsp; (1 = easiest → 5 = hardest)", unsafe_allow_html=True
    )

# ============================================================================
# TAB 3 — Captains & Differentials
# ============================================================================
with tab_picks:
    st.subheader("Captain Picks & Differentials")
    st.caption(
        "Scores blend recent form, points-per-game and underlying threat (xGI), weighted by "
        "fixture ease. **Captains** use the next gameweek's fixture; **differentials** use the "
        "average fixture over the horizon and are limited to low-owned players who can gain you rank."
    )

    ctrl = st.columns(4)
    horizon_p = ctrl[0].slider("Fixture horizon (GWs)", 1, 19, 3, key="picks_horizon")
    min_mins = ctrl[1].slider("Min. minutes played", 0, int(df["minutes"].max()), 60, step=30)
    top_n = ctrl[2].slider("How many to show", 5, 25, 10)
    diff_own = ctrl[3].slider("Differential max ownership %", 1.0, 25.0, 10.0, step=0.5)

    start_gw_p = meta["next_gameweek"]
    horizon_p = max(1, min(horizon_p, 38 - start_gw_p + 1))
    rec = build_recommendations(df, fixtures, teams_raw, start_gw_p, horizon_p)

    fp1, fp2 = st.columns([1, 1])
    pos_filter = fp1.multiselect(
        "Positions", POSITION_ORDER,
        default=[p for p in POSITION_ORDER if p in rec["position"].unique()],
    )
    team_filter = fp2.multiselect(
        "Teams", sorted(rec["team"].unique()), default=[],
        help="Empty = all teams",
    )
    rec_pos = rec[rec["position"].isin(pos_filter)]
    if team_filter:
        rec_pos = rec_pos[rec_pos["team"].isin(team_filter)]

    caps = top_captains(rec_pos, n=top_n, min_minutes=min_mins)
    diffs = top_differentials(rec_pos, max_ownership=diff_own, n=top_n, min_minutes=min_mins)

    if len(caps):
        pick = caps.iloc[0]
        alt = caps.iloc[1] if len(caps) > 1 else pick
        c1, c2, c3 = st.columns(3)
        c1.metric("⭐ Top captain", pick["player"], f"{pick['team']} vs {pick['next_opp']}")
        c2.metric("Runner-up", alt["player"], f"{alt['team']} vs {alt['next_opp']}")
        c3.metric("Captain score", f"{pick['captain_score']:.1f}", f"form {pick['form']:.1f}")

    cap_cols = ["player", "team", "position", "next_opp", "next_fdr", "form",
                "points_per_game", "expected_goal_involvements", "selected_by_percent", "captain_score"]
    diff_cols = ["player", "team", "position", "next_opp", "avg_fdr", "form",
                 "expected_goal_involvements", "selected_by_percent", "differential_score"]
    score_config = {
        "player": "Player", "team": "Team", "position": "Pos",
        "next_opp": "Next", "form": st.column_config.NumberColumn("Form", format="%.1f"),
        "points_per_game": st.column_config.NumberColumn("PPG", format="%.1f"),
        "expected_goal_involvements": st.column_config.NumberColumn("xGI", format="%.2f"),
        "selected_by_percent": st.column_config.NumberColumn("Owned", format="%.1f%%"),
        "next_fdr": st.column_config.NumberColumn("FDR", format="%.0f", help="Next fixture difficulty"),
        "avg_fdr": st.column_config.NumberColumn("Avg FDR", format="%.2f", help="Average fixture difficulty over the horizon"),
        "captain_score": st.column_config.NumberColumn("Score", format="%.1f"),
        "differential_score": st.column_config.NumberColumn("Score", format="%.1f"),
    }

    st.markdown("#### ⭐ Best captain options (next gameweek)")
    if len(caps):
        st.dataframe(caps[cap_cols], use_container_width=True, hide_index=True, column_config=score_config)
    else:
        st.info("No captain options match the current filters.")

    st.markdown(f"#### 💎 Differentials (≤ {diff_own:.0f}% owned)")
    if len(diffs):
        st.dataframe(diffs[diff_cols], use_container_width=True, hide_index=True, column_config=score_config)
    else:
        st.info("No differentials match the current filters — try raising the ownership cap.")

# ============================================================================
# TAB 4 — My Team (transfer suggestions)
# ============================================================================
with tab_myteam:
    st.subheader("My Team — Transfer Suggestions")
    st.caption(
        "Enter your FPL team ID to pull your squad and get suggested single-transfer upgrades: "
        "for each player, the best-scoring affordable replacement in the same position. "
        "Find your ID in the FPL site URL: `.../entry/**1234567**/event/...`."
    )

    mc = st.columns([1.2, 1, 1, 1])
    team_id_str = mc[0].text_input("FPL Team ID", placeholder="e.g. 1234567")
    horizon_m = mc[1].slider("Fixture horizon (GWs)", 1, 19, 5, key="myteam_horizon")
    min_mins_m = mc[2].slider("Min. minutes (targets)", 0, int(df["minutes"].max()), 60, step=30,
                              key="myteam_minmins")
    n_sug = mc[3].slider("Suggestions", 1, 10, 5, key="myteam_n")

    if not team_id_str.strip():
        st.info("Enter your team ID above to see your squad and transfer suggestions.")
    elif not team_id_str.strip().isdigit():
        st.error("Team ID must be a number (digits only).")
    else:
        team_id = int(team_id_str.strip())
        try:
            entry = fetch_entry(team_id, cfg=CFG)
            picks_data = fetch_picks(team_id, meta["picks_gw"], cfg=CFG)
        except Exception:
            st.error(
                f"Couldn't load team {team_id}. Check the ID is correct and public "
                "(the FPL API only serves teams that have set a squad)."
            )
        else:
            bank = picks_data["entry_history"]["bank"] / 10.0
            value = picks_data["entry_history"]["value"] / 10.0
            start_m = max(1, min(horizon_m, 38 - meta["next_gameweek"] + 1))
            rec_m = build_recommendations(df, fixtures, teams_raw, meta["next_gameweek"], start_m)
            squad = build_squad(rec_m, picks_data["picks"])

            h1, h2, h3, h4 = st.columns(4)
            h1.metric("Team", entry.get("name", "—"))
            h2.metric("Overall points", entry.get("summary_overall_points", "—"))
            rank = entry.get("summary_overall_rank")
            h3.metric("Overall rank", f"{rank:,}" if rank else "—")
            h4.metric("In the bank", f"£{bank:.1f}m", f"squad £{value:.1f}m")

            # Best captain within the owned squad.
            starters = squad[~squad["on_bench"]]
            if len(starters):
                cap = starters.sort_values("captain_score", ascending=False).iloc[0]
                st.markdown(
                    f"**⭐ Suggested captain (from your squad):** {cap['player']} "
                    f"({cap['team']}) — next {cap['next_opp']}, form {cap['form']:.1f}"
                )

            st.markdown("#### 🔁 Suggested transfers")
            sug = suggest_transfers(rec_m, squad, bank, n=n_sug, min_minutes=min_mins_m)
            if len(sug):
                st.caption(
                    "Ranked by projected score gain. Each swap is costed on its own against your "
                    "bank + the sold player's price — combining several may exceed your budget. "
                    "Selling price is approximated by current price (the API doesn't expose it)."
                )
                st.dataframe(
                    sug, use_container_width=True, hide_index=True,
                    column_config={
                        "out": st.column_config.TextColumn("OUT"),
                        "out_team": "Team", "position": "Pos",
                        "out_score": st.column_config.NumberColumn("Score", format="%.1f"),
                        "in": st.column_config.TextColumn("IN"),
                        "in_team": "Team", "in_next": "IN next",
                        "in_score": st.column_config.NumberColumn("Score", format="%.1f"),
                        "improvement": st.column_config.NumberColumn("Gain", format="+%.1f"),
                        "cost": st.column_config.NumberColumn("Cost", format="£%+.1fm"),
                    },
                )
            else:
                st.success("No clear upgrades found within budget — your squad looks well set!")

            st.markdown("#### Your current squad")
            squad_view = squad.assign(
                role=squad.apply(
                    lambda r: ("(C)" if r["is_captain"] else "(V)" if r["is_vice"] else "")
                    + (" 🪑" if r["on_bench"] else ""),
                    axis=1,
                )
            )
            st.dataframe(
                squad_view[["player", "team", "position", "role", "price", "next_opp",
                            "next_fdr", "form", "expected_goal_involvements",
                            "selected_by_percent", "differential_score"]],
                use_container_width=True, hide_index=True,
                column_config={
                    "player": "Player", "team": "Team", "position": "Pos", "role": "",
                    "price": st.column_config.NumberColumn("Price", format="£%.1fm"),
                    "next_opp": "Next", "next_fdr": st.column_config.NumberColumn("FDR", format="%.0f"),
                    "form": st.column_config.NumberColumn("Form", format="%.1f"),
                    "expected_goal_involvements": st.column_config.NumberColumn("xGI", format="%.2f"),
                    "selected_by_percent": st.column_config.NumberColumn("Owned", format="%.1f%%"),
                    "differential_score": st.column_config.NumberColumn("Score", format="%.1f"),
                },
            )

st.caption(
    "Data: official Fantasy Premier League API (fantasy.premierleague.com). "
    "Not affiliated with the Premier League or FPL."
)
