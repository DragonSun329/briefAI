#!/usr/bin/env python3
"""
Product Hunt API Scraper - GraphQL-based scraper for product launches

Fetches:
- Hot products from last N days
- Product details (name, tagline, description)
- Upvote counts and comment counts
- User comments and reviews
- Maker information
"""

import os
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class ProductHuntScraper:
    """Scraper for Product Hunt using GraphQL API"""

    def __init__(self, access_token: Optional[str] = None):
        """
        Initialize Product Hunt scraper

        Args:
            access_token: OAuth access token (from .env if not provided)

        Raises:
            ValueError: If access token is missing
        """
        self.access_token = access_token or os.getenv('PRODUCTHUNT_ACCESS_TOKEN')

        if not self.access_token:
            raise ValueError(
                "Product Hunt access token missing. Set PRODUCTHUNT_ACCESS_TOKEN in .env\n"
                "Run: python3 scripts/setup_producthunt_oauth.py"
            )

        self.endpoint = "https://api.producthunt.com/v2/api/graphql"
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }

        logger.info("Product Hunt API initialized")

    def scrape_hot_products(
        self,
        days_back: int = 7,
        limit: int = 50,
        min_votes: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Scrape hot products from last N days

        Args:
            days_back: Days to look back
            limit: Maximum products to fetch
            min_votes: Minimum upvote count

        Returns:
            List of article dictionaries
        """
        articles = []

        try:
            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=days_back)
            cutoff_str = cutoff_date.strftime('%Y-%m-%dT%H:%M:%SZ')

            # GraphQL query
            query = '''
            query GetPosts($postedAfter: DateTime!, $first: Int!) {
              posts(order: VOTES, postedAfter: $postedAfter, first: $first) {
                edges {
                  node {
                    id
                    name
                    tagline
                    description
                    votesCount
                    commentsCount
                    createdAt
                    url
                    website
                    featured
                    productLinks {
                      url
                      type
                    }
                    thumbnail {
                      url
                    }
                    topics {
                      edges {
                        node {
                          name
                        }
                      }
                    }
                    makers {
                      edges {
                        node {
                          name
                          headline
                        }
                      }
                    }
                    comments(first: 10) {
                      edges {
                        node {
                          id
                          body
                          createdAt
                          votesCount
                          user {
                            name
                            headline
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
            '''

            variables = {
                'postedAfter': cutoff_str,
                'first': limit
            }

            # Execute GraphQL query
            response = requests.post(
                self.endpoint,
                json={'query': query, 'variables': variables},
                headers=self.headers,
                timeout=30
            )

            response.raise_for_status()
            data = response.json()

            # Check for errors
            if 'errors' in data:
                logger.error(f"GraphQL errors: {data['errors']}")
                return []

            # Parse products
            posts = data.get('data', {}).get('posts', {}).get('edges', [])

            for edge in posts:
                node = edge.get('node', {})

                # Filter by votes
                if node.get('votesCount', 0) < min_votes:
                    continue

                # Extract comments
                comments = self._extract_comments(node.get('comments', {}).get('edges', []))

                # Extract topics
                topics = [
                    t.get('node', {}).get('name')
                    for t in node.get('topics', {}).get('edges', [])
                ]

                # Extract makers
                makers = [
                    m.get('node', {}).get('name')
                    for m in node.get('makers', {}).get('edges', [])
                ]

                # Build article dict
                article = {
                    'title': f"{node.get('name')} - {node.get('tagline', '')}",
                    'url': node.get('url', ''),
                    'source': 'Product Hunt',
                    'content': node.get('description', node.get('tagline', ''))[:2000],
                    'date': datetime.fromisoformat(node.get('createdAt').replace('Z', '+00:00')).strftime('%Y-%m-%d'),
                    'published_date': datetime.fromisoformat(node.get('createdAt').replace('Z', '+00:00')),
                    'language': 'en',

                    # Product Hunt-specific metadata
                    'ph_product_id': node.get('id'),
                    'ph_product_name': node.get('name'),
                    'ph_tagline': node.get('tagline'),
                    'ph_votes': node.get('votesCount', 0),
                    'ph_comments_count': node.get('commentsCount', 0),
                    'ph_comments': comments,
                    'ph_website': node.get('website'),
                    'ph_featured': node.get('featured', False),
                    'ph_thumbnail': node.get('thumbnail', {}).get('url'),
                    'ph_topics': topics,
                    'ph_makers': makers,

                    # For review extraction
                    'has_reviews': len(comments) > 0,
                    'review_count': len(comments),
                    'trending_score': self._calculate_trending_score(node)
                }

                articles.append(article)

            logger.info(f"Scraped {len(articles)} products from Product Hunt")

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP error scraping Product Hunt: {e}")
        except Exception as e:
            logger.error(f"Error scraping Product Hunt: {e}")

        return articles

    def _extract_comments(self, comment_edges: List[Dict]) -> List[Dict[str, Any]]:
        """
        Extract comments from GraphQL response

        Args:
            comment_edges: Comment edges from GraphQL

        Returns:
            List of comment dictionaries
        """
        comments = []

        for edge in comment_edges:
            node = edge.get('node', {})
            user = node.get('user', {})

            comments.append({
                'body': node.get('body', ''),
                'votes': node.get('votesCount', 0),
                'author': user.get('name', 'Anonymous'),
                'author_headline': user.get('headline', ''),
                'created_at': node.get('createdAt', ''),
                'source': 'Product Hunt'
            })

        return comments

    def _calculate_trending_score(self, product_node: Dict) -> float:
        """
        Calculate trending score for a product

        Score based on:
        - Votes (50%)
        - Comments engagement (30%)
        - Recency (20%)

        Args:
            product_node: Product node from GraphQL

        Returns:
            Trending score (0-10)
        """
        # Votes component (0-5)
        votes = product_node.get('votesCount', 0)
        votes_score = min(votes / 100, 1.0) * 5.0

        # Comments engagement (0-3)
        comments_count = product_node.get('commentsCount', 0)
        comments_score = min(comments_count / 50, 1.0) * 3.0

        # Recency (0-2)
        created_at = datetime.fromisoformat(product_node.get('createdAt').replace('Z', '+00:00'))
        hours_old = (datetime.utcnow().replace(tzinfo=created_at.tzinfo) - created_at).total_seconds() / 3600
        recency_score = max(1 - (hours_old / 168), 0) * 2.0  # 168 hours = 1 week

        total_score = votes_score + comments_score + recency_score

        return min(total_score, 10.0)

    def test_connection(self) -> bool:
        """
        Test Product Hunt API connection

        Returns:
            True if connection successful, False otherwise
        """
        try:
            query = '''
            query {
              viewer {
                user {
                  name
                }
              }
            }
            '''

            response = requests.post(
                self.endpoint,
                json={'query': query},
                headers=self.headers,
                timeout=10
            )

            response.raise_for_status()
            data = response.json()

            if 'errors' in data:
                logger.error(f"❌ API errors: {data['errors']}")
                return False

            viewer = data.get('data', {}).get('viewer', {})
            if viewer:
                logger.info(f"✅ Product Hunt API connection successful (read-only mode)")
                return True
            else:
                logger.info(f"✅ Product Hunt API connection successful")
                return True

        except Exception as e:
            logger.error(f"❌ Product Hunt API connection failed: {e}")
            return False


# Convenience function for integration with web_scraper.py

def scrape_producthunt_api(
    source: Dict[str, Any],
    days_back: int = 7
) -> List[Dict[str, Any]]:
    """
    Scrape Product Hunt API (for integration with WebScraper)

    Args:
        source: Source config dict
        days_back: Days to look back

    Returns:
        List of articles
    """
    try:
        scraper = ProductHuntScraper()
        articles = scraper.scrape_hot_products(
            days_back=days_back,
            limit=50,
            min_votes=5
        )

        # Add source metadata
        for article in articles:
            article['source_id'] = source.get('id')
            article['credibility_score'] = source.get('credibility_score', 9)
            article['relevance_weight'] = source.get('relevance_weight', 10)

        return articles

    except Exception as e:
        logger.error(f"Error scraping Product Hunt API: {e}")
        return []


if __name__ == "__main__":
    # Test Product Hunt scraper
    import sys

    # Check for credentials
    access_token = os.getenv('PRODUCTHUNT_ACCESS_TOKEN')

    if not access_token:
        print("❌ Product Hunt access token not found in .env")
        print("\nSetup instructions:")
        print("1. Run: python3 scripts/setup_producthunt_oauth.py")
        print("2. Follow OAuth flow to get access token")
        print("3. Add to .env:")
        print("   PRODUCTHUNT_ACCESS_TOKEN=your_access_token")
        sys.exit(1)

    # Test scraper
    print("Testing Product Hunt scraper...\n")

    scraper = ProductHuntScraper()

    # Test connection
    if not scraper.test_connection():
        print("❌ Connection test failed")
        sys.exit(1)

    # Test scraping
    print("\nScraping hot products...")
    articles = scraper.scrape_hot_products(days_back=7, limit=10)

    print(f"\n✅ Scraped {len(articles)} products\n")

    if articles:
        print("Sample product:")
        article = articles[0]
        print(f"  Name: {article['ph_product_name']}")
        print(f"  Tagline: {article['ph_tagline']}")
        print(f"  Votes: {article['ph_votes']}")
        print(f"  Comments: {article['ph_comments_count']}")
        print(f"  Trending Score: {article['trending_score']:.1f}/10")
        print(f"  Topics: {', '.join(article['ph_topics'][:3])}")
        print(f"  Top comment: {article['ph_comments'][0]['body'][:80] if article['ph_comments'] else 'None'}...")
