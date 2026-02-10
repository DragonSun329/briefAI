# -*- coding: utf-8 -*-
"""
Earnings Call Scraper

Scrapes earnings call transcripts and extracts AI-related commentary.
Uses Seeking Alpha and free transcript sources.
"""

import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import time
import re
from bs4 import BeautifulSoup


@dataclass 
class EarningsSignal:
    """An earnings-related signal."""
    id: str
    company: str
    ticker: str
    event_type: str  # earnings_call, guidance, announcement
    title: str
    date: str
    url: str
    ai_mentions: int
    key_quotes: List[str]
    sentiment: str  # bullish, neutral, bearish
    source: str


class EarningsScraper:
    """Scraper for earnings calls and transcripts."""
    
    # AI companies to track
    COMPANIES = {
        "NVDA": "NVIDIA",
        "MSFT": "Microsoft", 
        "GOOGL": "Alphabet",
        "META": "Meta",
        "AMZN": "Amazon",
        "AAPL": "Apple",
        "AMD": "AMD",
        "INTC": "Intel",
        "CRM": "Salesforce",
        "ORCL": "Oracle",
        "IBM": "IBM",
        "PLTR": "Palantir",
        "SNOW": "Snowflake",
        "AI": "C3.ai",
        "PATH": "UiPath",
        "DDOG": "Datadog",
    }
    
    # AI keywords to search for in transcripts
    AI_KEYWORDS = [
        "artificial intelligence", "AI", "machine learning", "ML",
        "generative AI", "GenAI", "large language model", "LLM",
        "GPT", "ChatGPT", "Copilot", "neural network",
        "deep learning", "natural language", "NLP",
        "computer vision", "inference", "training",
        "GPU", "accelerator", "data center",
    ]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "earnings_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
    
    def fetch_recent_earnings_news(self, ticker: str, company: str) -> List[Dict[str, Any]]:
        """Fetch recent earnings-related news for a ticker."""
        signals = []
        
        try:
            # Use Yahoo Finance API for earnings news
            url = f"https://query1.finance.yahoo.com/v1/finance/search"
            params = {
                "q": f"{company} earnings",
                "newsCount": 5,
                "quotesCount": 0,
            }
            
            resp = requests.get(url, params=params, headers=self.headers, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                news = data.get("news", [])
                
                for item in news:
                    title = item.get("title", "")
                    
                    # Count AI mentions
                    ai_count = sum(1 for kw in self.AI_KEYWORDS if kw.lower() in title.lower())
                    
                    signals.append({
                        "id": f"earn_{ticker}_{item.get('uuid', '')}",
                        "company": company,
                        "ticker": ticker,
                        "event_type": "earnings_news",
                        "title": title,
                        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                        "url": item.get("link", ""),
                        "ai_mentions": ai_count,
                        "source": item.get("publisher", "Yahoo Finance"),
                    })
            
        except Exception as e:
            print(f"    Error fetching news for {ticker}: {e}")
        
        return signals
    
    def fetch_earnings_calendar(self) -> List[Dict[str, Any]]:
        """Fetch upcoming earnings dates."""
        events = []
        
        for ticker, company in self.COMPANIES.items():
            try:
                url = f"https://query1.finance.yahoo.com/v7/finance/quote"
                params = {"symbols": ticker}
                
                resp = requests.get(url, params=params, headers=self.headers, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    quotes = data.get("quoteResponse", {}).get("result", [])
                    
                    if quotes:
                        quote = quotes[0]
                        earnings_ts = quote.get("earningsTimestamp")
                        
                        if earnings_ts:
                            dt = datetime.fromtimestamp(earnings_ts, timezone.utc)
                            now = datetime.now(timezone.utc)
                            
                            # Only include upcoming earnings (next 30 days)
                            if now <= dt <= now + timedelta(days=30):
                                events.append({
                                    "ticker": ticker,
                                    "company": company,
                                    "date": dt.strftime("%Y-%m-%d"),
                                    "datetime": dt.isoformat(),
                                })
                
                time.sleep(0.1)
                
            except Exception as e:
                continue
        
        return sorted(events, key=lambda x: x["date"])
    
    def analyze_sentiment(self, text: str) -> str:
        """Basic sentiment analysis of earnings text."""
        positive = ["beat", "exceed", "strong", "growth", "record", "surge", "bullish", "optimistic"]
        negative = ["miss", "decline", "weak", "concern", "slow", "bearish", "cut", "lower"]
        
        text_lower = text.lower()
        pos_count = sum(1 for w in positive if w in text_lower)
        neg_count = sum(1 for w in negative if w in text_lower)
        
        if pos_count > neg_count:
            return "bullish"
        elif neg_count > pos_count:
            return "bearish"
        return "neutral"
    
    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run earnings scraper."""
        print("=" * 60)
        print("EARNINGS CALL SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "earnings_news": [],
            "upcoming_earnings": [],
        }
        
        # Fetch earnings news
        print("\nFetching earnings news...")
        for ticker, company in self.COMPANIES.items():
            print(f"  {ticker} ({company})...")
            news = self.fetch_recent_earnings_news(ticker, company)
            if news:
                print(f"    Found {len(news)} articles")
                results["earnings_news"].extend(news)
            time.sleep(0.2)
        
        # Fetch earnings calendar
        print("\nFetching earnings calendar...")
        calendar = self.fetch_earnings_calendar()
        results["upcoming_earnings"] = calendar
        print(f"  Found {len(calendar)} upcoming earnings")
        
        # Save
        if save:
            output_file = self.output_dir / f"earnings_{datetime.now().strftime('%Y-%m-%d')}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        print(f"Earnings news articles: {len(results['earnings_news'])}")
        print(f"Upcoming earnings: {len(results['upcoming_earnings'])}")
        
        if results["upcoming_earnings"]:
            print("\nNext earnings:")
            for e in results["upcoming_earnings"][:5]:
                print(f"  {e['date']}: {e['company']} ({e['ticker']})")
        
        # AI mentions
        ai_articles = [n for n in results["earnings_news"] if n.get("ai_mentions", 0) > 0]
        if ai_articles:
            print(f"\nArticles mentioning AI: {len(ai_articles)}")
        
        return results


if __name__ == "__main__":
    scraper = EarningsScraper()
    scraper.run()
