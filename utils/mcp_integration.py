"""
MCP Integration Utilities

Provides MCP-enhanced functionality for the BriefAI pipeline.
Uses MCP resources and tools for JIT context loading.
"""

import asyncio
import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from loguru import logger

# Import MCP client (sync wrapper)
try:
    from utils.mcp_client import SyncMCPClient, parse_tool_call, TOOL_CALLING_PROMPT
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCP client not available - install mcp package")


class MCPContextLoader:
    """
    JIT Context Loader using MCP resources.

    Provides a unified interface to load context from various sources
    using MCP resources, with fallback to direct file access.
    """

    def __init__(self, use_mcp: bool = True):
        """
        Initialize context loader.

        Args:
            use_mcp: If True, use MCP for context loading. If False, use direct access.
        """
        self.use_mcp = use_mcp and MCP_AVAILABLE
        self._mcp_client = None

        if self.use_mcp:
            try:
                self._mcp_client = SyncMCPClient()
                logger.info("MCP context loader initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize MCP client: {e}")
                self.use_mcp = False

    def get_latest_trends(self) -> List[Dict[str, Any]]:
        """Get latest trending entities.

        Returns:
            List of trending entities with momentum scores
        """
        if self.use_mcp and self._mcp_client:
            try:
                result = self._mcp_client.read_resource("trend://latest")
                return json.loads(result)
            except Exception as e:
                logger.warning(f"MCP trend fetch failed: {e}")

        # Fallback to direct database access
        return self._get_trends_direct()

    def _get_trends_direct(self) -> List[Dict[str, Any]]:
        """Direct database access fallback for trends."""
        import sqlite3
        db_path = Path(__file__).parent.parent / "data" / "trend_radar.db"
        if not db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT entity_name, momentum_score, article_count
                FROM trend_signals
                ORDER BY momentum_score DESC
                LIMIT 20
            """)
            results = cursor.fetchall()
            conn.close()
            return [
                {"entity": r[0], "momentum": r[1], "articles": r[2]}
                for r in results
            ]
        except Exception as e:
            logger.error(f"Direct trend fetch failed: {e}")
            return []

    def get_signal_profile(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """Get signal profile for an entity.

        Args:
            entity_name: Name of the entity

        Returns:
            Signal profile dict or None
        """
        if self.use_mcp and self._mcp_client:
            try:
                result = self._mcp_client.read_resource(f"signals://profile/{entity_name}")
                data = json.loads(result)
                if "error" not in data:
                    return data
            except Exception as e:
                logger.warning(f"MCP signal profile fetch failed: {e}")

        # Fallback to direct database access
        return self._get_signal_profile_direct(entity_name)

    def _get_signal_profile_direct(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """Direct database access fallback for signal profiles."""
        import sqlite3
        db_path = Path(__file__).parent.parent / "data" / "signals.db"
        if not db_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT entity_name, composite_score, technical_score,
                       company_score, financial_score, momentum_7d
                FROM signal_profiles
                WHERE entity_name LIKE ?
                ORDER BY as_of DESC LIMIT 1
            """, (f"%{entity_name}%",))
            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    "entity": row[0],
                    "composite": row[1],
                    "technical": row[2],
                    "company": row[3],
                    "financial": row[4],
                    "momentum_7d": row[5]
                }
        except Exception as e:
            logger.error(f"Direct signal profile fetch failed: {e}")

        return None

    def get_conviction_scores(self) -> List[Dict[str, Any]]:
        """Get latest conviction scores from Devil's Advocate analysis.

        Returns:
            List of entities with conviction analysis
        """
        if self.use_mcp and self._mcp_client:
            try:
                result = self._mcp_client.read_resource("conviction://scores")
                return json.loads(result)
            except Exception as e:
                logger.warning(f"MCP conviction fetch failed: {e}")

        # Fallback to direct database access
        return self._get_conviction_direct()

    def _get_conviction_direct(self) -> List[Dict[str, Any]]:
        """Direct database access fallback for conviction scores."""
        import sqlite3
        db_path = Path(__file__).parent.parent / "data" / "trend_radar.db"
        if not db_path.exists():
            return []

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("""
                SELECT entity_name, conviction_score, recommendation,
                       bull_thesis, bear_thesis
                FROM conviction_scores
                ORDER BY conviction_score DESC LIMIT 20
            """)
            results = cursor.fetchall()
            conn.close()
            return [
                {
                    "entity": r[0],
                    "conviction": r[1],
                    "recommendation": r[2],
                    "bull_thesis": r[3],
                    "bear_thesis": r[4]
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Direct conviction fetch failed: {e}")
            return []

    def get_article_context(self, date: str = None) -> Dict[str, Any]:
        """Get cached article context for a date.

        Args:
            date: Date in YYYYMMDD format (defaults to latest)

        Returns:
            Article context dict
        """
        if self.use_mcp and self._mcp_client:
            try:
                uri = f"context://articles/{date}" if date else "context://articles/latest"
                result = self._mcp_client.read_resource(uri)
                return json.loads(result)
            except Exception as e:
                logger.warning(f"MCP article context fetch failed: {e}")

        # Fallback to direct file access
        return self._get_article_context_direct(date)

    def _get_article_context_direct(self, date: str = None) -> Dict[str, Any]:
        """Direct file access fallback for article context."""
        cache_dir = Path(__file__).parent.parent / "data" / "cache" / "article_contexts"
        if not cache_dir.exists():
            return {"error": "No article contexts found", "articles": []}

        if date:
            file_path = cache_dir / f"{date}.json"
        else:
            files = sorted(cache_dir.glob("*.json"), reverse=True)
            file_path = files[0] if files else None

        if not file_path or not file_path.exists():
            return {"error": "No article context found", "articles": []}

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Direct article context fetch failed: {e}")
            return {"error": str(e), "articles": []}


class MCPToolRunner:
    """
    Tool Runner using MCP tools.

    Provides access to MCP tools for active operations like
    web scraping, GitHub API calls, and data fetching.
    """

    def __init__(self):
        """Initialize tool runner."""
        self._mcp_client = None
        if MCP_AVAILABLE:
            try:
                self._mcp_client = SyncMCPClient()
            except Exception as e:
                logger.warning(f"Failed to initialize MCP client for tools: {e}")

    def get_repo_health(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Get GitHub repository health metrics.

        Args:
            owner: GitHub username or org
            repo: Repository name

        Returns:
            Dict with stars, forks, issues, etc.
        """
        if self._mcp_client:
            try:
                result = self._mcp_client.call_tool(
                    "get_repo_health",
                    {"owner": owner, "repo": repo}
                )
                return json.loads(result) if isinstance(result, str) else result
            except Exception as e:
                logger.warning(f"MCP get_repo_health failed: {e}")

        return None

    def fetch_funding_data(self, company_name: str) -> Optional[Dict[str, Any]]:
        """Fetch funding information for a company.

        Args:
            company_name: Company name

        Returns:
            Dict with funding data
        """
        if self._mcp_client:
            try:
                result = self._mcp_client.call_tool(
                    "fetch_funding_data",
                    {"company_name": company_name}
                )
                return json.loads(result) if isinstance(result, str) else result
            except Exception as e:
                logger.warning(f"MCP fetch_funding_data failed: {e}")

        return None

    def semantic_search(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Search for semantically similar content.

        Args:
            query: Search query
            top_k: Max results

        Returns:
            List of matching results
        """
        if self._mcp_client:
            try:
                result = self._mcp_client.call_tool(
                    "semantic_search",
                    {"query": query, "top_k": top_k}
                )
                data = json.loads(result) if isinstance(result, str) else result
                return data.get("results", [])
            except Exception as e:
                logger.warning(f"MCP semantic_search failed: {e}")

        return []


# Global instances for easy access
_context_loader = None
_tool_runner = None


def get_context_loader(use_mcp: bool = True) -> MCPContextLoader:
    """Get global context loader instance."""
    global _context_loader
    if _context_loader is None:
        _context_loader = MCPContextLoader(use_mcp=use_mcp)
    return _context_loader


def get_tool_runner() -> MCPToolRunner:
    """Get global tool runner instance."""
    global _tool_runner
    if _tool_runner is None:
        _tool_runner = MCPToolRunner()
    return _tool_runner
