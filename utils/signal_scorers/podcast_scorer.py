"""
Podcast Signal Scorer

Scores podcast mentions and insights as media signals.
Expert discussions on high-credibility podcasts provide valuable
trend signals for emerging companies and technologies.

Sources:
- Podcast transcripts from AI-focused channels
- LLM-extracted entities and topics
- Host credibility scores (7-9 scale)

Scoring methodology:
- Host credibility weighted heavily (experts have signal value)
- Mention frequency in discussions
- Discussion depth (duration/context)
- Multi-podcast validation (same entity across podcasts)
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from .base_scorer import BaseScorer


class PodcastScorer(BaseScorer):
    """
    Scores podcast mentions as media signals.

    Podcasts like Lex Fridman, No Priors, and Latent Space feature
    expert discussions that often signal emerging trends before
    mainstream coverage.

    Weighting rationale:
    - host_credibility (30%): Expert hosts filter for quality topics
    - mention_depth (25%): Discussion depth > casual mention
    - mention_count (25%): Frequency indicates importance
    - multi_show_bonus (20%): Cross-podcast validation
    """

    # Component weights
    WEIGHTS = {
        'host_credibility': 0.30,   # Podcast tier (Lex=9, No Priors=9, All-In=8)
        'mention_depth': 0.25,      # How deeply discussed (vs brief mention)
        'mention_count': 0.25,      # Times entity mentioned in transcript
        'multi_show_bonus': 0.20,   # Mentioned across multiple podcasts
    }

    # Credibility tiers for podcasts
    CREDIBILITY_TIERS = {
        9: 'tier1',  # Top AI podcasts (Lex Fridman, No Priors, Latent Space)
        8: 'tier2',  # Quality podcasts (All-In, Dwarkesh, Lenny, Gradient Dissent)
        7: 'tier3',  # Good podcasts (Practical AI)
    }

    @property
    def category(self) -> str:
        return "media"  # Podcasts are a media signal type

    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate podcast mention score.

        Expected raw_data keys:
        - source: "podcast"
        - podcast_channel: str (channel name)
        - host_credibility: int (7-9)
        - mention_count: int (times entity mentioned in transcript)
        - duration_min: int (episode duration)
        - is_main_topic: bool (entity is main discussion topic)
        - discussion_context: str (surrounding text for depth analysis)
        - episode_count: int (number of episodes mentioning entity)
        - shows: List[str] (list of show names mentioning entity)
        """
        components = {}

        # Host credibility score (30%)
        credibility = raw_data.get('host_credibility', 7)
        credibility_score = self._score_credibility(credibility)
        components['host_credibility'] = (credibility_score, self.WEIGHTS['host_credibility'])

        # Mention depth (25%)
        depth_score = self._score_mention_depth(raw_data)
        components['mention_depth'] = (depth_score, self.WEIGHTS['mention_depth'])

        # Mention count (25%)
        mention_count = raw_data.get('mention_count', 1)
        # 50 mentions across podcasts = 100
        mention_score = self.log_scale(mention_count, 1.7)
        components['mention_count'] = (mention_score, self.WEIGHTS['mention_count'])

        # Multi-show bonus (20%)
        shows = raw_data.get('shows', [])
        episode_count = raw_data.get('episode_count', 1)
        multi_score = self._score_multi_show(shows, episode_count)
        components['multi_show_bonus'] = (multi_score, self.WEIGHTS['multi_show_bonus'])

        return self.weighted_average(components)

    def _score_credibility(self, credibility: int) -> float:
        """
        Convert host credibility (7-9) to 0-100 score.

        Higher credibility podcasts have expert hosts who filter
        for significant topics.
        """
        # Map 7-9 to score range
        # 9 -> 100, 8 -> 80, 7 -> 60
        credibility = max(5, min(10, credibility))
        return (credibility - 5) * 20  # 5->0, 6->20, 7->40, 8->60, 9->80, 10->100

    def _score_mention_depth(self, raw_data: Dict[str, Any]) -> float:
        """
        Score based on discussion depth.

        Main topic > extended discussion > brief mention
        """
        # Main topic (entity is focus of episode)
        if raw_data.get('is_main_topic', False):
            return 100.0

        # Check discussion duration/context
        duration_min = raw_data.get('duration_min', 0)
        mention_count = raw_data.get('mention_count', 1)

        # Estimate discussion depth from mention density
        # More mentions in longer episodes = deeper discussion
        if duration_min > 0 and mention_count > 0:
            density = mention_count / duration_min
            # 1 mention per minute = substantial discussion
            if density >= 1.0:
                return 90.0
            elif density >= 0.5:
                return 70.0
            elif density >= 0.2:
                return 50.0

        # Check for discussion context
        context = raw_data.get('discussion_context', '')
        if len(context) > 500:  # Extended context = deeper discussion
            return 60.0
        elif len(context) > 200:
            return 45.0

        # Default: brief mention
        return 30.0

    def _score_multi_show(self, shows: List[str], episode_count: int) -> float:
        """
        Score based on mentions across multiple podcasts.

        Same entity mentioned by multiple expert hosts = strong signal.
        """
        unique_shows = len(set(shows)) if shows else 0

        # Multiple shows is a strong validation signal
        if unique_shows >= 4:
            return 100.0
        elif unique_shows >= 3:
            return 85.0
        elif unique_shows >= 2:
            return 70.0
        elif unique_shows == 1:
            # Single show - score by episode count
            if episode_count >= 3:
                return 50.0
            elif episode_count >= 2:
                return 35.0
            return 20.0

        return 0.0

    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate confidence based on data quality.

        Higher confidence for:
        - High-credibility podcasts
        - Multiple mentions
        - Multiple shows
        """
        credibility = raw_data.get('host_credibility', 7)
        mention_count = raw_data.get('mention_count', 0)
        shows = raw_data.get('shows', [])

        # Base confidence from credibility
        base_confidence = {
            9: 0.90,  # Top tier podcasts
            8: 0.80,  # Quality podcasts
            7: 0.70,  # Good podcasts
        }.get(credibility, 0.60)

        # Boost for multiple mentions
        if mention_count >= 10:
            base_confidence += 0.05
        elif mention_count >= 5:
            base_confidence += 0.03

        # Boost for multi-show validation
        unique_shows = len(set(shows)) if shows else 0
        if unique_shows >= 3:
            base_confidence += 0.05
        elif unique_shows >= 2:
            base_confidence += 0.03

        return min(0.95, base_confidence)

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """Get breakdown of component scores."""
        components = {}

        credibility = raw_data.get('host_credibility', 7)
        components['host_credibility'] = self._score_credibility(credibility)

        components['mention_depth'] = self._score_mention_depth(raw_data)

        mention_count = raw_data.get('mention_count', 1)
        components['mention_frequency'] = self.log_scale(mention_count, 1.7)

        shows = raw_data.get('shows', [])
        episode_count = raw_data.get('episode_count', 1)
        components['multi_show_validation'] = self._score_multi_show(shows, episode_count)

        return components

    @staticmethod
    def aggregate_podcast_mentions(
        episodes: List[Dict[str, Any]],
        entity_name: str
    ) -> Dict[str, Any]:
        """
        Aggregate podcast data for a specific entity.

        Args:
            episodes: List of podcast episode dicts with entities
            entity_name: Entity to aggregate for

        Returns:
            Dict ready for score() method
        """
        entity_lower = entity_name.lower()
        relevant_episodes = []
        total_mentions = 0
        shows = []
        max_credibility = 7
        total_duration = 0

        for episode in episodes:
            # Check if entity mentioned
            entities = episode.get('entities', [])
            content = episode.get('content', '').lower()
            summary = episode.get('summary', '').lower()

            # Count mentions in content
            mention_count = content.count(entity_lower)
            if mention_count == 0:
                # Check entities list
                for entity in entities:
                    if isinstance(entity, str) and entity_lower in entity.lower():
                        mention_count += 1
                    elif isinstance(entity, dict):
                        name = entity.get('name', entity.get('entity', ''))
                        if entity_lower in name.lower():
                            mention_count += entity.get('count', 1)

            if mention_count > 0:
                relevant_episodes.append(episode)
                total_mentions += mention_count
                shows.append(episode.get('podcast_channel', 'Unknown'))
                max_credibility = max(
                    max_credibility,
                    episode.get('credibility_score', 7)
                )
                total_duration += episode.get('duration_min', 0)

        if not relevant_episodes:
            return {
                'source': 'podcast',
                'host_credibility': 7,
                'mention_count': 0,
                'episode_count': 0,
                'shows': [],
            }

        # Check if entity is main topic in any episode
        is_main_topic = any(
            entity_lower in ep.get('title', '').lower()
            for ep in relevant_episodes
        )

        return {
            'source': 'podcast',
            'host_credibility': max_credibility,
            'mention_count': total_mentions,
            'duration_min': total_duration,
            'is_main_topic': is_main_topic,
            'episode_count': len(relevant_episodes),
            'shows': shows,
            'episodes': relevant_episodes,
        }