#!/usr/bin/env python3
"""
Bright Data Web Unlocker fallback for blocked sites.
Uses Bright Data's Web Unlocker when direct requests fail with 403/429.
"""
import os
from typing import Optional
from loguru import logger

# API token from environment
BRIGHTDATA_API_TOKEN = os.environ.get("BRIGHT_DATA_API_TOKEN", "") or os.environ.get("BRIGHTDATA_API_TOKEN", "")

def is_available() -> bool:
    """Check if Bright Data is configured."""
    return bool(BRIGHTDATA_API_TOKEN)

def fetch_url(url: str, timeout: int = 60) -> Optional[str]:
    """
    Fetch a URL using Bright Data Web Unlocker (sync).
    Returns HTML string or None on failure.
    """
    if not is_available():
        logger.debug("Bright Data not configured, skipping")
        return None
    
    try:
        from brightdata import SyncBrightDataClient
        with SyncBrightDataClient(token=BRIGHTDATA_API_TOKEN) as client:
            result = client.scrape_url(url)
            if result and result.data:
                return result.data if isinstance(result.data, str) else str(result.data)
    except Exception as e:
        logger.warning(f"Bright Data fetch failed for {url}: {e}")
    return None

def fetch_json(url: str, timeout: int = 60) -> Optional[dict]:
    """
    Fetch a JSON URL using Bright Data Web Unlocker (sync).
    Returns parsed JSON or None on failure.
    """
    import json
    html = fetch_url(url, timeout)
    if html:
        try:
            return json.loads(html)
        except json.JSONDecodeError:
            logger.warning(f"Bright Data returned non-JSON for {url}")
    return None
