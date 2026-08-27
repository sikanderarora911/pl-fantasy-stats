"""Fetch Premier League rumour/team-news headlines from RSS feeds and match them to players.

This is the honest, no-cost, ToS-safe alternative to scraping Twitter/X: it reads public
RSS feeds (BBC Sport, Sky Sports) and attaches any headline that mentions a player's name to
that player. Matching is keyword-based on the player's surname tokens (accent-insensitive,
word-boundary), so it can occasionally match the wrong player when a surname is shared — the
UI labels the column as headline matches, not confirmed facts.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import feedparser
import pandas as pd

from .fpl_client import ROOT, load_config


def _normalize(text: str) -> str:
    """Lowercase and strip accents so 'Álvarez' matches 'alvarez'."""
    nfkd = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return stripped.lower()


def _cache_path(cfg: dict[str, Any]) -> Path:
    cache_dir = ROOT / cfg["cache"]["dir"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "news_feed.json"


def fetch_feed_items(force_refresh: bool = False, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return normalized RSS items across all configured feeds, using a disk cache.

    Each item: ``{title, summary, link, source, published}`` (published is an ISO string or None).
    Falls back to cache on any parse/network failure; never raises for a single bad feed.
    """
    cfg = cfg or load_config()
    news_cfg = cfg.get("news", {})
    path = _cache_path(cfg)
    ttl = int(news_cfg.get("ttl_minutes", 30))

    if not force_refresh and path.exists():
        if time.time() - path.stat().st_mtime < ttl * 60:
            return json.loads(path.read_text(encoding="utf-8"))

    items: list[dict[str, Any]] = []
    for feed in news_cfg.get("feeds", []):
        try:
            parsed = feedparser.parse(feed["url"])
            for entry in parsed.entries:
                published = None
                if getattr(entry, "published_parsed", None):
                    published = time.strftime("%Y-%m-%dT%H:%M:%SZ", entry.published_parsed)
                items.append(
                    {
                        "title": entry.get("title", ""),
                        "summary": re.sub("<[^<]+?>", "", entry.get("summary", "")),
                        "link": entry.get("link", ""),
                        "source": feed.get("name", feed["url"]),
                        "published": published,
                    }
                )
        except Exception:
            # One flaky feed should never break the others.
            continue

    if items:
        path.write_text(json.dumps(items), encoding="utf-8")
        return items
    # Nothing fetched — fall back to any cached copy.
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def _player_tokens(name: str, min_len: int) -> list[str]:
    """Match tokens for a player: the surname (last long-enough word of the display name).

    Headlines refer to players by surname, so matching only the last qualifying token avoids
    first-name collisions (e.g. 'Pedro Porro' wrongly matching a 'Joao Pedro' headline). Names
    whose only token is too short (e.g. 'Son') yield no token and simply never match.
    """
    norm = _normalize(name)
    tokens = [tok for tok in re.split(r"[^a-z]+", norm) if len(tok) >= min_len]
    return tokens[-1:]  # surname only (empty list if nothing qualifies)


def attach_rumours(
    df: pd.DataFrame, items: list[dict[str, Any]], cfg: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Add ``rumours`` (joined headlines) and ``rumour_count`` columns to the players DataFrame.

    A player matches an item when any of their name tokens appears as a whole word in the
    item's title or summary.
    """
    cfg = cfg or load_config()
    news_cfg = cfg.get("news", {})
    min_len = int(news_cfg.get("min_token_len", 4))
    cap = int(news_cfg.get("max_items_per_player", 3))

    df = df.copy()
    # Pre-normalize item text once.
    norm_items = [(_normalize(f"{it['title']} {it['summary']}"), it) for it in items]

    rumours: list[str] = []
    counts: list[int] = []
    for name in df["player"]:
        tokens = _player_tokens(name, min_len)
        matched: list[str] = []
        if tokens:
            patterns = [re.compile(rf"\b{re.escape(t)}\b") for t in tokens]
            for text, it in norm_items:
                if any(p.search(text) for p in patterns):
                    matched.append(it["title"])
                    if len(matched) >= cap:
                        break
        rumours.append(" | ".join(matched))
        counts.append(len(matched))

    df["rumours"] = rumours
    df["rumour_count"] = counts
    return df
