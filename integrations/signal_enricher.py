"""
Signal Enricher Module

Hooks into briefAI's signal flow to enrich signals with real market data.
Adds price-based validation scores and technical indicator overlays.

This module bridges briefAI's alternative data signals with real-time
market data for validation and enrichment.
"""

import asyncio
import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None
    logger.warning("yfinance not installed - install with: pip install yfinance")

try:
    import pandas_ta as ta
except ImportError:
    ta = None
    logger.warning("pandas-ta not installed - install with: pip install pandas-ta")


@dataclass
class EnrichedSignal:
    """A briefAI signal enriched with market data."""
    entity_id: str
    ticker: str
    
    # Original briefAI signal
    briefai_sentiment: float  # 0-10 scale
    briefai_momentum: str     # "bullish", "bearish", "neutral"
    briefai_confidence: float # 0-1
    
    # Market enrichment
    current_price: float
    price_change_1d: float
    price_change_5d: float
    volume_ratio: float  # Current vs 20-day avg
    
    # Technical overlay
    rsi_14: Optional[float] = None
    macd_signal: str = "neutral"
    trend_alignment: str = "unknown"  # "aligned", "divergent", "neutral"
    
    # Validation
    validation_score: float = 0.5  # 0-1, how well briefAI aligns with technicals
    validation_notes: List[str] = field(default_factory=list)
    
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "ticker": self.ticker,
            "briefai": {
                "sentiment": self.briefai_sentiment,
                "momentum": self.briefai_momentum,
                "confidence": self.briefai_confidence,
            },
            "market": {
                "current_price": self.current_price,
                "price_change_1d": round(self.price_change_1d, 4),
                "price_change_5d": round(self.price_change_5d, 4),
                "volume_ratio": round(self.volume_ratio, 2),
            },
            "technicals": {
                "rsi_14": round(self.rsi_14, 2) if self.rsi_14 else None,
                "macd_signal": self.macd_signal,
                "trend_alignment": self.trend_alignment,
            },
            "validation": {
                "score": round(self.validation_score, 3),
                "notes": self.validation_notes,
            },
            "timestamp": self.timestamp.isoformat(),
        }


