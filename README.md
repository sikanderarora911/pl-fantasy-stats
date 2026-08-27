# PL Fantasy Stats — Player Picker

A Streamlit web app that pulls the **latest Premier League stats** from the official
Fantasy Premier League (FPL) API and presents a rich, filterable **player picker** to help
you make informed FPL transfer, captaincy and differential decisions.

## Features

### 🎯 Player Picker
- Every player with price, total points, form, points-per-game, minutes, goals/assists,
  clean sheets, bonus, expected goals/assists/involvements (xG/xA/xGI), ICT index,
  ownership %, and injury/availability status.
- **Value** metric = points per £m, the key value-for-money signal for transfers.
- **Price movement**: net change since season start, this-gameweek net transfers, and a
  momentum-based estimate of the next price move (▲ Rising / ▼ Falling / – Stable).
- **Injury & rotation watch**: official FPL team news (injuries, suspensions, doubts).
- **Transfer & press rumours**: headlines from public RSS feeds (BBC Sport, Sky Sports)
  keyword-matched to players by surname, plus a browsable latest-headlines list with links.
- Sidebar filters: position, team, price range, minimum minutes, available-only, flagged-only,
  rumours-only, name search. Sort by any headline metric.

### 📅 Fixture Difficulty
- Colour-coded FDR ticker: each team's upcoming opponents (home/away) coloured by FPL's
  Fixture Difficulty Rating (1 = easiest → 5 = hardest), sorted by average difficulty.
- Adjustable horizon (3–8 gameweeks) and easiest/hardest-first ordering.
- Handles blank and double gameweeks.

### ⭐ Captains & Differentials
- **Captain picks** for the next gameweek: ranks available, playing players by a score that
  blends form, points-per-game and xGI, weighted by the next fixture's ease.
- **Differentials**: in-form, low-owned players (adjustable ownership cap) with a good fixture
  *run* — weighted by average difficulty over the horizon.
- Controls for horizon, minimum minutes, count, ownership cap, positions, and teams.

### 🔁 My Team
- Enter your **FPL team ID** to pull your live squad, points, rank, bank and team value.
- **Suggested transfers**: for each player, the best-scoring affordable replacement in the same
  position, ranked by projected gain (distinct OUT/IN players, costed against bank + selling price).
- A suggested captain drawn from your own squad, plus your full squad with fixtures and scores.
- Note: the public API doesn't expose selling price, so it's approximated by current price.

### General
- **🔄 Refresh** button + a disk cache so stats stay current without hammering the API.

## Setup

```bash
cd pl-fantasy-stats
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

Then open the URL Streamlit prints (default http://localhost:8501).

## Test

```bash
pytest -q
```

## Data source

Official Fantasy Premier League API (`https://fantasy.premierleague.com/api/`) —
free, no API key. This project is not affiliated with the Premier League or FPL.

## Configuration

`config.yaml` controls the API base URL, request `User-Agent` (required — the API 403s
some default agents), timeout, and cache TTL (`cache.ttl_minutes`, default 60).

## Project layout

```
app.py                  # Streamlit UI: Player Picker + Fixture Difficulty tabs
src/fpl_client.py        # FPL API fetch (bootstrap, fixtures) + disk cache
src/transform.py         # tidy players DataFrame + derived metrics
src/news_feed.py         # RSS rumour fetch + surname matching
src/fixtures.py          # fixture-difficulty ticker
src/insights.py          # captain & differential scoring
src/myteam.py            # squad mapping + transfer suggestions
tests/                   # unit tests (no network)
cache/                   # cached API JSON
config.yaml              # settings (API, cache, news feeds)
```

## Roadmap (next versions)

- Per-player gameweek history & trends (sparklines).
- Multi-transfer planning within a combined budget.
- Chip strategy hints (Wildcard / Bench Boost / Triple Captain).
