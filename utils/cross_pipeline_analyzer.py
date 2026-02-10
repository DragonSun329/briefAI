"""
Cross-Pipeline Analyzer

Analyzes entities and trends across multiple pipeline reports to surface
cross-pipeline insights for the CEO dashboard.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EntityMention:
    """Represents an entity mention across pipelines"""
    entity_name: str
    entity_type: str  # companies, models, people, topics
    pipeline_mentions: Dict[str, int] = field(default_factory=dict)  # pipeline_id -> count
    article_titles: Dict[str, List[str]] = field(default_factory=dict)  # pipeline_id -> [titles]
    total_mentions: int = 0
    pipeline_count: int = 0  # Number of pipelines where entity appears

    def add_mention(self, pipeline_id: str, article_title: str):
        """Add a mention from a pipeline"""
        if pipeline_id not in self.pipeline_mentions:
            self.pipeline_mentions[pipeline_id] = 0
            self.article_titles[pipeline_id] = []
        self.pipeline_mentions[pipeline_id] += 1
        if article_title not in self.article_titles[pipeline_id]:
            self.article_titles[pipeline_id].append(article_title)
        self.total_mentions = sum(self.pipeline_mentions.values())
        self.pipeline_count = len(self.pipeline_mentions)


@dataclass
class PipelineData:
    """Holds data from a single pipeline"""
    pipeline_id: str
    pipeline_name: str
    report_date: str
    articles: List[Dict[str, Any]]
    article_count: int
    top_articles: List[Dict[str, Any]]  # Top 5 by weighted_score
    executive_summary: str = ""


class CrossPipelineAnalyzer:
    """Analyzes data across multiple pipelines"""

    PIPELINE_DISPLAY_NAMES = {
        "news": "AI News",
        "product": "Products",
        "investing": "Investing",
        "china_ai": "中国AI"
    }

    PIPELINE_ICONS = {
        "news": "📰",
        "product": "🚀",
        "investing": "💰",
        "china_ai": "🇨🇳"
    }

    PIPELINE_COLORS = {
        "news": "#1f77b4",      # Blue
        "product": "#2ca02c",   # Green
        "investing": "#ff7f0e",  # Gold/Orange
        "china_ai": "#e41a1c"   # Red
    }

    def __init__(self, cache_dir: str = "./data/cache/pipeline_contexts"):
        self.cache_dir = Path(cache_dir)
        self.pipelines: Dict[str, PipelineData] = {}
        self.entity_index: Dict[str, EntityMention] = {}  # entity_key -> EntityMention

    def load_pipelines_for_date(self, date_str: str) -> Dict[str, PipelineData]:
        """
        Load all pipeline data for a specific date

        Args:
            date_str: Date in YYYYMMDD format

        Returns:
            Dict mapping pipeline_id to PipelineData
        """
        self.pipelines = {}
        self.entity_index = {}

        # Look for pipeline cache files for this date
        for pipeline_id in ["news", "product", "investing", "china_ai"]:
            cache_file = self.cache_dir / f"{pipeline_id}_{date_str}.json"

            if cache_file.exists():
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    articles = data.get("articles", [])

                    # Sort by weighted_score to get top articles
                    sorted_articles = sorted(
                        articles,
                        key=lambda x: x.get("weighted_score", 0),
                        reverse=True
                    )

                    self.pipelines[pipeline_id] = PipelineData(
                        pipeline_id=pipeline_id,
                        pipeline_name=self.PIPELINE_DISPLAY_NAMES.get(pipeline_id, pipeline_id),
                        report_date=data.get("report_date", date_str),
                        articles=articles,
                        article_count=len(articles),
                        top_articles=sorted_articles[:5]
                    )

                    # Index entities from this pipeline
                    self._index_entities(pipeline_id, articles)

                except Exception as e:
                    print(f"Error loading {cache_file}: {e}")

        return self.pipelines

    def _index_entities(self, pipeline_id: str, articles: List[Dict[str, Any]]):
        """Index entities from articles for cross-pipeline analysis"""
        for article in articles:
            entities = article.get("searchable_entities", {})
            title = article.get("title", "")

            # Index each entity type
            for entity_type in ["companies", "models", "people"]:
                for entity_name in entities.get(entity_type, []):
                    if not entity_name:
                        continue

                    # Normalize entity name for matching
                    entity_key = f"{entity_type}:{entity_name.lower().strip()}"

                    if entity_key not in self.entity_index:
                        self.entity_index[entity_key] = EntityMention(
                            entity_name=entity_name,
                            entity_type=entity_type
                        )

                    self.entity_index[entity_key].add_mention(pipeline_id, title)

    def get_cross_pipeline_entities(self, min_pipelines: int = 2) -> List[EntityMention]:
        """
        Get entities that appear in multiple pipelines

        Args:
            min_pipelines: Minimum number of pipelines entity must appear in

        Returns:
            List of EntityMention sorted by total mentions
        """
        cross_entities = [
            entity for entity in self.entity_index.values()
            if entity.pipeline_count >= min_pipelines
        ]

        return sorted(cross_entities, key=lambda x: x.total_mentions, reverse=True)

    def get_hot_entities(self, top_n: int = 10) -> List[EntityMention]:
        """
        Get the hottest entities across all pipelines

        Args:
            top_n: Number of top entities to return

        Returns:
            List of top EntityMention by total mentions
        """
        all_entities = sorted(
            self.entity_index.values(),
            key=lambda x: (x.pipeline_count, x.total_mentions),
            reverse=True
        )
        return all_entities[:top_n]

    def get_bubble_chart_data(self) -> List[Dict[str, Any]]:
        """
        Generate data for Plotly bubble chart visualization

        Returns:
            List of dicts with x, y, size, color, name, hover data
        """
        bubble_data = []

        for entity in self.entity_index.values():
            if entity.total_mentions < 1:
                continue

            # Determine dominant pipeline (most mentions)
            dominant_pipeline = max(
                entity.pipeline_mentions.keys(),
                key=lambda p: entity.pipeline_mentions[p]
            )

            # Create hover text with breakdown
            hover_parts = [f"<b>{entity.entity_name}</b> ({entity.entity_type})"]
            hover_parts.append(f"Total mentions: {entity.total_mentions}")
            hover_parts.append("---")
            for pid, count in entity.pipeline_mentions.items():
                icon = self.PIPELINE_ICONS.get(pid, "")
                name = self.PIPELINE_DISPLAY_NAMES.get(pid, pid)
                hover_parts.append(f"{icon} {name}: {count}")

            bubble_data.append({
                "name": entity.entity_name,
                "entity_type": entity.entity_type,
                "x": entity.pipeline_count,  # X = number of pipelines
                "y": entity.total_mentions,  # Y = total mentions
                "size": max(10, entity.total_mentions * 5),  # Bubble size
                "color": self.PIPELINE_COLORS.get(dominant_pipeline, "#888"),
                "dominant_pipeline": dominant_pipeline,
                "hover": "<br>".join(hover_parts),
                "pipeline_breakdown": entity.pipeline_mentions
            })

        return bubble_data

    def get_entity_appearances_for_article(
        self,
        article: Dict[str, Any],
        current_pipeline: str
    ) -> List[Dict[str, Any]]:
        """
        Check if entities in an article appear in other pipelines

        Args:
            article: Article dict with searchable_entities
            current_pipeline: The pipeline this article is from

        Returns:
            List of other pipelines where article entities appear
        """
        other_appearances = []
        entities = article.get("searchable_entities", {})

        for entity_type in ["companies", "models", "people"]:
            for entity_name in entities.get(entity_type, []):
                if not entity_name:
                    continue

                entity_key = f"{entity_type}:{entity_name.lower().strip()}"

                if entity_key in self.entity_index:
                    entity = self.entity_index[entity_key]

                    # Find other pipelines
                    for pid in entity.pipeline_mentions:
                        if pid != current_pipeline:
                            other_appearances.append({
                                "pipeline_id": pid,
                                "pipeline_name": self.PIPELINE_DISPLAY_NAMES.get(pid, pid),
                                "icon": self.PIPELINE_ICONS.get(pid, ""),
                                "entity_name": entity_name,
                                "mentions": entity.pipeline_mentions[pid]
                            })

        # Deduplicate by pipeline
        seen_pipelines = set()
        unique_appearances = []
        for app in other_appearances:
            if app["pipeline_id"] not in seen_pipelines:
                seen_pipelines.add(app["pipeline_id"])
                unique_appearances.append(app)

        return unique_appearances

    def get_available_dates(self) -> List[str]:
        """Get list of dates with pipeline data available"""
        dates = set()

        if self.cache_dir.exists():
            for f in self.cache_dir.glob("*.json"):
                # Extract date from filename like "investing_20260106.json"
                parts = f.stem.split("_")
                if len(parts) >= 2:
                    date_part = parts[-1]
                    if len(date_part) == 8 and date_part.isdigit():
                        dates.add(date_part)

        return sorted(dates, reverse=True)

    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics across all loaded pipelines"""
        stats = {
            "total_articles": 0,
            "pipeline_counts": {},
            "cross_pipeline_entities": 0,
            "total_entities": len(self.entity_index),
            "top_entity": None
        }

        for pid, pdata in self.pipelines.items():
            stats["pipeline_counts"][pid] = pdata.article_count
            stats["total_articles"] += pdata.article_count

        cross_entities = self.get_cross_pipeline_entities(min_pipelines=2)
        stats["cross_pipeline_entities"] = len(cross_entities)

        if cross_entities:
            stats["top_entity"] = {
                "name": cross_entities[0].entity_name,
                "mentions": cross_entities[0].total_mentions,
                "pipelines": cross_entities[0].pipeline_count
            }

        return stats


