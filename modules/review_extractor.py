#!/usr/bin/env python3
"""
Review Extractor - Extract structured reviews from different sources

Extracts reviews from:
- Product Hunt comments
- Reddit comments
- Article mentions
- User feedback in text
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger


class ReviewExtractor:
    """Extract structured reviews from various sources"""

    def __init__(self):
        """Initialize review extractor"""
        logger.info("Review extractor initialized")

    def extract_reviews(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Extract reviews from all articles

        Args:
            articles: List of article dictionaries

        Returns:
            Articles with extracted reviews in 'reviews' field
        """
        for article in articles:
            reviews = []

            # Extract from Product Hunt comments
            if article.get('ph_comments'):
                ph_reviews = self.extract_from_producthunt(article)
                reviews.extend(ph_reviews)

            # Extract from Reddit comments
            if article.get('reddit_comments'):
                reddit_reviews = self.extract_from_reddit(article)
                reviews.extend(reddit_reviews)

            # Store reviews
            article['reviews'] = reviews
            article['review_count'] = len(reviews)
            article['has_reviews'] = len(reviews) > 0

        logger.info(f"Extracted reviews from {len(articles)} articles")
        return articles

    def extract_from_producthunt(self, article: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract reviews from Product Hunt comments

        Args:
            article: Article with ph_comments field

        Returns:
            List of review dictionaries
        """
        reviews = []

        for comment in article.get('ph_comments', []):
            review = {
                'text': comment.get('body', ''),
                'author': comment.get('author', 'Anonymous'),
                'author_headline': comment.get('author_headline', ''),
                'votes': comment.get('votes', 0),
                'date': comment.get('created_at', ''),
                'source': 'Product Hunt',
                'source_type': 'product_hunt',
                'product_name': article.get('ph_product_name', ''),
                'url': article.get('url', ''),

                # Review classification (to be filled by summarizer)
                'sentiment': None,  # positive/negative/mixed
                'is_user_testimonial': self._is_testimonial(comment.get('body', '')),
                'mentions_pros': self._mentions_pros(comment.get('body', '')),
                'mentions_cons': self._mentions_cons(comment.get('body', '')),
                'credibility_score': self._calculate_comment_credibility(comment)
            }

            reviews.append(review)

        return reviews

    def extract_from_reddit(self, article: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract reviews from Reddit comments

        Args:
            article: Article with reddit_comments field

        Returns:
            List of review dictionaries
        """
        reviews = []

        for comment in article.get('reddit_comments', []):
            review = {
                'text': comment.get('body', ''),
                'author': comment.get('author', '[deleted]'),
                'votes': comment.get('score', 0),
                'date': comment.get('created_utc', ''),
                'source': f"Reddit r/{article.get('subreddit', 'unknown')}",
                'source_type': 'reddit',
                'product_name': self._extract_product_name_from_text(
                    article.get('title', '') + ' ' + comment.get('body', '')
                ),
                'url': article.get('url', ''),

                # Review classification
                'sentiment': None,
                'is_user_testimonial': self._is_testimonial(comment.get('body', '')),
                'mentions_pros': self._mentions_pros(comment.get('body', '')),
                'mentions_cons': self._mentions_cons(comment.get('body', '')),
                'credibility_score': self._calculate_comment_credibility(comment),
                'is_op': comment.get('is_submitter', False)
            }

            reviews.append(review)

        return reviews

    def _is_testimonial(self, text: str) -> bool:
        """
        Check if comment is a user testimonial (personal experience)

        Args:
            text: Comment text

        Returns:
            True if testimonial, False otherwise
        """
        testimonial_patterns = [
            'i use', 'i tried', 'i tested', "i've been using",
            'works great', 'love this', 'game changer', 'highly recommend',
            'saved me', 'helped me', 'improved my', 'made my life',
            'been using it for', 'switched from', 'my experience',
            'personally', 'for me', 'in my case'
        ]

        text_lower = text.lower()
        return any(pattern in text_lower for pattern in testimonial_patterns)

    def _mentions_pros(self, text: str) -> bool:
        """
        Check if comment mentions positive aspects

        Args:
            text: Comment text

        Returns:
            True if mentions pros
        """
        pros_patterns = [
            'pro:', 'pros:', 'advantage', 'benefit', 'strength',
            'good thing', 'i like', 'love that', 'great feature',
            'works well', 'fast', 'easy to use', 'intuitive',
            'powerful', 'efficient', 'accurate', 'reliable'
        ]

        text_lower = text.lower()
        return any(pattern in text_lower for pattern in pros_patterns)

    def _mentions_cons(self, text: str) -> bool:
        """
        Check if comment mentions negative aspects

        Args:
            text: Comment text

        Returns:
            True if mentions cons
        """
        cons_patterns = [
            'con:', 'cons:', 'downside', 'disadvantage', 'weakness',
            'problem', 'issue', 'bug', 'annoying', 'frustrating',
            "doesn't work", 'not working', 'broken', 'slow',
            'expensive', 'pricey', 'too expensive', 'overpriced',
            'missing', 'lack of', 'wish it had', 'needs improvement'
        ]

        text_lower = text.lower()
        return any(pattern in text_lower for pattern in cons_patterns)

    def _calculate_comment_credibility(self, comment: Dict[str, Any]) -> float:
        """
        Calculate credibility score for a comment

        Based on:
        - Vote count (higher = more credible)
        - Length (too short or too long = less credible)
        - Author info availability

        Args:
            comment: Comment dictionary

        Returns:
            Credibility score (0-1)
        """
        score = 0.5  # Base score

        # Vote component (0-0.3)
        votes = comment.get('votes', 0) or comment.get('score', 0)
        if votes > 0:
            vote_score = min(votes / 20, 1.0) * 0.3
            score += vote_score

        # Length component (0-0.2)
        text = comment.get('body', '')
        text_len = len(text)
        if 50 <= text_len <= 500:
            score += 0.2
        elif text_len > 500:
            score += 0.1

        # Author component (0-0.1)
        author = comment.get('author', '')
        if author and author not in ['[deleted]', '[removed]', 'Anonymous']:
            score += 0.1

        return min(score, 1.0)

    def _extract_product_name_from_text(self, text: str) -> Optional[str]:
        """
        Try to extract product name from text

        Args:
            text: Text to analyze

        Returns:
            Product name if found, None otherwise
        """
        # Common product name patterns
        # This is a simple heuristic - will be improved by LLM in deduplicator

        # Look for capitalized phrases that might be product names
        words = text.split()

        # Common AI tools (hardcoded for now)
        known_products = [
            'ChatGPT', 'Claude', 'Cursor', 'Copilot', 'Midjourney',
            'DALL-E', 'Stable Diffusion', 'Notion', 'Obsidian',
            'Zapier', 'Make', 'n8n', 'Perplexity', 'Gemini'
        ]

        for product in known_products:
            if product.lower() in text.lower():
                return product

        return None

    def aggregate_reviews_by_product(
        self,
        articles: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group reviews by product name

        Args:
            articles: Articles with reviews

        Returns:
            Dictionary mapping product_name -> list of reviews
        """
        product_reviews = {}

        for article in articles:
            reviews = article.get('reviews', [])

            for review in reviews:
                product_name = review.get('product_name')

                if not product_name:
                    # Use article title as fallback
                    product_name = article.get('ph_product_name') or article.get('title', 'Unknown')

                if product_name not in product_reviews:
                    product_reviews[product_name] = []

                product_reviews[product_name].append(review)

        logger.info(f"Aggregated reviews for {len(product_reviews)} products")

        return product_reviews

    def get_review_statistics(
        self,
        articles: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Get statistics about extracted reviews

        Args:
            articles: Articles with reviews

        Returns:
            Statistics dictionary
        """
        total_reviews = 0
        product_hunt_reviews = 0
        reddit_reviews = 0
        testimonials = 0
        with_pros = 0
        with_cons = 0

        for article in articles:
            reviews = article.get('reviews', [])
            total_reviews += len(reviews)

            for review in reviews:
                if review['source_type'] == 'product_hunt':
                    product_hunt_reviews += 1
                elif review['source_type'] == 'reddit':
                    reddit_reviews += 1

                if review.get('is_user_testimonial'):
                    testimonials += 1
                if review.get('mentions_pros'):
                    with_pros += 1
                if review.get('mentions_cons'):
                    with_cons += 1

        return {
            'total_reviews': total_reviews,
            'product_hunt_reviews': product_hunt_reviews,
            'reddit_reviews': reddit_reviews,
            'testimonials': testimonials,
            'reviews_with_pros': with_pros,
            'reviews_with_cons': with_cons,
            'articles_with_reviews': sum(1 for a in articles if a.get('has_reviews')),
            'avg_reviews_per_article': total_reviews / len(articles) if articles else 0
        }


if __name__ == "__main__":
    # Test review extractor
    print("Testing ReviewExtractor...\n")

    # Sample data
    sample_articles = [
        {
            'title': 'Cursor IDE - AI-powered code editor',
            'ph_product_name': 'Cursor',
            'ph_comments': [
                {
                    'body': "I've been using Cursor for 2 weeks and it's a game changer for coding. The AI completions are 3x faster than Copilot.",
                    'author': 'john_dev',
                    'votes': 15,
                    'created_at': '2025-10-30'
                },
                {
                    'body': "Love the features but it's a bit expensive at $20/month. Would be great if there was a free tier.",
                    'author': 'jane_coder',
                    'votes': 8,
                    'created_at': '2025-10-30'
                }
            ],
            'reddit_comments': []
        }
    ]

    extractor = ReviewExtractor()

    # Extract reviews
    articles = extractor.extract_reviews(sample_articles)

    print(f"✅ Extracted reviews from {len(articles)} articles\n")

    # Show first article reviews
    article = articles[0]
    print(f"Article: {article['title']}")
    print(f"Reviews: {article['review_count']}\n")

    for i, review in enumerate(article['reviews'], 1):
        print(f"Review {i}:")
        print(f"  Author: {review['author']}")
        print(f"  Votes: {review['votes']}")
        print(f"  Text: {review['text'][:80]}...")
        print(f"  Testimonial: {review['is_user_testimonial']}")
        print(f"  Mentions pros: {review['mentions_pros']}")
        print(f"  Mentions cons: {review['mentions_cons']}")
        print(f"  Credibility: {review['credibility_score']:.2f}")
        print()

    # Get statistics
    stats = extractor.get_review_statistics(articles)
    print("Statistics:")
    for key, value in stats.items():
        print(f"  {key}: {value}")