class SignalEnricher:
    """
    Enriches briefAI signals with real market data.
    
    Takes entity signals from briefAI and adds:
    - Current price data
    - Technical indicators
    - Validation scores comparing sentiment to price action
    """
    
    def __init__(self, asset_mapping_path: Optional[Path] = None):
        """
        Initialize signal enricher.
        
        Args:
            asset_mapping_path: Path to entity-ticker mapping
        """
        if asset_mapping_path is None:
            asset_mapping_path = Path(__file__).parent.parent / "data" / "asset_mapping.json"
        
        self.asset_mapping = self._load_asset_mapping(asset_mapping_path)
        self._price_cache: Dict[str, Dict] = {}
        self._cache_expiry = 300  # 5 minutes
        
        logger.info(f"SignalEnricher initialized with {len(self.asset_mapping.get('entities', {}))} entities")
    
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
            # Try case-insensitive match
            for key, val in self.asset_mapping.get("entities", {}).items():
                if key.lower() == entity_id.lower():
                    entity = val
                    break
        
        if not entity:
            return None
        
        # Public companies have direct tickers
        if entity.get("status") == "public" and entity.get("tickers"):
            return entity["tickers"][0]
        
        # Private companies use proxy tickers
        if entity.get("proxy_tickers"):
            return entity["proxy_tickers"][0]
        
        return None
    
    def fetch_market_data(self, ticker: str, use_cache: bool = True) -> Dict[str, Any]:
        """
        Fetch current market data for a ticker.
        
        Returns dict with price, change, volume, and history.
        """
        if yf is None:
            logger.error("yfinance not available")
            return {}
        
        # Check cache
        cache_key = ticker
        if use_cache and cache_key in self._price_cache:
            cached = self._price_cache[cache_key]
            age = (datetime.now() - cached.get("fetched_at", datetime.min)).seconds
            if age < self._cache_expiry:
                return cached
        
        try:
            stock = yf.Ticker(ticker)
            
            # Get recent history for technical analysis
            hist = stock.history(period="3mo")
            
            if hist.empty:
                logger.warning(f"No data for {ticker}")
                return {}
            
            current_price = hist['Close'].iloc[-1]
            
            # Calculate changes
            if len(hist) >= 2:
                price_1d_ago = hist['Close'].iloc[-2]
                change_1d = (current_price - price_1d_ago) / price_1d_ago
            else:
                change_1d = 0.0
            
            if len(hist) >= 6:
                price_5d_ago = hist['Close'].iloc[-6]
                change_5d = (current_price - price_5d_ago) / price_5d_ago
            else:
                change_5d = 0.0
            
            # Volume ratio
            current_volume = hist['Volume'].iloc[-1]
            avg_volume_20d = hist['Volume'].tail(20).mean()
            volume_ratio = current_volume / avg_volume_20d if avg_volume_20d > 0 else 1.0
            
            result = {
                "ticker": ticker,
                "current_price": float(current_price),
                "change_1d": float(change_1d),
                "change_5d": float(change_5d),
                "volume_ratio": float(volume_ratio),
                "current_volume": int(current_volume),
                "history": hist,
                "fetched_at": datetime.now(),
            }
            
            self._price_cache[cache_key] = result
            return result
            
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {e}")
            return {}
    
    def calculate_technicals(self, hist) -> Dict[str, Any]:
        """
        Calculate technical indicators from price history.
        
        Uses pandas-ta if available, falls back to manual calculations.
        """
        if hist is None or len(hist) < 20:
            return {}
        
        close = hist['Close'].values
        high = hist['High'].values
        low = hist['Low'].values
        
        result = {}
        
        # RSI
        if ta is not None:
            try:
                rsi = ta.rsi(hist['Close'], length=14)
                result['rsi_14'] = float(rsi.iloc[-1]) if not rsi.empty and not np.isnan(rsi.iloc[-1]) else None
            except:
                result['rsi_14'] = self._manual_rsi(close, 14)
        else:
            result['rsi_14'] = self._manual_rsi(close, 14)
        
        # MACD
        if ta is not None:
            try:
                macd_df = ta.macd(hist['Close'], fast=12, slow=26, signal=9)
                if macd_df is not None and not macd_df.empty:
                    macd_line = macd_df.iloc[-1, 0]
                    signal_line = macd_df.iloc[-1, 2]
                    histogram = macd_df.iloc[-1, 1]
                    
                    result['macd'] = float(macd_line)
                    result['macd_signal'] = float(signal_line)
                    result['macd_histogram'] = float(histogram)
            except:
                pass
        
        # Bollinger Bands
        if ta is not None:
            try:
                bb = ta.bbands(hist['Close'], length=20, std=2)
                if bb is not None and not bb.empty:
                    result['bb_upper'] = float(bb.iloc[-1, 0])
                    result['bb_middle'] = float(bb.iloc[-1, 1])
                    result['bb_lower'] = float(bb.iloc[-1, 2])
            except:
                pass
        
        # SMAs
        result['sma_20'] = float(np.mean(close[-20:])) if len(close) >= 20 else None
        result['sma_50'] = float(np.mean(close[-50:])) if len(close) >= 50 else None
        
        # Trend direction
        if len(close) >= 20:
            recent_trend = close[-1] > close[-20]
            result['trend_20d'] = "up" if recent_trend else "down"
        
        return result
    
    def _manual_rsi(self, prices: np.ndarray, period: int = 14) -> Optional[float]:
        """Manual RSI calculation."""
        if len(prices) < period + 1:
            return None
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def interpret_macd_signal(self, technicals: Dict) -> str:
        """Interpret MACD as bullish/bearish/neutral."""
        histogram = technicals.get('macd_histogram')
        
        if histogram is None:
            return "neutral"
        
        if histogram > 0.5:
            return "bullish"
        elif histogram < -0.5:
            return "bearish"
        else:
            return "neutral"
    
    def calculate_alignment(
        self, 
        briefai_sentiment: float, 
        price_change: float, 
        rsi: Optional[float]
    ) -> Tuple[str, float, List[str]]:
        """
        Calculate alignment between briefAI signal and market action.
        
        Returns (alignment, score, notes)
        """
        notes = []
        score = 0.5  # Start neutral
        
        # Sentiment interpretation (0-10 scale, 5 = neutral)
        briefai_bullish = briefai_sentiment > 6.0
        briefai_bearish = briefai_sentiment < 4.0
        
        # Price action interpretation
        price_bullish = price_change > 0.01  # >1% up
        price_bearish = price_change < -0.01  # >1% down
        
        # Check alignment
        if briefai_bullish and price_bullish:
            alignment = "aligned"
            score = 0.7 + min(0.2, abs(price_change) * 5)
            notes.append("Bullish sentiment confirmed by price action")
        elif briefai_bearish and price_bearish:
            alignment = "aligned"
            score = 0.7 + min(0.2, abs(price_change) * 5)
            notes.append("Bearish sentiment confirmed by price action")
        elif briefai_bullish and price_bearish:
            alignment = "divergent"
            score = 0.3 - min(0.2, abs(price_change) * 5)
            notes.append("Bullish sentiment contradicted by price drop")
        elif briefai_bearish and price_bullish:
            alignment = "divergent"
            score = 0.3 - min(0.2, abs(price_change) * 5)
            notes.append("Bearish sentiment contradicted by price rally")
        else:
            alignment = "neutral"
            notes.append("Neutral conditions - no clear alignment")
        
        # RSI overlay
        if rsi is not None:
            if rsi > 70:
                notes.append(f"RSI overbought ({rsi:.1f}) - caution on bullish signals")
                if briefai_bullish:
                    score -= 0.1
            elif rsi < 30:
                notes.append(f"RSI oversold ({rsi:.1f}) - caution on bearish signals")
                if briefai_bearish:
                    score -= 0.1
        
        return alignment, max(0, min(1, score)), notes
    
    async def enrich_signal(
        self,
        entity_id: str,
        briefai_sentiment: float,
        briefai_momentum: str = "neutral",
        briefai_confidence: float = 0.5
    ) -> Optional[EnrichedSignal]:
        """
        Enrich a briefAI signal with market data.
        
        Args:
            entity_id: Entity identifier
            briefai_sentiment: briefAI sentiment score (0-10)
            briefai_momentum: briefAI momentum assessment
            briefai_confidence: briefAI confidence level
            
        Returns:
            EnrichedSignal with market data and validation
        """
        ticker = self.get_ticker_for_entity(entity_id)
        
        if not ticker:
            logger.warning(f"No ticker found for entity: {entity_id}")
            return None
        
        # Fetch market data
        market_data = self.fetch_market_data(ticker)
        
        if not market_data:
            logger.warning(f"Could not fetch market data for {ticker}")
            return None
        
        # Calculate technicals
        technicals = self.calculate_technicals(market_data.get('history'))
        
        # Calculate alignment
        alignment, score, notes = self.calculate_alignment(
            briefai_sentiment,
            market_data['change_1d'],
            technicals.get('rsi_14')
        )
        
        return EnrichedSignal(
            entity_id=entity_id,
            ticker=ticker,
            briefai_sentiment=briefai_sentiment,
            briefai_momentum=briefai_momentum,
            briefai_confidence=briefai_confidence,
            current_price=market_data['current_price'],
            price_change_1d=market_data['change_1d'],
            price_change_5d=market_data['change_5d'],
            volume_ratio=market_data['volume_ratio'],
            rsi_14=technicals.get('rsi_14'),
            macd_signal=self.interpret_macd_signal(technicals),
            trend_alignment=alignment,
            validation_score=score,
            validation_notes=notes,
        )
    
    async def enrich_batch(
        self,
        signals: List[Dict[str, Any]]
    ) -> List[EnrichedSignal]:
        """
        Enrich multiple signals.
        
        Args:
            signals: List of dicts with entity_id, sentiment, momentum, confidence
            
        Returns:
            List of EnrichedSignals
        """
        results = []
        
        for sig in signals:
            enriched = await self.enrich_signal(
                entity_id=sig.get('entity_id', ''),
                briefai_sentiment=sig.get('sentiment', 5.0),
                briefai_momentum=sig.get('momentum', 'neutral'),
                briefai_confidence=sig.get('confidence', 0.5)
            )
            if enriched:
                results.append(enriched)
        
        return results
    
    def rank_by_validation(
        self,
        enriched_signals: List[EnrichedSignal],
        min_score: float = 0.0
    ) -> List[EnrichedSignal]:
        """
        Rank enriched signals by validation score.
        
        Args:
            enriched_signals: List of enriched signals
            min_score: Minimum validation score to include
            
        Returns:
            Sorted list by validation score (descending)
        """
        filtered = [s for s in enriched_signals if s.validation_score >= min_score]
        return sorted(filtered, key=lambda x: x.validation_score, reverse=True)
    
    def generate_summary(
        self,
        enriched_signals: List[EnrichedSignal]
    ) -> Dict[str, Any]:
        """
        Generate summary report of enriched signals.
        """
        if not enriched_signals:
            return {"error": "No signals to summarize"}
        
        aligned = [s for s in enriched_signals if s.trend_alignment == "aligned"]
        divergent = [s for s in enriched_signals if s.trend_alignment == "divergent"]
        
        avg_validation = sum(s.validation_score for s in enriched_signals) / len(enriched_signals)
        
        # Top validated signals
        top_signals = self.rank_by_validation(enriched_signals)[:5]
        
        return {
            "total_signals": len(enriched_signals),
            "aligned_count": len(aligned),
            "divergent_count": len(divergent),
            "avg_validation_score": round(avg_validation, 3),
            "top_validated": [
                {
                    "entity": s.entity_id,
                    "ticker": s.ticker,
                    "validation": s.validation_score,
                    "sentiment": s.briefai_sentiment,
                    "price_change_1d": f"{s.price_change_1d*100:.2f}%"
                }
                for s in top_signals
            ],
            "divergent_signals": [
                {
                    "entity": s.entity_id,
                    "ticker": s.ticker,
                    "sentiment": s.briefai_sentiment,
                    "price_action": f"{s.price_change_1d*100:.2f}%",
                    "notes": s.validation_notes
                }
                for s in divergent[:3]
            ],
            "generated_at": datetime.now().isoformat()
        }


