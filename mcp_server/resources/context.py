"""
Context Resources

Read-only access to cached article contexts and pipeline contexts.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from loguru import logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

CACHE_DIR = Path(__file__).parent.parent.parent / "data" / "cache"
ARTICLE_CONTEXTS_DIR = CACHE_DIR / "article_contexts"
PIPELINE_CONTEXTS_DIR = CACHE_DIR / "pipeline_contexts"
TREND_AGGREGATE_DIR = CACHE_DIR / "trend_aggregate"


def _get_latest_date_file(directory: Path, prefix: str = "") -> Optional[Path]:
    """Get the most recent date-based file in a directory."""
    if not directory.exists():
        return None

    pattern = f"{prefix}*.json" if prefix else "*.json"
    files = sorted(directory.glob(pattern), reverse=True)
    return files[0] if files else None


def _load_json_file(file_path: Path) -> dict:
    """Load and parse a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {file_path}: {e}")
        return {"error": str(e)}


def register(mcp: "FastMCP"):
    """Register context resources with MCP server."""

    @mcp.resource("context://articles/latest")
    def get_latest_articles() -> str:
        """Get the most recent cached article context.

        Returns evaluated articles with scores and metadata.
        """
        latest_file = _get_latest_date_file(ARTICLE_CONTEXTS_DIR)
        if not latest_file:
            return json.dumps({"error": "No article contexts found", "articles": []})

        data = _load_json_file(latest_file)
        if "error" in data:
            return json.dumps(data)

        # Return summary view
        articles = data.get("articles", [])
        return json.dumps({
            "report_date": data.get("report_date"),
            "article_count": len(articles),
            "articles": [
                {
                    "id": a.get("id"),
                    "title": a.get("title"),
                    "source": a.get("source"),
                    "published_date": a.get("published_date"),
                    "weighted_score": a.get("evaluation", {}).get("weighted_score"),
                    "key_takeaway": a.get("evaluation", {}).get("key_takeaway"),
                    "category": a.get("evaluation", {}).get("recommended_category")
                }
                for a in articles[:30]  # Limit to top 30
            ]
        })

    @mcp.resource("context://articles/{date}")
    def get_articles_by_date(date: str) -> str:
        """Get cached article context for a specific date.

        Args:
            date: Date in YYYYMMDD format (e.g., 20260122)
        """
        file_path = ARTICLE_CONTEXTS_DIR / f"{date}.json"
        if not file_path.exists():
            return json.dumps({"error": f"No articles found for date: {date}"})

        data = _load_json_file(file_path)
        if "error" in data:
            return json.dumps(data)

        articles = data.get("articles", [])
        return json.dumps({
            "report_date": data.get("report_date"),
            "generation_time": data.get("generation_time"),
            "article_count": len(articles),
            "articles": [
                {
                    "id": a.get("id"),
                    "title": a.get("title"),
                    "url": a.get("url"),
                    "source": a.get("source"),
                    "published_date": a.get("published_date"),
                    "credibility_score": a.get("credibility_score"),
                    "entities": a.get("entities"),
                    "evaluation": a.get("evaluation")
                }
                for a in articles
            ]
        })

    @mcp.resource("context://pipeline/{pipeline_name}")
    def get_pipeline_context(pipeline_name: str) -> str:
        """Get latest context for a specific pipeline.

        Args:
            pipeline_name: Pipeline name (e.g., 'news', 'investing', 'product', 'china_ai')
        """
        latest_file = _get_latest_date_file(PIPELINE_CONTEXTS_DIR, prefix=f"{pipeline_name}_")
        if not latest_file:
            return json.dumps({"error": f"No context found for pipeline: {pipeline_name}"})

        data = _load_json_file(latest_file)
        if "error" in data:
            return json.dumps(data)

        return json.dumps(data)

    @mcp.resource("context://pipelines/list")
    def list_pipeline_contexts() -> str:
        """List all available pipeline contexts with their dates."""
        if not PIPELINE_CONTEXTS_DIR.exists():
            return json.dumps({"error": "Pipeline contexts directory not found", "pipelines": []})

        pipelines = {}
        for file in PIPELINE_CONTEXTS_DIR.glob("*.json"):
            # Extract pipeline name and date from filename (e.g., "news_20260122.json")
            parts = file.stem.rsplit("_", 1)
            if len(parts) == 2:
                pipeline_name, date = parts
                if pipeline_name not in pipelines:
                    pipelines[pipeline_name] = []
                pipelines[pipeline_name].append(date)

        # Sort dates for each pipeline
        for name in pipelines:
            pipelines[name] = sorted(pipelines[name], reverse=True)

        return json.dumps({
            "pipelines": [
                {
                    "name": name,
                    "dates": dates[:7],  # Last 7 dates
                    "latest": dates[0] if dates else None
                }
                for name, dates in sorted(pipelines.items())
            ]
        })

    @mcp.resource("context://trends/aggregate")
    def get_trend_aggregate() -> str:
        """Get latest aggregated trend data across all sources."""
        latest_file = _get_latest_date_file(TREND_AGGREGATE_DIR, prefix="combined_")
        if not latest_file:
            return json.dumps({"error": "No trend aggregate found", "trends": []})

        data = _load_json_file(latest_file)
        if "error" in data:
            return json.dumps(data)

        return json.dumps(data)

    @mcp.resource("context://cache/stats")
    def get_cache_stats() -> str:
        """Get statistics about cached context data."""
        stats = {
            "cache_dir": str(CACHE_DIR),
            "article_contexts": {"available": False},
            "pipeline_contexts": {"available": False},
            "trend_aggregate": {"available": False}
        }

        if ARTICLE_CONTEXTS_DIR.exists():
            files = list(ARTICLE_CONTEXTS_DIR.glob("*.json"))
            if files:
                stats["article_contexts"] = {
                    "available": True,
                    "file_count": len(files),
                    "latest": sorted(files, reverse=True)[0].stem,
                    "oldest": sorted(files)[0].stem
                }

        if PIPELINE_CONTEXTS_DIR.exists():
            files = list(PIPELINE_CONTEXTS_DIR.glob("*.json"))
            if files:
                pipelines = set()
                for f in files:
                    parts = f.stem.rsplit("_", 1)
                    if len(parts) == 2:
                        pipelines.add(parts[0])
                stats["pipeline_contexts"] = {
                    "available": True,
                    "file_count": len(files),
                    "pipelines": sorted(pipelines)
                }

        if TREND_AGGREGATE_DIR.exists():
            files = list(TREND_AGGREGATE_DIR.glob("combined_*.json"))
            if files:
                stats["trend_aggregate"] = {
                    "available": True,
                    "file_count": len(files),
                    "latest": sorted(files, reverse=True)[0].stem
                }

        return json.dumps(stats)
