"""
US Tech Company News Scraper for briefAI

Scrapes news from multiple sources for major US tech companies with AI relevance.
Focuses on NVDA, GOOGL, META, MSFT, AMD and additional AI-relevant tickers.

Target Companies (Priority 1):
- NVIDIA (NVDA) — AI chips leader
- Google/Alphabet (GOOGL) — Gemini, DeepMind
- Meta (META) — Llama, PyTorch
- Microsoft (MSFT) — OpenAI partner, Copilot
- AMD (AMD) — AI chips competitor

Additional Companies (Priority 2):
- Amazon (AMZN) — AWS AI, Anthropic investor
- Apple (AAPL) — Apple Intelligence
- Tesla (TSLA) — FSD, Optimus
- Palantir (PLTR) — Enterprise AI
- Salesforce (CRM) — Einstein AI
- Adobe (ADBE) — Firefly
- Snowflake (SNOW) — Data/AI
- IBM (IBM) — WatsonX
- Oracle (ORCL) — Cloud AI
- Databricks — Data/AI (private)

Data Sources:
1. Google News RSS (per company + AI keywords)
2. Yahoo Finance news API
3. Company newsrooms (investor relations)
4. Alpha Vantage News API (if configured)

Output: data/alternative_signals/us_tech_news_YYYY-MM-DD.json
        Also stores signals in data/signals.db
"""

import requests
import feedparser
import json
import re
import time
import random
import sqlite3
import uuid
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from urllib.parse import quote, urljoin
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class NewsArticle:
    """News article from any source."""
    title: str
    url: str
    company: str                          # Company name
    ticker: str                           # Stock ticker
    source: str                           # News source name
    source_type: str                      # google_news, yahoo, newsroom, etc.
    published_date: Optional[str] = None
    summary: Optional[str] = None
    content_preview: Optional[str] = None
    sentiment_keywords: List[str] = field(default_factory=list)
    ai_relevance_score: float = 0.5       # 0-1 how AI-related


@dataclass
class CompanyNewsSignal:
    """Signal format for database storage."""
    entity_id: str
    source_id: str
    category: str = "media"
    observed_at: str = ""
    raw_value: float = 5.0                # Default neutral sentiment (1-10)
    raw_data: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.7


# ============================================================================
# COMPANY CONFIGURATION
# ============================================================================

