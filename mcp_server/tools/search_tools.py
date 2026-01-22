"""
Search Tools

Active operations for semantic search across BriefAI data.
"""

import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional
from loguru import logger

from mcp_server.errors import MCPToolError

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Paths
DATA_DIR = Path(__file__).parent.parent.parent / "data"
CHROMA_DB_PATH = DATA_DIR / "chroma_db"

# Lazy-loaded deduplicator
_semantic_dedup = None


def _get_semantic_dedup():
    """Lazy-load semantic deduplicator to avoid startup overhead."""
    global _semantic_dedup
    if _semantic_dedup is None:
        try:
            from utils.semantic_deduplication import SemanticDeduplicator, SEMANTIC_AVAILABLE
            if SEMANTIC_AVAILABLE:
                _semantic_dedup = SemanticDeduplicator(
                    db_path=str(CHROMA_DB_PATH),
                    strict_mode=False  # Lower threshold for search
                )
            else:
                logger.warning("Semantic search unavailable - missing dependencies")
        except Exception as e:
            logger.error(f"Failed to initialize semantic search: {e}")
    return _semantic_dedup


def register(mcp: "FastMCP"):
    """Register search tools with MCP server."""

    @mcp.tool()
    def semantic_search(query: str, top_k: int = 10, include_metadata: bool = True) -> dict:
        """Search for semantically similar content across indexed articles.

        Uses sentence embeddings (all-MiniLM-L6-v2) and vector search (Chroma)
        to find articles that are semantically related to the query.

        Args:
            query: Natural language search query
            top_k: Maximum number of results to return (1-50)
            include_metadata: Include article metadata in results

        Returns:
            Dict with query, results list, and search stats
        """
        dedup = _get_semantic_dedup()
        if dedup is None or not dedup.available:
            return {
                "query": query,
                "error": "Semantic search not available. Install: pip install sentence-transformers chromadb",
                "results": []
            }

        top_k = min(max(1, top_k), 50)  # Clamp to 1-50

        try:
            # Generate embedding for query
            embedding = dedup.model.encode([query])[0].tolist()

            # Query vector database
            results = dedup.collection.query(
                query_embeddings=[embedding],
                n_results=top_k,
                include=["metadatas", "distances"]
            )

            # Convert to response format
            search_results = []
            for i, doc_id in enumerate(results['ids'][0]):
                # Convert distance to similarity (Chroma cosine: 0=identical, 2=opposite)
                distance = results['distances'][0][i]
                similarity = 1.0 - (distance / 2.0)

                result = {
                    "id": doc_id,
                    "similarity": round(similarity, 4)
                }

                if include_metadata and results['metadatas']:
                    metadata = results['metadatas'][0][i]
                    result["title"] = metadata.get("title", "")
                    result["date"] = metadata.get("date", "")
                    result["source"] = metadata.get("source", "")
                    result["url"] = metadata.get("url", "")

                search_results.append(result)

            return {
                "query": query,
                "num_results": len(search_results),
                "results": search_results,
                "index_size": dedup.collection.count()
            }

        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            raise MCPToolError("search_tools", str(e))

    @mcp.tool()
    def search_trend_database(
        entity_name: Optional[str] = None,
        min_momentum: Optional[float] = None,
        days: int = 7,
        limit: int = 20
    ) -> dict:
        """Search the trend_radar.db for entities matching criteria.

        Args:
            entity_name: Filter by entity name (partial match)
            min_momentum: Minimum momentum score threshold
            days: Look back period in days
            limit: Maximum results (1-100)

        Returns:
            Dict with matching entities and their trend data
        """
        db_path = DATA_DIR / "trend_radar.db"
        if not db_path.exists():
            return {
                "error": "Trend database not found",
                "results": []
            }

        limit = min(max(1, limit), 100)

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Build query dynamically
            conditions = ["date > date('now', '-{} days')".format(days)]
            params = []

            if entity_name:
                conditions.append("entity_name LIKE ?")
                params.append(f"%{entity_name}%")

            if min_momentum is not None:
                conditions.append("momentum_score >= ?")
                params.append(min_momentum)

            where_clause = " AND ".join(conditions)

            query = f"""
                SELECT entity_name, momentum_score, article_count, date, source
                FROM trend_signals
                WHERE {where_clause}
                ORDER BY momentum_score DESC
                LIMIT ?
            """
            params.append(limit)

            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()

            return {
                "filters": {
                    "entity_name": entity_name,
                    "min_momentum": min_momentum,
                    "days": days
                },
                "num_results": len(results),
                "results": [
                    {
                        "entity": r[0],
                        "momentum": r[1],
                        "articles": r[2],
                        "date": r[3],
                        "source": r[4]
                    }
                    for r in results
                ]
            }

        except sqlite3.OperationalError as e:
            # Table might not exist
            logger.warning(f"Trend database query failed: {e}")
            return {
                "error": str(e),
                "suggestion": "Run trend scraper to populate the database",
                "results": []
            }
        except Exception as e:
            raise MCPToolError("search_tools", str(e))

    @mcp.tool()
    def search_conviction_scores(
        entity_name: Optional[str] = None,
        min_conviction: Optional[float] = None,
        recommendation: Optional[str] = None,
        limit: int = 20
    ) -> dict:
        """Search conviction scores from Devil's Advocate analysis.

        Args:
            entity_name: Filter by entity name (partial match)
            min_conviction: Minimum conviction score threshold
            recommendation: Filter by recommendation (ALERT, INVESTIGATE, MONITOR, IGNORE)
            limit: Maximum results (1-100)

        Returns:
            Dict with matching conviction analyses
        """
        db_path = DATA_DIR / "trend_radar.db"
        if not db_path.exists():
            return {
                "error": "Trend database not found",
                "results": []
            }

        limit = min(max(1, limit), 100)

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            conditions = []
            params = []

            if entity_name:
                conditions.append("entity_name LIKE ?")
                params.append(f"%{entity_name}%")

            if min_conviction is not None:
                conditions.append("conviction_score >= ?")
                params.append(min_conviction)

            if recommendation:
                valid_recs = ['ALERT', 'INVESTIGATE', 'MONITOR', 'IGNORE']
                if recommendation.upper() not in valid_recs:
                    return {
                        "error": f"Invalid recommendation. Valid: {valid_recs}",
                        "results": []
                    }
                conditions.append("recommendation = ?")
                params.append(recommendation.upper())

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            query = f"""
                SELECT
                    entity_name, entity_type, conviction_score,
                    conflict_intensity, recommendation,
                    bull_thesis, bear_thesis, synthesis, analyzed_at
                FROM conviction_scores
                WHERE {where_clause}
                ORDER BY conviction_score DESC, analyzed_at DESC
                LIMIT ?
            """
            params.append(limit)

            cursor.execute(query, params)
            results = cursor.fetchall()
            conn.close()

            return {
                "filters": {
                    "entity_name": entity_name,
                    "min_conviction": min_conviction,
                    "recommendation": recommendation
                },
                "num_results": len(results),
                "results": [
                    {
                        "entity": r[0],
                        "entity_type": r[1],
                        "conviction": r[2],
                        "conflict_intensity": r[3],
                        "recommendation": r[4],
                        "bull_thesis": r[5],
                        "bear_thesis": r[6],
                        "synthesis": r[7],
                        "analyzed_at": r[8]
                    }
                    for r in results
                ]
            }

        except sqlite3.OperationalError as e:
            logger.warning(f"Conviction scores query failed: {e}")
            return {
                "error": str(e),
                "suggestion": "Run Devil's Advocate analysis to populate conviction scores",
                "results": []
            }
        except Exception as e:
            raise MCPToolError("search_tools", str(e))
