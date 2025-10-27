"""
Context Retriever Module

Loads and retrieves cached article contexts for future reference, research, or Q&A.
Provides simple search and filtering capabilities across cached articles.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class ContextRetriever:
    """Retrieves cached article contexts from storage"""

    def __init__(self, cache_dir: str = "./data/cache/article_contexts"):
        """
        Initialize context retriever

        Args:
            cache_dir: Directory where article contexts are cached
        """
        self.cache_dir = Path(cache_dir)
        if not self.cache_dir.exists():
            logger.warning(f"Cache directory does not exist: {cache_dir}")
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def list_available_reports(self) -> List[Dict[str, Any]]:
        """
        List all available cached reports

        Returns:
            List of dicts with report metadata:
            [
                {
                    "date": "2024-10-25",
                    "file_path": "20241025.json",
                    "article_count": 15,
                    "generation_time": "2024-10-25T10:30:00"
                }
            ]
        """
        reports = []

        for cache_file in sorted(self.cache_dir.glob("*.json"), reverse=True):
            try:
                # Parse date from filename
                file_date = datetime.strptime(cache_file.stem, "%Y%m%d")

                # Load metadata
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                reports.append({
                    "date": file_date.strftime("%Y-%m-%d"),
                    "file_path": cache_file.name,
                    "article_count": len(data.get("articles", [])),
                    "generation_time": data.get("generation_time", "")
                })

            except (ValueError, json.JSONDecodeError) as e:
                logger.warning(f"Skipping invalid cache file {cache_file.name}: {e}")
                continue

        return reports

    def load_report_by_date(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Load a cached report by date

        Args:
            date: Date string in YYYY-MM-DD or YYYYMMDD format

        Returns:
            Full report data including all articles, or None if not found
        """
        # Normalize date format to YYYYMMDD
        try:
            if '-' in date:
                date_obj = datetime.strptime(date, "%Y-%m-%d")
            else:
                date_obj = datetime.strptime(date, "%Y%m%d")

            filename = date_obj.strftime("%Y%m%d.json")
            cache_path = self.cache_dir / filename

            if not cache_path.exists():
                logger.warning(f"No cached report found for date: {date}")
                return None

            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            logger.info(f"Loaded report from {date} with {len(data.get('articles', []))} articles")
            return data

        except ValueError as e:
            logger.error(f"Invalid date format: {date}. Use YYYY-MM-DD or YYYYMMDD")
            return None
        except Exception as e:
            logger.error(f"Failed to load report for {date}: {e}")
            return None

    def load_latest_report(self) -> Optional[Dict[str, Any]]:
        """
        Load the most recent cached report

        Returns:
            Full report data, or None if no reports exist
        """
        reports = self.list_available_reports()
        if not reports:
            logger.warning("No cached reports found")
            return None

        latest_date = reports[0]["date"]
        return self.load_report_by_date(latest_date)

    def get_article_by_id(self, date: str, article_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific article by ID from a cached report

        Args:
            date: Report date (YYYY-MM-DD or YYYYMMDD)
            article_id: Article ID (e.g., "001", "015")

        Returns:
            Article data, or None if not found
        """
        report = self.load_report_by_date(date)
        if not report:
            return None

        for article in report.get("articles", []):
            if article.get("id") == article_id:
                logger.info(f"Found article {article_id}: {article.get('title')}")
                return article

        logger.warning(f"Article {article_id} not found in report {date}")
        return None

    def search_by_keyword(
        self,
        keyword: str,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search_fields: List[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search cached articles by keyword

        Args:
            keyword: Search term (case-insensitive)
            date_from: Start date (YYYY-MM-DD) - optional
            date_to: End date (YYYY-MM-DD) - optional
            search_fields: Fields to search in (default: ["title", "full_content"])

        Returns:
            List of matching articles with metadata
        """
        if search_fields is None:
            search_fields = ["title", "full_content"]

        keyword_lower = keyword.lower()
        results = []

        # Get date range
        reports = self.list_available_reports()

        for report_meta in reports:
            report_date = report_meta["date"]

            # Filter by date range
            if date_from and report_date < date_from:
                continue
            if date_to and report_date > date_to:
                continue

            # Load report
            report = self.load_report_by_date(report_date)
            if not report:
                continue

            # Search articles
            for article in report.get("articles", []):
                # Check if keyword matches any search field
                match = False
                for field in search_fields:
                    field_value = str(article.get(field, "")).lower()
                    if keyword_lower in field_value:
                        match = True
                        break

                if match:
                    # Add report metadata
                    article["report_date"] = report_date
                    results.append(article)

        logger.info(f"Found {len(results)} articles matching '{keyword}'")
        return results

    def search_by_entity(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search cached articles by entity

        Args:
            entity_name: Entity name to search for (case-insensitive)
            entity_type: Optional entity type filter (companies, models, people, locations, other)
            date_from: Start date (YYYY-MM-DD) - optional
            date_to: End date (YYYY-MM-DD) - optional

        Returns:
            List of matching articles
        """
        entity_lower = entity_name.lower()
        results = []

        # Get reports in date range
        reports = self.list_available_reports()

        for report_meta in reports:
            report_date = report_meta["date"]

            # Filter by date range
            if date_from and report_date < date_from:
                continue
            if date_to and report_date > date_to:
                continue

            # Load report
            report = self.load_report_by_date(report_date)
            if not report:
                continue

            # Search articles
            for article in report.get("articles", []):
                entities = article.get("entities", {})

                # If entity_type specified, search only that type
                if entity_type:
                    entity_list = entities.get(entity_type, [])
                    if any(entity_lower in e.lower() for e in entity_list):
                        article["report_date"] = report_date
                        article["matched_entity_type"] = entity_type
                        results.append(article)
                else:
                    # Search all entity types
                    for etype, elist in entities.items():
                        if any(entity_lower in e.lower() for e in elist):
                            article["report_date"] = report_date
                            article["matched_entity_type"] = etype
                            results.append(article)
                            break  # Avoid duplicates

        logger.info(f"Found {len(results)} articles mentioning entity '{entity_name}'")
        return results

    def get_article_statistics(self, date: str) -> Dict[str, Any]:
        """
        Get statistics for a cached report

        Args:
            date: Report date (YYYY-MM-DD or YYYYMMDD)

        Returns:
            Statistics dict with counts, averages, etc.
        """
        report = self.load_report_by_date(date)
        if not report:
            return {}

        articles = report.get("articles", [])

        if not articles:
            return {
                "total_articles": 0,
                "report_date": date
            }

        # Calculate statistics
        total_articles = len(articles)
        avg_credibility = sum(a.get("credibility_score", 0) for a in articles) / total_articles
        avg_relevance = sum(a.get("relevance_score", 0) for a in articles) / total_articles

        # Count entities
        all_entities = {
            "companies": set(),
            "models": set(),
            "people": set(),
            "locations": set(),
            "other": set()
        }

        sources = set()

        for article in articles:
            sources.add(article.get("source", ""))

            entities = article.get("entities", {})
            for etype, elist in entities.items():
                if etype in all_entities:
                    all_entities[etype].update(elist)

        return {
            "report_date": date,
            "total_articles": total_articles,
            "avg_credibility_score": round(avg_credibility, 2),
            "avg_relevance_score": round(avg_relevance, 2),
            "unique_sources": len(sources),
            "sources": list(sources),
            "entity_counts": {
                etype: len(elist) for etype, elist in all_entities.items()
            },
            "top_entities": {
                etype: list(elist)[:10] for etype, elist in all_entities.items()
            }
        }


if __name__ == "__main__":
    # Test context retriever
    retriever = ContextRetriever()

    print("=== Available Reports ===")
    reports = retriever.list_available_reports()
    for report in reports:
        print(f"{report['date']}: {report['article_count']} articles")

    if reports:
        print("\n=== Latest Report ===")
        latest = retriever.load_latest_report()
        if latest:
            print(f"Date: {latest.get('report_date')}")
            print(f"Articles: {len(latest.get('articles', []))}")

            print("\n=== Statistics ===")
            stats = retriever.get_article_statistics(latest.get('report_date'))
            print(json.dumps(stats, indent=2, ensure_ascii=False))

            print("\n=== Search Test: 'GPT' ===")
            results = retriever.search_by_keyword("GPT")
            for result in results[:3]:  # Show first 3
                print(f"- {result.get('title')} ({result.get('report_date')})")

            print("\n=== Entity Search Test: 'OpenAI' ===")
            results = retriever.search_by_entity("OpenAI")
            for result in results[:3]:
                print(f"- {result.get('title')} ({result.get('report_date')})")