US_TECH_COMPANIES = {
    # Priority 1 - Major AI Companies
    "nvidia": {
        "name": "NVIDIA",
        "ticker": "NVDA",
        "priority": 1,
        "aliases": ["NVIDIA Corporation", "Nvidia", "NVDA"],
        "search_queries": [
            "NVIDIA AI",
            "NVIDIA GPU",
            "NVIDIA H100",
            "NVIDIA chips",
            "Jensen Huang NVIDIA",
            "NVIDIA CUDA",
            "NVIDIA inference",
        ],
        "ai_keywords": ["gpu", "h100", "h200", "blackwell", "cuda", "inference", 
                       "training", "data center", "jensen huang", "ai chips"],
        "newsroom_url": "https://nvidianews.nvidia.com/news",
        "ir_url": "https://investor.nvidia.com/news/press-release-details",
    },
    "google": {
        "name": "Google/Alphabet",
        "ticker": "GOOGL",
        "priority": 1,
        "aliases": ["Alphabet", "Alphabet Inc", "Google", "Google LLC", "GOOGL", "GOOG"],
        "search_queries": [
            "Google AI Gemini",
            "Google DeepMind",
            "Alphabet AI",
            "Google Bard",
            "Google Cloud AI",
        ],
        "ai_keywords": ["gemini", "deepmind", "bard", "palm", "vertex ai", "tpu",
                       "alphafold", "waymo", "google brain", "sundar pichai"],
        "newsroom_url": "https://blog.google/technology/ai/",
        "ir_url": "https://abc.xyz/investor/",
    },
    "meta": {
        "name": "Meta",
        "ticker": "META",
        "priority": 1,
        "aliases": ["Meta Platforms", "Meta Platforms Inc", "Facebook", "META"],
        "search_queries": [
            "Meta AI Llama",
            "Meta Llama 3",
            "Meta AI research",
            "Meta PyTorch",
            "Mark Zuckerberg AI",
        ],
        "ai_keywords": ["llama", "pytorch", "fair", "meta ai", "zuckerberg",
                       "open source ai", "metaverse ai", "ray-ban meta"],
        "newsroom_url": "https://ai.meta.com/blog/",
        "ir_url": "https://investor.fb.com/press-releases/",
    },
    "microsoft": {
        "name": "Microsoft",
        "ticker": "MSFT",
        "priority": 1,
        "aliases": ["Microsoft Corporation", "MSFT"],
        "search_queries": [
            "Microsoft Copilot AI",
            "Microsoft OpenAI",
            "Microsoft Azure AI",
            "Microsoft AI",
            "Satya Nadella AI",
        ],
        "ai_keywords": ["copilot", "azure ai", "openai partnership", "bing chat",
                       "github copilot", "microsoft research", "nadella", "phi"],
        "newsroom_url": "https://news.microsoft.com/source/",
        "ir_url": "https://www.microsoft.com/en-us/investor/",
    },
    "amd": {
        "name": "AMD",
        "ticker": "AMD",
        "priority": 1,
        "aliases": ["Advanced Micro Devices", "AMD Inc", "AMD"],
        "search_queries": [
            "AMD AI chips",
            "AMD MI300",
            "AMD GPU AI",
            "AMD data center",
            "Lisa Su AMD AI",
        ],
        "ai_keywords": ["mi300", "instinct", "ryzen ai", "epyc", "rocm",
                       "lisa su", "ai accelerator", "data center gpu"],
        "newsroom_url": "https://ir.amd.com/news-events/press-releases",
        "ir_url": "https://ir.amd.com/news-events/press-releases",
    },
    # Priority 2 - Additional AI-relevant companies
    "amazon": {
        "name": "Amazon",
        "ticker": "AMZN",
        "priority": 2,
        "aliases": ["Amazon.com", "Amazon Inc", "AWS", "AMZN"],
        "search_queries": [
            "Amazon AWS AI",
            "Amazon Bedrock",
            "AWS machine learning",
            "Amazon Anthropic",
        ],
        "ai_keywords": ["aws", "bedrock", "sagemaker", "anthropic investment",
                       "alexa ai", "amazon q", "trainium", "inferentia"],
        "newsroom_url": "https://www.aboutamazon.com/news",
        "ir_url": "https://ir.aboutamazon.com/news-releases",
    },
    "apple": {
        "name": "Apple",
        "ticker": "AAPL",
        "priority": 2,
        "aliases": ["Apple Inc", "AAPL"],
        "search_queries": [
            "Apple Intelligence",
            "Apple AI",
            "Apple machine learning",
            "Siri AI",
        ],
        "ai_keywords": ["apple intelligence", "siri", "neural engine", "core ml",
                       "on-device ai", "private cloud compute", "tim cook ai"],
        "newsroom_url": "https://www.apple.com/newsroom/",
        "ir_url": "https://investor.apple.com/press-releases/",
    },
    "tesla": {
        "name": "Tesla",
        "ticker": "TSLA",
        "priority": 2,
        "aliases": ["Tesla Inc", "TSLA"],
        "search_queries": [
            "Tesla FSD AI",
            "Tesla Optimus robot",
            "Tesla Dojo",
            "Tesla AI Day",
        ],
        "ai_keywords": ["fsd", "full self-driving", "optimus", "dojo", "autopilot",
                       "tesla bot", "elon musk tesla ai", "robotaxi"],
        "newsroom_url": "https://ir.tesla.com/press-releases",  # tesla.com/blog blocks scrapers (403)
        "ir_url": "https://ir.tesla.com/press-releases",
    },
    "palantir": {
        "name": "Palantir",
        "ticker": "PLTR",
        "priority": 2,
        "aliases": ["Palantir Technologies", "PLTR"],
        "search_queries": [
            "Palantir AI",
            "Palantir AIP",
            "Palantir Foundry AI",
            "Alex Karp Palantir",
        ],
        "ai_keywords": ["aip", "foundry", "gotham", "enterprise ai", "alex karp",
                       "government ai", "defense ai", "boot camp"],
        "newsroom_url": "https://www.palantir.com/newsroom/",
        "ir_url": "https://investors.palantir.com/news-releases",
    },
    "salesforce": {
        "name": "Salesforce",
        "ticker": "CRM",
        "priority": 2,
        "aliases": ["Salesforce.com", "CRM"],
        "search_queries": [
            "Salesforce Einstein AI",
            "Salesforce Agentforce",
            "Salesforce AI",
            "Marc Benioff AI",
        ],
        "ai_keywords": ["einstein", "agentforce", "crm ai", "slack ai",
                       "benioff", "tableau ai", "data cloud"],
        "newsroom_url": "https://www.salesforce.com/news/",
        "ir_url": "https://investor.salesforce.com/press-releases/",
    },
    "adobe": {
        "name": "Adobe",
        "ticker": "ADBE",
        "priority": 2,
        "aliases": ["Adobe Inc", "ADBE"],
        "search_queries": [
            "Adobe Firefly AI",
            "Adobe Sensei",
            "Adobe generative AI",
            "Adobe AI",
        ],
        "ai_keywords": ["firefly", "sensei", "generative fill", "photoshop ai",
                       "premiere ai", "illustrator ai", "creative cloud ai"],
        "newsroom_url": "https://news.adobe.com/",
        "ir_url": "https://www.adobe.com/investor-relations.html",
    },
    "snowflake": {
        "name": "Snowflake",
        "ticker": "SNOW",
        "priority": 2,
        "aliases": ["Snowflake Inc", "SNOW"],
        "search_queries": [
            "Snowflake AI",
            "Snowflake Cortex",
            "Snowflake data cloud AI",
            "Snowflake ML",
        ],
        "ai_keywords": ["cortex", "snowpark", "data cloud", "streamlit",
                       "ml functions", "data sharing", "sridhar ramaswamy"],
        "newsroom_url": "https://www.snowflake.com/en/news/",
        "ir_url": "https://investors.snowflake.com/news/",
    },
    "ibm": {
        "name": "IBM",
        "ticker": "IBM",
        "priority": 2,
        "aliases": ["International Business Machines", "IBM Corp"],
        "search_queries": [
            "IBM watsonx AI",
            "IBM Watson",
            "IBM AI",
            "IBM Granite",
        ],
        "ai_keywords": ["watsonx", "watson", "granite", "enterprise ai",
                       "ibm research", "arvind krishna ai", "red hat ai"],
        "newsroom_url": "https://newsroom.ibm.com/",
        "ir_url": "https://investor.ibm.com/news-releases",
    },
    "oracle": {
        "name": "Oracle",
        "ticker": "ORCL",
        "priority": 2,
        "aliases": ["Oracle Corporation", "ORCL"],
        "search_queries": [
            "Oracle AI cloud",
            "Oracle OCI AI",
            "Oracle machine learning",
            "Oracle AI",
        ],
        "ai_keywords": ["oci", "oracle cloud ai", "autonomous database",
                       "larry ellison ai", "cohere oracle", "fusion ai"],
        "newsroom_url": "https://www.oracle.com/news/",
        "ir_url": "https://investor.oracle.com/news-events/",
    },
    "databricks": {
        "name": "Databricks",
        "ticker": "PRIVATE",
        "priority": 2,
        "aliases": ["Databricks Inc"],
        "search_queries": [
            "Databricks AI",
            "Databricks MLflow",
            "Databricks lakehouse AI",
            "Databricks DBRX",
        ],
        "ai_keywords": ["lakehouse", "mlflow", "delta lake", "mosaic ml",
                       "dbrx", "unity catalog", "ali ghodsi"],
        "newsroom_url": "https://www.databricks.com/blog",
        "ir_url": None,
    },
}

