"""
Cache Manager

Handles caching of scraped articles and API responses to avoid redundant work.
"""

import os
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from loguru import logger


class CacheManager:
    """Manages file-based caching for articles and API responses"""

    def __init__(self, cache_dir: str = "./data/cache"):
        """
        Initialize cache manager

        Args:
            cache_dir: Directory to store cache files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Cache directory: {self.cache_dir}")

    def _get_cache_key(self, key: str) -> str:
        """Generate a hash-based cache key"""
        return hashlib.md5(key.encode()).hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """Get the file path for a cache key"""
        cache_key = self._get_cache_key(key)
        return self.cache_dir / f"{cache_key}.json"

    def get(
        self,
        key: str,
        max_age_hours: Optional[int] = None
    ) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key
            max_age_hours: Maximum age of cache in hours (None = no expiry)

        Returns:
            Cached value or None if not found/expired
        """
        cache_path = self._get_cache_path(key)

        if not cache_path.exists():
            logger.debug(f"Cache miss: {key}")
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)

            # Check expiry
            if max_age_hours is not None:
                cached_time = datetime.fromisoformat(cache_data['timestamp'])
                age = datetime.now() - cached_time

                if age > timedelta(hours=max_age_hours):
                    logger.debug(f"Cache expired: {key} (age: {age})")
                    return None

            logger.debug(f"Cache hit: {key}")
            return cache_data['value']

        except Exception as e:
            logger.warning(f"Failed to read cache for {key}: {e}")
            return None

    def set(self, key: str, value: Any) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache (must be JSON-serializable)

        Returns:
            True if successful
        """
        cache_path = self._get_cache_path(key)

        try:
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'key': key,
                'value': value
            }

            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

            logger.debug(f"Cached: {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to cache {key}: {e}")
            return False

    def clear(self, older_than_hours: Optional[int] = None):
        """
        Clear cache files

        Args:
            older_than_hours: Only clear files older than X hours (None = all)
        """
        cleared = 0

        for cache_file in self.cache_dir.glob("*.json"):
            try:
                if older_than_hours is not None:
                    # Check file age
                    file_time = datetime.fromtimestamp(cache_file.stat().st_mtime)
                    age = datetime.now() - file_time

                    if age <= timedelta(hours=older_than_hours):
                        continue

                cache_file.unlink()
                cleared += 1

            except Exception as e:
                logger.warning(f"Failed to delete {cache_file}: {e}")

        logger.info(f"Cleared {cleared} cache files")
        return cleared


if __name__ == "__main__":
    # Test cache manager
    cache = CacheManager()

    # Set a value
    cache.set("test_key", {"hello": "world"})

    # Get it back
    value = cache.get("test_key")
    print(f"Retrieved: {value}")

    # Test expiry
    value = cache.get("test_key", max_age_hours=0)
    print(f"With expiry: {value}")