if __name__ == "__main__":
    # Test the analyzer
    analyzer = CrossPipelineAnalyzer()

    # Get available dates
    dates = analyzer.get_available_dates()
    print(f"Available dates: {dates}")

    if dates:
        # Load latest date
        latest = dates[0]
        print(f"\nLoading data for {latest}...")

        pipelines = analyzer.load_pipelines_for_date(latest)

        for pid, pdata in pipelines.items():
            print(f"\n{pdata.pipeline_name}: {pdata.article_count} articles")
            print(f"  Top article: {pdata.top_articles[0]['title'] if pdata.top_articles else 'N/A'}")

        # Cross-pipeline entities
        print("\n--- Cross-Pipeline Entities ---")
        cross_entities = analyzer.get_cross_pipeline_entities()
        for entity in cross_entities[:5]:
            print(f"{entity.entity_name} ({entity.entity_type}): {entity.pipeline_mentions}")

        # Hot entities
        print("\n--- Hot Entities ---")
        hot = analyzer.get_hot_entities(5)
        for entity in hot:
            print(f"{entity.entity_name}: {entity.total_mentions} mentions across {entity.pipeline_count} pipelines")

        # Summary stats
        print("\n--- Summary Stats ---")
        stats = analyzer.get_summary_stats()
        print(json.dumps(stats, indent=2))