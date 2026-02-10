#!/usr/bin/env python3
"""
TechMeme Scraper for briefAI
Fetches top stories from TechMeme with higher signal quality than RSS.
Captures story clusters, related coverage, and social buzz.

No API key required - scrapes public TechMeme page.
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    print("Missing dependencies. Run: pip install requests beautifulsoup4")
    sys.exit(1)

from loguru import logger

# Output paths
DATA_DIR = Path(__file__).parent.parent / "data" / "news_signals"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TECHMEME_URL = "https://www.techmeme.com/"


def fetch_page() -> Optional[str]:
    """Fetch TechMeme homepage HTML."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    
    try:
        response = requests.get(TECHMEME_URL, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logger.error(f"Failed to fetch TechMeme: {e}")
        return None


def parse_stories(html: str) -> List[Dict]:
    """
    Parse TechMeme stories from HTML.
    
    Returns:
        List of story dicts with title, url, source, and related links
    """
    soup = BeautifulSoup(html, 'html.parser')
    stories = []
    
    # Find all story divs - TechMeme uses a specific structure
    # Main stories are in divs with class containing 'topmf' or story items
    story_divs = soup.find_all('div', class_=re.compile(r'clus|topmf|ii'))
    
    # Alternative: find all headline links
    if not story_divs:
        # Fallback to finding strong tags with links (main headlines)
        headlines = soup.find_all('strong')
        
        for headline in headlines:
            link = headline.find('a')
            if link and link.get('href'):
                url = link.get('href', '')
                if url.startswith('http'):
                    story = {
                        'title': link.get_text(strip=True),
                        'url': url,
                        'source': extract_source(url),
                        'related': [],
                        'signal_type': 'techmeme_story',
                        'scraped_at': datetime.now().isoformat()
                    }
                    stories.append(story)
    
    # Parse story clusters
    for div in story_divs:
        # Find the main headline
        headline_link = div.find('a', class_=re.compile(r'ourh'))
        if not headline_link:
            headline_link = div.find('strong')
            if headline_link:
                headline_link = headline_link.find('a')
        
        if not headline_link:
            continue
        
        url = headline_link.get('href', '')
        if not url.startswith('http'):
            continue
        
        title = headline_link.get_text(strip=True)
        if not title or len(title) < 10:
            continue
        
        # Find related/more links
        related = []
        related_links = div.find_all('a', class_=re.compile(r'ourl'))
        if not related_links:
            # Try finding links in cite tags
            cites = div.find_all('cite')
            for cite in cites:
                link = cite.find('a')
                if link:
                    related_links.append(link)
        
        for link in related_links[:5]:  # Limit related links
            related_url = link.get('href', '')
            if related_url.startswith('http') and related_url != url:
                related.append({
                    'url': related_url,
                    'source': link.get_text(strip=True) or extract_source(related_url)
                })
        
        story = {
            'title': title,
            'url': url,
            'source': extract_source(url),
            'related_count': len(related),
            'related': related,
            'signal_type': 'techmeme_story',
            'source_name': 'techmeme',
            'scraped_at': datetime.now().isoformat()
        }
        
        stories.append(story)
    
    # Deduplicate by URL
    seen_urls = set()
    unique_stories = []
    for story in stories:
        if story['url'] not in seen_urls:
            seen_urls.add(story['url'])
            unique_stories.append(story)
    
    return unique_stories


def extract_source(url: str) -> str:
    """Extract publication name from URL."""
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        # Remove www. and common TLDs
        source = domain.replace('www.', '').split('.')[0]
        return source.title()
    except:
        return 'Unknown'


def score_ai_relevance(title: str) -> float:
    """
    Score how relevant a story is to AI.
    
    Returns:
        Float 0-1 indicating AI relevance
    """
    title_lower = title.lower()
    
    # High relevance keywords
    high_keywords = [
        'ai', 'artificial intelligence', 'gpt', 'llm', 'chatgpt', 'claude',
        'openai', 'anthropic', 'deepmind', 'machine learning', 'neural',
        'transformer', 'generative', 'copilot', 'gemini', 'llama', 'mistral'
    ]
    
    # Medium relevance
    medium_keywords = [
        'nvidia', 'chips', 'gpu', 'semiconductor', 'autonomous', 'robot',
        'automation', 'data center', 'cloud', 'microsoft', 'google', 'meta',
        'training', 'model', 'inference'
    ]
    
    # Low relevance
    low_keywords = [
        'tech', 'startup', 'funding', 'vc', 'software', 'saas', 'developer'
    ]
    
    score = 0
    
    for kw in high_keywords:
        if kw in title_lower:
            score += 0.3
    
    for kw in medium_keywords:
        if kw in title_lower:
            score += 0.15
    
    for kw in low_keywords:
        if kw in title_lower:
            score += 0.05
    
    return min(1.0, score)


def scrape_techmeme(limit: int = 30) -> Dict[str, Any]:
    """
    Main scraper function: fetches and parses TechMeme stories.
    
    Args:
        limit: Max stories to return
    
    Returns:
        Dict with stories and metadata
    """
    logger.info("=" * 50)
    logger.info("TechMeme Scraper")
    logger.info("=" * 50)
    
    html = fetch_page()
    if not html:
        return {'stories': [], 'error': 'Failed to fetch page'}
    
    logger.info("Parsing stories...")
    stories = parse_stories(html)
    
    # Score AI relevance
    for story in stories:
        story['ai_relevance'] = score_ai_relevance(story['title'])
    
    # Sort by AI relevance (most relevant first)
    stories.sort(key=lambda x: x.get('ai_relevance', 0), reverse=True)
    
    # Limit
    stories = stories[:limit]
    
    # Separate AI and general stories
    ai_stories = [s for s in stories if s.get('ai_relevance', 0) >= 0.3]
    general_stories = [s for s in stories if s.get('ai_relevance', 0) < 0.3]
    
    result = {
        'scraped_at': datetime.now().isoformat(),
        'total_stories': len(stories),
        'ai_stories_count': len(ai_stories),
        'stories': stories,
        'ai_stories': ai_stories,
        'general_stories': general_stories[:10]  # Keep top 10 general
    }
    
    logger.info("-" * 50)
    logger.info(f"Total stories: {len(stories)}")
    logger.info(f"AI-relevant: {len(ai_stories)}")
    
    return result


def save_signals(signals: Dict[str, Any]) -> Path:
    """Save signals to JSON file."""
    today = datetime.now().strftime("%Y-%m-%d")
    output_path = DATA_DIR / f"techmeme_{today}.json"
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(signals, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved to: {output_path}")
    return output_path


def main():
    """Run the TechMeme scraper."""
    signals = scrape_techmeme()
    save_signals(signals)
    
    # Print top AI stories
    if signals.get('ai_stories'):
        logger.info("\nTop AI Stories:")
        for story in signals['ai_stories'][:5]:
            logger.info(f"  • {story['title'][:70]}...")
            logger.info(f"    {story['source']} | Relevance: {story['ai_relevance']:.0%}")
    
    return signals


if __name__ == "__main__":
    main()
