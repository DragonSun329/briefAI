"""
Unified Config Loader

Single source for loading all JSON configs with caching.
"""

import json
from pathlib import Path
from functools import lru_cache
from typing import Dict, List, Any

CONFIG_DIR = Path(__file__).parent.parent / "config"


@lru_cache(maxsize=16)
def _load_json(filename: str) -> Dict[str, Any]:
    """Load and cache a JSON config file."""
    path = CONFIG_DIR / filename
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_sources() -> Dict[str, Any]:
    """Load sources.json config."""
    return _load_json("sources.json")


def load_categories() -> Dict[str, Any]:
    """Load categories.json config."""
    return _load_json("categories.json")


def load_financial_mappings() -> Dict[str, Any]:
    """Load financial_mappings.json config."""
    return _load_json("financial_mappings.json")


def load_ticker_buckets() -> Dict[str, List[str]]:
    """Load ticker-to-bucket mappings."""
    return load_financial_mappings().get("ticker_to_bucket", {})


def load_token_buckets() -> Dict[str, Dict[str, Any]]:
    """Load token-to-bucket mappings."""
    return load_financial_mappings().get("token_to_bucket", {})


def load_macro_series() -> Dict[str, Dict[str, Any]]:
    """Load macro series configuration."""
    return load_financial_mappings().get("macro_series", {})


def get_all_tickers() -> List[str]:
    """Get unique list of all tickers across all buckets."""
    ticker_buckets = load_ticker_buckets()
    all_tickers = set()
    for tickers in ticker_buckets.values():
        all_tickers.update(tickers)
    return sorted(all_tickers)


def get_all_tokens() -> List[str]:
    """Get list of all token symbols."""
    return list(load_token_buckets().keys())


def reload_configs():
    """Clear cache to reload configs (e.g., after edit)."""
    _load_json.cache_clear()
