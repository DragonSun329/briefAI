"""
MCP Caching Layer

Provides TTL-based caching for MCP tools to reduce external API calls
and improve response times.
"""

import json
import hashlib
import time
from pathlib import Path
from typing import Any, Optional, Callable
from functools import wraps
from loguru import logger

# Cache storage directory
CACHE_DIR = Path(__file__).parent.parent / "data" / "cache" / "mcp_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Default TTL values (in seconds)
DEFAULT_TTL = 300  # 5 minutes
TTL_CONFIGS = {
    "github": 600,       # 10 minutes - GitHub API data changes slowly
    "web_scrape": 1800,  # 30 minutes - web content
    "funding": 86400,    # 24 hours - funding data rarely changes
    "search": 300,       # 5 minutes - search results
    "trends": 60,        # 1 minute - trend data needs freshness
}


def _get_cache_key(prefix: str, **kwargs) -> str:
    """Generate a cache key from prefix and arguments."""
    args_str = json.dumps(kwargs, sort_keys=True)
    hash_val = hashlib.md5(args_str.encode()).hexdigest()[:12]
    return f"{prefix}_{hash_val}"


def _get_cache_path(cache_key: str) -> Path:
    """Get the file path for a cache entry."""
    return CACHE_DIR / f"{cache_key}.json"


def get_cached(cache_key: str, ttl: int = DEFAULT_TTL) -> Optional[Any]:
    """Retrieve a cached value if it exists and hasn't expired.

    Args:
        cache_key: The cache key
        ttl: Time-to-live in seconds

    Returns:
        Cached value or None if not found/expired
    """
    cache_path = _get_cache_path(cache_key)

    if not cache_path.exists():
        return None

    try:
        with open(cache_path, 'r', encoding='utf-8') as f:
            entry = json.load(f)

        # Check TTL
        cached_at = entry.get("cached_at", 0)
        if time.time() - cached_at > ttl:
            logger.debug(f"Cache expired for {cache_key}")
            cache_path.unlink()  # Delete expired entry
            return None

        logger.debug(f"Cache hit for {cache_key}")
        return entry.get("data")

    except Exception as e:
        logger.warning(f"Cache read error for {cache_key}: {e}")
        return None


def set_cached(cache_key: str, data: Any) -> bool:
    """Store a value in the cache.

    Args:
        cache_key: The cache key
        data: The data to cache

    Returns:
        True if cached successfully
    """
    cache_path = _get_cache_path(cache_key)

    try:
        entry = {
            "cached_at": time.time(),
            "data": data
        }
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)

        logger.debug(f"Cached {cache_key}")
        return True

    except Exception as e:
        logger.warning(f"Cache write error for {cache_key}: {e}")
        return False


def cached(prefix: str, ttl: int = None):
    """Decorator to cache function results.

    Args:
        prefix: Cache key prefix (e.g., "github", "funding")
        ttl: Time-to-live in seconds (uses TTL_CONFIGS default if not specified)

    Usage:
        @cached("github", ttl=600)
        def get_repo_health(owner: str, repo: str) -> dict:
            ...
    """
    if ttl is None:
        ttl = TTL_CONFIGS.get(prefix, DEFAULT_TTL)

    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            cache_key = _get_cache_key(
                f"{prefix}_{func.__name__}",
                args=args,
                kwargs=kwargs
            )

            # Try to get from cache
            cached_result = get_cached(cache_key, ttl)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = func(*args, **kwargs)
            if result is not None:
                set_cached(cache_key, result)

            return result

        return wrapper
    return decorator


def invalidate_cache(prefix: str = None) -> int:
    """Invalidate (delete) cached entries.

    Args:
        prefix: If specified, only delete entries with this prefix.
                If None, delete all cached entries.

    Returns:
        Number of entries deleted
    """
    count = 0
    pattern = f"{prefix}_*.json" if prefix else "*.json"

    for cache_file in CACHE_DIR.glob(pattern):
        try:
            cache_file.unlink()
            count += 1
        except Exception as e:
            logger.warning(f"Failed to delete cache file {cache_file}: {e}")

    logger.info(f"Invalidated {count} cache entries (prefix: {prefix or 'all'})")
    return count


def get_cache_stats() -> dict:
    """Get statistics about the cache.

    Returns:
        Dict with cache statistics
    """
    if not CACHE_DIR.exists():
        return {"available": False}

    cache_files = list(CACHE_DIR.glob("*.json"))
    total_size = sum(f.stat().st_size for f in cache_files)

    # Count by prefix
    prefix_counts = {}
    now = time.time()
    expired_count = 0

    for cache_file in cache_files:
        parts = cache_file.stem.split("_")
        if parts:
            prefix = parts[0]
            prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

        # Check if expired
        try:
            with open(cache_file, 'r') as f:
                entry = json.load(f)
            cached_at = entry.get("cached_at", 0)
            ttl = TTL_CONFIGS.get(parts[0] if parts else "", DEFAULT_TTL)
            if now - cached_at > ttl:
                expired_count += 1
        except:
            pass

    return {
        "available": True,
        "cache_dir": str(CACHE_DIR),
        "total_entries": len(cache_files),
        "expired_entries": expired_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "by_prefix": prefix_counts
    }


def cleanup_expired() -> int:
    """Remove all expired cache entries.

    Returns:
        Number of entries removed
    """
    if not CACHE_DIR.exists():
        return 0

    count = 0
    now = time.time()

    for cache_file in CACHE_DIR.glob("*.json"):
        try:
            with open(cache_file, 'r') as f:
                entry = json.load(f)

            cached_at = entry.get("cached_at", 0)
            # Get TTL based on prefix
            parts = cache_file.stem.split("_")
            prefix = parts[0] if parts else ""
            ttl = TTL_CONFIGS.get(prefix, DEFAULT_TTL)

            if now - cached_at > ttl:
                cache_file.unlink()
                count += 1

        except Exception as e:
            logger.warning(f"Error checking cache file {cache_file}: {e}")

    if count > 0:
        logger.info(f"Cleaned up {count} expired cache entries")

    return count
