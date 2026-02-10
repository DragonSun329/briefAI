"""
Technical Signal Scorer

Scores technical significance from developer/research adoption signals:
- GitHub: stars, forks, velocity (stars/week)
- HuggingFace: downloads, likes, model task
- Papers With Code: citations, benchmarks (future)

Scoring methodology:
- Uses log-scale for power-law metrics (stars, downloads)
- Incorporates velocity for momentum detection
- Weights: stars 25%, velocity 15%, forks 10%, HF downloads 20%, HF likes 10%, recency 5%
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base_scorer import BaseScorer


class TechnicalScorer(BaseScorer):
    """
    Scores technical/developer adoption signals.

    Data sources:
    - github_trending: Stars, forks, language, weekly velocity
    - huggingface_models: Downloads, likes, task type
    - huggingface_spaces: Likes, SDK, hardware tier
    """

    # Component weights (sum to 1.0)
    WEIGHTS = {
        'github_stars': 0.25,
        'github_velocity': 0.15,
        'github_forks': 0.10,
        'hf_downloads': 0.20,
        'hf_likes': 0.10,
        'citations': 0.15,  # Future: Papers With Code
        'recency': 0.05,
    }

    # Log scale parameters
    # GitHub stars: 1M (10^6) = 100
    GITHUB_STARS_MAX_LOG = 6.0
    # GitHub forks: 100K (10^5) = 100
    GITHUB_FORKS_MAX_LOG = 5.0
    # HuggingFace downloads: 100M (10^8) = 100
    HF_DOWNLOADS_MAX_LOG = 8.0
    # HuggingFace likes: 10K (10^4) = 100
    HF_LIKES_MAX_LOG = 4.0

    @property
    def category(self) -> str:
        return "technical"

    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate technical score from raw GitHub/HuggingFace data.

        Expected raw_data keys:
        - source: "github" | "huggingface_model" | "huggingface_space"
        - stars: int (GitHub)
        - forks: int (GitHub)
        - stars_week: int (GitHub velocity)
        - downloads: int (HuggingFace)
        - downloads_month: int (HuggingFace)
        - likes: int (HuggingFace)
        - last_modified: datetime | str
        """
        source = raw_data.get('source', 'unknown')

        if source == 'github':
            return self._score_github(raw_data)
        elif source in ('huggingface_model', 'huggingface_space'):
            return self._score_huggingface(raw_data)
        else:
            # Generic scoring for unknown sources
            return self._score_generic(raw_data)

    def _score_github(self, data: Dict[str, Any]) -> float:
        """Score GitHub repository data."""
        components = {}

        # Stars (25%)
        stars = data.get('stars', 0)
        star_score = self.log_scale(stars, self.GITHUB_STARS_MAX_LOG)
        components['github_stars'] = (star_score, self.WEIGHTS['github_stars'])

        # Velocity - stars gained per week (15%)
        stars_week = data.get('stars_week', data.get('stars_this_week', 0))
        # 1000 new stars/week is exceptional (log scale, max 3)
        velocity_score = self.log_scale(stars_week, 3.0)
        components['github_velocity'] = (velocity_score, self.WEIGHTS['github_velocity'])

        # Forks (10%)
        forks = data.get('forks', 0)
        fork_score = self.log_scale(forks, self.GITHUB_FORKS_MAX_LOG)
        components['github_forks'] = (fork_score, self.WEIGHTS['github_forks'])

        # Recency (5%)
        last_modified = data.get('last_modified')
        if isinstance(last_modified, str):
            try:
                last_modified = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            except:
                last_modified = None
        recency = self.recency_decay(last_modified, half_life_days=30) * 100
        components['recency'] = (recency, self.WEIGHTS['recency'])

        # Redistribute weights for missing HF data
        github_total_weight = sum(
            self.WEIGHTS[k] for k in ['github_stars', 'github_velocity', 'github_forks', 'recency']
        )
        normalizer = 1.0 / github_total_weight

        # Normalize weights
        for key in components:
            score, weight = components[key]
            components[key] = (score, weight * normalizer)

        return self.weighted_average(components)

    def _score_huggingface(self, data: Dict[str, Any]) -> float:
        """Score HuggingFace model/space data."""
        components = {}

        source = data.get('source', 'huggingface_model')

        if source == 'huggingface_model':
            # Downloads (primary signal for models)
            downloads = data.get('downloads', 0)
            download_score = self.log_scale(downloads, self.HF_DOWNLOADS_MAX_LOG)
            components['hf_downloads'] = (download_score, 0.50)

            # Monthly downloads velocity
            downloads_month = data.get('downloads_month', 0)
            velocity_score = self.log_scale(downloads_month, 7.0)  # 10M/month = 100
            components['hf_velocity'] = (velocity_score, 0.20)

            # Likes
            likes = data.get('likes', 0)
            like_score = self.log_scale(likes, self.HF_LIKES_MAX_LOG)
            components['hf_likes'] = (like_score, 0.15)

        else:  # huggingface_space
            # Spaces are scored primarily by likes
            likes = data.get('likes', 0)
            like_score = self.log_scale(likes, self.HF_LIKES_MAX_LOG)
            components['hf_likes'] = (like_score, 0.60)

            # Hardware tier bonus (indicates investment/demand)
            hardware = data.get('hardware', '')
            hardware_bonus = self._hardware_bonus(hardware)
            components['hardware'] = (hardware_bonus, 0.25)

        # Recency (15%)
        last_modified = data.get('last_modified')
        if isinstance(last_modified, str):
            try:
                last_modified = datetime.fromisoformat(last_modified.replace('Z', '+00:00'))
            except:
                last_modified = None
        recency = self.recency_decay(last_modified, half_life_days=60) * 100
        components['recency'] = (recency, 0.15)

        return self.weighted_average(components)

    def _score_generic(self, data: Dict[str, Any]) -> float:
        """Generic scoring for unrecognized technical sources."""
        # Look for common metric names
        stars = data.get('stars', 0)
        downloads = data.get('downloads', 0)
        likes = data.get('likes', 0)

        # Use whichever metrics are available
        if stars > 0:
            return self.log_scale(stars, self.GITHUB_STARS_MAX_LOG)
        elif downloads > 0:
            return self.log_scale(downloads, self.HF_DOWNLOADS_MAX_LOG)
        elif likes > 0:
            return self.log_scale(likes, self.HF_LIKES_MAX_LOG)

        return 0.0

    def _hardware_bonus(self, hardware: Optional[str]) -> float:
        """Score HuggingFace Space hardware tier."""
        if not hardware:
            return 20.0  # Basic CPU assumed

        hardware_lower = hardware.lower()

        # Higher-tier hardware indicates more investment/demand
        if 'a100' in hardware_lower or 'a10g' in hardware_lower:
            return 100.0
        elif 't4' in hardware_lower:
            return 80.0
        elif 'cpu-upgrade' in hardware_lower:
            return 50.0
        elif 'cpu-basic' in hardware_lower or 'cpu' in hardware_lower:
            return 30.0
        else:
            return 20.0

    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate confidence based on data completeness and source reliability.
        """
        source = raw_data.get('source', 'unknown')

        # Base confidence by source
        base_confidence = {
            'github': 0.9,       # API data, reliable
            'huggingface_model': 0.85,
            'huggingface_space': 0.85,
        }.get(source, 0.5)

        # Adjust for data completeness
        expected_fields = {
            'github': ['stars', 'forks'],
            'huggingface_model': ['downloads', 'likes'],
            'huggingface_space': ['likes'],
        }.get(source, ['stars', 'downloads'])

        present_fields = sum(1 for f in expected_fields if raw_data.get(f, 0) > 0)
        completeness = present_fields / len(expected_fields) if expected_fields else 0.5

        return round(base_confidence * completeness, 2)

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """Get breakdown of component scores."""
        source = raw_data.get('source', 'unknown')
        components = {}

        if source == 'github':
            components['stars'] = self.log_scale(
                raw_data.get('stars', 0), self.GITHUB_STARS_MAX_LOG
            )
            components['forks'] = self.log_scale(
                raw_data.get('forks', 0), self.GITHUB_FORKS_MAX_LOG
            )
            components['velocity'] = self.log_scale(
                raw_data.get('stars_week', 0), 3.0
            )
        elif source in ('huggingface_model', 'huggingface_space'):
            components['downloads'] = self.log_scale(
                raw_data.get('downloads', 0), self.HF_DOWNLOADS_MAX_LOG
            )
            components['likes'] = self.log_scale(
                raw_data.get('likes', 0), self.HF_LIKES_MAX_LOG
            )

        return components