# Sentiment keywords for basic scoring
POSITIVE_KEYWORDS = [
    'breakthrough', 'revolutionary', 'record', 'surge', 'soar', 'beat', 'exceeds',
    'growth', 'innovation', 'partnership', 'deal', 'contract', 'launch', 'release',
    'upgrade', 'bullish', 'outperform', 'buy', 'strong', 'accelerate', 'milestone',
    'impressive', 'dominant', 'leader', 'success', 'profitable', 'boom', 'rally',
]

NEGATIVE_KEYWORDS = [
    'decline', 'drop', 'fall', 'miss', 'below', 'weak', 'concern', 'risk', 'warning',
    'lawsuit', 'investigation', 'regulatory', 'antitrust', 'layoff', 'cut', 'downgrade',
    'bearish', 'sell', 'underperform', 'struggle', 'delay', 'cancel', 'loss', 'crash',
    'plunge', 'crisis', 'threat', 'challenge', 'controversy',
]


# ============================================================================
# NEWS SCRAPERS
# ============================================================================

class GoogleNewsScraper:
    """Scrape Google News RSS for company news."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.last_request = 0
        self.min_delay = 1.5
        
    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.1, 0.3))
        self.last_request = time.time()
        
    def search(
        self, 
        query: str, 
        company_id: str,
        company_config: Dict[str, Any],
        limit: int = 15,
        days_back: int = 7
    ) -> List[NewsArticle]:
        """Search Google News RSS for a query."""
        articles = []
        self._rate_limit()
        
        try:
            # Build RSS URL with date filter
            encoded_query = quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}+when:{days_back}d&hl=en-US&gl=US&ceid=US:en"
            
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:limit]:
                # Clean title - Google News adds source after " - "
                title = entry.title
                source = "Unknown"
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0]
                    source = parts[1] if len(parts) > 1 else "Unknown"
                    
                # Extract date
                pub_date = entry.get('published', None)
                
                # Calculate AI relevance
                ai_keywords = company_config.get('ai_keywords', [])
                text_lower = title.lower()
                ai_match_count = sum(1 for kw in ai_keywords if kw.lower() in text_lower)
                # Also check for generic AI terms in article title
                generic_ai_terms = ['ai', 'artificial intelligence', 'machine learning', 'deep learning', 'neural', 'llm', 'model']
                generic_match = sum(1 for t in generic_ai_terms if t in text_lower)
                ai_relevance = min(ai_match_count / max(len(ai_keywords), 1) + 0.3 + generic_match * 0.1, 1.0)
                
                # Extract sentiment keywords
                sentiment_kws = []
                for kw in POSITIVE_KEYWORDS:
                    if kw in text_lower:
                        sentiment_kws.append(f"+{kw}")
                for kw in NEGATIVE_KEYWORDS:
                    if kw in text_lower:
                        sentiment_kws.append(f"-{kw}")
                
                article = NewsArticle(
                    title=title,
                    url=entry.link,
                    company=company_config['name'],
                    ticker=company_config['ticker'],
                    source=source,
                    source_type="google_news",
                    published_date=pub_date,
                    summary=f"Source: {source}",
                    sentiment_keywords=sentiment_kws,
                    ai_relevance_score=ai_relevance,
                )
                articles.append(article)
                
        except Exception as e:
            print(f"    Error fetching Google News for '{query}': {e}")
            
        return articles


class YahooFinanceScraper:
    """Scrape Yahoo Finance news for company tickers."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })
        self.last_request = 0
        self.min_delay = 1.0
        
    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.1, 0.2))
        self.last_request = time.time()
        
    def get_news(
        self,
        ticker: str,
        company_id: str,
        company_config: Dict[str, Any],
        limit: int = 10
    ) -> List[NewsArticle]:
        """Get news for a stock ticker from Yahoo Finance."""
        articles = []
        
        if ticker == "PRIVATE":
            return articles
            
        self._rate_limit()
        
        try:
            # Use Yahoo Finance RSS
            rss_url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
            
            feed = feedparser.parse(rss_url)
            
            for entry in feed.entries[:limit]:
                title = entry.get('title', '')
                url = entry.get('link', '')
                pub_date = entry.get('published', None)
                summary = entry.get('summary', '')
                
                if not title or not url:
                    continue
                    
                # Calculate AI relevance
                ai_keywords = company_config.get('ai_keywords', [])
                text_lower = f"{title} {summary}".lower()
                ai_relevance = sum(1 for kw in ai_keywords if kw.lower() in text_lower)
                ai_relevance = min(ai_relevance / max(len(ai_keywords), 1) + 0.2, 1.0)
                
                # Extract sentiment keywords
                sentiment_kws = []
                for kw in POSITIVE_KEYWORDS:
                    if kw in text_lower:
                        sentiment_kws.append(f"+{kw}")
                for kw in NEGATIVE_KEYWORDS:
                    if kw in text_lower:
                        sentiment_kws.append(f"-{kw}")
                        
                article = NewsArticle(
                    title=title,
                    url=url,
                    company=company_config['name'],
                    ticker=company_config['ticker'],
                    source="Yahoo Finance",
                    source_type="yahoo_finance",
                    published_date=pub_date,
                    summary=summary[:300] if summary else None,
                    sentiment_keywords=sentiment_kws,
                    ai_relevance_score=ai_relevance,
                )
                articles.append(article)
                
        except Exception as e:
            print(f"    Error fetching Yahoo Finance for {ticker}: {e}")
            
        return articles


