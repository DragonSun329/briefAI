"""
Correlation Engine

Analyzes correlations between news sentiment and stock price movements.
Tracks lead/lag relationships to identify predictive signals.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger

import numpy as np
import yfinance as yf


@dataclass
class CorrelationResult:
    """Result of correlation analysis between news and stock."""
    entity_id: str
    ticker: str
    correlation: float  # Pearson correlation coefficient
    p_value: Optional[float] = None
    sample_size: int = 0
    lag_days: int = 0  # Positive = news leads stock
    significance: str = "low"  # low, medium, high
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "ticker": self.ticker,
            "correlation": round(self.correlation, 4),
            "p_value": round(self.p_value, 4) if self.p_value else None,
            "sample_size": self.sample_size,
            "lag_days": self.lag_days,
            "significance": self.significance,
        }


@dataclass
class LeadLagResult:
    """Lead/lag relationship analysis result."""
    entity_id: str
    ticker: str
    optimal_lag: int  # Days that news leads/lags stock
    correlations_by_lag: Dict[int, float] = field(default_factory=dict)
    news_leads_stock: bool = True
    predictive_power: float = 0.0  # 0-1, how predictive is the lag
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "ticker": self.ticker,
            "optimal_lag": self.optimal_lag,
            "news_leads_stock": self.news_leads_stock,
            "predictive_power": round(self.predictive_power, 4),
            "correlations_by_lag": {k: round(v, 4) for k, v in self.correlations_by_lag.items()},
        }


class CorrelationEngine:
    """
    Correlates news sentiment with stock price movements.
    
    Key capabilities:
    - Pearson correlation between sentiment and returns
    - Lead/lag analysis (does news predict stock moves?)
    - Cross-asset correlation matrix for AI sector
    - Rolling correlation windows
    """
    
    def __init__(self, asset_mapping_path: Optional[Path] = None):
        """
        Initialize correlation engine.
        
        Args:
            asset_mapping_path: Path to asset_mapping.json
        """
        if asset_mapping_path is None:
            asset_mapping_path = Path(__file__).parent.parent / "data" / "asset_mapping.json"
        
        self.asset_mapping = self._load_asset_mapping(asset_mapping_path)
        self._price_cache: Dict[str, Dict[date, float]] = {}
        
        logger.info(f"CorrelationEngine initialized with {len(self.asset_mapping.get('entities', {}))} entities")
    
    def _load_asset_mapping(self, path: Path) -> Dict[str, Any]:
        """Load asset mapping configuration."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load asset mapping: {e}")
            return {"entities": {}}
    
    def get_ticker_for_entity(self, entity_id: str) -> Optional[str]:
        """Get primary ticker for an entity."""
        entity = self.asset_mapping.get("entities", {}).get(entity_id)
        if not entity:
            return None
        
        # Public companies have direct tickers
        if entity.get("status") == "public" and entity.get("tickers"):
            return entity["tickers"][0]
        
        # Private companies use proxy tickers
        if entity.get("proxy_tickers"):
            return entity["proxy_tickers"][0]
        
        return None
    
    def fetch_price_history(
        self,
        ticker: str,
        start_date: date,
        end_date: date,
        use_cache: bool = True
    ) -> Dict[date, float]:
        """
        Fetch historical prices for a ticker.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date
            end_date: End date
            use_cache: Whether to use cached data
            
        Returns:
            Dict mapping date to adjusted close price
        """
        cache_key = f"{ticker}_{start_date}_{end_date}"
        
        if use_cache and ticker in self._price_cache:
            return self._price_cache[ticker]
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(start=start_date, end=end_date)
            
            if hist.empty:
                logger.warning(f"No price data for {ticker}")
                return {}
            
            prices = {}
            for idx, row in hist.iterrows():
                dt = idx.date() if hasattr(idx, 'date') else idx
                prices[dt] = float(row['Close'])
            
            if use_cache:
                self._price_cache[ticker] = prices
            
            return prices
            
        except Exception as e:
            logger.error(f"Error fetching prices for {ticker}: {e}")
            return {}
    
    def calculate_returns(
        self,
        prices: Dict[date, float],
        period_days: int = 1
    ) -> Dict[date, float]:
        """
        Calculate returns from prices.
        
        Args:
            prices: Dict of date -> price
            period_days: Return period (1 = daily, 5 = weekly)
            
        Returns:
            Dict of date -> return (as percentage)
        """
        sorted_dates = sorted(prices.keys())
        returns = {}
        
        for i, dt in enumerate(sorted_dates):
            if i < period_days:
                continue
            
            prev_dt = sorted_dates[i - period_days]
            prev_price = prices[prev_dt]
            curr_price = prices[dt]
            
            if prev_price > 0:
                ret = ((curr_price - prev_price) / prev_price) * 100
                returns[dt] = ret
        
        return returns
    
    def correlate_sentiment_to_returns(
        self,
        sentiment_series: Dict[date, float],
        returns_series: Dict[date, float],
        lag_days: int = 0
    ) -> CorrelationResult:
        """
        Calculate correlation between sentiment and returns.
        
        Args:
            sentiment_series: Dict of date -> sentiment score (0-10 or -1 to 1)
            returns_series: Dict of date -> return (%)
            lag_days: Days to lag sentiment (positive = sentiment leads returns)
            
        Returns:
            CorrelationResult with correlation coefficient
        """
        # Align series with lag
        aligned_sentiment = []
        aligned_returns = []
        
        for dt, sentiment in sentiment_series.items():
            # Get return from lag_days later
            target_date = dt + timedelta(days=lag_days)
            
            # Find closest trading day
            for offset in range(4):  # Allow up to 3 days for weekends/holidays
                check_date = target_date + timedelta(days=offset)
                if check_date in returns_series:
                    aligned_sentiment.append(sentiment)
                    aligned_returns.append(returns_series[check_date])
                    break
        
        if len(aligned_sentiment) < 10:
            return CorrelationResult(
                entity_id="",
                ticker="",
                correlation=0.0,
                sample_size=len(aligned_sentiment),
                lag_days=lag_days,
                significance="low"
            )
        
        # Calculate Pearson correlation
        try:
            correlation = np.corrcoef(aligned_sentiment, aligned_returns)[0, 1]
            
            # Calculate p-value (simplified)
            n = len(aligned_sentiment)
            t_stat = correlation * np.sqrt(n - 2) / np.sqrt(1 - correlation**2) if abs(correlation) < 1 else 0
            # Approximate p-value
            p_value = 2 * (1 - min(0.9999, abs(t_stat) / np.sqrt(n)))
            
            # Determine significance
            if abs(correlation) > 0.5 and p_value < 0.05:
                significance = "high"
            elif abs(correlation) > 0.3 and p_value < 0.1:
                significance = "medium"
            else:
                significance = "low"
            
            return CorrelationResult(
                entity_id="",
                ticker="",
                correlation=float(correlation),
                p_value=float(p_value),
                sample_size=n,
                lag_days=lag_days,
                significance=significance
            )
            
        except Exception as e:
            logger.error(f"Correlation calculation error: {e}")
            return CorrelationResult(
                entity_id="",
                ticker="",
                correlation=0.0,
                sample_size=0,
                lag_days=lag_days,
                significance="low"
            )
    
    def find_optimal_lag(
        self,
        entity_id: str,
        sentiment_series: Dict[date, float],
        ticker: Optional[str] = None,
        max_lag_days: int = 10
    ) -> LeadLagResult:
        """
        Find optimal lead/lag relationship between news and stock.
        
        Tests lags from -max_lag to +max_lag to find where correlation peaks.
        
        Args:
            entity_id: Entity identifier
            sentiment_series: Dict of date -> sentiment
            ticker: Ticker to use (auto-detected if None)
            max_lag_days: Maximum lag to test
            
        Returns:
            LeadLagResult with optimal lag and correlation by lag
        """
        if ticker is None:
            ticker = self.get_ticker_for_entity(entity_id)
        
        if not ticker:
            logger.warning(f"No ticker found for {entity_id}")
            return LeadLagResult(
                entity_id=entity_id,
                ticker="",
                optimal_lag=0,
                predictive_power=0.0
            )
        
        # Get price data
        if sentiment_series:
            start_date = min(sentiment_series.keys()) - timedelta(days=max_lag_days + 5)
            end_date = max(sentiment_series.keys()) + timedelta(days=max_lag_days + 5)
        else:
            return LeadLagResult(
                entity_id=entity_id,
                ticker=ticker,
                optimal_lag=0,
                predictive_power=0.0
            )
        
        prices = self.fetch_price_history(ticker, start_date, end_date)
        returns = self.calculate_returns(prices)
        
        # Test different lags
        correlations_by_lag = {}
        
        for lag in range(-max_lag_days, max_lag_days + 1):
            result = self.correlate_sentiment_to_returns(
                sentiment_series, returns, lag_days=lag
            )
            correlations_by_lag[lag] = result.correlation
        
        # Find optimal lag
        optimal_lag = max(correlations_by_lag.keys(), key=lambda k: abs(correlations_by_lag[k]))
        optimal_corr = correlations_by_lag[optimal_lag]
        
        # Calculate predictive power
        # Higher if correlation at optimal lag is significantly better than lag=0
        baseline_corr = correlations_by_lag.get(0, 0)
        if abs(optimal_corr) > abs(baseline_corr):
            predictive_power = abs(optimal_corr) - abs(baseline_corr)
        else:
            predictive_power = 0.0
        
        return LeadLagResult(
            entity_id=entity_id,
            ticker=ticker,
            optimal_lag=optimal_lag,
            correlations_by_lag=correlations_by_lag,
            news_leads_stock=optimal_lag > 0,
            predictive_power=min(1.0, predictive_power)
        )
    
    def build_correlation_matrix(
        self,
        tickers: List[str],
        start_date: date,
        end_date: date,
        return_period: int = 5  # Weekly returns
    ) -> Dict[str, Dict[str, float]]:
        """
        Build cross-asset correlation matrix.
        
        Args:
            tickers: List of tickers to include
            start_date: Analysis start date
            end_date: Analysis end date
            return_period: Period for returns calculation
            
        Returns:
            Dict mapping ticker pair to correlation
        """
        # Fetch all price data
        all_returns: Dict[str, Dict[date, float]] = {}
        
        for ticker in tickers:
            prices = self.fetch_price_history(ticker, start_date, end_date)
            if prices:
                all_returns[ticker] = self.calculate_returns(prices, return_period)
        
        # Calculate pairwise correlations
        matrix: Dict[str, Dict[str, float]] = {}
        
        for ticker_a in all_returns:
            matrix[ticker_a] = {}
            for ticker_b in all_returns:
                if ticker_a == ticker_b:
                    matrix[ticker_a][ticker_b] = 1.0
                    continue
                
                # Align series
                common_dates = set(all_returns[ticker_a].keys()) & set(all_returns[ticker_b].keys())
                if len(common_dates) < 20:
                    matrix[ticker_a][ticker_b] = 0.0
                    continue
                
                returns_a = [all_returns[ticker_a][d] for d in sorted(common_dates)]
                returns_b = [all_returns[ticker_b][d] for d in sorted(common_dates)]
                
                try:
                    corr = np.corrcoef(returns_a, returns_b)[0, 1]
                    matrix[ticker_a][ticker_b] = round(float(corr), 4)
                except:
                    matrix[ticker_a][ticker_b] = 0.0
        
        return matrix
    
    def rolling_correlation(
        self,
        sentiment_series: Dict[date, float],
        returns_series: Dict[date, float],
        window_days: int = 30,
        lag_days: int = 1
    ) -> Dict[date, float]:
        """
        Calculate rolling correlation over time.
        
        Useful for detecting regime changes in the relationship.
        
        Args:
            sentiment_series: Sentiment time series
            returns_series: Returns time series
            window_days: Rolling window size
            lag_days: Lag between sentiment and returns
            
        Returns:
            Dict of date -> rolling correlation
        """
        sorted_dates = sorted(sentiment_series.keys())
        rolling_corr = {}
        
        for i, end_date in enumerate(sorted_dates):
            if i < window_days:
                continue
            
            window_start = i - window_days
            window_dates = sorted_dates[window_start:i]
            
            # Extract window data
            window_sentiment = {}
            for dt in window_dates:
                window_sentiment[dt] = sentiment_series[dt]
            
            # Calculate correlation for this window
            result = self.correlate_sentiment_to_returns(
                window_sentiment, returns_series, lag_days
            )
            rolling_corr[end_date] = result.correlation
        
        return rolling_corr
    
    def analyze_entity(
        self,
        entity_id: str,
        sentiment_history: Dict[date, float],
        lookback_days: int = 90
    ) -> Dict[str, Any]:
        """
        Complete correlation analysis for a single entity.
        
        Args:
            entity_id: Entity to analyze
            sentiment_history: Historical sentiment scores
            lookback_days: Days to analyze
            
        Returns:
            Dict with correlation metrics, lead/lag, and interpretation
        """
        ticker = self.get_ticker_for_entity(entity_id)
        
        if not ticker or not sentiment_history:
            return {
                "entity_id": entity_id,
                "ticker": None,
                "error": "No ticker or sentiment data",
                "has_signal": False
            }
        
        # Filter to lookback period
        cutoff = date.today() - timedelta(days=lookback_days)
        filtered_sentiment = {k: v for k, v in sentiment_history.items() if k >= cutoff}
        
        # Get returns
        start_date = min(filtered_sentiment.keys()) - timedelta(days=15)
        end_date = max(filtered_sentiment.keys()) + timedelta(days=15)
        
        prices = self.fetch_price_history(ticker, start_date, end_date)
        returns = self.calculate_returns(prices)
        
        # Basic correlation
        base_corr = self.correlate_sentiment_to_returns(filtered_sentiment, returns, lag_days=0)
        base_corr.entity_id = entity_id
        base_corr.ticker = ticker
        
        # Lead/lag analysis
        lead_lag = self.find_optimal_lag(entity_id, filtered_sentiment, ticker)
        
        # Interpretation
        interpretation = self._interpret_correlation(base_corr, lead_lag)
        
        return {
            "entity_id": entity_id,
            "ticker": ticker,
            "correlation": base_corr.to_dict(),
            "lead_lag": lead_lag.to_dict(),
            "interpretation": interpretation,
            "has_signal": base_corr.significance != "low" or lead_lag.predictive_power > 0.1,
            "analyzed_at": datetime.now().isoformat()
        }
    
    def _interpret_correlation(
        self,
        corr: CorrelationResult,
        lead_lag: LeadLagResult
    ) -> Dict[str, str]:
        """Generate human-readable interpretation of correlation results."""
        
        interpretation = {}
        
        # Correlation strength
        if abs(corr.correlation) > 0.5:
            interpretation["strength"] = "Strong correlation detected"
        elif abs(corr.correlation) > 0.3:
            interpretation["strength"] = "Moderate correlation detected"
        else:
            interpretation["strength"] = "Weak or no correlation"
        
        # Direction
        if corr.correlation > 0.3:
            interpretation["direction"] = "Positive news sentiment tends to precede positive returns"
        elif corr.correlation < -0.3:
            interpretation["direction"] = "News sentiment is contrarian indicator"
        else:
            interpretation["direction"] = "No clear directional relationship"
        
        # Lead/lag
        if lead_lag.optimal_lag > 0 and lead_lag.predictive_power > 0.1:
            interpretation["timing"] = f"News leads stock by ~{lead_lag.optimal_lag} days"
            interpretation["tradeable"] = "Potentially tradeable signal"
        elif lead_lag.optimal_lag < 0 and abs(lead_lag.correlations_by_lag.get(lead_lag.optimal_lag, 0)) > 0.3:
            interpretation["timing"] = f"Stock leads news by ~{abs(lead_lag.optimal_lag)} days"
            interpretation["tradeable"] = "News is reactive, not predictive"
        else:
            interpretation["timing"] = "No clear lead/lag relationship"
            interpretation["tradeable"] = "Not a timing signal"
        
        return interpretation


