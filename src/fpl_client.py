"""Client for the official Fantasy Premier League API with a simple disk cache.

The FPL API is public and needs no key, but it 403s some default user agents, so we
always send a browser-like ``User-Agent`` (from ``config.yaml``). The main endpoint,
``bootstrap-static``, carries players, teams, positions and gameweeks in one ~1.6MB payload.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests
import yaml

# Project root = parent of the ``src`` directory that holds this file.
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"


def load_config() -> dict[str, Any]:
    """Read ``config.yaml`` from the project root."""
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _cache_path(cfg: dict[str, Any], name: str) -> Path:
    cache_dir = ROOT / cfg["cache"]["dir"]
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / name


def _cache_is_fresh(path: Path, ttl_minutes: int) -> bool:
    if not path.exists():
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return age_seconds < ttl_minutes * 60


def fetch_bootstrap(force_refresh: bool = False, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the ``bootstrap-static`` payload, using a fresh disk cache when possible.

    Behaviour:
      * If a cached file exists and is younger than ``cache.ttl_minutes`` (and not
        ``force_refresh``), return it without hitting the network.
      * Otherwise GET the API, write the raw JSON to cache, and return it.
      * If the network call fails but a (possibly stale) cache exists, fall back to it.
      * If neither works, raise the underlying error.
    """
    cfg = cfg or load_config()
    api = cfg["api"]
    ttl = int(cfg["cache"]["ttl_minutes"])
    path = _cache_path(cfg, "bootstrap-static.json")

    if not force_refresh and _cache_is_fresh(path, ttl):
        return _read_cache(path)

    url = f"{api['base_url'].rstrip('/')}/bootstrap-static/"
    headers = {"User-Agent": api["user_agent"]}
    try:
        resp = requests.get(url, headers=headers, timeout=api.get("timeout_seconds", 20))
        resp.raise_for_status()
        data = resp.json()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data
    except requests.RequestException:
        # Network/API failure: fall back to any cached copy rather than crashing the app.
        if path.exists():
            return _read_cache(path)
        raise


def fetch_fixtures(force_refresh: bool = False, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return the full season fixture list, with the same disk-cache behaviour as bootstrap.

    Each fixture carries ``event`` (gameweek), ``team_h``/``team_a``, the FDR ratings
    ``team_h_difficulty``/``team_a_difficulty`` (1=easiest … 5=hardest), ``kickoff_time`` and
    ``finished``.
    """
    cfg = cfg or load_config()
    api = cfg["api"]
    ttl = int(cfg["cache"]["ttl_minutes"])
    path = _cache_path(cfg, "fixtures.json")

    if not force_refresh and _cache_is_fresh(path, ttl):
        return _read_cache(path)

    url = f"{api['base_url'].rstrip('/')}/fixtures/"
    headers = {"User-Agent": api["user_agent"]}
    try:
        resp = requests.get(url, headers=headers, timeout=api.get("timeout_seconds", 20))
        resp.raise_for_status()
        data = resp.json()
        path.write_text(json.dumps(data), encoding="utf-8")
        return data
    except requests.RequestException:
        if path.exists():
            return _read_cache(path)
        raise


def fetch_entry(team_id: int, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a manager's team summary (name, points, rank, bank, value). Not cached to disk."""
    cfg = cfg or load_config()
    api = cfg["api"]
    url = f"{api['base_url'].rstrip('/')}/entry/{int(team_id)}/"
    resp = requests.get(url, headers={"User-Agent": api["user_agent"]},
                        timeout=api.get("timeout_seconds", 20))
    resp.raise_for_status()
    return resp.json()


def fetch_picks(team_id: int, gameweek: int, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a manager's 15 picks for a gameweek, plus that gameweek's bank/value."""
    cfg = cfg or load_config()
    api = cfg["api"]
    url = f"{api['base_url'].rstrip('/')}/entry/{int(team_id)}/event/{int(gameweek)}/picks/"
    resp = requests.get(url, headers={"User-Agent": api["user_agent"]},
                        timeout=api.get("timeout_seconds", 20))
    resp.raise_for_status()
    return resp.json()


def cache_mtime(cfg: dict[str, Any] | None = None) -> float | None:
    """Epoch mtime of the bootstrap cache file, or ``None`` if it does not exist."""
    cfg = cfg or load_config()
    path = _cache_path(cfg, "bootstrap-static.json")
    return path.stat().st_mtime if path.exists() else None


def _read_cache(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
