"""
Market Context — Lightweight price data for news intelligence.

NOT a trading terminal. Provides just enough market data to contextualize
news analysis: "did the market react to this event?"

Rules:
- Daily close + intraday snapshot. No real-time streaming.
- No TA indicators (RSI, MACD, etc). Link to TradingView for that.
- Cache aggressively. One API call per ticker per day max.
- Price data answers "what happened" not "what to buy".
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from typing import Any, Dict, List, Optional
from pathlib import Path

from loguru import logger

# Try AKShare for A-shares, yfinance for US stocks
try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class PriceSnapshot:
    """Minimal price context for an entity."""
    ticker: str
    market: str              # "A-share", "HK", "US"
    price: Optional[float] = None
    change_pct: Optional[float] = None
    volume_vs_avg: Optional[float] = None  # ratio vs 20d avg
    five_day_trend: Optional[str] = None   # "up", "down", "flat"
    sector_change_pct: Optional[float] = None
    as_of: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class SectorSnapshot:
    """Sector-level context."""
    sector: str
    avg_change_pct: Optional[float] = None
    top_gainers: List[Dict[str, Any]] = field(default_factory=list)
    top_losers: List[Dict[str, Any]] = field(default_factory=list)
    as_of: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class _PriceCache:
    """Simple TTL cache for price lookups. Avoids hammering APIs."""

    def __init__(self, ttl_seconds: int = 3600):
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            val, ts = self._cache[key]
            if time.time() - ts < self._ttl:
                return val
            del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        self._cache[key] = (value, time.time())


_cache = _PriceCache(ttl_seconds=3600)  # 1 hour cache


# ---------------------------------------------------------------------------
# Market Context
# ---------------------------------------------------------------------------

class MarketContext:
    """
    Lightweight market data — context for news, not a terminal.

    Usage:
        ctx = MarketContext()
        snap = ctx.get_price_context("688256")  # A-share
        snap = ctx.get_price_context("NVDA", market="US")
    """

    def get_price_context(self, ticker: str, market: str = "auto") -> PriceSnapshot:
        """
        Get minimal price context for an entity.

        Args:
            ticker: Stock code (e.g., "688256" for A-share, "NVDA" for US)
            market: "A-share", "US", "HK", or "auto" (guess from ticker format)
        """
        if market == "auto":
            market = self._guess_market(ticker)

        cache_key = f"price:{market}:{ticker}"
        cached = _cache.get(cache_key)
        if cached:
            return cached

        try:
            if market == "A-share":
                snap = self._fetch_ashare(ticker)
            elif market == "US":
                snap = self._fetch_us(ticker)
            else:
                snap = PriceSnapshot(ticker=ticker, market=market, error=f"Unsupported market: {market}")
        except Exception as e:
            logger.debug(f"MarketContext fetch failed for {ticker}: {e}")
            snap = PriceSnapshot(ticker=ticker, market=market, error=str(e))

        _cache.set(cache_key, snap)
        return snap

    def get_sector_snapshot(self, sector: str) -> SectorSnapshot:
        """Top movers in a sector. Kept intentionally minimal."""
        cache_key = f"sector:{sector}"
        cached = _cache.get(cache_key)
        if cached:
            return cached

        snap = SectorSnapshot(sector=sector, as_of=datetime.now().isoformat())
        # Sector data is best-effort — if AKShare is down, return empty
        if AKSHARE_AVAILABLE:
            try:
                snap = self._fetch_sector_ashare(sector)
            except Exception as e:
                logger.debug(f"Sector snapshot failed for {sector}: {e}")

        _cache.set(cache_key, snap)
        return snap

    def get_risk_alerts(self) -> List[Dict[str, Any]]:
        """
        Get institutional risk alerts and market warnings.

        Returns:
            List of risk alerts with 'level', 'title', and 'detail' fields.
            Empty list if no alerts or feature not fully implemented.
        """
        # TODO: Implement risk alert detection based on:
        # - Unusual market volatility
        # - Sector-wide price movements
        # - Volume spikes across multiple tickers
        # For now, return empty list (stub implementation)
        return []

    # -----------------------------------------------------------------------
    # Private fetchers
    # -----------------------------------------------------------------------

    def _fetch_ashare(self, code: str) -> PriceSnapshot:
        """Fetch A-share daily context from AKShare."""
        if not AKSHARE_AVAILABLE:
            return PriceSnapshot(ticker=code, market="A-share", error="akshare not installed")

        snap = PriceSnapshot(ticker=code, market="A-share", as_of=datetime.now().isoformat())

        # Historical daily (last 30 days) — single call, no real-time
        try:
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=60)).strftime("%Y%m%d")
            df = ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=start_date, end_date=end_date, adjust="qfq"
            )
            if df is not None and not df.empty:
                latest = df.iloc[-1]
                snap.price = float(latest.get("收盘", 0))
                prev_close = float(df.iloc[-2].get("收盘", 0)) if len(df) >= 2 else None
                if prev_close and prev_close > 0:
                    snap.change_pct = round((snap.price - prev_close) / prev_close * 100, 2)

                # Volume vs 20-day average
                if len(df) >= 20:
                    avg_vol = df["成交量"].tail(20).mean()
                    today_vol = float(latest.get("成交量", 0))
                    if avg_vol > 0:
                        snap.volume_vs_avg = round(today_vol / avg_vol, 2)

                # 5-day trend
                if len(df) >= 5:
                    five_ago = float(df.iloc[-5].get("收盘", 0))
                    if five_ago > 0:
                        pct = (snap.price - five_ago) / five_ago * 100
                        snap.five_day_trend = "up" if pct > 1 else "down" if pct < -1 else "flat"
        except Exception as e:
            logger.debug(f"AKShare history failed for {code}: {e}")
            snap.error = str(e)

        return snap

    def _fetch_us(self, ticker: str) -> PriceSnapshot:
        """Fetch US stock daily context from yfinance."""
        if not YFINANCE_AVAILABLE:
            return PriceSnapshot(ticker=ticker, market="US", error="yfinance not installed")

        snap = PriceSnapshot(ticker=ticker, market="US", as_of=datetime.now().isoformat())

        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1mo")
            if hist is not None and not hist.empty:
                latest = hist.iloc[-1]
                snap.price = round(float(latest["Close"]), 2)
                if len(hist) >= 2:
                    prev = float(hist.iloc[-2]["Close"])
                    if prev > 0:
                        snap.change_pct = round((snap.price - prev) / prev * 100, 2)

                if len(hist) >= 20:
                    avg_vol = hist["Volume"].tail(20).mean()
                    today_vol = float(latest["Volume"])
                    if avg_vol > 0:
                        snap.volume_vs_avg = round(today_vol / avg_vol, 2)

                if len(hist) >= 5:
                    five_ago = float(hist.iloc[-5]["Close"])
                    if five_ago > 0:
                        pct = (snap.price - five_ago) / five_ago * 100
                        snap.five_day_trend = "up" if pct > 1 else "down" if pct < -1 else "flat"
        except Exception as e:
            logger.debug(f"yfinance failed for {ticker}: {e}")
            snap.error = str(e)

        return snap

    def _fetch_sector_ashare(self, sector: str) -> SectorSnapshot:
        """Fetch A-share sector data."""
        snap = SectorSnapshot(sector=sector, as_of=datetime.now().isoformat())
        try:
            df = ak.stock_board_concept_name_em()
            if df is not None and not df.empty:
                match = df[df["板块名称"].str.contains(sector, na=False)]
                if not match.empty:
                    row = match.iloc[0]
                    snap.avg_change_pct = float(row.get("涨跌幅", 0))
        except Exception as e:
            logger.debug(f"Sector fetch failed: {e}")
        return snap

    @staticmethod
    def _guess_market(ticker: str) -> str:
        """Guess market from ticker format."""
        if ticker.isdigit() and len(ticker) == 6:
            return "A-share"
        if ticker.isdigit() and len(ticker) == 5:
            return "HK"
        return "US"
