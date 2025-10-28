"""
Topic Trending Module - Track and analyze topic emergence and evolution over time

Provides tools for:
- Detecting emerging topics from article content
- Tracking topic frequency and intensity across weeks
- Identifying trends (rising, falling, sustained)
- Generating trend insights for the CEO briefing
"""

import json
from typing import List, Dict, Any, Optional, Tuple, Set
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path

try:
    from nltk.tokenize import sent_tokenize
    from nltk.corpus import stopwords
    import nltk
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt', quiet=True)
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords', quiet=True)
    HAS_NLTK = True
except ImportError:
    HAS_NLTK = False


class TopicTrending:
    """
    Analyzes topic trends across multiple weekly reports.

    Features:
    - Extract key topics from articles (using keywords + entities)
    - Track topic frequency over time
    - Detect trend directions (emerging, rising, sustained, fading)
    - Generate trend insights and recommendations
    - Compare week-over-week topic changes
    """

    def __init__(self, reports_dir: str = "./data/reports"):
        """
        Initialize topic trending analyzer.

        Args:
            reports_dir: Directory containing cached report data
        """
        self.reports_dir = Path(reports_dir)
        self.stop_words = self._load_stopwords()

    def _load_stopwords(self) -> Set[str]:
        """Load English stop words for filtering."""
        if HAS_NLTK:
            try:
                return set(stopwords.words('english'))
            except:
                pass

        # Fallback stop words list
        return {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
            'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
            'would', 'could', 'should', 'may', 'might', 'can', 'must', 'shall',
            'it', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she',
            'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how'
        }

    def extract_topics_from_article(
        self,
        article: Dict[str, Any],
        max_topics: int = 10,
        min_words: int = 2
    ) -> List[str]:
        """
        Extract key topics from an article.

        Args:
            article: Article dict with title, paraphrased_content, etc.
            max_topics: Maximum topics to extract
            min_words: Minimum words in a topic phrase

        Returns:
            List of topic phrases (e.g., "GPT-5", "language models", "reasoning")
        """
        topics = []

        # Get text to analyze
        title = article.get('title', '')
        content = article.get('paraphrased_content', '') or article.get('full_content', '')

        if not title and not content:
            return topics

        combined_text = (title + ' ' + content).lower()

        # Extract from entities if available
        if 'entities' in article:
            for entity_type, entities in article.get('entities', {}).items():
                if isinstance(entities, list):
                    topics.extend(entities[:3])

        # Extract noun phrases (simple approach: capitalize words that look like proper nouns)
        words = combined_text.split()
        for i, word in enumerate(words):
            if len(word) > 3 and word not in self.stop_words:
                # Check if word appears in title (likely important)
                if word in title.lower():
                    topics.append(word.capitalize())

        # Look for multi-word phrases
        phrases = self._extract_phrases(combined_text, max_phrases=5)
        topics.extend(phrases)

        # Remove duplicates and limit
        topics = list(set(topics))[:max_topics]

        return [t for t in topics if len(t.split()) >= min_words or len(t) > 3]

    def _extract_phrases(self, text: str, max_phrases: int = 5) -> List[str]:
        """Extract important multi-word phrases from text."""
        phrases = []

        # Simple heuristic: look for adjacent capitalized words in title
        if ' ' in text:
            words = text.split()
            for i in range(len(words) - 1):
                phrase = f"{words[i]} {words[i+1]}"
                if (len(words[i]) > 3 and len(words[i+1]) > 3 and
                    words[i] not in self.stop_words and
                    words[i+1] not in self.stop_words):
                    phrases.append(phrase.capitalize())

        return phrases[:max_phrases]

    def analyze_topic_distribution(
        self,
        articles: List[Dict[str, Any]],
        report_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze topic distribution in a set of articles (usually from one week).

        Args:
            articles: List of articles
            report_date: Date of the report (for tracking)

        Returns:
            Dict with topic frequencies and stats:
            {
                "date": "2025-10-28",
                "total_articles": 10,
                "topics": {
                    "GPT-5": {"count": 3, "frequency": 0.30, "articles": [...]},
                    ...
                },
                "top_topics": [("GPT-5", 3), ...],
                "topic_count": 25
            }
        """
        topic_articles = defaultdict(list)

        for article in articles:
            topics = self.extract_topics_from_article(article)
            for topic in topics:
                topic_articles[topic].append(article.get('title', 'Untitled'))

        # Build statistics
        topic_stats = {}
        for topic, article_titles in topic_articles.items():
            count = len(article_titles)
            topic_stats[topic] = {
                "count": count,
                "frequency": count / len(articles) if articles else 0,
                "articles": article_titles[:3]  # Top 3 articles for this topic
            }

        # Get top topics
        top_topics = sorted(
            topic_articles.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]

        return {
            "date": report_date or datetime.now().strftime("%Y-%m-%d"),
            "total_articles": len(articles),
            "topics": topic_stats,
            "top_topics": [(topic, len(articles)) for topic, articles in top_topics],
            "topic_count": len(topic_stats)
        }

    def track_topic_over_time(
        self,
        weekly_analyses: List[Dict[str, Any]],
        topic: str
    ) -> Dict[str, Any]:
        """
        Track a specific topic's appearance over multiple weeks.

        Args:
            weekly_analyses: List of analyze_topic_distribution() outputs from multiple weeks
            topic: Topic to track (case-insensitive)

        Returns:
            Dict with temporal trend:
            {
                "topic": "GPT-5",
                "weeks": [
                    {"date": "2025-10-14", "count": 2, "frequency": 0.20},
                    {"date": "2025-10-21", "count": 3, "frequency": 0.30},
                    ...
                ],
                "trend": "rising",
                "total_mentions": 8,
                "max_week": "2025-10-28"
            }
        """
        topic_lower = topic.lower()
        weeks_data = []

        for analysis in weekly_analyses:
            topic_match = None
            for t, stats in analysis.get('topics', {}).items():
                if t.lower() == topic_lower:
                    topic_match = stats
                    break

            if topic_match:
                weeks_data.append({
                    "date": analysis.get('date'),
                    "count": topic_match.get('count', 0),
                    "frequency": topic_match.get('frequency', 0)
                })
            else:
                weeks_data.append({
                    "date": analysis.get('date'),
                    "count": 0,
                    "frequency": 0
                })

        # Determine trend
        trend = self._detect_trend(weeks_data)

        # Find max week
        max_week = max(weeks_data, key=lambda x: x['count']) if weeks_data else {}

        return {
            "topic": topic,
            "weeks": weeks_data,
            "trend": trend,
            "total_mentions": sum(w['count'] for w in weeks_data),
            "max_week": max_week.get('date'),
            "max_count": max_week.get('count', 0)
        }

    def _detect_trend(self, weeks_data: List[Dict[str, int]]) -> str:
        """
        Detect trend direction from week-over-week counts.

        Returns: "emerging" | "rising" | "sustained" | "fading" | "stable"
        """
        if len(weeks_data) < 2:
            return "new"

        # Get counts
        counts = [w['count'] for w in weeks_data]

        # Filter out zeros
        nonzero_counts = [c for c in counts if c > 0]
        if len(nonzero_counts) == 0:
            return "not_appearing"
        if len(nonzero_counts) == 1:
            return "emerging"

        # Look at recent trend
        recent = counts[-3:] if len(counts) >= 3 else counts
        recent_nonzero = [c for c in recent if c > 0]

        if len(recent_nonzero) < 2:
            return "emerging"

        # Calculate trend
        avg_recent = sum(recent_nonzero) / len(recent_nonzero)
        avg_before = sum(counts[:-len(recent)]) / len(counts[:-len(recent)]) if len(counts) > len(recent) else counts[0]

        if avg_recent > avg_before * 1.2:
            return "rising"
        elif avg_recent < avg_before * 0.8:
            return "fading"
        else:
            return "sustained"

    def compare_weeks(
        self,
        week1_analysis: Dict[str, Any],
        week2_analysis: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compare topic distribution between two weeks.

        Args:
            week1_analysis: Earlier week analysis
            week2_analysis: Later week analysis

        Returns:
            Dict with comparison:
            {
                "period": "2025-10-21 to 2025-10-28",
                "new_topics": [...],
                "emerging_topics": [...],
                "fading_topics": [...],
                "sustained_topics": [...],
                "topic_diversity": {"week1": 25, "week2": 28, "change": 3}
            }
        """
        topics1 = set(week1_analysis.get('topics', {}).keys())
        topics2 = set(week2_analysis.get('topics', {}).keys())

        new_topics = topics2 - topics1
        fading_topics = topics1 - topics2
        sustained = topics1 & topics2

        # Find emerging (appear in week2 with higher frequency)
        emerging = []
        for topic in sustained:
            freq1 = week1_analysis['topics'][topic]['frequency']
            freq2 = week2_analysis['topics'][topic]['frequency']
            if freq2 > freq1 * 1.5:  # 50% increase
                emerging.append(topic)

        return {
            "period": f"{week1_analysis.get('date')} to {week2_analysis.get('date')}",
            "new_topics": list(new_topics)[:5],
            "emerging_topics": emerging[:5],
            "fading_topics": list(fading_topics)[:5],
            "sustained_topics": list(sustained),
            "topic_diversity": {
                "week1": week1_analysis.get('topic_count', 0),
                "week2": week2_analysis.get('topic_count', 0),
                "change": week2_analysis.get('topic_count', 0) - week1_analysis.get('topic_count', 0)
            }
        }

    def generate_trend_insights(
        self,
        topic_tracks: List[Dict[str, Any]],
        week_comparisons: List[Dict[str, Any]],
        lang: str = "zh"
    ) -> List[str]:
        """
        Generate human-readable trend insights for CEO briefing.

        Args:
            topic_tracks: List of track_topic_over_time() results
            week_comparisons: List of compare_weeks() results
            lang: Language for output (zh/en)

        Returns:
            List of insight strings
        """
        insights = []

        # Find strongest rising topics
        rising_topics = [t for t in topic_tracks if t['trend'] == 'rising']
        if rising_topics:
            top_rising = sorted(rising_topics, key=lambda x: x['total_mentions'], reverse=True)[0]
            if lang == "zh":
                insights.append(
                    f"📈 {top_rising['topic']} 热度上升，本周提及 {top_rising['max_count']} 次，环比增长显著"
                )
            else:
                insights.append(
                    f"📈 {top_rising['topic']} is trending up with {top_rising['max_count']} mentions this week"
                )

        # Find most sustained topics
        sustained_topics = [t for t in topic_tracks if t['trend'] == 'sustained']
        if sustained_topics:
            top_sustained = sorted(sustained_topics, key=lambda x: x['total_mentions'], reverse=True)[0]
            if lang == "zh":
                insights.append(
                    f"💪 {top_sustained['topic']} 持续受关注，过去四周平均 {top_sustained['total_mentions']//4:.0f} 次提及"
                )
            else:
                insights.append(
                    f"💪 {top_sustained['topic']} remains consistently important with steady mentions"
                )

        # Highlight new emerging topics
        emerging_topics = [t for t in topic_tracks if t['trend'] == 'emerging']
        if emerging_topics:
            top_emerging = emerging_topics[0]
            if lang == "zh":
                insights.append(
                    f"🌟 新兴话题 {top_emerging['topic']} 本周出现，值得关注其进一步发展"
                )
            else:
                insights.append(
                    f"🌟 New topic {top_emerging['topic']} emerged this week - worth monitoring"
                )

        # Highlight topics losing momentum
        fading_topics = [t for t in topic_tracks if t['trend'] == 'fading']
        if fading_topics:
            top_fading = sorted(fading_topics, key=lambda x: x['total_mentions'], reverse=True)[0]
            if lang == "zh":
                insights.append(
                    f"📉 {top_fading['topic']} 热度下降，市场关注度在减弱"
                )
            else:
                insights.append(
                    f"📉 {top_fading['topic']} is losing momentum with fewer mentions"
                )

        # Highlight major topic changes week-over-week
        if week_comparisons:
            latest_comparison = week_comparisons[-1]
            if latest_comparison.get('new_topics'):
                topics_str = ', '.join(latest_comparison['new_topics'][:3])
                if lang == "zh":
                    insights.append(
                        f"🔄 本周新进话题：{topics_str}"
                    )
                else:
                    insights.append(
                        f"🔄 New topics this week: {topics_str}"
                    )

        return insights

    def is_available(self) -> bool:
        """Check if topic trending analysis is available."""
        return True  # Always available, no external dependencies
