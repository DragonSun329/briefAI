"""
Trend aggregation and detection logic.

This module provides the TrendAggregator class for:
1. Aggregating entity mentions across weekly briefings
2. Detecting trend signals (velocity spikes, new entities, score surges, combo signals)
3. Computing confidence scores for detected signals
"""

from typing import List, Dict, Optional, Any
from collections import defaultdict
from pathlib import Path
import json

from utils.context_retriever import ContextRetriever
from utils.entity_extractor import EntityExtractor
from utils.schemas import EntityMention, TrendSignal
from utils.entity_normalizer import normalize_entity_name


class TrendAggregator:
    """
    Aggregates entity mentions and detects trend signals.

    This class provides the core logic for:
    - Counting entity mentions per week
    - Computing baseline activity over multiple weeks
    - Detecting unusual patterns (velocity spikes, score surges, new entities)
    - Scoring confidence for each detected signal
    """

    def __init__(
        self,
        context: ContextRetriever,
        config_path: str = "./config/trend_detection.json"
    ):
        """
        Initialize trend aggregator.

        Args:
            context: ContextRetriever instance for accessing weekly articles
            config_path: Path to trend detection configuration JSON
        """
        self.context = context
        self.entity_extractor = EntityExtractor()

        # Load configuration
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def aggregate_week(self, week_id: str) -> List[EntityMention]:
        """
        Aggregate entity mentions for a single week.

        Groups all entity mentions from a week's articles, computes statistics
        (mention count, avg/max/total scores), and returns EntityMention objects.

        Args:
            week_id: Week identifier (e.g., "2025-W01")

        Returns:
            List of EntityMention objects for the week
        """
        # Get all articles for the week
        articles = self._get_articles_for_week(week_id)

        if not articles:
            return []

        # Group by entity
        entity_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'count': 0,
            'scores': [],
            'article_ids': [],
            'display_name': None,
            'entity_type': None
        })

        for article in articles:
            # Get article score (weighted_score or composite)
            article_score = article.get('weighted_score') or article.get('composite_score', 0.0)
            article_id = article.get('id', '')

            # Extract entities from article (check if already extracted)
            entities_dict = article.get('entities', {})

            # If entities not already extracted, extract them now
            if not entities_dict and article.get('full_content'):
                entities_dict = self.entity_extractor.extract_entities(
                    article['full_content']
                )

            # Process each entity type
            for entity_type_plural in ['companies', 'models', 'topics', 'people']:
                entity_type_singular = entity_type_plural.rstrip('s')  # "companies" -> "company"
                if entity_type_singular == 'companie':  # Handle "companies" edge case
                    entity_type_singular = 'company'
                elif entity_type_singular == 'people':  # Handle "people" edge case
                    entity_type_singular = 'person'

                entity_list = entities_dict.get(entity_type_plural, [])

                for entity_name in entity_list:
                    # Normalize entity name for grouping
                    entity_id = normalize_entity_name(entity_name, entity_type_singular)

                    # Skip empty normalized names
                    if not entity_id:
                        continue

                    # Accumulate data
                    entity_data[entity_id]['count'] += 1
                    entity_data[entity_id]['scores'].append(article_score)
                    if article_id not in entity_data[entity_id]['article_ids']:
                        entity_data[entity_id]['article_ids'].append(article_id)

                    # Store display name and type (use first occurrence)
                    if entity_data[entity_id]['display_name'] is None:
                        entity_data[entity_id]['display_name'] = entity_name
                        entity_data[entity_id]['entity_type'] = entity_type_singular

        # Convert to EntityMention objects
        mentions = []
        for entity_id, data in entity_data.items():
            scores = data['scores']

            # Handle empty score lists safely
            if scores:
                avg_score = sum(scores) / len(scores)
                max_score = max(scores)
                total_score = sum(scores)
            else:
                avg_score = 0.0
                max_score = 0.0
                total_score = 0.0

            mention = EntityMention(
                entity_id=entity_id,
                entity_name=data['display_name'] or entity_id,
                entity_type=data['entity_type'] or 'topic',  # Fallback to topic
                week_id=week_id,
                mention_count=data['count'],
                avg_score=avg_score,
                max_score=max_score,
                total_score=total_score,
                article_ids=data['article_ids']
            )
            mentions.append(mention)

        return mentions

    def _get_articles_for_week(self, week_id: str) -> List[Dict[str, Any]]:
        """
        Get all articles for a given week.

        Args:
            week_id: Week identifier (e.g., "2025-W01")

        Returns:
            List of article dictionaries
        """
        # Parse week_id (format: YYYY-WXX)
        from datetime import datetime, timedelta
        import re

        match = re.match(r'(\d{4})-W(\d{2})', week_id)
        if not match:
            return []

        year = int(match.group(1))
        week = int(match.group(2))

        # Calculate start and end dates for the week (ISO 8601 week)
        # Week 1 is the first week with at least 4 days in January
        jan_4 = datetime(year, 1, 4)
        week_1_start = jan_4 - timedelta(days=jan_4.weekday())
        week_start = week_1_start + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6)

        # Convert to date strings
        date_from = week_start.strftime("%Y-%m-%d")
        date_to = week_end.strftime("%Y-%m-%d")

        # Get all reports in date range
        articles = []
        reports = self.context.list_available_reports()

        for report_meta in reports:
            report_date = report_meta["date"]

            # Filter by week date range
            if report_date < date_from or report_date > date_to:
                continue

            # Load report
            report = self.context.load_report_by_date(report_date)
            if not report:
                continue

            # Add all articles from this report
            report_articles = report.get("articles", [])
            for article in report_articles:
                article["report_date"] = report_date
                articles.append(article)

        return articles

    def detect_trend_signals(
        self,
        current_week: str,
        baseline_weeks: int = 4
    ) -> List[TrendSignal]:
        """
        Detect trend signals by comparing current week against baseline.

        Analyzes current week's entity mentions and compares against historical
        baseline to detect:
        - velocity_spike: Mention frequency increased >3x baseline
        - new_entity: Entity appeared for first time with sufficient mentions
        - score_surge: Impact score increased >1.5x baseline
        - combo: Multiple signals fired simultaneously

        Args:
            current_week: Week to analyze (e.g., "2025-W01")
            baseline_weeks: Number of historical weeks for baseline (default: 4)

        Returns:
            List of detected TrendSignal objects above confidence threshold
        """
        MIN_BASELINE_MENTIONS = self.config.get('thresholds', {}).get('min_baseline_mentions', 2)
        MIN_BASELINE_WEEKS = self.config.get('min_baseline_weeks', 2)
        MIN_CONFIDENCE = self.config.get('min_confidence', 0.3)

        # Get current week's mentions
        current_mentions = self.aggregate_week(current_week)
        current_by_entity = {m.entity_id: m for m in current_mentions}

        # Get baseline weeks
        baseline_week_ids = self._get_baseline_weeks(current_week, baseline_weeks)

        # Aggregate baseline data per entity
        baseline_data: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total_mentions': 0,
            'total_score': 0.0,
            'weeks_observed': 0
        })

        for week_id in baseline_week_ids:
            week_mentions = self.aggregate_week(week_id)
            for mention in week_mentions:
                baseline_data[mention.entity_id]['total_mentions'] += mention.mention_count
                baseline_data[mention.entity_id]['total_score'] += mention.total_score
                baseline_data[mention.entity_id]['weeks_observed'] += 1

        # Detect signals
        signals = []

        for entity_id, current_mention in current_by_entity.items():
            baseline = baseline_data.get(entity_id)

            # NEW ENTITY signal
            if baseline is None or baseline['weeks_observed'] == 0:
                new_entity_threshold = self.config['thresholds']['new_entity_min_mentions']
                if current_mention.mention_count >= new_entity_threshold:
                    confidence = self._compute_new_entity_confidence(current_mention)
                    if confidence >= MIN_CONFIDENCE:
                        signal = TrendSignal(
                            entity_id=entity_id,
                            entity_name=current_mention.entity_name,
                            entity_type=current_mention.entity_type,
                            signal_type="new_entity",
                            confidence=confidence,
                            current_week=current_week,
                            baseline_weeks=baseline_weeks,
                            baseline_mentions=0.0,
                            baseline_score=None,
                            weeks_observed=0,
                            current_mentions=current_mention.mention_count,
                            current_score=current_mention.avg_score,
                            velocity_change=0.0,
                            score_delta=None,
                            evidence_article_ids=current_mention.article_ids[:5],
                            evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                        )
                        signals.append(signal)
                continue

            # Compute baseline averages
            baseline_avg_mentions = baseline['total_mentions'] / baseline['weeks_observed']
            baseline_avg_score = baseline['total_score'] / baseline['total_mentions'] if baseline['total_mentions'] > 0 else 0.0

            # Guard against tiny baselines (reduce false positives)
            if baseline_avg_mentions < MIN_BASELINE_MENTIONS:
                continue

            # Guard against insufficient baseline weeks
            if baseline['weeks_observed'] < MIN_BASELINE_WEEKS:
                continue

            # VELOCITY SPIKE signal
            velocity = (current_mention.mention_count - baseline_avg_mentions) / baseline_avg_mentions
            velocity_threshold = self.config['thresholds']['velocity_spike']

            # SCORE SURGE signal
            score_surge = None
            if baseline_avg_score > 0:  # Only compute if baseline has scores
                score_surge = current_mention.avg_score / baseline_avg_score

            score_surge_threshold = self.config['thresholds']['score_surge']

            # Detect signals
            is_velocity_spike = velocity >= velocity_threshold
            is_score_surge = score_surge is not None and score_surge >= score_surge_threshold

            # COMBO signal (multiple signals fire)
            if is_velocity_spike and is_score_surge and score_surge is not None:
                confidence = self._compute_combo_confidence(
                    velocity=velocity,
                    score_surge=score_surge,
                    current_mention=current_mention,
                    baseline_weeks_observed=baseline['weeks_observed']
                )
                if confidence >= MIN_CONFIDENCE:
                    signal = TrendSignal(
                        entity_id=entity_id,
                        entity_name=current_mention.entity_name,
                        entity_type=current_mention.entity_type,
                        signal_type="combo",
                        confidence=confidence,
                        current_week=current_week,
                        baseline_weeks=baseline_weeks,
                        baseline_mentions=baseline_avg_mentions,
                        baseline_score=baseline_avg_score,
                        weeks_observed=baseline['weeks_observed'],
                        current_mentions=current_mention.mention_count,
                        current_score=current_mention.avg_score,
                        velocity_change=velocity,
                        score_delta=current_mention.avg_score - baseline_avg_score,
                        evidence_article_ids=current_mention.article_ids[:5],
                        evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                    )
                    signals.append(signal)

            # Individual VELOCITY SPIKE
            elif is_velocity_spike:
                confidence = self._compute_velocity_confidence(
                    velocity=velocity,
                    current_mention=current_mention,
                    baseline_weeks_observed=baseline['weeks_observed']
                )
                if confidence >= MIN_CONFIDENCE:
                    signal = TrendSignal(
                        entity_id=entity_id,
                        entity_name=current_mention.entity_name,
                        entity_type=current_mention.entity_type,
                        signal_type="velocity_spike",
                        confidence=confidence,
                        current_week=current_week,
                        baseline_weeks=baseline_weeks,
                        baseline_mentions=baseline_avg_mentions,
                        baseline_score=baseline_avg_score,
                        weeks_observed=baseline['weeks_observed'],
                        current_mentions=current_mention.mention_count,
                        current_score=current_mention.avg_score,
                        velocity_change=velocity,
                        score_delta=current_mention.avg_score - baseline_avg_score if baseline_avg_score > 0 else None,
                        evidence_article_ids=current_mention.article_ids[:5],
                        evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                    )
                    signals.append(signal)

            # Individual SCORE SURGE
            elif is_score_surge and score_surge is not None:
                confidence = self._compute_score_surge_confidence(
                    score_surge=score_surge,
                    current_mention=current_mention,
                    baseline_weeks_observed=baseline['weeks_observed']
                )
                if confidence >= MIN_CONFIDENCE:
                    signal = TrendSignal(
                        entity_id=entity_id,
                        entity_name=current_mention.entity_name,
                        entity_type=current_mention.entity_type,
                        signal_type="score_surge",
                        confidence=confidence,
                        current_week=current_week,
                        baseline_weeks=baseline_weeks,
                        baseline_mentions=baseline_avg_mentions,
                        baseline_score=baseline_avg_score,
                        weeks_observed=baseline['weeks_observed'],
                        current_mentions=current_mention.mention_count,
                        current_score=current_mention.avg_score,
                        velocity_change=velocity,
                        score_delta=current_mention.avg_score - baseline_avg_score,
                        evidence_article_ids=current_mention.article_ids[:5],
                        evidence_titles=self._get_article_titles(current_mention.article_ids[:5])
                    )
                    signals.append(signal)

        return signals

    # Helper methods

    def _get_baseline_weeks(self, current_week: str, num_weeks: int) -> List[str]:
        """
        Get list of baseline week IDs before current_week.

        Args:
            current_week: Week to start from (e.g., "2025-W02")
            num_weeks: Number of previous weeks to retrieve

        Returns:
            List of week IDs (e.g., ["2024-W52", "2025-W01"])
        """
        from datetime import datetime, timedelta
        import re

        # Parse current week
        match = re.match(r'(\d{4})-W(\d{2})', current_week)
        if not match:
            return []

        year = int(match.group(1))
        week = int(match.group(2))

        # Calculate start date of current week
        jan_4 = datetime(year, 1, 4)
        week_1_start = jan_4 - timedelta(days=jan_4.weekday())
        current_week_start = week_1_start + timedelta(weeks=week - 1)

        # Generate previous N weeks
        baseline_weeks = []
        for i in range(1, num_weeks + 1):
            prev_week_start = current_week_start - timedelta(weeks=i)

            # Calculate ISO week number and year
            iso_year, iso_week, _ = prev_week_start.isocalendar()

            week_id = f"{iso_year}-W{iso_week:02d}"
            baseline_weeks.append(week_id)

        # Return in chronological order (oldest first)
        baseline_weeks.reverse()
        return baseline_weeks

    def _get_article_titles(self, article_ids: List[str]) -> List[str]:
        """
        Fetch article titles for evidence display.

        Args:
            article_ids: List of article IDs

        Returns:
            List of article titles (same length as article_ids)
        """
        titles = []

        # Note: article_ids here are not date-scoped, so we need to search across reports
        # For now, return placeholder titles. This will be improved when we have better article ID management.
        for article_id in article_ids:
            titles.append(f"Article {article_id}")

        return titles

    # Confidence scoring methods

    def _compute_new_entity_confidence(self, mention: EntityMention) -> float:
        """
        Compute confidence for new_entity signal.

        Factors considered:
        - Mention count (higher = more confident)
        - Average score (higher = more confident)

        Args:
            mention: EntityMention for the new entity

        Returns:
            Confidence score (0-1), clamped to min_confidence
        """
        # Factor in mention count (cap at 5 mentions)
        mention_factor = min(mention.mention_count / 5.0, 1.0)

        # Factor in average score (cap at score 8)
        score_factor = min(mention.avg_score / 8.0, 1.0)

        # Weighted combination (60% mentions, 40% score)
        confidence = (mention_factor * 0.6 + score_factor * 0.4)

        # Clamp to min_confidence
        min_confidence = self.config.get('min_confidence', 0.3)
        return max(confidence, min_confidence)

    def _compute_velocity_confidence(
        self,
        velocity: float,
        current_mention: EntityMention,
        baseline_weeks_observed: int
    ) -> float:
        """
        Compute confidence for velocity_spike signal.

        Factors considered:
        - Velocity magnitude (higher = more confident)
        - Baseline stability (more weeks = more confident)
        - Current mention count (higher = more confident)

        Args:
            velocity: Velocity change ratio (e.g., 3.5 = 350% increase)
            current_mention: EntityMention for current week
            baseline_weeks_observed: Number of weeks entity appeared in baseline

        Returns:
            Confidence score (0-1), clamped to min_confidence
        """
        # Factor in velocity magnitude (cap at 5x)
        velocity_factor = min(velocity / 5.0, 1.0)

        # Factor in baseline stability (more weeks = more stable, cap at 4 weeks)
        stability_factor = min(baseline_weeks_observed / 4.0, 1.0)

        # Factor in current mentions (cap at 8 mentions)
        mention_factor = min(current_mention.mention_count / 8.0, 1.0)

        # Weighted combination (50% velocity, 30% stability, 20% mentions)
        confidence = (velocity_factor * 0.5 + stability_factor * 0.3 + mention_factor * 0.2)

        # Clamp to min_confidence
        min_confidence = self.config.get('min_confidence', 0.3)
        return max(confidence, min_confidence)

    def _compute_score_surge_confidence(
        self,
        score_surge: float,
        current_mention: EntityMention,
        baseline_weeks_observed: int
    ) -> float:
        """
        Compute confidence for score_surge signal.

        Factors considered:
        - Surge magnitude (higher = more confident)
        - Baseline stability (more weeks = more confident)

        Args:
            score_surge: Score surge ratio (e.g., 1.8 = 180% of baseline)
            current_mention: EntityMention for current week
            baseline_weeks_observed: Number of weeks entity appeared in baseline

        Returns:
            Confidence score (0-1), clamped to min_confidence
        """
        # Factor in surge magnitude (normalize above 1.0, cap at 2.0x surge)
        surge_factor = min((score_surge - 1.0) / 1.0, 1.0)

        # Factor in baseline stability (cap at 4 weeks)
        stability_factor = min(baseline_weeks_observed / 4.0, 1.0)

        # Weighted combination (60% surge, 40% stability)
        confidence = (surge_factor * 0.6 + stability_factor * 0.4)

        # Clamp to min_confidence
        min_confidence = self.config.get('min_confidence', 0.3)
        return max(confidence, min_confidence)

    def _compute_combo_confidence(
        self,
        velocity: float,
        score_surge: float,
        current_mention: EntityMention,
        baseline_weeks_observed: int
    ) -> float:
        """
        Compute confidence for combo signal (multi-signal breakout).

        Factors considered:
        - Velocity magnitude
        - Score surge magnitude
        - Baseline stability
        - Current mention count
        - Bonus: 20% boost for combo signals

        Args:
            velocity: Velocity change ratio
            score_surge: Score surge ratio
            current_mention: EntityMention for current week
            baseline_weeks_observed: Number of weeks entity appeared in baseline

        Returns:
            Confidence score (0-1), clamped to 1.0 max after boost
        """
        # Factor in velocity magnitude (cap at 5x)
        velocity_factor = min(velocity / 5.0, 1.0)

        # Factor in surge magnitude (normalize above 1.0, cap at 2.0x)
        surge_factor = min((score_surge - 1.0) / 1.0, 1.0)

        # Factor in baseline stability (cap at 4 weeks)
        stability_factor = min(baseline_weeks_observed / 4.0, 1.0)

        # Factor in current mentions (cap at 8 mentions)
        mention_factor = min(current_mention.mention_count / 8.0, 1.0)

        # Weighted combination (30% velocity, 30% surge, 20% stability, 20% mentions)
        confidence = (
            velocity_factor * 0.3 +
            surge_factor * 0.3 +
            stability_factor * 0.2 +
            mention_factor * 0.2
        )

        # Boost combo signals by 20%
        confidence = confidence * 1.2

        # Clamp to 1.0 max
        return min(confidence, 1.0)