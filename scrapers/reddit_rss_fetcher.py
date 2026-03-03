"""
Reddit RSS Fetcher for briefAI

Fetches posts from Reddit via RSS/Atom feeds since the JSON API is blocked (403).
RSS feeds at https://www.reddit.com/r/SUBREDDIT/.rss still work as of March 2026.
"""

import feedparser
import requests
import time
import re
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from html import unescape


class RedditRSSFetcher:
    """Fetch Reddit posts via RSS feeds."""

    HEADERS = {
        "User-Agent": "briefAI/2.0 (RSS reader)",
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags and unescape entities."""
        text = re.sub(r'<[^>]+>', ' ', html)
        text = unescape(text)
        return re.sub(r'\s+', ' ', text).strip()

    def _parse_entry(self, entry: dict, subreddit: str) -> Dict[str, Any]:
        """Parse a single RSS entry into our standard post format."""
        # Extract author (RSS gives /u/name format)
        author = getattr(entry, 'author', '') or ''
        author = author.replace('/u/', '').strip()

        # URL / permalink
        link = entry.get('link', '')
        # Try to get reddit permalink
        permalink = ''
        if 'reddit.com/r/' in link:
            permalink = link.replace('https://www.reddit.com', '').replace('https://reddit.com', '')

        # Content snippet
        content = ''
        if hasattr(entry, 'content') and entry.content:
            content = self._strip_html(entry.content[0].get('value', ''))
        elif hasattr(entry, 'summary'):
            content = self._strip_html(entry.summary or '')

        # Timestamp
        created_utc = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                created_utc = time.mktime(entry.published_parsed)
            except Exception:
                pass
        elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            try:
                created_utc = time.mktime(entry.updated_parsed)
            except Exception:
                pass

        # Extract post ID from link
        post_id = ''
        m = re.search(r'/comments/([a-z0-9]+)/', link)
        if m:
            post_id = m.group(1)

        return {
            "id": post_id,
            "title": entry.get('title', ''),
            "subreddit": subreddit,
            "url": link,
            "permalink": permalink,
            "score": 0,  # RSS doesn't provide score
            "upvote_ratio": 0,
            "num_comments": 0,  # RSS doesn't provide this
            "created_utc": created_utc,
            "author": author,
            "is_self": 'reddit.com/r/' in link and '/comments/' in link,
            "selftext": content[:500],
            "link_flair_text": None,
            "source_subreddit": subreddit,
            "source": "rss",
        }

    def fetch_subreddit(self, subreddit: str, feed_type: str = "hot") -> List[Dict[str, Any]]:
        """Fetch posts from a subreddit RSS feed.
        
        feed_type: 'hot' (default), 'new', 'top'
        """
        if feed_type == "hot":
            url = f"https://www.reddit.com/r/{subreddit}/.rss"
        elif feed_type == "top":
            url = f"https://www.reddit.com/r/{subreddit}/top/.rss?t=week"
        else:
            url = f"https://www.reddit.com/r/{subreddit}/{feed_type}/.rss"

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            feed = feedparser.parse(resp.text)

            if feed.bozo and not feed.entries:
                print(f"    RSS parse error for r/{subreddit}: {feed.bozo_exception}")
                return []

            posts = []
            for entry in feed.entries:
                posts.append(self._parse_entry(entry, subreddit))
            return posts

        except Exception as e:
            print(f"    Error fetching RSS for r/{subreddit}: {e}")
            return []

    def fetch_multiple_subreddits(self, subreddits: List[str], 
                                   include_top: bool = True) -> List[Dict[str, Any]]:
        """Fetch from multiple subreddits with rate limiting. Returns deduplicated posts."""
        all_posts = []
        seen_ids = set()

        for i, sub in enumerate(subreddits):
            if i > 0:
                time.sleep(1)  # Rate limit: 1 req/sec

            print(f"  Fetching r/{sub} (RSS)...")
            posts = self.fetch_subreddit(sub, "hot")
            
            for p in posts:
                pid = p["id"]
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_posts.append(p)

            # Also fetch top/week for broader coverage
            if include_top:
                time.sleep(1)
                top_posts = self.fetch_subreddit(sub, "top")
                for p in top_posts:
                    pid = p["id"]
                    if pid and pid not in seen_ids:
                        seen_ids.add(pid)
                        all_posts.append(p)

            print(f"    Got {sum(1 for p in all_posts if p['source_subreddit'] == sub)} posts from r/{sub}")

        return all_posts


def test_fetch(subreddits: List[str] = None):
    """Quick test with a few subreddits."""
    if not subreddits:
        subreddits = ["MachineLearning", "LocalLLaMA", "OpenAI"]

    fetcher = RedditRSSFetcher()
    print(f"Testing RSS fetch for: {subreddits}")
    posts = fetcher.fetch_multiple_subreddits(subreddits, include_top=True)
    print(f"\nTotal posts: {len(posts)}")
    
    for p in posts[:5]:
        print(f"  [{p['subreddit']}] {p['title'][:60]}...")
        print(f"    Author: {p['author']} | URL: {p['url'][:80]}")
    
    return posts


if __name__ == "__main__":
    test_fetch()
