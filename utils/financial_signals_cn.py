"""
China Market Financial Signals Module

Fetches financial data from AkShare (A-shares) and yfinance (HK stocks).
Outputs PMS-CN (Public Market Signal China) and MRS-CN (Macro Regime Signal China).
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from loguru import logger

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except ImportError:
    AKSHARE_AVAILABLE = False
    logger.warning("akshare not available - CN A-share data will be limited")

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not available - HK stock data will be limited")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CNEquityData:
    """Raw equity data for A-share or HK stock."""
    ticker: str
    name: str
    asof: datetime
    price: float
    change_1d_pct: float
    change_7d_pct: float
    change_30d_pct: float
    volume: int
    volume_ratio: float  # vs 30-day avg
    market: str  # "A" or "HK"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "ticker": self.ticker,
            "name": self.name,
            "asof": self.asof.isoformat(),
            "price": self.price,
            "change_1d_pct": self.change_1d_pct,
            "change_7d_pct": self.change_7d_pct,
            "change_30d_pct": self.change_30d_pct,
            "volume": self.volume,
            "volume_ratio": self.volume_ratio,
            "market": self.market,
        }


@dataclass
class CNMacroData:
    """Raw macro indicator data for China."""
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


@dataclass
class CNFlowData:
    """Capital flow data for China market."""
    asof: datetime
    northbound_net: float  # Northbound net inflow in 100M CNY
    northbound_buy: float
    northbound_sell: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asof": self.asof.isoformat(),
            "northbound_net": self.northbound_net,
            "northbound_buy": self.northbound_buy,
            "northbound_sell": self.northbound_sell,
        }


# =============================================================================
# Config Loader
# =============================================================================

def load_cn_config() -> Dict[str, Any]:
    """Load CN market configuration."""
    config_path = Path(__file__).parent.parent / "config" / "financial_mappings_cn.json"
    if not config_path.exists():
        logger.warning(f"CN config not found at {config_path}")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cn_ticker_buckets() -> Dict[str, List[str]]:
    """Load CN ticker-to-bucket mapping."""
    cfg = load_cn_config()
    return cfg.get("ticker_to_bucket", {})


def load_cn_macro_series() -> Dict[str, Dict]:
    """Load CN macro series configuration."""
    cfg = load_cn_config()
    return cfg.get("macro_series_cn", {})


def load_cn_bucket_names() -> Dict[str, str]:
    """Load CN bucket display names."""
    cfg = load_cn_config()
    return cfg.get("bucket_names", {})


def get_all_cn_tickers() -> List[str]:
    """Get unique list of all CN tickers."""
    buckets = load_cn_ticker_buckets()
    return list(set(t for tickers in buckets.values() for t in tickers))


# =============================================================================
# Fetchers
# =============================================================================

class CNEquityFetcher:
    """Fetches A-share and HK stock data."""

    def __init__(self, tickers: Optional[List[str]] = None):
        self.tickers = tickers or get_all_cn_tickers()
        self.ashare_tickers = [t for t in self.tickers if t.endswith('.SS') or t.endswith('.SZ')]
        self.hk_tickers = [t for t in self.tickers if t.endswith('.HK')]
        logger.info(f"CNEquityFetcher: {len(self.ashare_tickers)} A-shares, {len(self.hk_tickers)} HK stocks")

    def fetch(self) -> List[CNEquityData]:
        """Fetch all CN equity data."""
        results = []

        # Fetch A-shares using AkShare
        if self.ashare_tickers and AKSHARE_AVAILABLE:
            results.extend(self._fetch_ashares())

        # Fetch HK stocks using yfinance
        if self.hk_tickers and YFINANCE_AVAILABLE:
            results.extend(self._fetch_hk_stocks())

        logger.info(f"Fetched {len(results)} CN equities")
        return results

    def _fetch_ashares(self) -> List[CNEquityData]:
        """Fetch A-share data using AkShare."""
        results = []
        now = datetime.now()

        for ticker in self.ashare_tickers:
            try:
                # Convert ticker format: 688041.SS -> 688041
                code = ticker.split('.')[0]

                # Fetch historical data
                df = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=(date.today() - timedelta(days=35)).strftime("%Y%m%d"),
                    end_date=date.today().strftime("%Y%m%d"),
                    adjust="qfq"  # 前复权
                )

                if df is None or len(df) < 2:
                    logger.warning(f"No data for {ticker}")
                    continue

                # Calculate returns
                df = df.sort_values("日期")
                closes = df["收盘"].values
                volumes = df["成交量"].values

                price = closes[-1]
                change_1d = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 else 0
                change_7d = ((closes[-1] / closes[-6]) - 1) * 100 if len(closes) >= 6 else 0
                change_30d = ((closes[-1] / closes[0]) - 1) * 100 if len(closes) >= 2 else 0

                vol = volumes[-1]
                vol_avg = volumes[-30:].mean() if len(volumes) >= 30 else volumes.mean()
                vol_ratio = vol / vol_avg if vol_avg > 0 else 1.0

                # Get stock name
                try:
                    info = ak.stock_individual_info_em(symbol=code)
                    name = info[info["item"] == "股票简称"]["value"].values[0] if len(info) > 0 else code
                except Exception:
                    name = code

                results.append(CNEquityData(
                    ticker=ticker,
                    name=name,
                    asof=now,
                    price=float(price),
                    change_1d_pct=round(change_1d, 2),
                    change_7d_pct=round(change_7d, 2),
                    change_30d_pct=round(change_30d, 2),
                    volume=int(vol),
                    volume_ratio=round(vol_ratio, 2),
                    market="A"
                ))

            except Exception as e:
                logger.warning(f"Failed to fetch {ticker}: {e}")
                continue

        return results

    def _fetch_hk_stocks(self) -> List[CNEquityData]:
        """Fetch HK stock data using yfinance."""
        results = []
        now = datetime.now()

        if not YFINANCE_AVAILABLE:
            return results

        try:
            # Batch download HK stocks
            end_date = date.today()
            start_date = end_date - timedelta(days=35)

            df = yf.download(
                self.hk_tickers,
                start=start_date,
                end=end_date,
                progress=False,
                threads=True
            )

            if df.empty:
                return results

            for ticker in self.hk_tickers:
                try:
                    if len(self.hk_tickers) == 1:
                        closes = df['Close'].dropna()
                        volumes = df['Volume'].dropna()
                    else:
                        closes = df['Close'][ticker].dropna()
                        volumes = df['Volume'][ticker].dropna()

                    if len(closes) < 2:
                        continue

                    price = closes.iloc[-1]
                    change_1d = ((closes.iloc[-1] / closes.iloc[-2]) - 1) * 100
                    change_7d = ((closes.iloc[-1] / closes.iloc[-6]) - 1) * 100 if len(closes) >= 6 else 0
                    change_30d = ((closes.iloc[-1] / closes.iloc[0]) - 1) * 100

                    vol = volumes.iloc[-1]
                    vol_avg = volumes.iloc[-30:].mean() if len(volumes) >= 30 else volumes.mean()
                    vol_ratio = vol / vol_avg if vol_avg > 0 else 1.0

                    # Get stock info
                    try:
                        stock = yf.Ticker(ticker)
                        name = stock.info.get('shortName', ticker)
                    except Exception:
                        name = ticker

                    results.append(CNEquityData(
                        ticker=ticker,
                        name=name,
                        asof=now,
                        price=float(price),
                        change_1d_pct=round(float(change_1d), 2),
                        change_7d_pct=round(float(change_7d), 2),
                        change_30d_pct=round(float(change_30d), 2),
                        volume=int(vol),
                        volume_ratio=round(float(vol_ratio), 2),
                        market="HK"
                    ))

                except Exception as e:
                    logger.warning(f"Failed to process {ticker}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to fetch HK stocks: {e}")

        return results


class CNMacroFetcher:
    """Fetches China macro indicators using AkShare."""

    def __init__(self):
        self.series = load_cn_macro_series()
        self._historical: Dict[str, List[float]] = {}

    def fetch(self) -> List[CNMacroData]:
        """Fetch all CN macro indicators."""
        results = []
        now = datetime.now()

        if not AKSHARE_AVAILABLE:
            logger.warning("AkShare not available for CN macro data")
            return results

        # Fetch 10Y bond yield
        try:
            bond_data = self._fetch_bond_yield()
            if bond_data:
                results.append(bond_data)
        except Exception as e:
            logger.warning(f"Failed to fetch bond yield: {e}")

        # Fetch SHIBOR
        try:
            shibor_data = self._fetch_shibor()
            if shibor_data:
                results.append(shibor_data)
        except Exception as e:
            logger.warning(f"Failed to fetch SHIBOR: {e}")

        # Fetch USD/CNY
        try:
            fx_data = self._fetch_usd_cny()
            if fx_data:
                results.append(fx_data)
        except Exception as e:
            logger.warning(f"Failed to fetch USD/CNY: {e}")

        logger.info(f"Fetched {len(results)} CN macro indicators")
        return results

    def _fetch_bond_yield(self) -> Optional[CNMacroData]:
        """Fetch China 10Y government bond yield."""
        try:
            df = ak.bond_zh_us_rate(start_date=(date.today() - timedelta(days=365)).strftime("%Y%m%d"))
            if df is None or df.empty:
                return None

            # Get latest China 10Y yield
            latest = df.iloc[-1]
            value = float(latest.get("中国国债收益率10年", 0))

            # Calculate z-score from historical
            historical = df["中国国债收益率10年"].dropna().tolist()[-100:]
            z_score = self._compute_z_score(value, historical)

            # Invert (high yield = risk off)
            z_score = -z_score if z_score else None

            return CNMacroData(
                series_id="10y_bond",
                name="10Y国债收益率",
                asof=datetime.now(),
                value=value,
                z_score=z_score
            )
        except Exception as e:
            logger.warning(f"Bond yield fetch error: {e}")
            return None

    def _fetch_shibor(self) -> Optional[CNMacroData]:
        """Fetch SHIBOR 3-month rate."""
        try:
            df = ak.rate_interbank(
                market="上海银行同业拆借市场",
                symbol="Shibor人民币",
                indicator="3月"
            )
            if df is None or df.empty:
                return None

            latest = df.iloc[-1]
            value = float(latest.get("利率", latest.iloc[-1]))

            # Calculate z-score
            historical = df.iloc[:, -1].dropna().tolist()[-100:]
            z_score = self._compute_z_score(value, historical)
            z_score = -z_score if z_score else None  # Invert

            return CNMacroData(
                series_id="shibor_3m",
                name="3M SHIBOR",
                asof=datetime.now(),
                value=value,
                z_score=z_score
            )
        except Exception as e:
            logger.warning(f"SHIBOR fetch error: {e}")
            return None

    def _fetch_usd_cny(self) -> Optional[CNMacroData]:
        """Fetch USD/CNY exchange rate."""
        try:
            df = ak.fx_spot_quote()
            if df is None or df.empty:
                return None

            # Find USD/CNY row
            usd_row = df[df["货币对"].str.contains("美元", na=False)]
            if usd_row.empty:
                return None

            value = float(usd_row.iloc[0].get("买入价", 7.0))

            # Simple z-score (no historical readily available)
            # Assume normal range 6.8-7.4, center 7.1
            z_score = (value - 7.1) / 0.2
            z_score = -z_score  # Invert (weaker CNY = risk off)

            return CNMacroData(
                series_id="usd_cny",
                name="美元兑人民币",
                asof=datetime.now(),
                value=value,
                z_score=round(z_score, 2)
            )
        except Exception as e:
            logger.warning(f"USD/CNY fetch error: {e}")
            return None

    def _compute_z_score(self, value: float, historical: List[float]) -> Optional[float]:
        """Compute z-score from historical values."""
        if not historical or len(historical) < 10:
            return None

        try:
            mean = statistics.mean(historical)
            stdev = statistics.stdev(historical)
            if stdev == 0:
                return 0.0
            return round((value - mean) / stdev, 2)
        except Exception:
            return None

    def compute_mrs_cn(self, macro_data: List[CNMacroData]) -> float:
        """Compute MRS-CN from z-scores."""
        if not macro_data:
            return 0.0

        total_weight = 0.0
        weighted_sum = 0.0

        for data in macro_data:
            if data.z_score is None:
                continue

            config = self.series.get(data.series_id, {})
            weight = config.get("weight", 0.2)

            weighted_sum += data.z_score * weight
            total_weight += weight

        if total_weight == 0:
            return 0.0

        mrs = weighted_sum / total_weight
        mrs = max(-1.0, min(1.0, mrs))

        return round(mrs, 2)

    def interpret_mrs_cn(self, mrs: float) -> str:
        """Get human-readable interpretation of MRS-CN."""
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


class CNFlowFetcher:
    """Fetches northbound capital flow data."""

    def fetch(self) -> Optional[CNFlowData]:
        """Fetch latest northbound flow data."""
        if not AKSHARE_AVAILABLE:
            return None

        try:
            df = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
            if df is None or df.empty:
                return None

            latest = df.iloc[-1]

            return CNFlowData(
                asof=datetime.now(),
                northbound_net=float(latest.get("净买入", 0)),
                northbound_buy=float(latest.get("买入", 0)),
                northbound_sell=float(latest.get("卖出", 0))
            )
        except Exception as e:
            logger.warning(f"Northbound flow fetch error: {e}")
            return None


# =============================================================================
# Bucket Signal Aggregator
# =============================================================================

@dataclass
class CNBucketFinancialSignal:
    """Financial signals for a single CN bucket."""
    bucket_id: str
    bucket_name: str

    # Public Market Signal China
    pms_cn: Optional[float] = None
    pms_cn_coverage: Optional[Dict[str, Any]] = None
    pms_cn_contributors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bucket_id": self.bucket_id,
            "bucket_name": self.bucket_name,
            "pms_cn": self.pms_cn,
            "pms_cn_coverage": self.pms_cn_coverage,
            "pms_cn_contributors": self.pms_cn_contributors,
            "pms_cn_contributors_text": [
                f"{c['ticker']} {c['change_7d_pct']:+.1f}%"
                for c in self.pms_cn_contributors[:3]
            ] if self.pms_cn_contributors else [],
        }


class CNBucketSignalAggregator:
    """Aggregates CN equity data into bucket-level signals."""

    def __init__(self):
        self.ticker_buckets = load_cn_ticker_buckets()
        self.bucket_names = load_cn_bucket_names()

    def compute_bucket_signals(
        self,
        equity_data: List[CNEquityData]
    ) -> Dict[str, CNBucketFinancialSignal]:
        """Compute PMS-CN signals per bucket."""
        signals: Dict[str, CNBucketFinancialSignal] = {}

        # Initialize all buckets
        for bucket_id in self.ticker_buckets.keys():
            signals[bucket_id] = CNBucketFinancialSignal(
                bucket_id=bucket_id,
                bucket_name=self.bucket_names.get(bucket_id, bucket_id)
            )

        if not equity_data:
            return signals

        # Group equities by bucket
        bucket_equities: Dict[str, List[CNEquityData]] = {
            bucket_id: [] for bucket_id in self.ticker_buckets.keys()
        }
        equity_by_ticker = {e.ticker: e for e in equity_data}

        for bucket_id, tickers in self.ticker_buckets.items():
            for ticker in tickers:
                if ticker in equity_by_ticker:
                    bucket_equities[bucket_id].append(equity_by_ticker[ticker])

        # Collect all 7d changes for percentile calculation
        all_changes = []
        for equities in bucket_equities.values():
            if equities:
                avg_change = sum(e.change_7d_pct for e in equities) / len(equities)
                all_changes.append(avg_change)

        if not all_changes:
            return signals

        # Compute PMS-CN per bucket
        for bucket_id, equities in bucket_equities.items():
            if not equities:
                continue

            avg_change = sum(e.change_7d_pct for e in equities) / len(equities)
            pms_cn = self._to_percentile(avg_change, all_changes)

            # Coverage info
            expected_tickers = self.ticker_buckets.get(bucket_id, [])
            present_tickers = [e.ticker for e in equities]
            missing_tickers = [t for t in expected_tickers if t not in present_tickers]

            # Contributors
            contributors = sorted(
                [{"ticker": e.ticker, "name": e.name, "change_7d_pct": e.change_7d_pct,
                  "weight": 1.0/len(equities), "contribution": e.change_7d_pct/len(equities)}
                 for e in equities],
                key=lambda x: abs(x["change_7d_pct"]),
                reverse=True
            )

            signals[bucket_id].pms_cn = pms_cn
            signals[bucket_id].pms_cn_coverage = {
                "tickers_present": len(present_tickers),
                "tickers_total": len(expected_tickers),
                "missing": missing_tickers
            }
            signals[bucket_id].pms_cn_contributors = contributors

        return signals

    def _to_percentile(self, value: float, all_values: List[float]) -> float:
        """Convert value to percentile within list."""
        if not all_values:
            return 50.0

        sorted_values = sorted(all_values)
        n = len(sorted_values)

        # Count values less than current
        count_less = sum(1 for v in sorted_values if v < value)

        percentile = (count_less / n) * 100
        return round(percentile, 1)


# =============================================================================
# Output Generator
# =============================================================================

@dataclass
class CNFinancialSignalsOutput:
    """Complete CN financial signals output."""
    date: str
    generated_at: str

    # Quality tracking
    quality: Dict[str, Any]

    # Source status
    sources: Dict[str, Any]

    # Raw data
    raw_equities: List[Dict[str, Any]]
    raw_macro: List[Dict[str, Any]]
    raw_flow: Optional[Dict[str, Any]]

    # Aggregated signals
    mrs_cn: float
    mrs_cn_interpretation: str
    bucket_signals: Dict[str, Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": {"name": "financial_signals_cn", "version": "1.0"},
            "date": self.date,
            "generated_at": self.generated_at,
            "quality": self.quality,
            "sources": self.sources,
            "raw": {
                "equities": self.raw_equities,
                "macro": self.raw_macro,
                "flow": self.raw_flow,
            },
            "macro_regime_cn": {
                "mrs_cn": self.mrs_cn,
                "interpretation": self.mrs_cn_interpretation,
            },
            "bucket_signals": self.bucket_signals,
        }


def generate_cn_financial_signals(
    output_dir: Path,
    target_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Generate CN financial signals and save to JSON.

    Args:
        output_dir: Directory to save output JSON
        target_date: Target date (default: today)

    Returns:
        Dict with generated signals
    """
    if target_date is None:
        target_date = date.today()

    logger.info(f"Generating CN financial signals for {target_date}")

    warnings = []

    # Fetch equity data
    equity_fetcher = CNEquityFetcher()
    equity_data = equity_fetcher.fetch()

    expected_tickers = len(get_all_cn_tickers())
    if len(equity_data) < expected_tickers * 0.8:
        warnings.append(f"Only {len(equity_data)}/{expected_tickers} equities fetched")

    # Fetch macro data
    macro_fetcher = CNMacroFetcher()
    macro_data = macro_fetcher.fetch()

    # Compute MRS-CN
    mrs_cn = macro_fetcher.compute_mrs_cn(macro_data)
    mrs_cn_interpretation = macro_fetcher.interpret_mrs_cn(mrs_cn)

    # Fetch flow data
    flow_fetcher = CNFlowFetcher()
    flow_data = flow_fetcher.fetch()

    # Compute bucket signals
    aggregator = CNBucketSignalAggregator()
    bucket_signals = aggregator.compute_bucket_signals(equity_data)

    # Build output
    output = CNFinancialSignalsOutput(
        date=target_date.strftime("%Y-%m-%d"),
        generated_at=datetime.now().isoformat(),
        quality={
            "overall_status": "ok" if not warnings else "degraded",
            "warnings": warnings
        },
        sources={
            "akshare": {
                "status": "ok" if AKSHARE_AVAILABLE else "unavailable",
                "ashare_fetched": len([e for e in equity_data if e.market == "A"]),
            },
            "yfinance": {
                "status": "ok" if YFINANCE_AVAILABLE else "unavailable",
                "hk_fetched": len([e for e in equity_data if e.market == "HK"]),
            },
        },
        raw_equities=[e.to_dict() for e in equity_data],
        raw_macro=[m.to_dict() for m in macro_data],
        raw_flow=flow_data.to_dict() if flow_data else None,
        mrs_cn=mrs_cn,
        mrs_cn_interpretation=mrs_cn_interpretation,
        bucket_signals={k: v.to_dict() for k, v in bucket_signals.items()}
    )

    # Save to file
    output_file = output_dir / f"financial_signals_cn_{target_date.strftime('%Y-%m-%d')}.json"
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output.to_dict(), f, indent=2, ensure_ascii=False)

    logger.info(f"CN financial signals saved to {output_file}")

    return output.to_dict()


# =============================================================================
# Convenience Functions
# =============================================================================

def get_cn_bucket_financial_signals(target_date: Optional[date] = None) -> Dict[str, Dict]:
    """
    Load CN financial signals for bucket integration.

    Returns:
        Dict mapping bucket_id to signal data
    """
    signals_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    if target_date is None:
        target_date = date.today()

    signals_file = signals_dir / f"financial_signals_cn_{target_date.strftime('%Y-%m-%d')}.json"

    if not signals_file.exists():
        logger.warning(f"CN signals file not found: {signals_file}")
        return {}

    with open(signals_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    return data.get("bucket_signals", {})


if __name__ == "__main__":
    # Quick test
    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"
    result = generate_cn_financial_signals(output_dir)
    print(f"Generated {len(result.get('bucket_signals', {}))} bucket signals")
    print(f"MRS-CN: {result.get('macro_regime_cn', {}).get('mrs_cn')} ({result.get('macro_regime_cn', {}).get('interpretation')})")