class NewsroomScraper:
    """Scrape official company newsrooms and blogs."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        self.last_request = 0
        self.min_delay = 2.0
        
    def _rate_limit(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.min_delay:
            time.sleep(self.min_delay - elapsed + random.uniform(0.2, 0.5))
        self.last_request = time.time()
        
    def scrape_newsroom(
        self,
        company_id: str,
        company_config: Dict[str, Any],
        limit: int = 10
    ) -> List[NewsArticle]:
        """Scrape company newsroom page."""
        articles = []
        newsroom_url = company_config.get('newsroom_url')
        
        if not newsroom_url:
            return articles
            
        self._rate_limit()
        
        try:
            response = self.session.get(newsroom_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code in (403, 429):
                # Try Bright Data fallback
                from bright_data_fetcher import fetch_url as bd_fetch
                print(f"    Trying Bright Data fallback for {company_config['name']} newsroom...")
                html = bd_fetch(newsroom_url)
                if html:
                    soup = BeautifulSoup(html, 'html.parser')
                else:
                    print(f"    Error scraping newsroom for {company_config['name']}: {e}")
                    return articles
            else:
                print(f"    Error scraping newsroom for {company_config['name']}: {e}")
                return articles
        except Exception as e:
            print(f"    Error scraping newsroom for {company_config['name']}: {e}")
            return articles
        
        try:
            # Generic article extraction patterns
            article_selectors = [
                'article',
                'div[class*="post"]',
                'div[class*="news"]',
                'div[class*="article"]',
                'div[class*="blog"]',
                'a[href*="/blog/"]',
                'a[href*="/news/"]',
                'a[href*="/press"]',
            ]
            
            found_articles = []
            for selector in article_selectors:
                elements = soup.select(selector)
                if elements:
                    found_articles = elements[:limit * 2]  # Get extras for filtering
                    break
                    
            for elem in found_articles[:limit]:
                try:
                    # Extract title
                    title = ""
                    title_elem = elem.find(['h1', 'h2', 'h3', 'h4'])
                    if title_elem:
                        title = title_elem.get_text(strip=True)
                    elif elem.name == 'a':
                        title = elem.get_text(strip=True)
                        
                    if not title or len(title) < 10:
                        continue
                        
                    # Extract URL
                    url = ""
                    if elem.name == 'a':
                        url = elem.get('href', '')
                    else:
                        link = elem.find('a')
                        if link:
                            url = link.get('href', '')
                            
                    if url and not url.startswith('http'):
                        url = urljoin(newsroom_url, url)
                        
                    if not url:
                        continue
                        
                    # Extract summary
                    summary = ""
                    desc_elem = elem.find(['p', 'div[class*="excerpt"]', 'span[class*="summary"]'])
                    if desc_elem:
                        summary = desc_elem.get_text(strip=True)[:300]
                        
                    # Extract date
                    pub_date = None
                    date_elem = elem.find(['time', 'span[class*="date"]', 'div[class*="date"]'])
                    if date_elem:
                        date_text = date_elem.get('datetime') or date_elem.get_text(strip=True)
                        pub_date = date_text
                        
                    # Calculate AI relevance
                    ai_keywords = company_config.get('ai_keywords', [])
                    text_lower = f"{title} {summary}".lower()
                    ai_relevance = sum(1 for kw in ai_keywords if kw.lower() in text_lower)
                    ai_relevance = min(ai_relevance / max(len(ai_keywords), 1) + 0.4, 1.0)  # Higher base for official
                    
                    article = NewsArticle(
                        title=title,
                        url=url,
                        company=company_config['name'],
                        ticker=company_config['ticker'],
                        source=f"{company_config['name']} Newsroom",
                        source_type="newsroom",
                        published_date=pub_date,
                        summary=summary,
                        ai_relevance_score=ai_relevance,
                    )
                    articles.append(article)
                    
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"    Error scraping newsroom for {company_config['name']}: {e}")
            
        return articles


# ============================================================================
# MAIN AGGREGATOR
# ============================================================================

class USTechNewsScraper:
    """Main aggregator for US tech company news."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.google_news = GoogleNewsScraper()
        self.yahoo_finance = YahooFinanceScraper()
        self.newsroom = NewsroomScraper()
        
        self.db_path = Path(__file__).parent.parent / "data" / "signals.db"
        
    def scrape_company(
        self,
        company_id: str,
        company_config: Dict[str, Any],
        days_back: int = 7
    ) -> List[NewsArticle]:
        """Scrape all news sources for a single company."""
        all_articles = []
        seen_titles = set()
        
        company_name = company_config['name']
        print(f"  [{company_config['ticker']}] {company_name}")
        
        # 1. Google News - multiple queries
        for query in company_config.get('search_queries', [])[:3]:  # Limit queries
            articles = self.google_news.search(
                query, company_id, company_config, 
                limit=10, days_back=days_back
            )
            for a in articles:
                title_lower = a.title.lower()[:50]
                if title_lower not in seen_titles:
                    seen_titles.add(title_lower)
                    all_articles.append(a)
        print(f"      Google News: {sum(1 for a in all_articles if a.source_type == 'google_news')} articles")
        
        # 2. Yahoo Finance
        yahoo_articles = self.yahoo_finance.get_news(
            company_config['ticker'], company_id, company_config, limit=10
        )
        for a in yahoo_articles:
            title_lower = a.title.lower()[:50]
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                all_articles.append(a)
        print(f"      Yahoo Finance: {sum(1 for a in all_articles if a.source_type == 'yahoo_finance')} articles")
        
        # 3. Company Newsroom
        newsroom_articles = self.newsroom.scrape_newsroom(
            company_id, company_config, limit=8
        )
        for a in newsroom_articles:
            title_lower = a.title.lower()[:50]
            if title_lower not in seen_titles:
                seen_titles.add(title_lower)
                all_articles.append(a)
        print(f"      Newsroom: {sum(1 for a in all_articles if a.source_type == 'newsroom')} articles")
        
        return all_articles
        
    def scrape_all(
        self,
        companies: Optional[List[str]] = None,
        priority: Optional[int] = None,
        days_back: int = 7
    ) -> List[NewsArticle]:
        """Scrape news for all configured companies."""
        all_articles = []
        
        # Filter companies
        companies_to_scrape = companies or list(US_TECH_COMPANIES.keys())
        
        for company_id in companies_to_scrape:
            config = US_TECH_COMPANIES.get(company_id)
            if not config:
                continue
                
            # Filter by priority
            if priority and config.get('priority', 2) > priority:
                continue
                
            print(f"\n{'='*50}")
            articles = self.scrape_company(company_id, config, days_back)
            all_articles.extend(articles)
            
            # Rate limit between companies
            time.sleep(1)
            
        return all_articles
        
    def calculate_sentiment(self, article: NewsArticle) -> float:
        """Calculate sentiment score (1-10) from article."""
        positive_count = sum(1 for kw in article.sentiment_keywords if kw.startswith('+'))
        negative_count = sum(1 for kw in article.sentiment_keywords if kw.startswith('-'))
        
        # Base neutral score
        score = 5.0
        
        # Adjust based on keywords
        score += positive_count * 0.5
        score -= negative_count * 0.5
        
        # Adjust by AI relevance (more AI-related = stronger signal)
        if article.ai_relevance_score > 0.5:
            score = 5.0 + (score - 5.0) * 1.2
            
        # Clamp to 1-10
        return max(1.0, min(10.0, score))
        
    def get_or_create_entity(self, conn: sqlite3.Connection, company_id: str, config: Dict) -> str:
        """Get or create entity in database, returns entity_id."""
        cursor = conn.cursor()
        
        # Search by name first
        cursor.execute(
            "SELECT id FROM entities WHERE LOWER(name) = ? OR LOWER(name) = ?",
            (config['name'].lower(), config['ticker'].lower())
        )
        result = cursor.fetchone()
        
        if result:
            return result[0]
            
        # Create new entity
        entity_id = str(uuid.uuid4())
        aliases_json = json.dumps(config.get('aliases', []))
        
        cursor.execute("""
            INSERT INTO entities (id, canonical_id, name, entity_type, aliases, description, website)
            VALUES (?, ?, ?, 'company', ?, ?, ?)
        """, (
            entity_id,
            entity_id,
            config['name'],
            aliases_json,
            f"US tech company focused on AI. Ticker: {config['ticker']}",
            config.get('ir_url') or config.get('newsroom_url', ''),
        ))
        
        conn.commit()
        print(f"      Created entity: {config['name']} ({entity_id[:8]}...)")
        return entity_id
        
    def get_or_create_source(self, conn: sqlite3.Connection, source_type: str) -> str:
        """Get or create signal source in database."""
        cursor = conn.cursor()
        
        source_id = f"us_tech_{source_type}"
        
        cursor.execute("SELECT id FROM signal_sources WHERE id = ?", (source_id,))
        result = cursor.fetchone()
        
        if result:
            return result[0]
            
        # Create new source
        source_names = {
            'google_news': 'Google News (US Tech)',
            'yahoo_finance': 'Yahoo Finance News',
            'newsroom': 'Company Newsrooms',
        }
        
        cursor.execute("""
            INSERT INTO signal_sources (id, name, category, url, update_frequency, confidence_base, enabled)
            VALUES (?, ?, 'media', ?, 'hourly', 0.75, 1)
        """, (
            source_id,
            source_names.get(source_type, source_type),
            f"https://news.google.com",
        ))
        
        conn.commit()
        return source_id
        
    def store_signals(self, articles: List[NewsArticle]) -> int:
        """Store article signals in database."""
        if not articles:
            return 0
            
        conn = sqlite3.connect(self.db_path)
        stored_count = 0
        
        try:
            # Group by company
            by_company = defaultdict(list)
            for article in articles:
                # Find company_id
                for cid, config in US_TECH_COMPANIES.items():
                    if config['name'] == article.company:
                        by_company[cid].append(article)
                        break
                        
            for company_id, company_articles in by_company.items():
                config = US_TECH_COMPANIES[company_id]
                
                # Get/create entity
                entity_id = self.get_or_create_entity(conn, company_id, config)
                
                for article in company_articles:
                    # Get/create source
                    source_id = self.get_or_create_source(conn, article.source_type)
                    
                    # Calculate sentiment
                    sentiment = self.calculate_sentiment(article)
                    
                    # Prepare raw_data
                    raw_data = {
                        "title": article.title,
                        "url": article.url,
                        "source": article.source,
                        "company": article.company,
                        "ticker": article.ticker,
                        "ai_relevance": article.ai_relevance_score,
                        "sentiment_keywords": article.sentiment_keywords,
                    }
                    
                    # Parse date or use now
                    observed_at = datetime.now().isoformat()
                    if article.published_date:
                        try:
                            # Try parsing common formats
                            for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d"]:
                                try:
                                    dt = datetime.strptime(article.published_date[:25], fmt)
                                    observed_at = dt.isoformat()
                                    break
                                except:
                                    pass
                        except:
                            pass
                            
                    # Insert observation
                    obs_id = str(uuid.uuid4())
                    cursor = conn.cursor()
                    
                    try:
                        cursor.execute("""
                            INSERT INTO signal_observations 
                            (id, entity_id, source_id, category, observed_at, raw_value, raw_data, confidence)
                            VALUES (?, ?, ?, 'media', ?, ?, ?, ?)
                        """, (
                            obs_id,
                            entity_id,
                            source_id,
                            observed_at,
                            sentiment,
                            json.dumps(raw_data),
                            0.7 + article.ai_relevance_score * 0.2,
                        ))
                        stored_count += 1
                    except sqlite3.IntegrityError:
                        # Skip duplicates
                        pass
                        
            conn.commit()
            
        finally:
            conn.close()
            
        return stored_count
        
    def run(
        self,
        save: bool = True,
        companies: Optional[List[str]] = None,
        priority: Optional[int] = None,
        days_back: int = 30
    ) -> Dict[str, Any]:
        """Main entry point - scrape and optionally save."""
        print("=" * 60)
        print("US TECH COMPANY NEWS SCRAPER")
        print(f"Scraping news for {len(companies or US_TECH_COMPANIES)} companies")
        print(f"Looking back {days_back} days")
        print("=" * 60)
        
        # Scrape
        articles = self.scrape_all(companies, priority, days_back)
        
        print(f"\n{'='*60}")
        print(f"RESULTS: {len(articles)} total articles")
        print("=" * 60)
        
        if not articles:
            return {"status": "no_data", "articles": 0}
            
        # Analyze coverage
        by_company = defaultdict(int)
        by_source = defaultdict(int)
        high_ai_relevance = 0
        
        for article in articles:
            by_company[article.company] += 1
            by_source[article.source_type] += 1
            if article.ai_relevance_score > 0.35:
                high_ai_relevance += 1
                
        print("\nBy Company:")
        for company, count in sorted(by_company.items(), key=lambda x: -x[1]):
            print(f"  {company}: {count}")
            
        print("\nBy Source Type:")
        for source, count in by_source.items():
            print(f"  {source}: {count}")
            
        print(f"\nHigh AI Relevance: {high_ai_relevance} articles ({high_ai_relevance*100//len(articles)}%)")
        
        if save:
            # Save to JSON
            today = date.today().isoformat()
            output_file = self.output_dir / f"us_tech_news_{today}.json"
            
            data = [asdict(a) for a in articles]
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"\nSaved to: {output_file}")
            
            # Store in database
            stored = self.store_signals(articles)
            print(f"Stored {stored} signals in database")
            
        # Sample articles
        print("\n" + "=" * 60)
        print("SAMPLE HIGH-RELEVANCE ARTICLES")
        print("=" * 60)
        
        high_relevance = sorted(articles, key=lambda x: -x.ai_relevance_score)[:10]
        for article in high_relevance:
            print(f"\n[{article.ticker}] {article.title[:70]}...")
            print(f"  Source: {article.source} | AI Score: {article.ai_relevance_score:.2f}")
            if article.sentiment_keywords:
                print(f"  Sentiment: {', '.join(article.sentiment_keywords[:5])}")
                
        return {
            "status": "success",
            "articles": len(articles),
            "by_company": dict(by_company),
            "by_source": dict(by_source),
            "high_ai_relevance": high_ai_relevance,
            "signals": articles,
        }


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point for CLI usage."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape US tech company news")
    parser.add_argument(
        "--companies",
        nargs="+",
        choices=list(US_TECH_COMPANIES.keys()),
        help="Specific companies to scrape (default: all)"
    )
    parser.add_argument(
        "--priority",
        type=int,
        choices=[1, 2],
        help="Only scrape companies of this priority level or higher"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Days to look back (default: 30)"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save to file or database"
    )
    
    args = parser.parse_args()
    
    scraper = USTechNewsScraper()
    result = scraper.run(
        save=not args.no_save,
        companies=args.companies,
        priority=args.priority,
        days_back=args.days,
    )
    
    return result


if __name__ == "__main__":
    main()
