"""
Article Pre-filter Module (Tier 1)

Performs fast, zero-token filtering of articles based on:
- Keyword relevance to user categories
- Recency (recent articles score higher)
- Source credibility
- Trending/hot tags and indicators

Filters 60-70% of articles before expensive LLM evaluation.
"""

import re
from typing import List, Dict, Any, Set
from datetime import datetime, timedelta
from loguru import logger


class ArticleFilter:
    """Fast pre-filtering of articles without LLM calls"""

    def __init__(self, score_threshold: float = 2.0):
        """
        Initialize article filter

        Args:
            score_threshold: Minimum score to keep article (0-10 scale)
                            4.0 = aggressive filtering (save most tokens)
                            3.0 = moderate filtering (lose ~5% good articles)
                            2.0 = conservative (keep most articles)
        """
        self.score_threshold = score_threshold
        self.trending_indicators = self._build_trending_indicators()

        logger.info(f"Article filter initialized (threshold: {score_threshold})")

    def filter_articles(
        self,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Filter articles based on Tier 1 criteria

        Args:
            articles: List of scraped articles
            categories: User's selected categories (for keyword matching)

        Returns:
            Filtered list of articles above threshold score
        """
        logger.info(f"[TIER 1] Pre-filtering {len(articles)} articles...")

        # Build category keywords for matching
        category_keywords = self._build_category_keywords(categories)

        filtered_articles = []
        scores = []

        for article in articles:
            score = self._score_article(article, category_keywords)
            article['tier1_score'] = score
            article['tier1_rationale'] = self._get_score_rationale(score, article)

            scores.append(score)

            if score >= self.score_threshold:
                filtered_articles.append(article)
                logger.debug(
                    f"KEEP  [{score:.1f}] {article['title'][:60]}"
                )
            else:
                logger.debug(
                    f"SKIP  [{score:.1f}] {article['title'][:60]}"
                )

        # Log statistics
        avg_score = sum(scores) / len(scores) if scores else 0
        logger.info(
            f"[TIER 1] Results: {len(filtered_articles)}/{len(articles)} articles kept "
            f"(avg score: {avg_score:.1f}, threshold: {self.score_threshold})"
        )

        return filtered_articles

    def _score_article(
        self,
        article: Dict[str, Any],
        category_keywords: Set[str]
    ) -> float:
        """
        Calculate article importance score (0-10 scale)

        Scoring logic:
        - Keyword match (exact): +3 points
        - Keyword match (partial): +1 point
        - Trending tag: +2 points
        - Recent (<24h): +2 points
        - Somewhat recent (24-48h): +1 point
        - Source credibility (>=9): +1 point
        - Source credibility (>=8): +0.5 points
        """
        score = 0.0

        # 1. Keyword matching (title + description)
        title = article.get('title', '').lower()
        description = article.get('description', '')
        content = article.get('content', '')[:500].lower()  # First 500 chars

        text_to_search = f"{title} {description} {content}"

        # Exact keyword matches
        exact_matches = len([kw for kw in category_keywords if kw in text_to_search])
        if exact_matches > 0:
            score += min(3.0, exact_matches * 0.5)  # Cap at 3 points

        # Partial keyword matches (check if keyword is substring of longer word)
        partial_matches = len([
            kw for kw in category_keywords
            if any(word.startswith(kw) for word in text_to_search.split())
        ])
        if partial_matches > 0:
            score += min(1.0, partial_matches * 0.3)  # Cap at 1 point

        # 2. Trending/hot tags
        title_tags = self._extract_tags(title)
        desc_tags = self._extract_tags(article.get('description', ''))

        if any(tag in self.trending_indicators for tag in title_tags + desc_tags):
            score += 2.0
            logger.debug(f"Found trending tag in: {article['title'][:40]}")

        # 3. Recency scoring
        pub_date = article.get('published_at')
        if pub_date:
            try:
                if isinstance(pub_date, str):
                    # Try to parse ISO format or common formats
                    pub_dt = datetime.fromisoformat(pub_date.replace('Z', '+00:00'))
                else:
                    pub_dt = pub_date

                hours_old = (datetime.now(pub_dt.tzinfo) - pub_dt).total_seconds() / 3600

                if hours_old < 24:
                    score += 2.0  # Very recent
                elif hours_old < 48:
                    score += 1.0  # Recent
                # Else: no points for older articles

            except Exception as e:
                logger.debug(f"Could not parse date {pub_date}: {e}")

        # 4. Source credibility
        credibility = article.get('credibility_score', 5)
        if credibility >= 9:
            score += 1.0
        elif credibility >= 8:
            score += 0.5

        # 5. View count (if available)
        views = article.get('views', 0)
        if isinstance(views, int) and views >= 100:
            score += 0.5
        elif isinstance(views, int) and views >= 500:
            score += 1.0

        # Cap at 10
        return min(10.0, score)

    def _build_category_keywords(self, categories: List[Dict[str, Any]]) -> Set[str]:
        """Build set of keywords from selected categories"""
        keywords = set()

        for category in categories:
            # Add category name
            keywords.add(category['name'].lower())

            # Add aliases (these are the main keyword keywords)
            if 'aliases' in category:
                for alias in category['aliases']:
                    keywords.add(alias.lower())

            # Add focus tags if available
            if 'focus_tags' in category:
                for tag in category['focus_tags']:
                    keywords.add(tag.lower())

        logger.debug(f"Built keyword set: {keywords}")
        return keywords

    def _extract_tags(self, text: str) -> List[str]:
        """Extract hashtags and explicit tags from text"""
        tags = []

        # Look for hashtags
        hashtags = re.findall(r'#(\w+)', text)
        tags.extend([h.lower() for h in hashtags])

        # Look for emoji indicators
        if '🔥' in text or '热' in text:
            tags.append('hot')
        if '⭐' in text or '精选' in text:
            tags.append('featured')
        if '📌' in text or '推荐' in text:
            tags.append('recommended')

        return tags

    def _build_trending_indicators(self) -> Set[str]:
        """Build set of indicators that signal trending/hot content"""
        return {
            '热门',      # Chinese: "hot"
            '热',         # Chinese: "hot"
            '推荐',       # Chinese: "recommended"
            '推',         # Chinese: "recommend"
            '精选',       # Chinese: "featured"
            '精',         # Chinese: "featured"
            '置顶',       # Chinese: "pinned"
            'trending',
            'trending-now',
            'hot',
            'featured',
            'recommended',
            'pinned',
            'top-story',
            'breaking'
        }

    def _get_score_rationale(self, score: float, article: Dict[str, Any]) -> str:
        """Generate human-readable explanation for the score"""
        reasons = []

        if score >= 8:
            reasons.append("Excellent relevance and recency")
        elif score >= 6:
            reasons.append("Good relevance or trending indicator")
        elif score >= 4:
            reasons.append("Moderate relevance")
        else:
            reasons.append("Low relevance")

        if article.get('credibility_score', 0) >= 9:
            reasons.append("High credibility source")

        return " | ".join(reasons)
