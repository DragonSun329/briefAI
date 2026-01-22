"""
Data Tools

Active operations for fetching funding data and running scrapers.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from loguru import logger

from mcp_server.errors import MCPToolError

if TYPE_CHECKING:
    from fastmcp import FastMCP

# Path to scrapers and data directories
SCRAPERS_DIR = Path(__file__).parent.parent.parent / "scrapers"
DATA_DIR = Path(__file__).parent.parent.parent / "data"


def _get_latest_file(pattern: str) -> Optional[Path]:
    """Get the most recent file matching a pattern."""
    alt_signals_dir = DATA_DIR / "alternative_signals"
    if not alt_signals_dir.exists():
        return None

    files = sorted(alt_signals_dir.glob(pattern), reverse=True)
    return files[0] if files else None


def register(mcp: "FastMCP"):
    """Register data tools with MCP server."""

    @mcp.tool()
    def fetch_funding_data(company_name: str) -> dict:
        """Fetch funding information for a company from cached Crunchbase/OpenBook data.

        Args:
            company_name: Name of the company to look up

        Returns:
            Dict with funding rounds, investors, total raised
        """
        # Try Crunchbase data first
        crunchbase_file = _get_latest_file("crunchbase_*.json")
        if crunchbase_file:
            try:
                with open(crunchbase_file, 'r') as f:
                    data = json.load(f)
                    for company in data.get("companies", []):
                        if company.get("name", "").lower() == company_name.lower():
                            return {
                                "source": "crunchbase",
                                "name": company.get("name"),
                                "total_raised": company.get("total_raised"),
                                "last_funding_round": company.get("last_funding_round"),
                                "funding_stage": company.get("funding_stage"),
                                "investors": company.get("investors", []),
                            }
            except Exception as e:
                logger.debug(f"Could not read Crunchbase data: {e}")

        # Try OpenBook VC data
        openbook_file = _get_latest_file("openbook_vc_*.json")
        if openbook_file:
            try:
                with open(openbook_file, 'r') as f:
                    data = json.load(f)
                    # Search in VC firms for portfolio companies
                    for firm in data.get("vc_firms", []):
                        if company_name.lower() in firm.get("name", "").lower():
                            return {
                                "source": "openbook_vc",
                                "name": firm.get("name"),
                                "website": firm.get("website"),
                                "team": firm.get("team", [])[:5],  # Limit team members
                                "ai_focus": firm.get("ai_focus", False),
                            }
            except Exception as e:
                logger.debug(f"Could not read OpenBook data: {e}")

        return {
            "source": None,
            "message": f"No funding data found for '{company_name}'",
            "suggestion": "Try running the crunchbase or openbook_vc scraper"
        }

    @mcp.tool()
    def run_scraper(scraper_name: str, timeout: int = 300) -> dict:
        """Run a specific scraper to fetch fresh data.

        Args:
            scraper_name: Name of the scraper (e.g., 'github', 'hackernews', 'crunchbase')
            timeout: Maximum execution time in seconds (default 5 minutes)

        Returns:
            Dict with scraper status and output file path
        """
        # Validate scraper name (prevent command injection)
        valid_scrapers = [
            'github', 'hackernews', 'reddit', 'arxiv', 'huggingface',
            'paperswithcode', 'google_trends', 'polymarket', 'metaculus',
            'manifold', 'crunchbase', 'openbook_vc', 'ai_labs', 'news_search'
        ]

        if scraper_name not in valid_scrapers:
            raise MCPToolError(
                "data_tools",
                f"Invalid scraper: {scraper_name}. Valid options: {', '.join(valid_scrapers)}"
            )

        scraper_file = SCRAPERS_DIR / f"{scraper_name}_scraper.py"
        if not scraper_file.exists():
            raise MCPToolError(
                "data_tools",
                f"Scraper file not found: {scraper_file}"
            )

        try:
            result = subprocess.run(
                [sys.executable, str(scraper_file)],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(SCRAPERS_DIR.parent)  # Run from project root
            )

            if result.returncode != 0:
                return {
                    "status": "error",
                    "scraper": scraper_name,
                    "stderr": result.stderr[:1000] if result.stderr else None,
                    "return_code": result.returncode
                }

            # Find the output file
            output_file = _get_latest_file(f"{scraper_name}_*.json")

            return {
                "status": "success",
                "scraper": scraper_name,
                "output_file": str(output_file) if output_file else None,
                "stdout_preview": result.stdout[:500] if result.stdout else None
            }

        except subprocess.TimeoutExpired:
            raise MCPToolError(
                "data_tools",
                f"Scraper {scraper_name} timed out after {timeout}s"
            )
        except Exception as e:
            raise MCPToolError("data_tools", str(e))

    @mcp.tool()
    def list_available_data() -> dict:
        """List all available cached data files with their dates.

        Returns:
            Dict with data sources and their latest file timestamps
        """
        alt_signals_dir = DATA_DIR / "alternative_signals"
        crunchbase_dir = DATA_DIR / "crunchbase"
        kaggle_dir = DATA_DIR / "kaggle"

        data_sources = {}

        # Check alternative_signals directory
        if alt_signals_dir.exists():
            for pattern in ['github_*.json', 'hackernews_*.json', 'reddit_*.json',
                           'arxiv_*.json', 'huggingface_*.json', 'crunchbase_*.json',
                           'openbook_vc_*.json', 'polymarket_*.json', 'metaculus_*.json']:
                files = sorted(alt_signals_dir.glob(pattern), reverse=True)
                if files:
                    source_name = pattern.replace('_*.json', '')
                    data_sources[source_name] = {
                        "latest_file": files[0].name,
                        "file_count": len(files),
                        "last_modified": files[0].stat().st_mtime
                    }

        # Check crunchbase directory
        if crunchbase_dir.exists():
            files = list(crunchbase_dir.glob("*.json"))
            if files:
                data_sources["crunchbase_raw"] = {
                    "file_count": len(files),
                    "directory": str(crunchbase_dir)
                }

        # Check kaggle directory
        if kaggle_dir.exists():
            files = list(kaggle_dir.glob("*.csv"))
            if files:
                data_sources["kaggle"] = {
                    "file_count": len(files),
                    "files": [f.name for f in files[:5]]  # First 5 files
                }

        return {
            "data_directory": str(DATA_DIR),
            "sources": data_sources,
            "total_sources": len(data_sources)
        }
