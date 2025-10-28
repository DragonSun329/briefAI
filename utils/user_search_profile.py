"""
User Search Profile Module - Track CEO search patterns and interests

Learns from CEO search behavior to personalize weekly briefings:
- Tracks all searches (queries, topics, selected articles)
- Extracts interest topics from search patterns
- Calculates interest weights for topics
- Feeds into 5D scoring pipeline for personalization
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from loguru import logger


class UserSearchProfile:
    """
    Tracks CEO search patterns and builds interest profile.

    Features:
    - Log all searches to persistent storage
    - Extract topics from search queries
    - Calculate topic interest weights
    - Track search frequency and recency
    - Generate personalization scores for articles
    - Reset interest profile periodically (e.g., monthly)
    """

    def __init__(self, profile_file: str = "./data/user_search_profile.json"):
        """
        Initialize user search profile.

        Args:
            profile_file: Path to store search history and interest weights
        """
        self.profile_file = Path(profile_file)
        self.profile = self._load_profile()

    def _load_profile(self) -> Dict[str, Any]:
        """Load existing profile or create new one."""
        if self.profile_file.exists():
            try:
                with open(self.profile_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load profile: {e}")

        # Create new profile
        return {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat(),
            "search_history": [],
            "topic_interests": {},
            "search_count": 0,
            "last_week_count": 0,
            "personalization_enabled": True
        }

    def _save_profile(self) -> None:
        """Save profile to disk."""
        self.profile_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.profile_file, 'w', encoding='utf-8') as f:
            json.dump(self.profile, f, indent=2, ensure_ascii=False)

    def log_search(
        self,
        query: str,
        topics_extracted: List[str],
        results_count: int = 0,
        selected_articles: Optional[List[str]] = None,
        dwell_time_seconds: int = 0
    ) -> None:
        """
        Log a search action to profile.

        Args:
            query: Search query text
            topics_extracted: Topics extracted from results
            results_count: Number of results returned
            selected_articles: Article titles selected by CEO
            dwell_time_seconds: Time spent viewing results
        """
        search_entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "topics": topics_extracted,
            "results_count": results_count,
            "selected_articles": selected_articles or [],
            "dwell_time_seconds": dwell_time_seconds
        }

        self.profile["search_history"].append(search_entry)
        self.profile["search_count"] += 1
        self.profile["last_updated"] = datetime.now().isoformat()

        # Update topic interests
        self._update_topic_interests(query, topics_extracted, selected_articles)

        self._save_profile()

    def _update_topic_interests(
        self,
        query: str,
        topics: List[str],
        selected_articles: Optional[List[str]] = None
    ) -> None:
        """
        Update topic interest weights based on search.

        Args:
            query: Original search query
            topics: Topics extracted from results
            selected_articles: Articles selected (click-through)
        """
        # Extract query tokens
        query_tokens = set(token.lower() for token in query.split())

        # Weight calculation
        base_weight = 1.0  # Base search weight
        if selected_articles:
            base_weight += 0.5 * len(selected_articles)  # Bonus for clicks

        # Update interests for each topic
        for topic in topics:
            topic_lower = topic.lower()

            if topic_lower not in self.profile["topic_interests"]:
                self.profile["topic_interests"][topic_lower] = {
                    "name": topic,
                    "weight": 0,
                    "frequency": 0,
                    "last_searched": None,
                    "total_weight": 0
                }

            interest = self.profile["topic_interests"][topic_lower]
            interest["frequency"] += 1
            interest["last_searched"] = datetime.now().isoformat()
            interest["total_weight"] += base_weight
            interest["weight"] = self._calculate_interest_weight(interest)

    def _calculate_interest_weight(self, interest: Dict[str, Any]) -> float:
        """
        Calculate normalized interest weight (0.5 - 2.0).

        Args:
            interest: Interest record with frequency and last_searched

        Returns:
            Weight for boosting article scores (0.5-2.0, where 1.0 = baseline)
        """
        frequency = interest.get("frequency", 0)
        total_weight = interest.get("total_weight", 0)

        # Normalize by time decay
        last_searched = interest.get("last_searched")
        if last_searched:
            last_date = datetime.fromisoformat(last_searched)
            days_ago = (datetime.now() - last_date).days
            time_decay = 0.95 ** days_ago  # Decay 5% per day
        else:
            time_decay = 0

        # Combine frequency and recency
        base_weight = min(2.0, 0.5 + (frequency / 10.0) + (total_weight / 10.0))
        final_weight = 0.5 + (base_weight - 0.5) * time_decay

        return max(0.5, min(2.0, final_weight))

    def get_topic_weight(self, topic: str) -> float:
        """
        Get personalization weight for a topic (0.5 - 2.0).

        Args:
            topic: Topic name (case-insensitive)

        Returns:
            Weight for boosting article scores
        """
        topic_lower = topic.lower()
        if topic_lower in self.profile["topic_interests"]:
            return self.profile["topic_interests"][topic_lower].get("weight", 1.0)
        return 1.0  # Baseline weight for unsearched topics

    def get_top_interests(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Get CEO's top interest topics.

        Args:
            top_n: Number of topics to return

        Returns:
            List of topics sorted by weight
        """
        interests = self.profile["topic_interests"].values()
        sorted_interests = sorted(
            interests,
            key=lambda x: x.get("weight", 1.0),
            reverse=True
        )
        return sorted_interests[:top_n]

    def get_search_history(self, days: int = 30) -> List[Dict[str, Any]]:
        """
        Get search history for past N days.

        Args:
            days: Number of days to look back

        Returns:
            List of search entries
        """
        cutoff = datetime.now() - timedelta(days=days)
        history = []

        for entry in self.profile.get("search_history", []):
            try:
                entry_date = datetime.fromisoformat(entry["timestamp"])
                if entry_date > cutoff:
                    history.append(entry)
            except:
                pass

        return history

    def get_personality_summary(self, lang: str = "zh") -> str:
        """
        Generate human-readable summary of CEO interests.

        Args:
            lang: Language (zh/en)

        Returns:
            Summary string
        """
        top_interests = self.get_top_interests(5)
        search_count = self.profile.get("search_count", 0)

        if not top_interests:
            return "未检测到搜索记录" if lang == "zh" else "No search history yet"

        interests_str = ", ".join([i["name"] for i in top_interests])

        if lang == "zh":
            return f"CEO主要关注 {interests_str} 等话题 (搜索 {search_count} 次)"
        else:
            return f"CEO is interested in {interests_str} and other topics ({search_count} searches)"

    def get_personalization_boost(self, article: Dict[str, Any]) -> float:
        """
        Calculate personalization score boost for article (0.8 - 1.5).

        Args:
            article: Article dict with title, topics, etc.

        Returns:
            Boost factor to multiply with base score
        """
        if not self.profile["personalization_enabled"]:
            return 1.0

        article_topics = article.get("topics", [])
        if not article_topics:
            return 1.0

        # Average weight across article topics
        weights = [self.get_topic_weight(topic) for topic in article_topics]
        avg_weight = sum(weights) / len(weights) if weights else 1.0

        # Cap boost between 0.8 and 1.5
        return max(0.8, min(1.5, avg_weight))

    def get_profile_stats(self) -> Dict[str, Any]:
        """
        Get statistics about user search profile.

        Returns:
            Profile statistics
        """
        total_searches = self.profile.get("search_count", 0)
        topic_count = len(self.profile.get("topic_interests", {}))
        top_interests = self.get_top_interests(3)

        # Get week-over-week trend
        one_week_ago = datetime.now() - timedelta(days=7)
        recent_searches = sum(
            1 for entry in self.profile.get("search_history", [])
            if datetime.fromisoformat(entry.get("timestamp", "")) > one_week_ago
        )

        return {
            "total_searches": total_searches,
            "searches_last_week": recent_searches,
            "unique_topics": topic_count,
            "top_interests": top_interests,
            "profile_created": self.profile.get("created_at"),
            "last_updated": self.profile.get("last_updated"),
            "personalization_enabled": self.profile.get("personalization_enabled", True)
        }

    def reset_weights(self, older_than_days: int = 30) -> None:
        """
        Reset topic weights older than specified days (gradual forgetting).

        Useful for preventing old search patterns from dominating personalization.

        Args:
            older_than_days: Reset weights for topics not searched in N days
        """
        cutoff = datetime.now() - timedelta(days=older_than_days)

        for topic, interest in self.profile["topic_interests"].items():
            last_searched = interest.get("last_searched")
            if last_searched:
                try:
                    last_date = datetime.fromisoformat(last_searched)
                    if last_date < cutoff:
                        # Gradually reset to baseline
                        interest["weight"] = max(1.0, interest.get("weight", 1.0) * 0.7)
                except:
                    pass

        self._save_profile()

    def enable_personalization(self, enabled: bool = True) -> None:
        """Enable or disable personalization."""
        self.profile["personalization_enabled"] = enabled
        self._save_profile()

    def clear_history(self) -> None:
        """Clear all search history and reset to fresh profile."""
        self.profile["search_history"] = []
        self.profile["topic_interests"] = {}
        self.profile["search_count"] = 0
        self.profile["last_updated"] = datetime.now().isoformat()
        self._save_profile()

    def is_available(self) -> bool:
        """Check if user profile module is available."""
        return True  # Always available
