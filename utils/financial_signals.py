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
import ccxt
import dbnomics

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


class TokenFetcher:
    """Fetches AI token data from crypto exchanges."""

    # Mapping of token symbols to exchange trading pairs
    TOKEN_PAIRS = {
        "FET": "FET/USD",
        "AGIX": "AGIX/USD",
        "OCEAN": "OCEAN/USD",
        "TAO": "TAO/USD",
        "RNDR": "RNDR/USD",
        "ARKM": "ARKM/USD",
        "WLD": "WLD/USD",
        "AKT": "AKT/USD",
    }

    def __init__(self, tokens: Optional[List[str]] = None, exchange: str = "kraken"):
        """
        Initialize fetcher.

        Args:
            tokens: List of token symbols. If None, loads from config.
            exchange: Exchange to use (default: kraken)
        """
        self.tokens = tokens or get_all_tokens()
        self.exchange_name = exchange
        self.exchange = self._init_exchange(exchange)
        logger.info(f"TokenFetcher initialized with {len(self.tokens)} tokens on {exchange}")

    def _init_exchange(self, name: str):
        """Initialize exchange connection."""
        try:
            exchange_class = getattr(ccxt, name)
            return exchange_class({
                'enableRateLimit': True,
            })
        except Exception as e:
            logger.error(f"Failed to init exchange {name}: {e}")
            return None

    def fetch(self) -> List[TokenData]:
        """
        Fetch token data for all configured tokens.

        Returns:
            List of TokenData objects
        """
        if not self.exchange:
            logger.error("No exchange initialized")
            return []

        results = []
        now = datetime.now()

        for token in self.tokens:
            try:
                pair = self.TOKEN_PAIRS.get(token, f"{token}/USD")

                # Fetch current ticker
                ticker = self.exchange.fetch_ticker(pair)
                if not ticker:
                    continue

                current_price = ticker.get('last', 0)
                change_1d = ticker.get('percentage', 0)
                volume_24h = ticker.get('quoteVolume', 0)

                # Fetch OHLCV for 7d and 30d changes
                change_7d = self._calc_change_from_ohlcv(pair, 7, current_price)
                change_30d = self._calc_change_from_ohlcv(pair, 30, current_price)

                data = TokenData(
                    symbol=token,
                    asof=now,
                    price_usd=current_price,
                    change_1d_pct=round(change_1d, 2) if change_1d else 0,
                    change_7d_pct=change_7d,
                    change_30d_pct=change_30d,
                    volume_24h_usd=volume_24h,
                )
                results.append(data)

            except Exception as e:
                logger.warning(f"Error fetching {token}: {e}")
                continue

        logger.info(f"Fetched {len(results)}/{len(self.tokens)} tokens")
        return results

    def _calc_change_from_ohlcv(self, pair: str, days: int, current: float) -> float:
        """Calculate % change from OHLCV data."""
        try:
            ohlcv = self.exchange.fetch_ohlcv(pair, '1d', limit=days + 1)
            if ohlcv and len(ohlcv) > days:
                old_close = ohlcv[0][4]  # Close price from days ago
                if old_close > 0:
                    return round((current - old_close) / old_close * 100, 2)
        except Exception as e:
            logger.debug(f"OHLCV fetch failed for {pair}: {e}")
        return 0.0


class MacroFetcher:
    """Fetches macro indicators from DBnomics."""

    def __init__(self, series: Optional[Dict[str, Dict]] = None):
        """
        Initialize fetcher.

        Args:
            series: Dict of series configs. If None, loads from config.
        """
        self.series = series or load_macro_series()
        self._historical_data: Dict[str, List[float]] = {}
        logger.info(f"MacroFetcher initialized with {len(self.series)} series")

    def fetch(self) -> List[MacroData]:
        """
        Fetch macro indicator data.

        Returns:
            List of MacroData objects with z-scores
        """
        results = []
        now = datetime.now()

        for series_id, config in self.series.items():
            try:
                # Fetch from DBnomics
                df = dbnomics.fetch_series(series_id)

                if df is None or df.empty:
                    logger.warning(f"No data for {series_id}")
                    continue

                # Get latest value
                latest = df.iloc[-1]
                value = float(latest['value']) if 'value' in latest else float(latest.iloc[-1])

                # Get timestamp
                asof = latest.get('period', now)
                if isinstance(asof, str):
                    asof = datetime.fromisoformat(asof.replace('Z', '+00:00'))

                # Compute z-score from historical data
                values = df['value'].dropna().tolist() if 'value' in df.columns else []
                z_score = self._compute_zscore(value, values)

                # Invert if configured (high VIX = bad, so invert)
                if config.get('invert', False):
                    z_score = -z_score if z_score is not None else None

                data = MacroData(
                    series_id=series_id,
                    name=config.get('name', series_id),
                    asof=asof if isinstance(asof, datetime) else now,
                    value=value,
                    z_score=z_score,
                )
                results.append(data)

            except Exception as e:
                logger.warning(f"Error fetching {series_id}: {e}")
                continue

        logger.info(f"Fetched {len(results)}/{len(self.series)} macro series")
        return results

    def _compute_zscore(self, value: float, historical: List[float]) -> Optional[float]:
        """Compute z-score of value relative to historical data."""
        if not historical or len(historical) < 10:
            return None

        import statistics
        mean = statistics.mean(historical)
        stdev = statistics.stdev(historical)

        if stdev == 0:
            return 0.0

        z = (value - mean) / stdev
        return round(z, 2)

    def compute_mrs(self, macro_data: List[MacroData]) -> float:
        """
        Compute Macro Regime Signal from z-scores.

        MRS is weighted average of z-scores, clipped to [-1, 1].
        Negative = risk-off, Positive = risk-on.

        Args:
            macro_data: List of MacroData with z-scores

        Returns:
            MRS value between -1 and 1
        """
        if not macro_data:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for data in macro_data:
            if data.z_score is None:
                continue

            config = self.series.get(data.series_id, {})
            weight = config.get('weight', 0.2)

            weighted_sum += data.z_score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        mrs = weighted_sum / total_weight

        # Clip to [-1, 1]
        mrs = max(-1.0, min(1.0, mrs))

        return round(mrs, 2)

    def interpret_mrs(self, mrs: float) -> str:
        """Get human-readable interpretation of MRS."""
        if mrs < -0.5:
            return "risk_off"
        elif mrs < -0.2:
            return "mildly_risk_off"
        elif mrs < 0.2:
            return "neutral"
        elif mrs < 0.5:
            return "mildly_risk_on"
        else:
            return "risk_on"
