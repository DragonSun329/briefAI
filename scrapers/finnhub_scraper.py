#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Finnhub Market Data Scraper for briefAI

Primary source for stock prices (replaces unreliable yfinance from China).
Finnhub free tier: 60 API calls/min, US stock quotes, company profiles.

Also builds market-news correlation by matching price movers to news articles.

Output: data/market_signals/finnhub_YYYY-MM-DD.json
"""

import json
import os
import time
import requests
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from loguru import logger
except ImportError:
    import logging as logger

# Output
DATA_DIR = Path(__file__).parent.parent / "data" / "market_signals"
DATA_DIR.mkdir(parents=True, exist_ok=True)

NEWS_DIR = Path(__file__).parent.parent / "data" / "alternative_signals"

# AI/Tech tickers to track
AI_TICKERS = [
    # Big Tech / AI Leaders
    'NVDA', 'MSFT', 'GOOGL', 'META', 'AMZN', 'AAPL', 'AMD', 'INTC',
    # AI-focused
    'AI', 'PLTR', 'PATH', 'SNOW', 'DDOG', 'MDB', 'CRWD', 'ZS',
    # Semiconductors
    'AVGO', 'QCOM', 'ARM', 'TSM', 'ASML', 'MRVL',
    # Cloud / Enterprise
    'CRM', 'ORCL', 'IBM', 'NOW', 'ADBE', 'WDAY',
    # AI Pure-plays
    'UPST', 'DOCS', 'S', 'NET', 'U',
]

# Ticker → company name mapping for news correlation
TICKER_NAMES = {
    'NVDA': ['NVIDIA', 'Nvidia'],
    'MSFT': ['Microsoft'],
    'GOOGL': ['Google', 'Alphabet', 'DeepMind', 'Gemini'],
    'META': ['Meta', 'Facebook', 'Instagram', 'WhatsApp'],
    'AMZN': ['Amazon', 'AWS'],
    'AAPL': ['Apple'],
    'AMD': ['AMD', 'Advanced Micro'],
    'INTC': ['Intel'],
    'AI': ['C3.ai', 'C3 AI'],
    'PLTR': ['Palantir'],
    'PATH': ['UiPath'],
    'SNOW': ['Snowflake'],
    'DDOG': ['Datadog'],
    'MDB': ['MongoDB'],
    'CRWD': ['CrowdStrike'],
    'ZS': ['Zscaler'],
    'AVGO': ['Broadcom'],
    'QCOM': ['Qualcomm'],
    'ARM': ['ARM', 'Arm Holdings'],
    'TSM': ['TSMC', 'Taiwan Semiconductor'],
    'ASML': ['ASML'],
    'MRVL': ['Marvell'],
    'CRM': ['Salesforce'],
    'ORCL': ['Oracle'],
    'IBM': ['IBM'],
    'NOW': ['ServiceNow'],
    'ADBE': ['Adobe'],
    'WDAY': ['Workday'],
    'UPST': ['Upstart'],
    'NET': ['Cloudflare'],
}


class TechnicalAnalyzer:
    """Calculate technical indicators from price history.
    
    Uses Finnhub /stock/metric for fundamentals (free tier)
    and yfinance for historical candles (single-ticker, slow but works).
    Only runs for movers to keep it fast.
    """

    @staticmethod
    def get_metrics(api_key: str, symbol: str) -> Optional[Dict]:
        """Fetch basic metrics from Finnhub (free tier)."""
        try:
            r = requests.get(
                "https://finnhub.io/api/v1/stock/metric",
                params={"symbol": symbol, "metric": "all", "token": api_key},
                timeout=10,
            )
            if r.status_code != 200:
                return None
            m = r.json().get("metric", {})
            return {
                "52w_high": m.get("52WeekHigh"),
                "52w_low": m.get("52WeekLow"),
                "10d_avg_volume": m.get("10DayAverageTradingVolume"),
                "3m_avg_volume": m.get("3MonthAverageTradingVolume"),
                "beta": m.get("beta"),
                "pe_ratio": m.get("peBasicExclExtraTTM"),
                "pb_ratio": m.get("pbQuarterly"),
                "dividend_yield": m.get("dividendYieldIndicatedAnnual"),
                "market_cap": m.get("marketCapitalization"),
            }
        except Exception:
            return None

    @staticmethod
    def get_candles_yf(symbol: str, period: str = "3mo") -> Optional[List[float]]:
        """Fetch closing prices via yfinance (fallback, single ticker)."""
        try:
            import threading
            result = [None]
            def _fetch():
                try:
                    import yfinance as yf
                    data = yf.Ticker(symbol).history(period=period)
                    if data is not None and not data.empty:
                        result[0] = data['Close'].dropna().tolist()
                except Exception:
                    pass
            t = threading.Thread(target=_fetch, daemon=True)
            t.start()
            t.join(timeout=20)
            return result[0]
        except Exception:
            return None

    @staticmethod
    def compute_rsi(closes: List[float], period: int = 14) -> Optional[float]:
        """Compute RSI from closing prices."""
        if len(closes) < period + 1:
            return None
        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]

        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 1)

    @staticmethod
    def compute_macd(closes: List[float]) -> Optional[Dict]:
        """Compute MACD (12,26,9) from closing prices."""
        if len(closes) < 35:
            return None

        def ema(data, period):
            multiplier = 2 / (period + 1)
            result = [sum(data[:period]) / period]
            for price in data[period:]:
                result.append((price - result[-1]) * multiplier + result[-1])
            return result

        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        # Align lengths
        offset = len(ema12) - len(ema26)
        macd_line = [ema12[i + offset] - ema26[i] for i in range(len(ema26))]

        if len(macd_line) < 9:
            return None
        signal_line = ema(macd_line, 9)
        histogram = macd_line[-1] - signal_line[-1]

        return {
            "macd": round(macd_line[-1], 3),
            "signal": round(signal_line[-1], 3),
            "histogram": round(histogram, 3),
            "trend": "bullish" if histogram > 0 else "bearish",
        }

    @staticmethod
    def compute_bollinger(closes: List[float], period: int = 20) -> Optional[Dict]:
        """Compute Bollinger Bands."""
        if len(closes) < period:
            return None
        recent = closes[-period:]
        sma = sum(recent) / period
        std = (sum((x - sma) ** 2 for x in recent) / period) ** 0.5
        upper = sma + 2 * std
        lower = sma - 2 * std
        current = closes[-1]

        # Position within bands (0% = lower, 100% = upper)
        width = upper - lower
        position = ((current - lower) / width * 100) if width > 0 else 50

        return {
            "upper": round(upper, 2),
            "middle": round(sma, 2),
            "lower": round(lower, 2),
            "position_pct": round(position, 1),
            "squeeze": width / sma < 0.04,  # Tight bands = potential breakout
        }

    @staticmethod
    def compute_sma_cross(closes: List[float]) -> Optional[Dict]:
        """Check SMA 20/50 crossover."""
        if len(closes) < 50:
            return None
        sma20 = sum(closes[-20:]) / 20
        sma50 = sum(closes[-50:]) / 50

        # Check previous day's SMAs for crossover detection
        sma20_prev = sum(closes[-21:-1]) / 20
        sma50_prev = sum(closes[-51:-1]) / 50

        cross = "none"
        if sma20_prev < sma50_prev and sma20 > sma50:
            cross = "golden_cross"  # Bullish
        elif sma20_prev > sma50_prev and sma20 < sma50:
            cross = "death_cross"  # Bearish

        return {
            "sma20": round(sma20, 2),
            "sma50": round(sma50, 2),
            "sma20_above_sma50": sma20 > sma50,
            "crossover": cross,
        }

    @classmethod
    def analyze(cls, symbol: str, api_key: str, current_price: float = None) -> Dict:
        """Full technical analysis for a single ticker."""
        result = {"symbol": symbol}

        # 1. Finnhub metrics (fast, free)
        metrics = cls.get_metrics(api_key, symbol)
        if metrics:
            result["metrics"] = metrics
            # 52-week position
            if metrics.get("52w_high") and metrics.get("52w_low"):
                h, l = metrics["52w_high"], metrics["52w_low"]
                if h > l and current_price:
                    result["52w_position_pct"] = round(((current_price - l) / (h - l)) * 100, 1)

        # 2. Historical candles from yfinance (slow, for movers only)
        closes = cls.get_candles_yf(symbol)
        if closes and len(closes) >= 14:
            result["rsi"] = cls.compute_rsi(closes)

            macd = cls.compute_macd(closes)
            if macd:
                result["macd"] = macd

            bb = cls.compute_bollinger(closes)
            if bb:
                result["bollinger"] = bb

            sma = cls.compute_sma_cross(closes)
            if sma:
                result["sma_cross"] = sma

            # Summary signal
            signals = []
            if result.get("rsi"):
                if result["rsi"] > 70:
                    signals.append("overbought")
                elif result["rsi"] < 30:
                    signals.append("oversold")
            if macd:
                signals.append(f"macd_{macd['trend']}")
            if bb and bb["position_pct"] > 95:
                signals.append("near_upper_band")
            elif bb and bb["position_pct"] < 5:
                signals.append("near_lower_band")
            if sma and sma["crossover"] != "none":
                signals.append(sma["crossover"])

            result["ta_signals"] = signals
        else:
            result["ta_signals"] = ["no_history"]

        return result


class FinnhubScraper:
    """Fetch stock data from Finnhub API."""

    BASE_URL = "https://finnhub.io/api/v1"

    def __init__(self):
        self.api_key = os.environ.get("FINNHUB_API_KEY", "")
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY not set in .env")
        self.session = requests.Session()
        self.session.params = {"token": self.api_key}
        self.session.timeout = 10
        self._call_count = 0

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """Make a rate-limited API call."""
        # Free tier: 60 calls/min
        if self._call_count > 0 and self._call_count % 55 == 0:
            logger.info("  Rate limit pause (1s)...")
            time.sleep(1.0)

        try:
            r = self.session.get(f"{self.BASE_URL}{endpoint}", params=params or {}, timeout=10)
            self._call_count += 1
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            logger.debug(f"  Finnhub error {endpoint}: {e}")
            return None

    def get_quote(self, symbol: str) -> Optional[Dict]:
        """Get real-time quote for a symbol.
        Returns: c(current), d(change), dp(change%), h(high), l(low), o(open), pc(prev close), t(timestamp)
        """
        data = self._get("/quote", {"symbol": symbol})
        if not data or data.get("c", 0) == 0:
            return None
        return data

    def get_company_news(self, symbol: str, from_date: str, to_date: str) -> List[Dict]:
        """Get company news from Finnhub."""
        data = self._get("/company-news", {
            "symbol": symbol,
            "from": from_date,
            "to": to_date,
        })
        return data if isinstance(data, list) else []

    def fetch_all_quotes(self, tickers: List[str] = None) -> List[Dict]:
        """Fetch quotes for all tracked tickers."""
        if tickers is None:
            tickers = AI_TICKERS

        quotes = []
        for i, ticker in enumerate(tickers):
            q = self.get_quote(ticker)
            if q is None:
                logger.debug(f"  {ticker}: no data")
                continue

            current = q["c"]
            prev_close = q["pc"]
            change_pct = q["dp"]

            # Signal determination
            signal = "neutral"
            score = 0
            if change_pct > 5:
                signal = "bullish"
                score = min(0.8, change_pct / 10)
            elif change_pct > 2:
                signal = "slightly_bullish"
                score = change_pct / 20
            elif change_pct < -5:
                signal = "bearish"
                score = max(-0.8, change_pct / 10)
            elif change_pct < -2:
                signal = "slightly_bearish"
                score = change_pct / 20

            entry = {
                "ticker": ticker,
                "current_price": round(current, 2),
                "open": round(q["o"], 2),
                "day_high": round(q["h"], 2),
                "day_low": round(q["l"], 2),
                "previous_close": round(prev_close, 2),
                "change": round(q["d"], 2),
                "change_pct": round(change_pct, 2),
                "signal": signal,
                "score": round(score, 3),
                "timestamp": q.get("t", 0),
                "source": "finnhub",
            }

            # Intraday range position
            if q["h"] > q["l"]:
                entry["intraday_range_pct"] = round(
                    ((current - q["l"]) / (q["h"] - q["l"])) * 100, 1
                )

            quotes.append(entry)

            if (i + 1) % 10 == 0:
                logger.info(f"  {i+1}/{len(tickers)} quotes fetched")

            time.sleep(0.1)  # Stay well under rate limit

        return quotes


class MarketNewsCorrelator:
    """Correlate price moves with news articles from today's scrape."""

    def __init__(self):
        self.news_articles = self._load_todays_news()

    def _load_todays_news(self) -> List[Dict]:
        """Load today's news from all available scraped sources."""
        today = date.today().isoformat()
        articles = []

        # Load from different news sources
        sources = [
            f"news_search_{today}.json",
            f"us_tech_news_{today}.json",
            f"blog_signals_{today}.json",
        ]

        for fname in sources:
            fpath = NEWS_DIR / fname
            if not fpath.exists():
                continue
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Normalize: each source has articles/posts in different keys
                items = []
                for key in ["articles", "posts", "stories"]:
                    candidate = data.get(key, [])
                    if isinstance(candidate, list) and candidate:
                        items = candidate
                        break
                for item in items:
                    articles.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", item.get("link", "")),
                        "source_file": fname,
                        "summary": item.get("summary", item.get("description", item.get("content", "")))[:300],
                    })
            except Exception as e:
                logger.debug(f"  Could not load {fname}: {e}")

        logger.info(f"  Loaded {len(articles)} news articles for correlation")
        return articles

    def find_related_news(self, ticker: str, max_results: int = 5) -> List[Dict]:
        """Find news articles mentioning this ticker or company."""
        names = TICKER_NAMES.get(ticker, [ticker])
        # Also match the ticker itself
        search_terms = [ticker] + names

        matches = []
        for article in self.news_articles:
            text = f"{article['title']} {article.get('summary', '')}".upper()
            for term in search_terms:
                if term.upper() in text:
                    matches.append({
                        "title": article["title"],
                        "url": article["url"],
                        "matched_term": term,
                    })
                    break  # One match per article is enough

        return matches[:max_results]

    def correlate(self, quotes: List[Dict]) -> List[Dict]:
        """Add news context to price movers (>2% change)."""
        correlations = []

        movers = [q for q in quotes if abs(q.get("change_pct", 0)) > 2]
        movers.sort(key=lambda q: abs(q["change_pct"]), reverse=True)

        for mover in movers:
            ticker = mover["ticker"]
            related = self.find_related_news(ticker)

            if related:
                correlations.append({
                    "ticker": ticker,
                    "change_pct": mover["change_pct"],
                    "signal": mover["signal"],
                    "price": mover["current_price"],
                    "related_news_count": len(related),
                    "news": related,
                    "narrative": self._build_narrative(mover, related),
                })

        return correlations

    def _build_narrative(self, mover: Dict, news: List[Dict]) -> str:
        """Build a one-line narrative connecting price move to news."""
        direction = "up" if mover["change_pct"] > 0 else "down"
        ticker = mover["ticker"]
        pct = abs(mover["change_pct"])
        top_headline = news[0]["title"][:80] if news else "no matching news"
        return f"{ticker} {direction} {pct:.1f}% -- possibly related to: {top_headline}"


