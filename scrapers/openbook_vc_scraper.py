#!/usr/bin/env python3
"""
OpenBook VC Database Scraper

Fetches venture capital firm and investor data from DoltHub's OpenBook database.
Source: https://www.dolthub.com/repositories/iloveitaly/venture_capital_firms

Data includes:
- VC firm names and websites
- Team member/investor contact info (name, role, email, twitter, linkedin)
"""

import json
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import quote

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class OpenBookVCScraper:
    """Scraper for OpenBook VC database on DoltHub"""

    DOLTHUB_API_BASE = "https://www.dolthub.com/api/v1alpha1/iloveitaly/venture_capital_firms/main"

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _query_dolthub(self, sql: str) -> Dict[str, Any]:
        """Execute SQL query against DoltHub API"""
        url = f"{self.DOLTHUB_API_BASE}?q={quote(sql)}"
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"DoltHub API error: {e}")
            return {"rows": [], "query_execution_status": "Error", "error": str(e)}

    def fetch_vc_firms(self) -> List[Dict[str, Any]]:
        """Fetch all VC firms from the database"""
        logger.info("Fetching VC firms from DoltHub...")

        result = self._query_dolthub("SELECT name, url, normalized_url FROM venture_capital_firms")

        if result.get("query_execution_status") != "Success":
            logger.error(f"Query failed: {result.get('query_execution_message', 'Unknown error')}")
            return []

        firms = []
        for row in result.get("rows", []):
            firms.append({
                "name": row.get("name", ""),
                "url": row.get("url", ""),
                "normalized_url": row.get("normalized_url", ""),
            })

        logger.info(f"Fetched {len(firms)} VC firms")
        return firms

    def fetch_investors(self) -> List[Dict[str, Any]]:
        """Fetch all investors/team members from the database"""
        logger.info("Fetching investors from DoltHub...")

        result = self._query_dolthub(
            "SELECT name, normalized_url, person_name, person_role, "
            "role_description, email, twitter, linkedin FROM people"
        )

        if result.get("query_execution_status") != "Success":
            logger.error(f"Query failed: {result.get('query_execution_message', 'Unknown error')}")
            return []

        investors = []
        for row in result.get("rows", []):
            # Only include investors with contact info
            has_contact = any([
                row.get("email"),
                row.get("twitter"),
                row.get("linkedin")
            ])

            investors.append({
                "firm_name": row.get("name", ""),
                "firm_url": row.get("normalized_url", ""),
                "person_name": row.get("person_name", ""),
                "role": row.get("person_role", ""),
                "role_description": row.get("role_description", ""),
                "email": row.get("email", ""),
                "twitter": row.get("twitter", ""),
                "linkedin": row.get("linkedin", ""),
                "has_contact_info": has_contact,
            })

        logger.info(f"Fetched {len(investors)} investors")
        return investors

    def _identify_ai_focused_firms(self, firms: List[Dict], investors: List[Dict]) -> List[str]:
        """Identify firms likely focused on AI based on keywords"""
        ai_keywords = [
            "ai", "artificial intelligence", "machine learning", "ml", "deep learning",
            "neural", "llm", "gpt", "foundation model", "generative", "computer vision",
            "nlp", "natural language", "robotics", "autonomous", "data science"
        ]

        ai_focused = set()

        # Check firm names
        for firm in firms:
            name_lower = firm.get("name", "").lower()
            if any(kw in name_lower for kw in ai_keywords):
                ai_focused.add(firm.get("name"))

        # Check investor roles/descriptions for AI keywords
        for inv in investors:
            desc = (inv.get("role_description", "") + " " + inv.get("role", "")).lower()
            if any(kw in desc for kw in ai_keywords):
                ai_focused.add(inv.get("firm_name"))

        return list(ai_focused)

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Main entry point - fetch all data and return standardized output"""
        logger.info("Starting OpenBook VC scraper...")

        # Fetch data
        firms = self.fetch_vc_firms()
        investors = self.fetch_investors()

        # Identify AI-focused firms
        ai_focused_firms = self._identify_ai_focused_firms(firms, investors)

        # Aggregate by firm
        firm_investor_map: Dict[str, List[Dict]] = {}
        for inv in investors:
            firm_name = inv.get("firm_name", "")
            if firm_name:
                if firm_name not in firm_investor_map:
                    firm_investor_map[firm_name] = []
                firm_investor_map[firm_name].append(inv)

        # Build enriched firm records
        enriched_firms = []
        for firm in firms:
            firm_name = firm.get("name", "")
            team = firm_investor_map.get(firm_name, [])

            enriched_firms.append({
                **firm,
                "team_count": len(team),
                "team_with_contact": sum(1 for t in team if t.get("has_contact_info")),
                "ai_focus": firm_name in ai_focused_firms,
            })

        # Build result
        result = {
            "source": "openbook_vc",
            "scraped_at": datetime.now().isoformat(),
            "dolthub_repo": "iloveitaly/venture_capital_firms",
            "total_firms": len(firms),
            "total_investors": len(investors),
            "investors_with_contact": sum(1 for i in investors if i.get("has_contact_info")),
            "ai_focused_firms_count": len(ai_focused_firms),
            "ai_focused_firms": ai_focused_firms,
            "vc_firms": enriched_firms,
            "investors": investors,
            "summary": {
                "top_firms_by_team_size": sorted(
                    enriched_firms,
                    key=lambda x: x.get("team_count", 0),
                    reverse=True
                )[:10],
            }
        }

        # Save to file
        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"openbook_vc_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved OpenBook VC data to {output_file}")

        logger.info(
            f"OpenBook VC scrape complete: {len(firms)} firms, "
            f"{len(investors)} investors, {len(ai_focused_firms)} AI-focused"
        )

        return result


def main():
    """CLI entry point"""
    scraper = OpenBookVCScraper()
    result = scraper.run(save=True)

    print(f"\nOpenBook VC Scraper Results:")
    print(f"  Total VC Firms: {result['total_firms']}")
    print(f"  Total Investors: {result['total_investors']}")
    print(f"  With Contact Info: {result['investors_with_contact']}")
    print(f"  AI-Focused Firms: {result['ai_focused_firms_count']}")

    if result.get("summary", {}).get("top_firms_by_team_size"):
        print(f"\n  Top Firms by Team Size:")
        for firm in result["summary"]["top_firms_by_team_size"][:5]:
            print(f"    - {firm['name']}: {firm['team_count']} members")


if __name__ == "__main__":
    main()
