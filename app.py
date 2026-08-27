"""PL Fantasy Stats — a Streamlit app backed by the official FPL API.

Tabs: a player picker and a fixture-difficulty ticker.
Run with:  streamlit run app.py
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from src.fixtures import build_ticker, color_for
from src.fpl_client import cache_mtime, fetch_bootstrap, fetch_fixtures, load_config
from src.insights import build_recommendations, top_captains, top_differentials
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
    meta = {
        "gameweek": current["id"] if current else (upcoming["id"] if upcoming else None),
        "gameweek_kind": "current" if current else ("upcoming" if upcoming else None),
        "next_gameweek": upcoming["id"] if upcoming else (current["id"] + 1 if current else 1),
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

# --- Sidebar filters (player picker) ----------------------------------------
st.sidebar.header("Player filters")
st.sidebar.caption("Apply to the Player Picker tab.")

positions = [p for p in POSITION_ORDER if p in df["position"].unique()]
sel_positions = st.sidebar.multiselect("Position", positions, default=positions)

teams = sorted(df["team"].unique())
sel_teams = st.sidebar.multiselect("Team", teams, default=[])  # empty = all

price_min, price_max = float(df["price"].min()), float(df["price"].max())
sel_price = st.sidebar.slider(
    "Price (£m)", min_value=round(price_min, 1), max_value=round(price_max, 1),
    value=(round(price_min, 1), round(price_max, 1)), step=0.1,
)

max_minutes = int(df["minutes"].max()) if len(df) else 0
min_minutes = st.sidebar.slider("Minimum minutes played", 0, max_minutes, 0, step=10)

available_only = st.sidebar.toggle("Available players only", value=False)
flagged_only = st.sidebar.toggle("Flagged (injury/rotation news) only", value=False)
rumours_only = st.sidebar.toggle("Has press rumours only", value=False)
name_query = st.sidebar.text_input("Search player name")

st.sidebar.divider()
sort_label = st.sidebar.selectbox("Sort by", list(SORT_OPTIONS.keys()), index=0)
sort_desc = st.sidebar.radio("Order", ["Descending", "Ascending"], index=0) == "Descending"

tab_picker, tab_fixtures, tab_picks = st.tabs(
    ["🎯 Player Picker", "📅 Fixture Difficulty", "⭐ Captains & Differentials"]
)

# ============================================================================
# TAB 1 — Player Picker
# ============================================================================
with tab_picker:
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
    table_columns = [c for c in view.columns if c != "rumour_count"]
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
    horizon = c1.slider("Gameweeks ahead", min_value=3, max_value=8, value=5)
    easiest_first = c2.radio("Sort", ["Easiest first", "Hardest first"], index=0,
                             horizontal=True) == "Easiest first"

    start_gw = meta["next_gameweek"]
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
    horizon_p = ctrl[0].slider("Fixture horizon (GWs)", 1, 6, 3, key="picks_horizon")
    min_mins = ctrl[1].slider("Min. minutes played", 0, int(df["minutes"].max()), 60, step=30)
    top_n = ctrl[2].slider("How many to show", 5, 25, 10)
    diff_own = ctrl[3].slider("Differential max ownership %", 1.0, 25.0, 10.0, step=0.5)

    start_gw_p = meta["next_gameweek"]
    rec = build_recommendations(df, fixtures, teams_raw, start_gw_p, horizon_p)

    pos_filter = st.multiselect(
        "Positions", POSITION_ORDER,
        default=[p for p in POSITION_ORDER if p in rec["position"].unique()],
    )
    rec_pos = rec[rec["position"].isin(pos_filter)]

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

st.caption(
    "Data: official Fantasy Premier League API (fantasy.premierleague.com). "
    "Not affiliated with the Premier League or FPL."
)
