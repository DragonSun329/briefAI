# -*- coding: utf-8 -*-
"""
Financial Data Scraper

Scrapes SEC filings (EDGAR) and earnings transcripts for AI companies.
Focuses on 8-K, 10-K, 10-Q filings and earnings call transcripts.
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
class FinancialSignal:
    """A financial data signal."""
    id: str
    signal_type: str  # sec_filing, earnings_call, guidance, analyst
    entity: str
    ticker: str
    title: str
    url: str
    source: str
    published_at: str
    summary: str
    filing_type: Optional[str] = None  # 8-K, 10-K, 10-Q, etc.
    relevance: float = 1.0


class FinancialDataScraper:
    """Scraper for SEC filings and financial data."""
    
    # AI companies to track (ticker -> (entity name, CIK))
    AI_TICKERS = {
        # Big Tech (CIKs pre-loaded for reliability)
        "NVDA": ("NVIDIA", "0001045810"),
        "MSFT": ("Microsoft", "0000789019"),
        "GOOGL": ("Alphabet", "0001652044"),
        "META": ("Meta", "0001326801"),
        "AMZN": ("Amazon", "0001018724"),
        "AAPL": ("Apple", "0000320193"),
        # AI-focused
        "AMD": ("AMD", "0000002488"),
        "INTC": ("Intel", "0000050863"),
        "AVGO": ("Broadcom", "0001649338"),
        "QCOM": ("Qualcomm", "0000804328"),
        "ARM": ("ARM Holdings", "0001973239"),
        "MRVL": ("Marvell", "0001058057"),
        # Cloud
        "CRM": ("Salesforce", "0001108524"),
        "ORCL": ("Oracle", "0001341439"),
        "SNOW": ("Snowflake", "0001640147"),
        "PLTR": ("Palantir", "0001321655"),
        # AI Pure-Play
        "AI": ("C3.ai", "0001577526"),
        "PATH": ("UiPath", "0001830029"),
        "SOUN": ("SoundHound AI", "0001840856"),
        "UPST": ("Upstart", "0001647639"),
    }
    
    # SEC EDGAR API base
    EDGAR_BASE = "https://data.sec.gov"
    EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index"
    
    # Filing types to track
    FILING_TYPES = ["8-K", "10-K", "10-Q", "S-1", "DEF 14A"]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "financial_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # SEC requires proper User-Agent
        self.headers = {
            "User-Agent": "BriefAI Research Bot (contact@example.com)",
            "Accept": "application/json",
        }
    
    def get_company_cik(self, ticker: str) -> Optional[str]:
        """Get CIK number for a ticker (from hardcoded map)."""
        if ticker in self.AI_TICKERS:
            return self.AI_TICKERS[ticker][1]
        return None
    
    def get_company_name(self, ticker: str) -> str:
        """Get company name for a ticker."""
        if ticker in self.AI_TICKERS:
            return self.AI_TICKERS[ticker][0]
        return ticker
    
    def fetch_recent_filings(self, ticker: str, days: int = 7) -> List[Dict[str, Any]]:
        """Fetch recent SEC filings for a ticker."""
        cik = self.get_company_cik(ticker)
        if not cik:
            return []
        
        try:
            # Get company submissions
            url = f"{self.EDGAR_BASE}/submissions/CIK{cik}.json"
            resp = requests.get(url, headers=self.headers, timeout=15)
            data = resp.json()
            
            filings = []
            recent = data.get("filings", {}).get("recent", {})
            
            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            descriptions = recent.get("primaryDocDescription", [])
            
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
            
            for i, (form, date, accession, desc) in enumerate(zip(forms, dates, accessions, descriptions)):
                if date < cutoff:
                    break
                    
                if form in self.FILING_TYPES:
                    filings.append({
                        "ticker": ticker,
                        "entity": self.get_company_name(ticker),
                        "form": form,
                        "date": date,
                        "accession": accession.replace("-", ""),
                        "description": desc or form,
                        "url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form}",
                    })
            
            return filings[:10]  # Max 10 per company
            
        except Exception as e:
            print(f"    Error fetching filings for {ticker}: {e}")
            return []
    
    def scrape_all_filings(self, days: int = 7) -> List[FinancialSignal]:
        """Scrape SEC filings for all AI companies."""
        print(f"Fetching SEC filings (last {days} days)...")
        
        all_signals = []
        
        for ticker, (entity, cik) in self.AI_TICKERS.items():
            print(f"  Checking {ticker} ({entity})...")
            filings = self.fetch_recent_filings(ticker, days)
            
            for filing in filings:
                signal = FinancialSignal(
                    id=f"sec_{ticker}_{filing['date']}_{filing['form']}",
                    signal_type="sec_filing",
                    entity=entity,
                    ticker=ticker,
                    title=f"{entity} ({ticker}) files {filing['form']}: {filing['description']}",
                    url=filing["url"],
                    source="sec_edgar",
                    published_at=filing["date"],
                    summary=f"SEC {filing['form']} filing by {entity}",
                    filing_type=filing["form"],
                )
                all_signals.append(signal)
            
            time.sleep(0.2)  # Rate limit
        
        print(f"  Found {len(all_signals)} filings")
        return all_signals
    
    def fetch_earnings_calendar(self) -> List[Dict[str, Any]]:
        """Fetch upcoming earnings dates for AI companies."""
        # Using Yahoo Finance earnings calendar API
        try:
            today = datetime.now(timezone.utc)
            start = today.strftime("%Y-%m-%d")
            end = (today + timedelta(days=14)).strftime("%Y-%m-%d")
            
            earnings = []
            
            # Check each ticker (get top 15)
            tickers_to_check = list(self.AI_TICKERS.keys())[:15]
            for ticker in tickers_to_check:
                try:
                    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
                    resp = requests.get(url, timeout=10)
                    data = resp.json()
                    
                    if "quoteResponse" in data and data["quoteResponse"]["result"]:
                        quote = data["quoteResponse"]["result"][0]
                        earnings_date = quote.get("earningsTimestamp")
                        
                        if earnings_date:
                            dt = datetime.fromtimestamp(earnings_date, timezone.utc)
                            if today <= dt <= today + timedelta(days=30):
                                earnings.append({
                                    "ticker": ticker,
                                    "entity": self.get_company_name(ticker),
                                    "date": dt.strftime("%Y-%m-%d"),
                                    "datetime": dt.isoformat(),
                                })
                    
                    time.sleep(0.1)
                except:
                    continue
            
            return earnings
            
        except Exception as e:
            print(f"  Error fetching earnings: {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run all financial data scrapers."""
        print("=" * 60)
        print("FINANCIAL DATA SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "sec_filings": [],
            "upcoming_earnings": [],
        }
        
        # SEC filings
        filings = self.scrape_all_filings(days=7)
        results["sec_filings"] = [asdict(f) for f in filings]
        
        # Earnings calendar
        print("\nFetching earnings calendar...")
        earnings = self.fetch_earnings_calendar()
        results["upcoming_earnings"] = earnings
        print(f"  Found {len(earnings)} upcoming earnings")
        
        # Save results
        output_file = self.output_dir / f"financial_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\nSaved to {output_file}")
        
        # Summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"  SEC filings: {len(results['sec_filings'])}")
        print(f"  Upcoming earnings: {len(results['upcoming_earnings'])}")
        
        if results["upcoming_earnings"]:
            print("\n  Upcoming earnings:")
            for e in results["upcoming_earnings"][:5]:
                print(f"    {e['date']}: {e['entity']} ({e['ticker']})")
        
        return results


if __name__ == "__main__":
    scraper = FinancialDataScraper()
    scraper.run()
