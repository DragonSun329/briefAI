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


# =============================================================================
# Bucket Signal Aggregator
# =============================================================================

@dataclass
class BucketFinancialSignal:
    """Financial signals for a single bucket."""
    bucket_id: str

    # Public Market Signal (from equities)
    pms: Optional[float] = None
    pms_coverage: Optional[Dict[str, Any]] = None
    pms_contributors: List[Dict[str, Any]] = field(default_factory=list)

    # Crypto Sentiment Signal (from tokens)
    css: Optional[float] = None
    css_coverage: Optional[Dict[str, Any]] = None
    css_contributors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON."""
        return {
            "bucket_id": self.bucket_id,
            "pms": self.pms,
            "pms_coverage": self.pms_coverage,
            "pms_contributors": self.pms_contributors,
            "pms_contributors_text": [
                f"{c['ticker']} {c['change_7d_pct']:+.1f}%"
                for c in self.pms_contributors[:3]
            ] if self.pms_contributors else [],
            "css": self.css,
            "css_coverage": self.css_coverage,
            "css_contributors": self.css_contributors,
            "css_contributors_text": [
                f"{c['symbol']} {c['change_7d_pct']:+.1f}%"
                for c in self.css_contributors[:3]
            ] if self.css_contributors else [],
        }


class BucketSignalAggregator:
    """Aggregates equity and token data into bucket-level signals."""

    def __init__(self):
        self.ticker_buckets = load_ticker_buckets()
        self.token_buckets = load_token_buckets()

        # Build reverse mappings
        self.ticker_to_buckets: Dict[str, List[str]] = {}
        for bucket_id, tickers in self.ticker_buckets.items():
            for ticker in tickers:
                if ticker not in self.ticker_to_buckets:
                    self.ticker_to_buckets[ticker] = []
                self.ticker_to_buckets[ticker].append(bucket_id)

    def compute_bucket_signals(
        self,
        equity_data: Optional[List[EquityData]] = None,
        token_data: Optional[List[TokenData]] = None,
    ) -> Dict[str, BucketFinancialSignal]:
        """
        Compute PMS and CSS signals per bucket.

        Args:
            equity_data: List of EquityData from Yahoo Finance
            token_data: List of TokenData from crypto exchange

        Returns:
            Dict mapping bucket_id to BucketFinancialSignal
        """
        # Get all bucket IDs
        all_buckets = set(self.ticker_buckets.keys())
        for token_config in self.token_buckets.values():
            all_buckets.add(token_config["primary"])
            all_buckets.update(token_config.get("secondary", []))

        signals: Dict[str, BucketFinancialSignal] = {
            bucket_id: BucketFinancialSignal(bucket_id=bucket_id)
            for bucket_id in all_buckets
        }

        # Compute PMS from equities
        if equity_data:
            self._compute_pms(signals, equity_data)

        # Compute CSS from tokens
        if token_data:
            self._compute_css(signals, token_data)

        return signals

    def _compute_pms(
        self,
        signals: Dict[str, BucketFinancialSignal],
        equity_data: List[EquityData]
    ):
        """Compute PMS (Public Market Signal) for each bucket."""
        # Group equities by bucket
        bucket_equities: Dict[str, List[EquityData]] = {}
        equity_by_ticker = {e.ticker: e for e in equity_data}

        for bucket_id, tickers in self.ticker_buckets.items():
            bucket_equities[bucket_id] = []
            for ticker in tickers:
                if ticker in equity_by_ticker:
                    bucket_equities[bucket_id].append(equity_by_ticker[ticker])

        # Collect all 7d changes for percentile calculation
        all_changes = []
        for equities in bucket_equities.values():
            if equities:
                avg_change = sum(e.change_7d_pct for e in equities) / len(equities)
                all_changes.append(avg_change)

        # Compute PMS per bucket (percentile of average 7d change)
        for bucket_id, equities in bucket_equities.items():
            if not equities:
                continue

            # Average 7d change for this bucket
            avg_change = sum(e.change_7d_pct for e in equities) / len(equities)

            # Convert to percentile
            pms = self._to_percentile(avg_change, all_changes)

            # Coverage info
            expected_tickers = self.ticker_buckets.get(bucket_id, [])
            present_tickers = [e.ticker for e in equities]
            missing_tickers = [t for t in expected_tickers if t not in present_tickers]

            # Contributors (sorted by contribution)
            contributors = sorted(
                [{"ticker": e.ticker, "change_7d_pct": e.change_7d_pct,
                  "weight": 1.0/len(equities), "contribution": e.change_7d_pct/len(equities)}
                 for e in equities],
                key=lambda x: abs(x["change_7d_pct"]),
                reverse=True
            )

            signals[bucket_id].pms = pms
            signals[bucket_id].pms_coverage = {
                "tickers_present": len(equities),
                "tickers_total": len(expected_tickers),
                "missing": missing_tickers,
            }
            signals[bucket_id].pms_contributors = contributors

    def _compute_css(
        self,
        signals: Dict[str, BucketFinancialSignal],
        token_data: List[TokenData]
    ):
        """Compute CSS (Crypto Sentiment Signal) for each bucket."""
        token_by_symbol = {t.symbol: t for t in token_data}

        # Group tokens by bucket (primary and secondary)
        bucket_tokens: Dict[str, List[tuple]] = {}  # bucket -> [(token, confidence)]

        for symbol, config in self.token_buckets.items():
            if symbol not in token_by_symbol:
                continue

            token = token_by_symbol[symbol]
            confidence = config.get("confidence", 0.7)

            # Primary bucket
            primary = config["primary"]
            if primary not in bucket_tokens:
                bucket_tokens[primary] = []
            bucket_tokens[primary].append((token, confidence))

            # Secondary buckets (lower weight)
            for secondary in config.get("secondary", []):
                if secondary not in bucket_tokens:
                    bucket_tokens[secondary] = []
                bucket_tokens[secondary].append((token, confidence * 0.5))

        # Collect all 7d changes for percentile calculation
        all_changes = []
        for tokens in bucket_tokens.values():
            if tokens:
                weighted_change = sum(t.change_7d_pct * c for t, c in tokens) / sum(c for _, c in tokens)
                all_changes.append(weighted_change)

        # Compute CSS per bucket
        for bucket_id, tokens in bucket_tokens.items():
            if not tokens:
                continue

            # Confidence-weighted average 7d change
            total_weight = sum(c for _, c in tokens)
            weighted_change = sum(t.change_7d_pct * c for t, c in tokens) / total_weight

            # Convert to percentile
            css = self._to_percentile(weighted_change, all_changes)

            # Coverage info
            expected_tokens = [s for s, cfg in self.token_buckets.items()
                            if cfg["primary"] == bucket_id or bucket_id in cfg.get("secondary", [])]
            present_tokens = [t.symbol for t, _ in tokens]
            missing_tokens = [t for t in expected_tokens if t not in present_tokens]

            # Contributors
            contributors = sorted(
                [{"symbol": t.symbol, "change_7d_pct": t.change_7d_pct,
                  "weight": c / total_weight, "contribution": t.change_7d_pct * c / total_weight}
                 for t, c in tokens],
                key=lambda x: abs(x["change_7d_pct"]),
                reverse=True
            )

            signals[bucket_id].css = css
            signals[bucket_id].css_coverage = {
                "tokens_present": len(tokens),
                "tokens_total": len(expected_tokens),
                "missing": missing_tokens,
            }
            signals[bucket_id].css_contributors = contributors

    def _to_percentile(self, value: float, all_values: List[float]) -> float:
        """Convert value to percentile within all_values."""
        if not all_values:
            return 50.0

        below = sum(1 for v in all_values if v < value)
        percentile = (below / len(all_values)) * 100
        return round(percentile, 1)


# =============================================================================
# Output Generator
# =============================================================================

@dataclass
class FinancialSignalsOutput:
    """Complete financial signals output artifact."""
    date: date
    equities: List[EquityData]
    tokens: List[TokenData]
    macro: List[MacroData]
    bucket_signals: Dict[str, BucketFinancialSignal]
    mrs: float
    mrs_interpretation: str

    # Source status tracking
    sources_status: Dict[str, Dict] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to full output schema."""
        # Determine overall status
        degraded_sources = [s for s, info in self.sources_status.items()
                          if info.get("status") == "degraded"]
        overall_status = "degraded" if degraded_sources else "ok"

        return {
            "schema": {
                "name": "financial_signals",
                "version": "1.0",
                "compatible_with": ["1.0"]
            },
            "date": self.date.isoformat(),
            "generated_at": datetime.now().isoformat(),

            "quality": {
                "overall_status": overall_status,
                "warnings": self.warnings,
            },

            "sources": self.sources_status,

            "methods": {
                "pms": {
                    "window_days": [1, 7, 30],
                    "weighting": "equal",
                    "aggregation": "bucket_equal_weight",
                    "transform": "percentile"
                },
                "css": {
                    "window_days": [1, 7, 30],
                    "weighting": "equal",
                    "aggregation": "confidence_weighted",
                    "transform": "percentile"
                },
                "mrs": {
                    "components": ["volatility", "rates", "employment", "credit", "cli"],
                    "transform": "zscore_composite",
                    "normalize": "clip_-1_1"
                }
            },

            "raw": {
                "equities": [e.to_dict() for e in self.equities],
                "tokens": [t.to_dict() for t in self.tokens],
                "macro": [m.to_dict() for m in self.macro],
            },

            "macro_regime": {
                "mrs": self.mrs,
                "interpretation": self.mrs_interpretation,
                "components": {
                    m.name.lower().replace(" ", "_"): {
                        "z_score": m.z_score,
                        "weight": load_macro_series().get(m.series_id, {}).get("weight", 0.2)
                    }
                    for m in self.macro
                }
            },

            "bucket_signals": {
                bucket_id: signal.to_dict()
                for bucket_id, signal in self.bucket_signals.items()
            }
        }

    def save(self, path: Path):
        """Save output to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Saved financial signals to {path}")


def generate_financial_signals(
    output_dir: Optional[Path] = None,
    target_date: Optional[date] = None,
) -> FinancialSignalsOutput:
    """
    Generate complete financial signals artifact.

    Args:
        output_dir: Directory to save output. If None, uses default.
        target_date: Date for the signals. If None, uses today.

    Returns:
        FinancialSignalsOutput object
    """
    if target_date is None:
        target_date = date.today()

    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    logger.info(f"Generating financial signals for {target_date}")

    sources_status = {}
    warnings = []

    # Fetch equities
    equity_fetcher = EquityFetcher()
    equities = equity_fetcher.fetch()
    sources_status["yahoo_finance"] = {
        "status": "ok" if len(equities) > 20 else "degraded",
        "tickers_fetched": len(equities),
        "tickers_expected": len(equity_fetcher.tickers),
    }
    if len(equities) < len(equity_fetcher.tickers) * 0.8:
        warnings.append(f"Only fetched {len(equities)}/{len(equity_fetcher.tickers)} equities")

    # Fetch tokens
    token_fetcher = TokenFetcher()
    tokens = token_fetcher.fetch()
    sources_status["kraken"] = {
        "status": "ok" if len(tokens) > 5 else "degraded",
        "tokens_fetched": len(tokens),
        "tokens_expected": len(token_fetcher.tokens),
    }
    if len(tokens) < len(token_fetcher.tokens) * 0.8:
        warnings.append(f"Only fetched {len(tokens)}/{len(token_fetcher.tokens)} tokens")

    # Fetch macro
    macro_fetcher = MacroFetcher()
    macro = macro_fetcher.fetch()
    sources_status["dbnomics"] = {
        "status": "ok" if len(macro) > 3 else "degraded",
        "series_fetched": len(macro),
        "series_expected": len(macro_fetcher.series),
    }

    # Compute MRS
    mrs = macro_fetcher.compute_mrs(macro)
    mrs_interpretation = macro_fetcher.interpret_mrs(mrs)

    # Aggregate to bucket signals
    aggregator = BucketSignalAggregator()
    bucket_signals = aggregator.compute_bucket_signals(
        equity_data=equities,
        token_data=tokens,
    )

    output = FinancialSignalsOutput(
        date=target_date,
        equities=equities,
        tokens=tokens,
        macro=macro,
        bucket_signals=bucket_signals,
        mrs=mrs,
        mrs_interpretation=mrs_interpretation,
        sources_status=sources_status,
        warnings=warnings,
    )

    # Save to file
    output_path = output_dir / f"financial_signals_{target_date.isoformat()}.json"
    output.save(output_path)

    return output