# Convenience function for quick enrichment
async def enrich_entity(
    entity_id: str,
    sentiment: float = 5.0,
    momentum: str = "neutral",
    confidence: float = 0.5
) -> Optional[Dict[str, Any]]:
    """
    Quick function to enrich a single entity signal.
    
    Returns dict representation of enriched signal.
    """
    enricher = SignalEnricher()
    signal = await enricher.enrich_signal(entity_id, sentiment, momentum, confidence)
    return signal.to_dict() if signal else None


if __name__ == "__main__":
    async def main():
        print("Testing Signal Enricher")
        print("=" * 60)
        
        enricher = SignalEnricher()
        
        # Test with AI companies
        test_signals = [
            {"entity_id": "nvidia", "sentiment": 7.5, "momentum": "bullish", "confidence": 0.8},
            {"entity_id": "microsoft", "sentiment": 6.0, "momentum": "neutral", "confidence": 0.6},
            {"entity_id": "meta", "sentiment": 4.5, "momentum": "bearish", "confidence": 0.7},
            {"entity_id": "amd", "sentiment": 6.5, "momentum": "bullish", "confidence": 0.65},
            {"entity_id": "google", "sentiment": 5.5, "momentum": "neutral", "confidence": 0.5},
        ]
        
        print("\nEnriching signals for AI companies...")
        enriched = await enricher.enrich_batch(test_signals)
        
        for signal in enriched:
            print(f"\n{signal.entity_id.upper()} ({signal.ticker})")
            print(f"  briefAI sentiment: {signal.briefai_sentiment}")
            print(f"  Current price: ${signal.current_price:.2f}")
            print(f"  1D change: {signal.price_change_1d*100:.2f}%")
            print(f"  RSI(14): {signal.rsi_14:.1f}" if signal.rsi_14 else "  RSI: N/A")
            print(f"  Alignment: {signal.trend_alignment}")
            print(f"  Validation: {signal.validation_score:.2f}")
            for note in signal.validation_notes:
                print(f"    - {note}")
        
        # Generate summary
        print("\n" + "=" * 60)
        print("SUMMARY REPORT")
        print("=" * 60)
        summary = enricher.generate_summary(enriched)
        print(json.dumps(summary, indent=2))
    
    asyncio.run(main())
