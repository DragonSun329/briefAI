"""
Financial Signals Module

Fetches financial data from Yahoo Finance, Kraken, and DBnomics.
Outputs PMS (Public Market Signal), CSS (Crypto Sentiment Signal),
and MRS (Macro Regime Signal) as independent channels.
"""

from __future__ import annotations

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from loguru import logger

import yfinance as yf

from utils.config_loader import (
    load_ticker_buckets,
    load_token_buckets,
    load_macro_series,
    get_all_tickers,
    get_all_tokens,
)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class EquityData:
    """Raw equity data from Yahoo Finance."""
    ticker: str
    asof: datetime
    price: float
    change_1d_pct: float
    change_7d_pct: float
    change_30d_pct: float
    volume: int
    volume_avg_30d: int
    market_cap_b: Optional[float] = None

    @property
    def volume_ratio(self) -> float:
        """Volume relative to 30-day average."""
        if self.volume_avg_30d and self.volume_avg_30d > 0:
            return round(self.volume / self.volume_avg_30d, 2)
        return 1.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ticker": self.ticker,
            "asof": self.asof.isoformat(),
            "price": self.price,
            "change_1d_pct": self.change_1d_pct,
            "change_7d_pct": self.change_7d_pct,
            "change_30d_pct": self.change_30d_pct,
            "volume": self.volume,
            "volume_avg_30d": self.volume_avg_30d,
            "volume_ratio": self.volume_ratio,
            "market_cap_b": self.market_cap_b,
        }


@dataclass
class TokenData:
    """Raw token data from crypto exchange."""
    symbol: str
    asof: datetime
    price_usd: float
    change_1d_pct: float
    change_7d_pct: float
    change_30d_pct: float
    volume_24h_usd: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "symbol": self.symbol,
            "asof": self.asof.isoformat(),
            "price_usd": self.price_usd,
            "change_1d_pct": self.change_1d_pct,
            "change_7d_pct": self.change_7d_pct,
            "change_30d_pct": self.change_30d_pct,
            "volume_24h_usd": self.volume_24h_usd,
        }


@dataclass
class MacroData:
    """Raw macro indicator data from DBnomics."""
    series_id: str
    name: str
    asof: datetime
    value: float
    z_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "series_id": self.series_id,
            "name": self.name,
            "asof": self.asof.isoformat(),
            "value": self.value,
            "z_score": self.z_score,
        }


# =============================================================================
# Fetchers
# =============================================================================

class EquityFetcher:
    """Fetches equity data from Yahoo Finance."""

    def __init__(self, tickers: Optional[List[str]] = None):
        """
        Initialize fetcher.

        Args:
            tickers: List of ticker symbols. If None, loads from config.
        """
        self.tickers = tickers or get_all_tickers()
        logger.info(f"EquityFetcher initialized with {len(self.tickers)} tickers")

    def fetch(self) -> List[EquityData]:
        """
        Fetch equity data for all tickers.

        Returns:
            List of EquityData objects
        """
        results = []
        now = datetime.now()

        # Batch fetch for efficiency
        try:
            tickers_obj = yf.Tickers(" ".join(self.tickers))

            for ticker_symbol in self.tickers:
                try:
                    ticker = tickers_obj.tickers.get(ticker_symbol)
                    if ticker is None:
                        logger.warning(f"Ticker {ticker_symbol} not found")
                        continue

                    info = ticker.info
                    if not info:
                        logger.warning(f"No info for {ticker_symbol}")
                        continue

                    # Get historical data for % changes
                    hist = ticker.history(period="1mo")
                    if hist.empty:
                        logger.warning(f"No history for {ticker_symbol}")
                        continue

                    current_price = info.get('regularMarketPrice') or info.get('currentPrice', 0)

                    # Calculate % changes
                    prices = hist['Close']
                    change_1d = self._calc_change(prices, 1, current_price)
                    change_7d = self._calc_change(prices, 5, current_price)  # 5 trading days
                    change_30d = self._calc_change(prices, len(prices) - 1, current_price)

                    data = EquityData(
                        ticker=ticker_symbol,
                        asof=now,
                        price=current_price,
                        change_1d_pct=change_1d,
                        change_7d_pct=change_7d,
                        change_30d_pct=change_30d,
                        volume=info.get('regularMarketVolume', 0),
                        volume_avg_30d=info.get('averageVolume', 0),
                        market_cap_b=info.get('marketCap', 0) / 1e9 if info.get('marketCap') else None,
                    )
                    results.append(data)

                except Exception as e:
                    logger.error(f"Error fetching {ticker_symbol}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error in batch fetch: {e}")

        logger.info(f"Fetched {len(results)}/{len(self.tickers)} equities")
        return results

    def _calc_change(self, prices, days_back: int, current: float) -> float:
        """Calculate percentage change from days_back to now."""
        try:
            if len(prices) > days_back:
                old_price = prices.iloc[-(days_back + 1)]
                if old_price > 0:
                    return round((current - old_price) / old_price * 100, 2)
        except Exception:
            pass
        return 0.0
