"""Unit tests for RSS rumour matching — pure logic, no network."""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.news_feed import _normalize, _player_tokens, attach_rumours  # noqa: E402

CFG = {"news": {"min_token_len": 4, "max_items_per_player": 3}}


def test_normalize_strips_accents():
    assert _normalize("Álvarez") == "alvarez"
    assert _normalize("João Pedro") == "joao pedro"


def test_surname_only_token():
    # Only the last long-enough token (surname) is used.
    assert _player_tokens("Pedro Porro", 4) == ["porro"]
    assert _player_tokens("João Pedro", 4) == ["pedro"]
    assert _player_tokens("J.Murphy", 4) == ["murphy"]
    # Too-short names yield no token (never match).
    assert _player_tokens("Son", 4) == []


def _items():
    return [
        {"title": "Tottenham sign Man City's Marmoush on loan", "summary": ""},
        {"title": "Fiorentina in talks over Zirkzee loan", "summary": "United's Zirkzee could move."},
        {"title": "Alvarez skips training amid exit talk", "summary": ""},
    ]


def test_attach_rumours_matches_surnames():
    df = pd.DataFrame({"player": ["Marmoush", "Zirkzee", "Álvarez", "Haaland"]})
    out = attach_rumours(df, _items(), cfg=CFG).set_index("player")
    assert out.loc["Marmoush", "rumour_count"] == 1
    assert "Marmoush" in out.loc["Marmoush", "rumours"]
    assert out.loc["Zirkzee", "rumour_count"] == 1
    # Accent-insensitive: 'Álvarez' matches 'Alvarez' headline.
    assert out.loc["Álvarez", "rumour_count"] == 1
    # Unmentioned player -> no rumours.
    assert out.loc["Haaland", "rumour_count"] == 0
    assert out.loc["Haaland", "rumours"] == ""


def test_summary_mention_does_not_match():
    # Regression: a player named only in the SUMMARY (not the headline) must not match, so a
    # Barcola transfer story that lists Gakpo as squad competition isn't tagged to Gakpo.
    items = [
        {"title": "Liverpool agree £123m deal for PSG's Barcola",
         "summary": "New signing adds to competition alongside Gakpo and Diaz."},
    ]
    df = pd.DataFrame({"player": ["Gakpo", "Barcola"]})
    out = attach_rumours(df, items, cfg=CFG).set_index("player")
    assert out.loc["Gakpo", "rumour_count"] == 0     # only in summary -> no match
    assert out.loc["Barcola", "rumour_count"] == 1   # in headline -> matches


def test_rumours_respect_cap():
    df = pd.DataFrame({"player": ["Smith"]})
    items = [{"title": f"Smith story {i}", "summary": ""} for i in range(10)]
    out = attach_rumours(df, items, cfg={"news": {"min_token_len": 4, "max_items_per_player": 2}})
    assert out.iloc[0]["rumour_count"] == 2
