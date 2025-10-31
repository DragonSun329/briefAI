#!/usr/bin/env python3
"""
Reddit Scraper - PRAW-based scraper for AI product discussions

Fetches:
- Hot posts from AI/product subreddits
- Top comments with user feedback
- Upvote counts and engagement metrics
- Product mentions and reviews
"""

import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger

try:
    import praw
    PRAW_AVAILABLE = True
except ImportError:
    PRAW_AVAILABLE = False
    logger.warning("PRAW not installed - Reddit scraping disabled")


class RedditScraper:
    """Scraper for Reddit using PRAW (Python Reddit API Wrapper)"""

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """
        Initialize Reddit scraper

        Args:
            client_id: Reddit API client ID (from .env if not provided)
            client_secret: Reddit API client secret (from .env if not provided)
            user_agent: User agent string (from .env if not provided)

        Raises:
            ImportError: If PRAW is not installed
            ValueError: If credentials are missing
        """
        if not PRAW_AVAILABLE:
            raise ImportError(
                "PRAW not installed. Install with: pip install praw"
            )

        # Get credentials from environment if not provided
        self.client_id = client_id or os.getenv('REDDIT_CLIENT_ID')
        self.client_secret = client_secret or os.getenv('REDDIT_CLIENT_SECRET')
        self.user_agent = user_agent or os.getenv('REDDIT_USER_AGENT', 'briefAI:v1.0 (by /u/briefai)')

        if not self.client_id or not self.client_secret:
            raise ValueError(
                "Reddit credentials missing. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET in .env"
            )

        # Initialize PRAW
        try:
            self.reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
                check_for_async=False  # We're using synchronous mode
            )
            logger.info(f"Reddit API initialized (read-only mode)")
            logger.debug(f"User agent: {self.user_agent}")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit API: {e}")
            raise

    def scrape_subreddit(
        self,
        subreddit_name: str,
        limit: int = 50,
        days_back: int = 7,
        sort: str = 'hot',
        min_score: int = 5,
        min_comments: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Scrape posts from a subreddit

        Args:
            subreddit_name: Name of subreddit (e.g., "ChatGPT")
            limit: Maximum number of posts to fetch
            days_back: Only include posts from last N days
            sort: Sorting method ('hot', 'new', 'top', 'rising')
            min_score: Minimum upvote score
            min_comments: Minimum number of comments

        Returns:
            List of article dictionaries
        """
        articles = []

        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)

            # Get posts based on sort method
            if sort == 'hot':
                posts = subreddit.hot(limit=limit)
            elif sort == 'new':
                posts = subreddit.new(limit=limit)
            elif sort == 'top':
                posts = subreddit.top(time_filter='week', limit=limit)
            elif sort == 'rising':
                posts = subreddit.rising(limit=limit)
            else:
                logger.warning(f"Unknown sort method: {sort}, using 'hot'")
                posts = subreddit.hot(limit=limit)

            # Process posts
            for submission in posts:
                # Check if post is recent enough
                post_date = datetime.utcfromtimestamp(submission.created_utc)
                if post_date < cutoff_date:
                    continue

                # Filter by score and comments
                if submission.score < min_score:
                    continue
                if submission.num_comments < min_comments:
                    continue

                # Filter for AI product discussions
                if not self._is_product_related(submission.title, submission.selftext):
                    continue

                # Extract top comments
                top_comments = self._extract_comments(submission, limit=10)

                # Build article dict
                article = {
                    'title': submission.title,
                    'url': f"https://reddit.com{submission.permalink}",
                    'source': f"Reddit r/{subreddit_name}",
                    'content': submission.selftext[:2000] if submission.selftext else submission.title,
                    'date': post_date.strftime('%Y-%m-%d'),
                    'published_date': post_date,
                    'language': 'en',

                    # Reddit-specific metadata
                    'reddit_score': submission.score,
                    'reddit_upvote_ratio': submission.upvote_ratio,
                    'reddit_num_comments': submission.num_comments,
                    'reddit_comments': top_comments,
                    'reddit_author': str(submission.author) if submission.author else '[deleted]',
                    'reddit_flair': submission.link_flair_text,
                    'reddit_post_id': submission.id,
                    'subreddit': subreddit_name,

                    # For review extraction
                    'has_reviews': len(top_comments) > 0,
                    'review_count': len(top_comments),
                    'engagement_score': self._calculate_engagement_score(submission)
                }

                articles.append(article)

            logger.info(f"Scraped {len(articles)} product-related posts from r/{subreddit_name}")

        except Exception as e:
            logger.error(f"Error scraping r/{subreddit_name}: {e}")

        return articles

    def scrape_multiple_subreddits(
        self,
        subreddit_names: List[str],
        limit_per_subreddit: int = 30,
        days_back: int = 7
    ) -> List[Dict[str, Any]]:
        """
        Scrape multiple subreddits

        Args:
            subreddit_names: List of subreddit names
            limit_per_subreddit: Posts per subreddit
            days_back: Days to look back

        Returns:
            Combined list of articles from all subreddits
        """
        all_articles = []

        for subreddit_name in subreddit_names:
            articles = self.scrape_subreddit(
                subreddit_name=subreddit_name,
                limit=limit_per_subreddit,
                days_back=days_back
            )
            all_articles.extend(articles)

        logger.info(f"Total articles from {len(subreddit_names)} subreddits: {len(all_articles)}")

        return all_articles

    def _extract_comments(
        self,
        submission,
        limit: int = 10,
        min_score: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Extract top comments from a submission

        Args:
            submission: PRAW submission object
            limit: Maximum comments to extract
            min_score: Minimum comment score

        Returns:
            List of comment dictionaries
        """
        comments = []

        try:
            # Replace MoreComments objects
            submission.comments.replace_more(limit=0)

            # Get top-level comments sorted by score
            top_comments = sorted(
                submission.comments,
                key=lambda c: c.score,
                reverse=True
            )[:limit]

            for comment in top_comments:
                if comment.score < min_score:
                    continue

                # Skip deleted/removed comments
                if comment.body in ['[deleted]', '[removed]']:
                    continue

                comments.append({
                    'body': comment.body[:500],  # Truncate long comments
                    'score': comment.score,
                    'author': str(comment.author) if comment.author else '[deleted]',
                    'created_utc': datetime.utcfromtimestamp(comment.created_utc).strftime('%Y-%m-%d'),
                    'is_submitter': comment.is_submitter,
                    'depth': 0  # Top-level comment
                })

        except Exception as e:
            logger.warning(f"Error extracting comments: {e}")

        return comments

    def _is_product_related(self, title: str, selftext: str) -> bool:
        """
        Check if post is related to AI products/tools

        Args:
            title: Post title
            selftext: Post body text

        Returns:
            True if product-related, False otherwise
        """
        # Product-related keywords
        product_keywords = [
            'tool', 'app', 'product', 'software', 'platform',
            'built', 'made', 'created', 'launched', 'released',
            'review', 'recommendation', 'suggest', 'alternative',
            'cursor', 'copilot', 'chatgpt', 'claude', 'midjourney',
            'ai tool', 'ai app', 'ai product', 'ai software',
            'automation', 'workflow', 'productivity',
            'show hn', 'show reddit', 'feedback', 'thoughts on'
        ]

        text = (title + ' ' + selftext).lower()

        return any(keyword in text for keyword in product_keywords)

    def _calculate_engagement_score(self, submission) -> float:
        """
        Calculate engagement score for a post

        Score based on:
        - Upvote ratio (30%)
        - Comments per upvote (40%)
        - Absolute score (30%)

        Args:
            submission: PRAW submission object

        Returns:
            Engagement score (0-10)
        """
        # Upvote ratio component (0-3)
        ratio_score = submission.upvote_ratio * 3.0

        # Comments per upvote (0-4)
        if submission.score > 0:
            comments_ratio = min(submission.num_comments / submission.score, 1.0)
            comments_score = comments_ratio * 4.0
        else:
            comments_score = 0.0

        # Absolute score (0-3)
        absolute_score = min(submission.score / 100, 1.0) * 3.0

        total_score = ratio_score + comments_score + absolute_score

        return min(total_score, 10.0)

    def test_connection(self) -> bool:
        """
        Test Reddit API connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            # Try to access Reddit frontpage
            subreddit = self.reddit.subreddit('popular')
            next(subreddit.hot(limit=1))
            logger.info("✅ Reddit API connection successful")
            return True
        except Exception as e:
            logger.error(f"❌ Reddit API connection failed: {e}")
            return False


# Convenience function for integration with web_scraper.py

def scrape_reddit_source(
    source: Dict[str, Any],
    days_back: int = 7
) -> List[Dict[str, Any]]:
    """
    Scrape a Reddit source (for integration with WebScraper)

    Args:
        source: Source config dict with 'subreddit' key
        days_back: Days to look back

    Returns:
        List of articles
    """
    if not PRAW_AVAILABLE:
        logger.warning(f"PRAW not available - skipping {source.get('name', 'Reddit')}")
        return []

    subreddit_name = source.get('subreddit')
    if not subreddit_name:
        logger.warning(f"No subreddit specified for source: {source.get('name')}")
        return []

    try:
        scraper = RedditScraper()
        articles = scraper.scrape_subreddit(
            subreddit_name=subreddit_name,
            limit=50,
            days_back=days_back
        )

        # Add source metadata
        for article in articles:
            article['source_id'] = source.get('id')
            article['credibility_score'] = source.get('credibility_score', 7)
            article['relevance_weight'] = source.get('relevance_weight', 7)

        return articles

    except Exception as e:
        logger.error(f"Error scraping Reddit source {source.get('name')}: {e}")
        return []


if __name__ == "__main__":
    # Test Reddit scraper
    import sys

    if not PRAW_AVAILABLE:
        print("❌ PRAW not installed. Install with: pip install praw")
        sys.exit(1)

    # Check for credentials
    client_id = os.getenv('REDDIT_CLIENT_ID')
    client_secret = os.getenv('REDDIT_CLIENT_SECRET')

    if not client_id or not client_secret:
        print("❌ Reddit credentials not found in .env")
        print("\nSetup instructions:")
        print("1. Go to https://www.reddit.com/prefs/apps")
        print("2. Click 'create another app...'")
        print("3. Choose 'script'")
        print("4. Set redirect URI: http://localhost:8080")
        print("5. Add to .env:")
        print("   REDDIT_CLIENT_ID=your_client_id")
        print("   REDDIT_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    # Test scraper
    print("Testing Reddit scraper...\n")

    scraper = RedditScraper()

    # Test connection
    if not scraper.test_connection():
        print("❌ Connection test failed")
        sys.exit(1)

    # Test scraping
    print("\nScraping r/ChatGPT...")
    articles = scraper.scrape_subreddit('ChatGPT', limit=10, days_back=7)

    print(f"\n✅ Scraped {len(articles)} articles\n")

    if articles:
        print("Sample article:")
        article = articles[0]
        print(f"  Title: {article['title'][:60]}...")
        print(f"  Score: {article['reddit_score']} ({article['reddit_upvote_ratio']:.0%} upvoted)")
        print(f"  Comments: {article['reddit_num_comments']}")
        print(f"  Engagement: {article['engagement_score']:.1f}/10")
        print(f"  Top comment: {article['reddit_comments'][0]['body'][:80] if article['reddit_comments'] else 'None'}...")