def run() -> Dict[str, Any]:
    """Main entry point for the scraper."""
    print(f"\n{'=' * 50}")
    print("FINNHUB MARKET DATA + NEWS CORRELATION")
    print(f"{'=' * 50}")

    scraper = FinnhubScraper()

    # 1. Fetch quotes
    print(f"\nFetching quotes for {len(AI_TICKERS)} tickers...")
    quotes = scraper.fetch_all_quotes()
    print(f"  Got {len(quotes)} quotes")

    if not quotes:
        print("  No quotes received, aborting")
        return {"stocks": [], "movers": [], "correlations": []}

    # 2. Market summary
    movers = [q for q in quotes if abs(q["change_pct"]) > 2]
    movers.sort(key=lambda q: abs(q["change_pct"]), reverse=True)

    print(f"\n  Big movers (>2%): {len(movers)}")
    for m in movers[:5]:
        arrow = "+" if m["change_pct"] > 0 else ""
        print(f"    {m['ticker']:6} ${m['current_price']:>8.2f}  {arrow}{m['change_pct']:.1f}%  [{m['signal']}]")

    # 3. Sector summary
    sectors = {
        "Big Tech": ['NVDA', 'MSFT', 'GOOGL', 'META', 'AMZN', 'AAPL'],
        "Semis": ['AMD', 'INTC', 'AVGO', 'QCOM', 'ARM', 'TSM', 'ASML', 'MRVL'],
        "AI Pure-play": ['AI', 'PLTR', 'PATH', 'SNOW', 'DDOG', 'CRWD', 'UPST'],
        "Enterprise": ['CRM', 'ORCL', 'IBM', 'NOW', 'ADBE', 'WDAY'],
    }

    quote_map = {q["ticker"]: q for q in quotes}
    print(f"\n  Sector performance:")
    for sector, tickers in sectors.items():
        changes = [quote_map[t]["change_pct"] for t in tickers if t in quote_map]
        if changes:
            avg = sum(changes) / len(changes)
            print(f"    {sector:15} avg: {avg:+.2f}%  ({len(changes)} stocks)")

    # 4. Technical analysis for top movers
    ta_results = {}
    if movers:
        ta_tickers = [m["ticker"] for m in movers[:8]]  # Top 8 movers only
        print(f"\n  Running TA on {len(ta_tickers)} movers...")
        for ticker in ta_tickers:
            price = quote_map.get(ticker, {}).get("current_price")
            ta = TechnicalAnalyzer.analyze(ticker, scraper.api_key, price)
            ta_results[ticker] = ta
            signals_str = ", ".join(ta.get("ta_signals", []))
            rsi = ta.get("rsi", "?")
            print(f"    {ticker:6} RSI:{rsi}  [{signals_str}]")
            time.sleep(0.2)

    # 5. News correlation
    print(f"\n  Correlating movers with news...")
    correlator = MarketNewsCorrelator()
    correlations = correlator.correlate(quotes)

    if correlations:
        print(f"  Found {len(correlations)} price-news correlations:")
        for c in correlations[:5]:
            print(f"    {c['narrative']}")
    else:
        print("  No correlations found (no movers or no matching news)")

    # Enrich correlations with TA
    for c in correlations:
        ta = ta_results.get(c["ticker"])
        if ta:
            c["technical"] = {
                "rsi": ta.get("rsi"),
                "macd": ta.get("macd"),
                "bollinger_position": ta.get("bollinger", {}).get("position_pct"),
                "sma_cross": ta.get("sma_cross", {}).get("crossover"),
                "ta_signals": ta.get("ta_signals", []),
            }

    # 6. Save
    today = date.today().isoformat()
    result = {
        "scraped_at": datetime.now().isoformat(),
        "source": "finnhub",
        "ticker_count": len(quotes),
        "mover_count": len(movers),
        "correlation_count": len(correlations),
        "stocks": quotes,
        "movers": [{"ticker": m["ticker"], "change_pct": m["change_pct"], "signal": m["signal"]} for m in movers],
        "technical_analysis": ta_results,
        "correlations": correlations,
    }

    output_path = DATA_DIR / f"finnhub_{today}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nSaved to {output_path}")
    return result


# Compatibility with run_high_value_scrapers.py
def scrape_market_signals():
    return run()

def save_signals(data):
    pass  # Already saved in run()


if __name__ == "__main__":
    run()
