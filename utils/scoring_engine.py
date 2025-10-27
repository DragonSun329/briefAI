"""
Scoring Engine Module

Provides utilities for calculating weighted scores using the 5D scoring system.
Dimensions: Market Impact (25%), Competitive Impact (20%), Strategic Relevance (20%),
            Operational Relevance (15%), Credibility (10%)
"""

from typing import Dict, Any, List
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()


class ScoringEngine:
    """Handles 5D weighted scoring calculations"""

    # 5D Scoring weights (must sum to 1.0)
    DEFAULT_WEIGHTS = {
        'market_impact': float(os.getenv('SCORING_MARKET_WEIGHT', 0.25)),
        'competitive_impact': float(os.getenv('SCORING_COMPETITIVE_WEIGHT', 0.20)),
        'strategic_relevance': float(os.getenv('SCORING_STRATEGIC_WEIGHT', 0.20)),
        'operational_relevance': float(os.getenv('SCORING_OPERATIONAL_WEIGHT', 0.15)),
        'credibility': float(os.getenv('SCORING_CREDIBILITY_WEIGHT', 0.10))
    }

    def __init__(self, weights: Dict[str, float] = None):
        """
        Initialize scoring engine with custom weights

        Args:
            weights: Custom weight dictionary. If None, uses DEFAULT_WEIGHTS
        """
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()

        # Validate weights sum to 1.0
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            logger.warning(f"Scoring weights sum to {weight_sum:.3f}, expected 1.0. Normalizing...")
            # Normalize weights
            for key in self.weights:
                self.weights[key] = self.weights[key] / weight_sum

        logger.info(f"Scoring engine initialized with weights: {self.weights}")

    def calculate_weighted_score(self, scores: Dict[str, float]) -> float:
        """
        Calculate weighted score from 5D individual scores

        Args:
            scores: Dictionary with keys: market_impact, competitive_impact,
                   strategic_relevance, operational_relevance, credibility
                   Each value should be 1-10

        Returns:
            Weighted score (1-10 scale)
        """
        weighted_score = 0.0

        for dimension, weight in self.weights.items():
            score = scores.get(dimension, 5.0)  # Default to 5 if missing

            # Ensure score is in 1-10 range
            score = max(1, min(10, score))

            weighted_score += score * weight

        return round(weighted_score, 2)

    def get_score_breakdown_str(self, scores: Dict[str, float]) -> str:
        """
        Get human-readable score breakdown string

        Args:
            scores: Dictionary with 5D scores

        Returns:
            Formatted string like "Market: 8/10 | Competitive: 7/10 | Strategic: 9/10 | Operational: 6/10 | Credibility: 8/10"
        """
        breakdown_parts = []

        dimension_names = {
            'market_impact': 'Market',
            'competitive_impact': 'Competitive',
            'strategic_relevance': 'Strategic',
            'operational_relevance': 'Operational',
            'credibility': 'Credibility'
        }

        for dimension, short_name in dimension_names.items():
            score = scores.get(dimension, 5)
            breakdown_parts.append(f"{short_name}: {int(score)}/10")

        return " | ".join(breakdown_parts)

    def rank_articles_by_score(
        self,
        articles: List[Dict[str, Any]],
        reverse: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Sort articles by weighted score

        Args:
            articles: List of articles with 5d_score_breakdown
            reverse: Sort descending (True) or ascending (False)

        Returns:
            Sorted list of articles
        """
        articles_copy = articles.copy()
        articles_copy.sort(
            key=lambda x: x.get('weighted_score', 0),
            reverse=reverse
        )
        return articles_copy

    def get_score_distribution(self, articles: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get statistics about score distribution in article list

        Args:
            articles: List of evaluated articles

        Returns:
            Dictionary with min, max, mean, median scores
        """
        if not articles:
            return {
                'min': 0,
                'max': 0,
                'mean': 0,
                'median': 0,
                'count': 0
            }

        scores = [a.get('weighted_score', 0) for a in articles]
        scores.sort()

        mean = sum(scores) / len(scores)
        median = scores[len(scores) // 2] if len(scores) > 0 else 0

        return {
            'min': min(scores),
            'max': max(scores),
            'mean': round(mean, 2),
            'median': median,
            'count': len(scores)
        }

    def filter_by_score_threshold(
        self,
        articles: List[Dict[str, Any]],
        threshold: float = 6.0
    ) -> List[Dict[str, Any]]:
        """
        Filter articles by minimum weighted score

        Args:
            articles: List of articles
            threshold: Minimum weighted score (1-10)

        Returns:
            Articles with weighted_score >= threshold
        """
        filtered = [a for a in articles if a.get('weighted_score', 0) >= threshold]
        logger.info(f"Score filtering: {len(articles)} → {len(filtered)} articles (threshold: {threshold})")
        return filtered

    def get_top_articles(
        self,
        articles: List[Dict[str, Any]],
        top_n: int = 15
    ) -> List[Dict[str, Any]]:
        """
        Get top N articles by weighted score

        Args:
            articles: List of articles
            top_n: Number of top articles

        Returns:
            Top N articles sorted by score (descending)
        """
        ranked = self.rank_articles_by_score(articles, reverse=True)
        return ranked[:top_n]

    def get_score_summary(self, articles: List[Dict[str, Any]]) -> str:
        """
        Get summary string of article scores

        Args:
            articles: List of articles

        Returns:
            Summary like "Score range: 5.2 - 8.9, Average: 7.1"
        """
        if not articles:
            return "No articles"

        scores = [a.get('weighted_score', 0) for a in articles]
        min_score = min(scores)
        max_score = max(scores)
        avg_score = sum(scores) / len(scores)

        return f"Score range: {min_score:.1f} - {max_score:.1f}, Average: {avg_score:.1f}"


if __name__ == "__main__":
    # Test scoring engine
    engine = ScoringEngine()

    # Test single article scoring
    sample_scores = {
        'market_impact': 8,
        'competitive_impact': 7,
        'strategic_relevance': 9,
        'operational_relevance': 6,
        'credibility': 8
    }

    weighted_score = engine.calculate_weighted_score(sample_scores)
    print(f"Sample scores: {sample_scores}")
    print(f"Weighted score: {weighted_score}")
    print(f"Breakdown: {engine.get_score_breakdown_str(sample_scores)}")

    # Test with multiple articles
    articles = [
        {
            'title': 'Article 1',
            'weighted_score': 7.5,
            '5d_score_breakdown': sample_scores
        },
        {
            'title': 'Article 2',
            'weighted_score': 6.2,
            '5d_score_breakdown': sample_scores
        },
        {
            'title': 'Article 3',
            'weighted_score': 8.1,
            '5d_score_breakdown': sample_scores
        }
    ]

    print(f"\nScore distribution: {engine.get_score_distribution(articles)}")
    print(f"Score summary: {engine.get_score_summary(articles)}")

    top_articles = engine.get_top_articles(articles, top_n=2)
    print(f"\nTop 2 articles: {[a['title'] for a in top_articles]}")
