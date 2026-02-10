"""
Media Sentiment Scorer

Adapts the existing 5D news scoring system for the signal framework.
Scores: public perception, narrative strength, hype level

Sources:
- Existing news pipeline with 5D scores
- Entity mentions from articles
- Social media sentiment (future)

Scoring methodology:
- Converts 1-10 weighted_score to 0-100 scale
- Adds mention frequency bonus
- Incorporates article count for coverage breadth
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from .base_scorer import BaseScorer


class MediaScorer(BaseScorer):
    """
    Adapts existing 5D news scoring to signal framework.

    The existing system uses:
    - market_impact (25%)
    - competitive_impact (20%)
    - strategic_relevance (20%)
    - operational_relevance (15%)
    - credibility (10%)

    This scorer converts to 0-100 and adds mention frequency.
    """

    # Component weights
    WEIGHTS = {
        'sentiment_score': 0.50,    # 5D weighted score
        'mention_count': 0.25,      # How often entity is mentioned
        'article_count': 0.15,      # Breadth of coverage
        'source_quality': 0.10,     # Quality of news sources
    }

    @property
    def category(self) -> str:
        return "media"

    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate media sentiment score from news data.

        Expected raw_data keys:
        - source: "news_pipeline" | "social_media"
        - weighted_score: float (1-10 from 5D system)
        - 5d_scores: Dict with individual dimension scores
        - mention_count: int (times entity mentioned)
        - article_count: int (unique articles mentioning entity)
        - articles: List[Dict] (full article data)
        - source_tiers: Dict[str, int] (count by source tier)
        """
        source = raw_data.get('source', 'news_pipeline')

        if source == 'news_pipeline':
            return self._score_news(raw_data)
        elif source == 'social_media':
            return self._score_social(raw_data)
        else:
            return self._score_generic(raw_data)

    def _score_news(self, data: Dict[str, Any]) -> float:
        """Score news pipeline data."""
        components = {}

        # Sentiment score from 5D system (50%)
        weighted_score = data.get('weighted_score')
        if weighted_score is not None:
            # Convert 1-10 to 0-100
            sentiment_score = self._convert_5d_score(weighted_score)
            components['sentiment_score'] = (sentiment_score, self.WEIGHTS['sentiment_score'])
        elif '5d_scores' in data or '5d_score_breakdown' in data:
            # Calculate from individual dimensions
            scores = data.get('5d_scores', data.get('5d_score_breakdown', {}))
            sentiment_score = self._calculate_from_5d(scores)
            components['sentiment_score'] = (sentiment_score, self.WEIGHTS['sentiment_score'])

        # Mention count (25%)
        mention_count = data.get('mention_count', data.get('mentions', 0))
        if mention_count > 0:
            # 100 mentions = 100 (log scale)
            mention_score = self.log_scale(mention_count, 2.0)
            components['mention_count'] = (mention_score, self.WEIGHTS['mention_count'])

        # Article count (15%)
        article_count = data.get('article_count', 0)
        if article_count == 0 and 'articles' in data:
            article_count = len(data['articles'])

        if article_count > 0:
            # 50 articles = 100
            article_score = self.log_scale(article_count, 1.7)
            components['article_count'] = (article_score, self.WEIGHTS['article_count'])

        # Source quality (10%)
        source_tiers = data.get('source_tiers', {})
        if source_tiers:
            quality_score = self._score_source_quality(source_tiers)
            components['source_quality'] = (quality_score, self.WEIGHTS['source_quality'])

        if not components:
            return 0.0

        # Normalize weights
        total_weight = sum(w for _, w in components.values())
        normalized = {k: (s, w / total_weight) for k, (s, w) in components.items()}

        return self.weighted_average(normalized)

    def _score_social(self, data: Dict[str, Any]) -> float:
        """Score social media sentiment (future implementation)."""
        components = {}

        # Engagement (likes, shares, comments)
        engagement = data.get('total_engagement', 0)
        if engagement > 0:
            # 100K engagement = 100
            engagement_score = self.log_scale(engagement, 5.0)
            components['engagement'] = (engagement_score, 0.40)

        # Sentiment polarity (-1 to 1 -> 0 to 100)
        sentiment = data.get('sentiment_polarity', 0)
        # Convert -1 to 1 range to 0-100
        sentiment_score = (sentiment + 1) / 2 * 100
        components['sentiment'] = (sentiment_score, 0.35)

        # Reach/impressions
        reach = data.get('reach', data.get('impressions', 0))
        if reach > 0:
            reach_score = self.log_scale(reach, 7.0)  # 10M reach = 100
            components['reach'] = (reach_score, 0.25)

        if not components:
            return 50.0  # Default neutral for empty social data

        total_weight = sum(w for _, w in components.values())
        normalized = {k: (s, w / total_weight) for k, (s, w) in components.items()}

        return self.weighted_average(normalized)

    def _score_generic(self, data: Dict[str, Any]) -> float:
        """Generic scoring for unknown media sources."""
        # Try common metric names
        score = data.get('score', data.get('weighted_score'))
        if score is not None:
            return self._convert_5d_score(score)

        mentions = data.get('mentions', data.get('mention_count', 0))
        if mentions > 0:
            return self.log_scale(mentions, 2.0)

        return 0.0

    def _convert_5d_score(self, score: float) -> float:
        """
        Convert 5D weighted score (1-10) to 0-100.

        The conversion isn't linear - a 5D score of 7+ is already
        quite significant, so we use a slight curve.
        """
        # Clamp to 1-10 range
        score = max(1.0, min(10.0, score))

        # Linear conversion with floor
        # 5D 1 -> 0, 5D 10 -> 100
        base_score = ((score - 1) / 9) * 100

        return round(base_score, 2)

    def _calculate_from_5d(self, scores: Dict[str, Any]) -> float:
        """
        Calculate weighted score from individual 5D dimensions.
        Uses same weights as existing ScoringEngine.
        """
        weights = {
            'market_impact': 0.25,
            'competitive_impact': 0.20,
            'strategic_relevance': 0.20,
            'operational_relevance': 0.15,
            'credibility': 0.10,
        }

        weighted_sum = 0.0
        total_weight = 0.0

        for dim, weight in weights.items():
            if dim in scores:
                value = scores[dim]
                if isinstance(value, (int, float)):
                    weighted_sum += value * weight
                    total_weight += weight

        if total_weight == 0:
            return 50.0

        # Calculate 1-10 weighted score, then convert to 0-100
        weighted_score = weighted_sum / total_weight
        return self._convert_5d_score(weighted_score)

    def _score_source_quality(self, source_tiers: Dict[str, int]) -> float:
        """
        Score based on quality of news sources.

        source_tiers: {"tier1": 5, "tier2": 10, "tier3": 3}
        Tier 1 = major outlets (WSJ, NYT, Bloomberg)
        Tier 2 = industry press (TechCrunch, VentureBeat)
        Tier 3 = blogs, smaller outlets
        """
        tier_weights = {
            'tier1': 100,
            'tier2': 70,
            'tier3': 40,
            'unknown': 30,
        }

        total_count = sum(source_tiers.values())
        if total_count == 0:
            return 50.0

        weighted_sum = 0.0
        for tier, count in source_tiers.items():
            weight = tier_weights.get(tier.lower(), 30)
            weighted_sum += weight * count

        return round(weighted_sum / total_count, 2)

    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """Calculate confidence based on data completeness."""
        source = raw_data.get('source', 'news_pipeline')

        base_confidence = {
            'news_pipeline': 0.85,
            'social_media': 0.65,
        }.get(source, 0.6)

        # Check for key data
        has_score = raw_data.get('weighted_score') is not None or \
                    raw_data.get('5d_scores') is not None

        has_mentions = raw_data.get('mention_count', 0) > 0 or \
                       raw_data.get('article_count', 0) > 0

        if not has_score and not has_mentions:
            return 0.3

        # Reduce confidence for social media (less reliable)
        if source == 'social_media':
            base_confidence *= 0.8

        return base_confidence

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """Get breakdown of component scores."""
        components = {}

        weighted_score = raw_data.get('weighted_score')
        if weighted_score is not None:
            components['5d_sentiment'] = self._convert_5d_score(weighted_score)

        mentions = raw_data.get('mention_count', 0)
        if mentions > 0:
            components['mention_frequency'] = self.log_scale(mentions, 2.0)

        articles = raw_data.get('article_count', 0)
        if articles > 0:
            components['coverage_breadth'] = self.log_scale(articles, 1.7)

        return components

    @staticmethod
    def aggregate_entity_media(
        articles: List[Dict[str, Any]],
        entity_name: str
    ) -> Dict[str, Any]:
        """
        Aggregate media data for a specific entity from article list.

        This helper extracts entity-specific metrics from the news pipeline.

        Args:
            articles: List of article dicts with scores and entity mentions
            entity_name: Entity to aggregate for

        Returns:
            Dict ready for score() method
        """
        entity_lower = entity_name.lower()
        relevant_articles = []
        total_mentions = 0

        for article in articles:
            # Check if entity mentioned in this article
            entities = article.get('entities', [])
            mentions = article.get('entity_mentions', [])

            # Check various entity mention formats
            mentioned = False
            mention_count = 0

            for entity in entities:
                if isinstance(entity, str):
                    if entity_lower in entity.lower():
                        mentioned = True
                        mention_count += 1
                elif isinstance(entity, dict):
                    name = entity.get('name', entity.get('entity', ''))
                    if entity_lower in name.lower():
                        mentioned = True
                        mention_count += entity.get('count', 1)

            for mention in mentions:
                if isinstance(mention, dict):
                    name = mention.get('entity', mention.get('name', ''))
                    if entity_lower in name.lower():
                        mentioned = True
                        mention_count += mention.get('count', 1)

            if mentioned:
                relevant_articles.append(article)
                total_mentions += max(1, mention_count)

        if not relevant_articles:
            return {
                'source': 'news_pipeline',
                'weighted_score': None,
                'mention_count': 0,
                'article_count': 0,
            }

        # Calculate average 5D score across relevant articles
        scores = [a.get('weighted_score', 5.0) for a in relevant_articles
                  if a.get('weighted_score') is not None]
        avg_score = sum(scores) / len(scores) if scores else 5.0

        return {
            'source': 'news_pipeline',
            'weighted_score': avg_score,
            'mention_count': total_mentions,
            'article_count': len(relevant_articles),
            'articles': relevant_articles,
        }
