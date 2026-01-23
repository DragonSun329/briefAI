"""
Cache Management Tools

Tools for managing the MCP cache layer.
"""

from typing import TYPE_CHECKING

from mcp_server.cache import (
    get_cache_stats,
    cleanup_expired,
    invalidate_cache,
    TTL_CONFIGS
)

if TYPE_CHECKING:
    from fastmcp import FastMCP


def register(mcp: "FastMCP"):
    """Register cache management tools with MCP server."""

    @mcp.tool()
    def cache_stats() -> dict:
        """Get statistics about the MCP cache.

        Returns:
            Dict with cache size, entry counts, and breakdown by prefix
        """
        stats = get_cache_stats()
        stats["ttl_configs"] = TTL_CONFIGS
        return stats

    @mcp.tool()
    def cache_cleanup() -> dict:
        """Remove expired cache entries.

        Returns:
            Dict with number of entries removed
        """
        count = cleanup_expired()
        return {
            "entries_removed": count,
            "status": "success"
        }

    @mcp.tool()
    def cache_invalidate(prefix: str = None) -> dict:
        """Invalidate (delete) cached entries.

        Args:
            prefix: If specified, only delete entries with this prefix
                   (e.g., 'github', 'funding', 'search').
                   If not specified, deletes all cache entries.

        Returns:
            Dict with number of entries deleted
        """
        count = invalidate_cache(prefix)
        return {
            "entries_deleted": count,
            "prefix": prefix or "all",
            "status": "success"
        }
