"""
Product Traction Scorer

Scores product/end-user demand signals:
- ProductHunt: Upvotes, daily rank, comments
- App Store: Downloads, ratings, reviews (future)
- Web traffic: Alexa/Similarweb rank (future)

Scoring methodology:
- Log scale for engagement metrics (upvotes, downloads)
- Rank-based scoring for leaderboard positions
- Recency weighting for launches
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base_scorer import BaseScorer


class ProductScorer(BaseScorer):
    """
    Scores product traction/end-user demand signals.

    Data sources:
    - producthunt: Upvotes, rank, comments, featured status
    - app_store: Downloads, rating, reviews (future)
    - web_traffic: Alexa rank, monthly visits (future)
    """

    # Component weights
    WEIGHTS = {
        'upvotes': 0.35,
        'daily_rank': 0.25,
        'comments': 0.15,
        'featured': 0.10,
        'recency': 0.15,
    }

    # ProductHunt upvote thresholds (log scale)
    # 5K upvotes (10^3.7) = 100
    PH_UPVOTES_MAX_LOG = 3.7

    # Daily rank brackets (lower = better)
    PH_RANK_BRACKETS = [
        (1, 100),    # #1 product = 100
        (3, 90),     # Top 3 = 90
        (5, 80),     # Top 5 = 80
        (10, 65),    # Top 10 = 65
        (20, 50),    # Top 20 = 50
        (50, 35),    # Top 50 = 35
        (100, 20),   # Top 100 = 20
        (float('inf'), 10),
    ]

    # App store download thresholds
    APP_DOWNLOADS_MAX_LOG = 9.0  # 1B downloads = 100

    @property
    def category(self) -> str:
        return "product"

    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate product traction score from raw data.

        Expected raw_data keys:
        - source: "producthunt" | "app_store" | "web_traffic"
        - upvotes: int
        - daily_rank: int
        - comments: int
        - featured: bool
        - launch_date: str | datetime
        - downloads: int (app store)
        - rating: float (app store, 1-5)
        - reviews_count: int
        """
        source = raw_data.get('source', 'producthunt')

        if source == 'producthunt':
            return self._score_producthunt(raw_data)
        elif source == 'app_store':
            return self._score_app_store(raw_data)
        elif source == 'web_traffic':
            return self._score_web_traffic(raw_data)
        else:
            return self._score_generic(raw_data)

    def _score_producthunt(self, data: Dict[str, Any]) -> float:
        """Score ProductHunt launch data."""
        components = {}

        # Upvotes (35%)
        upvotes = data.get('upvotes', data.get('votes', 0))
        if upvotes > 0:
            upvote_score = self.log_scale(upvotes, self.PH_UPVOTES_MAX_LOG)
            components['upvotes'] = (upvote_score, self.WEIGHTS['upvotes'])

        # Daily rank (25%)
        rank = data.get('daily_rank', data.get('rank'))
        if rank is not None and rank > 0:
            rank_score = self.bracket_scale(rank, self.PH_RANK_BRACKETS)
            components['daily_rank'] = (rank_score, self.WEIGHTS['daily_rank'])

        # Comments (15%) - engagement signal
        comments = data.get('comments', data.get('comment_count', 0))
        if comments > 0:
            # 500 comments = 100
            comment_score = self.log_scale(comments, 2.7)
            components['comments'] = (comment_score, self.WEIGHTS['comments'])

        # Featured status (10%)
        featured = data.get('featured', data.get('is_featured', False))
        featured_score = 100.0 if featured else 30.0
        components['featured'] = (featured_score, self.WEIGHTS['featured'])

        # Recency (15%)
        launch_date = data.get('launch_date', data.get('posted_at'))
        if launch_date:
            recency = self._score_launch_recency(launch_date)
            components['recency'] = (recency, self.WEIGHTS['recency'])

        if not components:
            return 0.0

        # Normalize weights
        total_weight = sum(w for _, w in components.values())
        normalized = {k: (s, w / total_weight) for k, (s, w) in components.items()}

        return self.weighted_average(normalized)

    def _score_app_store(self, data: Dict[str, Any]) -> float:
        """Score app store data."""
        components = {}

        # Downloads (40%)
        downloads = data.get('downloads', data.get('installs', 0))
        if downloads > 0:
            download_score = self.log_scale(downloads, self.APP_DOWNLOADS_MAX_LOG)
            components['downloads'] = (download_score, 0.40)

        # Rating (25%) - quality signal
        rating = data.get('rating', data.get('average_rating', 0))
        if rating > 0:
            # 5-star scale to 100
            rating_score = (rating / 5.0) * 100
            components['rating'] = (rating_score, 0.25)

        # Review count (20%) - engagement
        reviews = data.get('reviews_count', data.get('ratings_count', 0))
        if reviews > 0:
            # 1M reviews = 100
            review_score = self.log_scale(reviews, 6.0)
            components['reviews'] = (review_score, 0.20)

        # Recency of last update (15%)
        updated = data.get('last_updated', data.get('updated_at'))
        if updated:
            recency = self.recency_decay(
                datetime.fromisoformat(updated.replace('Z', '+00:00'))
                if isinstance(updated, str) else updated,
                half_life_days=90
            ) * 100
            components['recency'] = (recency, 0.15)

        if not components:
            return 0.0

        total_weight = sum(w for _, w in components.values())
        normalized = {k: (s, w / total_weight) for k, (s, w) in components.items()}

        return self.weighted_average(normalized)

    def _score_web_traffic(self, data: Dict[str, Any]) -> float:
        """Score web traffic data (Alexa, Similarweb)."""
        components = {}

        # Global rank (lower = better)
        global_rank = data.get('global_rank', data.get('alexa_rank'))
        if global_rank and global_rank > 0:
            # Rank brackets for web traffic
            rank_brackets = [
                (100, 100),       # Top 100 = 100
                (1000, 90),       # Top 1K = 90
                (10000, 75),      # Top 10K = 75
                (100000, 55),     # Top 100K = 55
                (1000000, 35),    # Top 1M = 35
                (float('inf'), 15),
            ]
            rank_score = self.bracket_scale(global_rank, rank_brackets)
            components['global_rank'] = (rank_score, 0.50)

        # Monthly visits (log scale)
        visits = data.get('monthly_visits', data.get('visits'))
        if visits and visits > 0:
            # 1B visits = 100
            visit_score = self.log_scale(visits, 9.0)
            components['monthly_visits'] = (visit_score, 0.35)

        # Time on site (engagement)
        time_on_site = data.get('avg_time_on_site', 0)  # in seconds
        if time_on_site > 0:
            # 5 minutes = good engagement
            time_score = min(100.0, (time_on_site / 300) * 100)
            components['engagement'] = (time_score, 0.15)

        if not components:
            return 0.0

        total_weight = sum(w for _, w in components.values())
        normalized = {k: (s, w / total_weight) for k, (s, w) in components.items()}

        return self.weighted_average(normalized)

    def _score_generic(self, data: Dict[str, Any]) -> float:
        """Generic scoring for unknown product sources."""
        # Try common metric names
        upvotes = data.get('upvotes', data.get('likes', data.get('votes', 0)))
        downloads = data.get('downloads', data.get('installs', 0))

        if downloads > 0:
            return self.log_scale(downloads, self.APP_DOWNLOADS_MAX_LOG)
        elif upvotes > 0:
            return self.log_scale(upvotes, self.PH_UPVOTES_MAX_LOG)

        return 0.0

    def _score_launch_recency(self, date: Any) -> float:
        """
        Score ProductHunt launch recency.
        Half-life: 30 days (PH momentum is short-lived).
        """
        if isinstance(date, str):
            try:
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                return 50.0

        if not isinstance(date, datetime):
            return 50.0

        return self.recency_decay(date, half_life_days=30) * 100

    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """Calculate confidence based on data source and completeness."""
        source = raw_data.get('source', 'producthunt')

        base_confidence = {
            'producthunt': 0.85,
            'app_store': 0.90,
            'web_traffic': 0.75,
        }.get(source, 0.6)

        # Check for key metrics
        has_engagement = (
            raw_data.get('upvotes', 0) > 0 or
            raw_data.get('downloads', 0) > 0 or
            raw_data.get('monthly_visits', 0) > 0
        )

        if not has_engagement:
            return 0.3

        return base_confidence

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """Get breakdown of component scores."""
        components = {}
        source = raw_data.get('source', 'producthunt')

        if source == 'producthunt':
            upvotes = raw_data.get('upvotes', 0)
            if upvotes > 0:
                components['upvotes'] = self.log_scale(upvotes, self.PH_UPVOTES_MAX_LOG)

            rank = raw_data.get('daily_rank')
            if rank:
                components['daily_rank'] = self.bracket_scale(rank, self.PH_RANK_BRACKETS)

        elif source == 'app_store':
            downloads = raw_data.get('downloads', 0)
            if downloads > 0:
                components['downloads'] = self.log_scale(downloads, self.APP_DOWNLOADS_MAX_LOG)

            rating = raw_data.get('rating', 0)
            if rating > 0:
                components['rating'] = (rating / 5.0) * 100

        return components
