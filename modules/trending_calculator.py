#!/usr/bin/env python3
"""
Trending Calculator - Calculate viral/trending scores for products

Aggregates trending signals from:
- Product Hunt upvotes
- Reddit upvote velocity
- Comment engagement
- Launch recency
- Source diversity
"""

from typing import List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger


class TrendingCalculator:
    """Calculate trending/viral scores for AI products"""

    def __init__(self):
        """Initialize trending calculator"""
        logger.info("Trending calculator initialized")

    def calculate_trending_scores(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculate trending scores for all articles

        Args:
            articles: List of article dictionaries

        Returns:
            Articles with 'trending_score' field added
        """
        for article in articles:
            score = self.calculate_trending_score(article)
            article['trending_score'] = score
            article['trending_tier'] = self._get_trending_tier(score)

        logger.info(f"Calculated trending scores for {len(articles)} articles")

        return articles

    def calculate_trending_score(self, article: Dict[str, Any]) -> float:
        """
        Calculate trending score for a single article

        Score (0-10) based on:
        - Product Hunt upvotes (30%)
        - Reddit upvote velocity (25%)
        - Comment engagement (20%)
        - Launch recency (15%)
        - Source diversity (10%)

        Args:
            article: Article dictionary

        Returns:
            Trending score (0-10)
        """
        score = 0.0

        # Component 1: Product Hunt upvotes (0-3)
        ph_votes = article.get('ph_votes', 0)
        if ph_votes > 0:
            # Normalize: 500+ votes = max score
            ph_score = min(ph_votes / 500, 1.0) * 3.0
            score += ph_score

        # Component 2: Reddit upvote velocity (0-2.5)
        reddit_score = article.get('reddit_score', 0)
        if reddit_score > 0:
            # Calculate upvote velocity (upvotes per hour)
            pub_date = article.get('published_date')
            if pub_date:
                if isinstance(pub_date, str):
                    try:
                        pub_date = datetime.strptime(pub_date, '%Y-%m-%d')
                    except:
                        pub_date = datetime.utcnow()

                hours_old = max((datetime.utcnow() - pub_date).total_seconds() / 3600, 1)
                velocity = reddit_score / hours_old

                # Normalize: 10+ upvotes/hour = max score
                velocity_score = min(velocity / 10, 1.0) * 2.5
                score += velocity_score

        # Component 3: Comment engagement (0-2)
        comment_count = 0
        comment_count += article.get('ph_comments_count', 0)
        comment_count += article.get('reddit_num_comments', 0)

        if comment_count > 0:
            # Normalize: 100+ comments = max score
            engagement_score = min(comment_count / 100, 1.0) * 2.0
            score += engagement_score

        # Component 4: Launch recency (0-1.5)
        pub_date = article.get('published_date')
        if pub_date:
            if isinstance(pub_date, str):
                try:
                    pub_date = datetime.strptime(pub_date, '%Y-%m-%d')
                except:
                    pub_date = None

            if pub_date:
                days_old = (datetime.utcnow() - pub_date).days

                if days_old <= 7:
                    # Linear decay over 7 days
                    recency_score = (1 - days_old / 7) * 1.5
                    score += recency_score

        # Component 5: Source diversity (0-1)
        # If product appears in multiple sources, it's more trending
        sources_seen = set()

        if article.get('ph_product_id'):
            sources_seen.add('product_hunt')
        if article.get('reddit_post_id'):
            sources_seen.add('reddit')
        if article.get('source'):
            sources_seen.add(article['source'].lower())

        # Normalize: 3+ sources = max score
        diversity_score = min(len(sources_seen) / 3, 1.0) * 1.0
        score += diversity_score

        return min(score, 10.0)

    def _get_trending_tier(self, score: float) -> str:
        """
        Get trending tier label

        Args:
            score: Trending score (0-10)

        Returns:
            Tier label
        """
        if score >= 9.0:
            return 'viral'  # 💎
        elif score >= 8.5:
            return 'very_hot'  # 🔥🔥🔥
        elif score >= 7.0:
            return 'hot'  # 🔥🔥
        elif score >= 5.0:
            return 'warm'  # 🔥
        else:
            return 'normal'

    def rank_by_trending(
        self,
        articles: List[Dict[str, Any]],
        top_n: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Rank articles by trending score

        Args:
            articles: Articles with trending_score
            top_n: Number of top articles to return

        Returns:
            Top N articles sorted by trending score
        """
        # Sort by trending score (descending)
        sorted_articles = sorted(
            articles,
            key=lambda x: x.get('trending_score', 0),
            reverse=True
        )

        return sorted_articles[:top_n]

    def get_trending_statistics(
        self,
        articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get statistics about trending scores

        Args:
            articles: Articles with trending_score

        Returns:
            Statistics dictionary
        """
        if not articles:
            return {}

        scores = [a.get('trending_score', 0) for a in articles]

        # Count by tier
        viral = sum(1 for s in scores if s >= 9.0)
        very_hot = sum(1 for s in scores if 8.5 <= s < 9.0)
        hot = sum(1 for s in scores if 7.0 <= s < 8.5)
        warm = sum(1 for s in scores if 5.0 <= s < 7.0)
        normal = sum(1 for s in scores if s < 5.0)

        return {
            'total_articles': len(articles),
            'avg_trending_score': sum(scores) / len(scores),
            'max_trending_score': max(scores),
            'min_trending_score': min(scores),
            'viral_count': viral,  # 💎
            'very_hot_count': very_hot,  # 🔥🔥🔥
            'hot_count': hot,  # 🔥🔥
            'warm_count': warm,  # 🔥
            'normal_count': normal
        }

    def calculate_composite_score(
        self,
        article: Dict[str, Any],
        trending_weight: float = 0.4,
        quality_weight: float = 0.6
    ) -> float:
        """
        Calculate composite score combining trending + quality

        Args:
            article: Article with trending_score and weighted_score
            trending_weight: Weight for trending component (0-1)
            quality_weight: Weight for quality component (0-1)

        Returns:
            Composite score (0-10)
        """
        trending_score = article.get('trending_score', 0)
        quality_score = article.get('weighted_score', 0)

        composite = (trending_score * trending_weight) + (quality_score * quality_weight)

        return min(composite, 10.0)


if __name__ == "__main__":
    # Test trending calculator
    print("Testing TrendingCalculator...\n")

    # Sample data
    sample_articles = [
        {
            'title': 'Cursor IDE - Viral AI code editor',
            'ph_votes': 850,
            'ph_comments_count': 120,
            'ph_product_id': 'cursor-123',
            'published_date': datetime.utcnow() - timedelta(days=1),
            'source': 'Product Hunt'
        },
        {
            'title': 'New AI tool discussion',
            'reddit_score': 450,
            'reddit_num_comments': 85,
            'reddit_post_id': 'abc123',
            'published_date': datetime.utcnow() - timedelta(hours=6),
            'source': 'Reddit'
        },
        {
            'title': 'Older product',
            'ph_votes': 120,
            'ph_comments_count': 15,
            'published_date': datetime.utcnow() - timedelta(days=30),
            'source': 'Product Hunt'
        }
    ]

    calculator = TrendingCalculator()

    # Calculate scores
    articles = calculator.calculate_trending_scores(sample_articles)

    print(f"✅ Calculated trending scores for {len(articles)} articles\n")

    # Show results
    for article in articles:
        print(f"Title: {article['title']}")
        print(f"  Trending Score: {article['trending_score']:.1f}/10")
        print(f"  Tier: {article['trending_tier']}")
        print()

    # Get statistics
    stats = calculator.get_trending_statistics(articles)
    print("Statistics:")
    for key, value in stats.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    # Test ranking
    print("\nTop 2 trending:")
    top_articles = calculator.rank_by_trending(articles, top_n=2)
    for i, article in enumerate(top_articles, 1):
        print(f"  {i}. {article['title']} ({article['trending_score']:.1f}/10)")
