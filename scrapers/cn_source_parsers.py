"""
Custom Parsers for Chinese AI News Sources

Provides site-specific parsing logic for Chinese news sources that
don't work well with generic RSS/HTML parsing.
"""

import re
import json
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from loguru import logger


class ChineseSourceParser:
    """Base class for Chinese source parsers"""

    def __init__(self, source_config: Dict[str, Any]):
        self.source = source_config
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })

    def parse(self, cutoff_date: datetime, max_articles: int = 20) -> List[Dict[str, Any]]:
        """Parse articles from the source"""
        raise NotImplementedError

    def _make_article(self, title: str, url: str, content: str,
                      pub_date: Optional[datetime] = None) -> Dict[str, Any]:
        """Create standardized article dict"""
        return {
            'title': title.strip(),
            'url': url,
            'content': content.strip() if content else '',
            'description': content.strip()[:300] if content else '',  # Tier 1 also checks description
            'published_at': (pub_date or datetime.now()).isoformat(),
            'source': self.source['name'],
            'source_id': self.source['id'],
            'language': self.source.get('language', 'zh-CN'),
            'credibility_score': self.source.get('credibility_score', 7),
            'relevance_weight': self.source.get('relevance_weight', 7),
            'focus_tags': self.source.get('focus_tags', [])
        }