def create_ai_sector_correlation_matrix(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Create correlation matrix for AI sector stocks.
    
    Convenience function for sector analysis.
    """
    if end_date is None:
        end_date = date.today()
    if start_date is None:
        start_date = end_date - timedelta(days=365)
    
    # Top AI stocks
    ai_tickers = [
        "NVDA", "AMD", "MSFT", "GOOGL", "META", 
        "TSLA", "PLTR", "SNOW", "CRM", "ADBE",
        "NOW", "CRWD", "NET", "MDB", "DDOG"
    ]
    
    engine = CorrelationEngine()
    matrix = engine.build_correlation_matrix(ai_tickers, start_date, end_date)
    
    return {
        "tickers": ai_tickers,
        "correlation_matrix": matrix,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "generated_at": datetime.now().isoformat()
    }


if __name__ == "__main__":
    # Test correlation engine
    print("Testing Correlation Engine")
    print("=" * 50)
    
    engine = CorrelationEngine()
    
    # Test ticker lookup
    print("\nTicker lookups:")
    for entity in ["nvidia", "openai", "anthropic", "palantir"]:
        ticker = engine.get_ticker_for_entity(entity)
        print(f"  {entity} -> {ticker}")
    
    # Test correlation matrix
    print("\nBuilding AI sector correlation matrix...")
    result = create_ai_sector_correlation_matrix(
        start_date=date.today() - timedelta(days=90),
        end_date=date.today()
    )
    
    print(f"Matrix includes {len(result['tickers'])} tickers")
    
    # Show sample correlations
    print("\nSample correlations (NVDA):")
    nvda_corrs = result["correlation_matrix"].get("NVDA", {})
    for ticker, corr in list(nvda_corrs.items())[:5]:
        print(f"  NVDA vs {ticker}: {corr:.3f}")
