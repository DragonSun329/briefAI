"""
Web Scraper Module

Scrapes articles from configured news sources using RSS feeds and HTML parsing.
Supports caching to avoid redundant scraping.
"""

import json
import requests
import feedparser
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from bs4 import BeautifulSoup
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed

from utils.cache_manager import CacheManager


class WebScraper:
    """Scrapes AI news from configured sources"""

    def __init__(
        self,
        sources_config: str = "./config/sources.json",
        cache_manager: CacheManager = None,
        max_articles_per_source: int = 20
    ):
        """
        Initialize web scraper

        Args:
            sources_config: Path to sources configuration file
            cache_manager: Cache manager instance (creates new if None)
            max_articles_per_source: Maximum articles to scrape per source
        """
        self.sources_config = Path(sources_config)
        self.cache_manager = cache_manager or CacheManager()
        self.max_articles_per_source = max_articles_per_source

        # Load sources
        with open(self.sources_config, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.sources = [s for s in config['sources'] if s.get('enabled', True)]
            self.weighting_config = config.get('weighting_config', {})

        logger.info(f"Loaded {len(self.sources)} enabled sources")
        if self.weighting_config.get('enabled', False):
            logger.info("Source weighting system enabled")

        # Setup session with headers
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (compatible; AI-Briefing-Agent/1.0)'
        })

    def scrape_all(
        self,
        categories: List[str] = None,
        days_back: int = 7,
        use_cache: bool = True,
        query_plan: Dict[str, Any] = None,
        enable_parallel: bool = True,
        max_workers: int = 8
    ) -> List[Dict[str, Any]]:
        """
        Scrape articles from all sources (with optional parallel execution)

        Args:
            categories: Filter by categories (None = all categories)
            days_back: Only get articles from last N days
            use_cache: Use cached articles if available
            query_plan: Query plan from ACE-Planner for keyword filtering
            enable_parallel: Use parallel scraping (default: True)
            max_workers: Number of parallel threads (default: 8)

        Returns:
            List of article dictionaries
        """
        all_articles = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Filter sources by category if specified
        sources_to_scrape = self.sources
        if categories:
            sources_to_scrape = [
                s for s in self.sources
                if set(s.get('categories', [])).intersection(categories)
            ]
            logger.info(f"Filtered to {len(sources_to_scrape)} sources matching categories")

        if enable_parallel and len(sources_to_scrape) > 1:
            # Parallel scraping with ThreadPoolExecutor
            logger.info(f"Starting parallel scraping ({len(sources_to_scrape)} sources, max_workers={max_workers})")
            all_articles = self._scrape_all_parallel(
                sources_to_scrape,
                cutoff_date,
                use_cache,
                query_plan,
                max_workers
            )
        else:
            # Sequential scraping (fallback)
            logger.info(f"Starting sequential scraping ({len(sources_to_scrape)} sources)")
            all_articles = self._scrape_all_sequential(
                sources_to_scrape,
                cutoff_date,
                use_cache,
                query_plan
            )

        logger.info(f"Total articles scraped: {len(all_articles)}")
        return all_articles

    def _scrape_all_parallel(
        self,
        sources: List[Dict[str, Any]],
        cutoff_date: datetime,
        use_cache: bool,
        query_plan: Dict[str, Any],
        max_workers: int
    ) -> List[Dict[str, Any]]:
        """
        Scrape multiple sources in parallel using ThreadPoolExecutor

        Args:
            sources: List of sources to scrape
            cutoff_date: Cutoff date for article filtering
            use_cache: Use cached articles
            query_plan: Query plan for filtering
            max_workers: Number of parallel threads

        Returns:
            List of all scraped articles
        """
        all_articles = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all scraping tasks
            futures = {
                executor.submit(
                    self._scrape_single_source,
                    source,
                    cutoff_date,
                    use_cache,
                    query_plan
                ): source['name']
                for source in sources
            }

            # Collect results as they complete
            completed = 0
            for future in as_completed(futures):
                source_name = futures[future]
                completed += 1
                try:
                    articles = future.result()
                    if articles:
                        all_articles.extend(articles)
                        logger.info(f"[{completed}/{len(sources)}] {source_name}: {len(articles)} articles")
                    else:
                        logger.debug(f"[{completed}/{len(sources)}] {source_name}: no articles")
                except Exception as e:
                    logger.error(f"[{completed}/{len(sources)}] {source_name} failed: {e}")

        return all_articles

    def _scrape_all_sequential(
        self,
        sources: List[Dict[str, Any]],
        cutoff_date: datetime,
        use_cache: bool,
        query_plan: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Scrape sources sequentially (fallback for single source or disabled parallel)

        Args:
            sources: List of sources to scrape
            cutoff_date: Cutoff date for article filtering
            use_cache: Use cached articles
            query_plan: Query plan for filtering

        Returns:
            List of all scraped articles
        """
        all_articles = []

        for i, source in enumerate(sources, 1):
            logger.info(f"Scraping [{i}/{len(sources)}]: {source['name']}")
            try:
                articles = self._scrape_single_source(source, cutoff_date, use_cache, query_plan)
                if articles:
                    all_articles.extend(articles)
                    logger.info(f"Scraped {len(articles)} articles from {source['name']}")
            except Exception as e:
                logger.error(f"Failed to scrape {source['name']}: {e}")
                continue

        return all_articles

    def _scrape_single_source(
        self,
        source: Dict[str, Any],
        cutoff_date: datetime,
        use_cache: bool,
        query_plan: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Scrape a single source with caching and query plan filtering

        Args:
            source: Source configuration
            cutoff_date: Cutoff date for filtering
            use_cache: Use cached results
            query_plan: Optional query plan for filtering

        Returns:
            List of articles from this source
        """
        # Check cache first
        cache_key = f"source_{source['id']}_7days"
        if use_cache:
            cached_articles = self.cache_manager.get(cache_key, max_age_hours=24)
            if cached_articles:
                # Apply keyword filtering if query plan exists
                if query_plan:
                    cached_articles = self._filter_by_query_plan(cached_articles, query_plan)
                return cached_articles

        # Scrape based on source type
        if source['type'] == 'rss':
            articles = self._scrape_rss(source, cutoff_date)
        elif source['type'] == 'web':
            articles = self._scrape_web(source, cutoff_date)
        else:
            logger.warning(f"Unknown source type: {source['type']}")
            return []

        # Apply keyword filtering if query plan exists
        if query_plan and articles:
            articles = self._filter_by_query_plan(articles, query_plan)

        # Cache the results
        if articles:
            self.cache_manager.set(cache_key, articles)

        return articles

    def _scrape_rss(
        self,
        source: Dict[str, Any],
        cutoff_date: datetime
    ) -> List[Dict[str, Any]]:
        """Scrape articles from RSS feed"""
        articles = []

        try:
            feed = feedparser.parse(source['rss_url'])

            # Check for feed errors
            if feed.get('bozo', False):
                error_msg = str(feed.get('bozo_exception', 'Unknown error'))
                if 'SSL' in error_msg or 'certificate' in error_msg.lower():
                    logger.error(f"SSL certificate error for {source['name']}: {error_msg}")
                    logger.error("Fix: Run /Applications/Python 3.9/Install Certificates.command")
                else:
                    logger.warning(f"RSS feed warning for {source['name']}: {error_msg}")

            if not feed.entries:
                logger.warning(f"No entries found in RSS feed for {source['name']}")
                return articles

            for entry in feed.entries[:self.max_articles_per_source]:
                # Parse published date
                pub_date = None
                if hasattr(entry, 'published_parsed'):
                    pub_date = datetime(*entry.published_parsed[:6])
                elif hasattr(entry, 'updated_parsed'):
                    pub_date = datetime(*entry.updated_parsed[:6])

                # Skip old articles
                if pub_date and pub_date < cutoff_date:
                    continue

                # Extract content
                content = ""
                if hasattr(entry, 'summary'):
                    content = entry.summary
                elif hasattr(entry, 'description'):
                    content = entry.description

                # Clean HTML from content
                if content:
                    soup = BeautifulSoup(content, 'html.parser')
                    content = soup.get_text().strip()

                article = {
                    'title': entry.title,
                    'url': entry.link,
                    'content': content,
                    'published_date': pub_date.isoformat() if pub_date else None,
                    'source': source['name'],
                    'source_id': source['id'],
                    'language': source['language'],
                    'credibility_score': source.get('credibility_score', 5),
                    'relevance_weight': source.get('relevance_weight', 5),
                    'focus_tags': source.get('focus_tags', [])
                }

                articles.append(article)

        except Exception as e:
            logger.error(f"RSS scraping error for {source['name']}: {e}")

        return articles

    def _scrape_web(
        self,
        source: Dict[str, Any],
        cutoff_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        Scrape articles from web page (HTML parsing)

        Implements generic scraping with fallback to RSS if available
        """
        articles = []

        try:
            # Try RSS URL first if available
            if 'rss_url' in source:
                return self._scrape_rss(source, cutoff_date)

            # Otherwise attempt generic HTML parsing
            logger.debug(f"Attempting HTML scraping for {source['name']}")
            response = self.session.get(source['url'], timeout=15)
            response.raise_for_status()
            response.encoding = source.get('encoding', 'utf-8')

            logger.debug(f"Successfully fetched {source['url']} ({response.status_code})")

            soup = BeautifulSoup(response.text, 'html.parser')

            # Generic article extraction (works for many news sites)
            article_selectors = [
                'article',
                '.article-item',
                '.news-item',
                '.post',
                'li.item'
            ]

            article_elements = []
            for selector in article_selectors:
                article_elements = soup.select(selector)
                if article_elements:
                    break

            for element in article_elements[:self.max_articles_per_source]:
                try:
                    # Extract title
                    title_elem = element.find(['h1', 'h2', 'h3', 'h4']) or element.find('a')
                    title = title_elem.get_text().strip() if title_elem else None

                    # Extract URL
                    link_elem = element.find('a')
                    url = link_elem.get('href', '') if link_elem else ''
                    if url and not url.startswith('http'):
                        from urllib.parse import urljoin
                        url = urljoin(source['url'], url)

                    # Extract summary/content
                    content_elem = element.find(['p', '.summary', '.description'])
                    content = content_elem.get_text().strip() if content_elem else ''

                    # Skip if missing critical fields
                    if not title or not url:
                        continue

                    article = {
                        'title': title,
                        'url': url,
                        'content': content,
                        'published_date': datetime.now().isoformat(),  # Fallback to now
                        'source': source['name'],
                        'source_id': source['id'],
                        'language': source['language'],
                        'credibility_score': source.get('credibility_score', 5),
                        'relevance_weight': source.get('relevance_weight', 5),
                        'focus_tags': source.get('focus_tags', [])
                    }

                    articles.append(article)

                except Exception as e:
                    logger.debug(f"Failed to parse article element: {e}")
                    continue

            if not articles:
                logger.warning(f"No articles extracted from {source['name']} using generic parser")

        except Exception as e:
            logger.error(f"Web scraping error for {source['name']}: {e}")

        return articles

    def _filter_by_query_plan(
        self,
        articles: List[Dict[str, Any]],
        query_plan: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Filter articles based on ACE-Planner query plan keywords

        Args:
            articles: List of articles to filter
            query_plan: Query plan with themes and keywords

        Returns:
            Filtered list of articles
        """
        if not query_plan or not query_plan.get('themes'):
            return articles

        filtered_articles = []

        for article in articles:
            # Combine title and content for matching
            text = (article.get('title', '') + ' ' + article.get('content', '')).lower()

            # Check if article matches any theme
            matches_theme = False

            for theme in query_plan['themes']:
                must_keywords = theme.get('must_keywords', [])
                should_keywords = theme.get('should_keywords', [])
                not_keywords = theme.get('not_keywords', [])

                # Check "not" keywords first (exclusion)
                has_not_keyword = any(kw.lower() in text for kw in not_keywords)
                if has_not_keyword:
                    continue  # Skip this theme

                # Check "must" keywords (at least one must match)
                has_must_keyword = any(kw.lower() in text for kw in must_keywords)

                # Check "should" keywords (optional, but boost relevance)
                should_count = sum(1 for kw in should_keywords if kw.lower() in text)

                # Article matches if:
                # - Has at least one "must" keyword, OR
                # - Has multiple "should" keywords (2+)
                if has_must_keyword or should_count >= 2:
                    matches_theme = True
                    break

            if matches_theme:
                filtered_articles.append(article)

        logger.debug(f"Keyword filtering: {len(articles)} → {len(filtered_articles)} articles")
        return filtered_articles


if __name__ == "__main__":
    # Test web scraper
    scraper = WebScraper()

    # Scrape recent articles
    articles = scraper.scrape_all(days_back=3, use_cache=False)

    print(f"\nScraped {len(articles)} articles:")
    for article in articles[:5]:
        print(f"- {article['title']} ({article['source']})")