class Parser36Kr(ChineseSourceParser):
    """Parser for 36氪 (36kr.com) AI channel"""

    def parse(self, cutoff_date: datetime, max_articles: int = 20) -> List[Dict[str, Any]]:
        articles = []

        try:
            # 36kr uses a JSON API for article lists
            api_url = "https://36kr.com/api/newsflash"
            params = {
                'column_id': 'ai',
                'per_page': max_articles,
                'page': 1
            }

            # Try the API first
            try:
                response = self.session.get(api_url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('data', {}).get('items', [])

                    for item in items[:max_articles]:
                        pub_time = item.get('published_at', '')
                        if pub_time:
                            pub_date = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
                            if pub_date.replace(tzinfo=None) < cutoff_date:
                                continue

                        article = self._make_article(
                            title=item.get('title', ''),
                            url=f"https://36kr.com/p/{item.get('id', '')}",
                            content=item.get('summary', '') or item.get('description', ''),
                            pub_date=pub_date if pub_time else None
                        )
                        articles.append(article)

                    if articles:
                        logger.info(f"36Kr API: fetched {len(articles)} articles")
                        return articles
            except Exception as e:
                logger.debug(f"36Kr API failed, trying HTML: {e}")

            # Fallback to HTML parsing
            html_url = "https://36kr.com/information/AI"
            response = self.session.get(html_url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 36kr article cards
            article_cards = soup.select('.article-item, .kr-flow-article-item, .flow-item')

            for card in article_cards[:max_articles]:
                try:
                    # Title and link
                    title_elem = card.select_one('a.article-item-title, h2 a, .title a')
                    if not title_elem:
                        title_elem = card.find('a')

                    if not title_elem:
                        continue

                    title = title_elem.get_text().strip()
                    url = title_elem.get('href', '')
                    if url and not url.startswith('http'):
                        url = urljoin('https://36kr.com', url)

                    # Summary
                    summary_elem = card.select_one('.article-item-description, .summary, p')
                    content = summary_elem.get_text().strip() if summary_elem else ''

                    # Date
                    date_elem = card.select_one('.kr-flow-bar-time, .time, time')
                    pub_date = None
                    if date_elem:
                        date_text = date_elem.get_text().strip()
                        pub_date = self._parse_chinese_date(date_text)

                    if not title or not url:
                        continue

                    article = self._make_article(title, url, content, pub_date)
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"36Kr parse error: {e}")
                    continue

            logger.info(f"36Kr HTML: extracted {len(articles)} articles")

        except Exception as e:
            logger.error(f"36Kr parsing failed: {e}")

        return articles

    def _parse_chinese_date(self, date_text: str) -> Optional[datetime]:
        """Parse Chinese date formats like '2小时前', '昨天', '01-22'"""
        now = datetime.now()

        if '分钟前' in date_text:
            minutes = int(re.search(r'(\d+)', date_text).group(1))
            return now - timedelta(minutes=minutes)
        elif '小时前' in date_text:
            hours = int(re.search(r'(\d+)', date_text).group(1))
            return now - timedelta(hours=hours)
        elif '昨天' in date_text:
            return now - timedelta(days=1)
        elif '前天' in date_text:
            return now - timedelta(days=2)
        elif '天前' in date_text:
            days = int(re.search(r'(\d+)', date_text).group(1))
            return now - timedelta(days=days)
        else:
            # Try standard date formats
            for fmt in ['%Y-%m-%d', '%m-%d', '%Y年%m月%d日']:
                try:
                    parsed = datetime.strptime(date_text, fmt)
                    if parsed.year == 1900:  # No year in format
                        parsed = parsed.replace(year=now.year)
                    return parsed
                except ValueError:
                    continue

        return None


class ParserBAAI(ChineseSourceParser):
    """Parser for 智源社区 (hub.baai.ac.cn)"""

    def parse(self, cutoff_date: datetime, max_articles: int = 20) -> List[Dict[str, Any]]:
        articles = []

        try:
            # BAAI Hub uses an API
            api_url = "https://hub.baai.ac.cn/api/v1/posts"
            params = {
                'page': 1,
                'per_page': max_articles,
                'sort': 'latest'
            }

            try:
                response = self.session.get(api_url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    posts = data.get('data', []) or data.get('posts', [])

                    for post in posts[:max_articles]:
                        pub_time = post.get('created_at', '') or post.get('published_at', '')
                        pub_date = None
                        if pub_time:
                            try:
                                pub_date = datetime.fromisoformat(pub_time.replace('Z', '+00:00'))
                                if pub_date.replace(tzinfo=None) < cutoff_date:
                                    continue
                            except:
                                pass

                        article = self._make_article(
                            title=post.get('title', ''),
                            url=f"https://hub.baai.ac.cn/view/{post.get('id', '')}",
                            content=post.get('summary', '') or post.get('content', '')[:500],
                            pub_date=pub_date
                        )
                        articles.append(article)

                    if articles:
                        logger.info(f"BAAI API: fetched {len(articles)} articles")
                        return articles
            except Exception as e:
                logger.debug(f"BAAI API failed, trying HTML: {e}")

            # Fallback to HTML parsing
            response = self.session.get(self.source['url'], timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # BAAI post cards
            post_items = soup.select('.post-item, .article-card, .content-item, article')

            for item in post_items[:max_articles]:
                try:
                    title_elem = item.select_one('h2 a, h3 a, .title a, a.title')
                    if not title_elem:
                        title_elem = item.find('a')

                    if not title_elem:
                        continue

                    title = title_elem.get_text().strip()
                    url = title_elem.get('href', '')
                    if url and not url.startswith('http'):
                        url = urljoin('https://hub.baai.ac.cn', url)

                    summary_elem = item.select_one('.summary, .excerpt, p')
                    content = summary_elem.get_text().strip() if summary_elem else ''

                    if not title or not url:
                        continue

                    article = self._make_article(title, url, content)
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"BAAI parse error: {e}")
                    continue

            logger.info(f"BAAI HTML: extracted {len(articles)} articles")

        except Exception as e:
            logger.error(f"BAAI parsing failed: {e}")

        return articles


class ParserPaperWeekly(ChineseSourceParser):
    """Parser for PaperWeekly"""

    def parse(self, cutoff_date: datetime, max_articles: int = 20) -> List[Dict[str, Any]]:
        articles = []

        try:
            # PaperWeekly main page
            response = self.session.get(self.source['url'], timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # PaperWeekly article items
            article_items = soup.select('.article-item, .paper-item, .post-item, article, .item')

            if not article_items:
                # Try alternative selectors
                article_items = soup.select('a[href*="/paper/"], a[href*="/article/"]')

            for item in article_items[:max_articles]:
                try:
                    # Handle both card and link elements
                    if item.name == 'a':
                        title = item.get_text().strip()
                        url = item.get('href', '')
                    else:
                        title_elem = item.select_one('h2, h3, .title, a')
                        if not title_elem:
                            continue
                        title = title_elem.get_text().strip()
                        link_elem = item.find('a')
                        url = link_elem.get('href', '') if link_elem else ''

                    if url and not url.startswith('http'):
                        url = urljoin(self.source['url'], url)

                    # Summary
                    summary_elem = item.select_one('.summary, .abstract, .description, p') if item.name != 'a' else None
                    content = summary_elem.get_text().strip() if summary_elem else ''

                    if not title or not url:
                        continue

                    # Skip non-article links
                    if '/user/' in url or '/tag/' in url or '/category/' in url:
                        continue

                    article = self._make_article(title, url, content)
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"PaperWeekly parse error: {e}")
                    continue

            logger.info(f"PaperWeekly: extracted {len(articles)} articles")

        except Exception as e:
            logger.error(f"PaperWeekly parsing failed: {e}")

        return articles


class ParserLeiphone(ChineseSourceParser):
    """Parser for 雷锋网 AI科技评论 (leiphone.com)"""

    def parse(self, cutoff_date: datetime, max_articles: int = 20) -> List[Dict[str, Any]]:
        articles = []

        try:
            response = self.session.get(self.source['url'], timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # Leiphone article cards
            article_items = soup.select('.lph-article-item, .article-item, article, .news-item')

            for item in article_items[:max_articles]:
                try:
                    title_elem = item.select_one('h3 a, h2 a, .title a, a.title')
                    if not title_elem:
                        title_elem = item.find('a')

                    if not title_elem:
                        continue

                    title = title_elem.get_text().strip()
                    url = title_elem.get('href', '')
                    if url and not url.startswith('http'):
                        url = urljoin('https://www.leiphone.com', url)

                    # Summary
                    summary_elem = item.select_one('.summary, .description, .excerpt, p')
                    content = summary_elem.get_text().strip() if summary_elem else ''

                    # Date
                    date_elem = item.select_one('.time, .date, time')
                    pub_date = None
                    if date_elem:
                        date_text = date_elem.get_text().strip()
                        pub_date = self._parse_date(date_text)

                    if not title or not url:
                        continue

                    article = self._make_article(title, url, content, pub_date)
                    articles.append(article)

                except Exception as e:
                    logger.debug(f"Leiphone parse error: {e}")
                    continue

            logger.info(f"Leiphone: extracted {len(articles)} articles")

        except Exception as e:
            logger.error(f"Leiphone parsing failed: {e}")

        return articles

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse leiphone date formats"""
        now = datetime.now()

        for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d', '%m-%d %H:%M', '%Y年%m月%d日']:
            try:
                parsed = datetime.strptime(date_text, fmt)
                if parsed.year == 1900:
                    parsed = parsed.replace(year=now.year)
                return parsed
            except ValueError:
                continue

        return None


class ParserXinzhiyuan(ChineseSourceParser):
    """
    Parser for 新智元 (WeChat official account)

    Note: WeChat articles are difficult to scrape directly.
    This parser attempts to fetch from aggregator sites or cached versions.
    """

    def parse(self, cutoff_date: datetime, max_articles: int = 20) -> List[Dict[str, Any]]:
        articles = []

        try:
            # WeChat official accounts are hard to scrape
            # Try using sogou weixin search as a proxy
            search_url = "https://weixin.sogou.com/weixin"
            params = {
                'type': 1,  # Official account search
                'query': '新智元',
                's_from': 'input',
            }

            try:
                response = self.session.get(search_url, params=params, timeout=15)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Get article links from search results
                    article_links = soup.select('.news-list li a[href*="weixin.qq.com"]')

                    for link in article_links[:max_articles]:
                        try:
                            title = link.get_text().strip()
                            url = link.get('href', '')

                            if title and url:
                                article = self._make_article(title, url, '')
                                articles.append(article)
                        except:
                            continue

                    if articles:
                        logger.info(f"Xinzhiyuan (Sogou): fetched {len(articles)} articles")
                        return articles
            except Exception as e:
                logger.debug(f"Xinzhiyuan Sogou search failed: {e}")

            # Alternative: Try to scrape from WeChat profile page (often blocked)
            logger.warning(f"Xinzhiyuan: WeChat scraping is limited, found {len(articles)} articles")

        except Exception as e:
            logger.error(f"Xinzhiyuan parsing failed: {e}")

        return articles


# Parser registry - maps source IDs to parser classes
CUSTOM_PARSERS = {
    '36kr_ai': Parser36Kr,
    'xinzhiyuan': ParserXinzhiyuan,
    'baai_hub': ParserBAAI,
    'paperweekly': ParserPaperWeekly,
    'aikeji_review': ParserLeiphone,
    'leiphone_ai': ParserLeiphone,
}


def get_custom_parser(source_id: str) -> Optional[type]:
    """Get custom parser class for a source ID"""
    return CUSTOM_PARSERS.get(source_id)


def has_custom_parser(source_id: str) -> bool:
    """Check if a source has a custom parser"""
    return source_id in CUSTOM_PARSERS


def parse_with_custom_parser(
    source: Dict[str, Any],
    cutoff_date: datetime,
    max_articles: int = 20
) -> List[Dict[str, Any]]:
    """
    Parse a source using its custom parser.

    Args:
        source: Source configuration dict
        cutoff_date: Cutoff date for articles
        max_articles: Maximum articles to fetch

    Returns:
        List of parsed articles
    """
    parser_class = CUSTOM_PARSERS.get(source['id'])
    if not parser_class:
        logger.warning(f"No custom parser for source: {source['id']}")
        return []

    try:
        parser = parser_class(source)
        articles = parser.parse(cutoff_date, max_articles)
        return articles
    except Exception as e:
        logger.error(f"Custom parser failed for {source['id']}: {e}")
        return []


if __name__ == "__main__":
    # Test parsers
    from datetime import datetime, timedelta

    test_sources = [
        {
            "id": "36kr_ai",
            "name": "36氪 AI频道",
            "url": "https://36kr.com/information/AI",
            "language": "zh-CN",
            "credibility_score": 8,
            "relevance_weight": 9,
            "focus_tags": ["AI创业", "融资"]
        },
        {
            "id": "baai_hub",
            "name": "智源社区",
            "url": "https://hub.baai.ac.cn",
            "language": "zh-CN",
            "credibility_score": 9,
            "relevance_weight": 9,
            "focus_tags": ["智源", "开源"]
        }
    ]

    cutoff = datetime.now() - timedelta(days=7)

    for source in test_sources:
        print(f"\n=== Testing {source['name']} ===")
        articles = parse_with_custom_parser(source, cutoff, max_articles=5)
        print(f"Found {len(articles)} articles:")
        for a in articles[:3]:
            print(f"  - {a['title'][:50]}...")
