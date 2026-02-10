#!/usr/bin/env python3
"""
Real-Time Validation Pipeline

Validates briefAI entity signals against real-time market data.
Compares sentiment signals with actual price movement and technical indicators.

Usage:
    python scripts/realtime_validator.py --entities "NVDA,MSFT,GOOGL"
    python scripts/realtime_validator.py --all-ai
    python scripts/realtime_validator.py --entity nvidia --detailed
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from loguru import logger

import numpy as np

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import yfinance as yf
except ImportError:
    print("ERROR: yfinance required. Install with: pip install yfinance")
    sys.exit(1)

try:
    import pandas_ta as ta
except ImportError:
    ta = None
    print("WARNING: pandas-ta not available, using manual indicator calculations")

# Import briefAI modules
try:
    from integrations.signal_enricher import SignalEnricher, EnrichedSignal
    from integrations.economic_context import EconomicContextProvider, MarketRegime
    from utils.correlation_engine import CorrelationEngine
    from utils.momentum_signals import MomentumCalculator
except ImportError as e:
    print(f"WARNING: Could not import briefAI modules: {e}")
    SignalEnricher = None


@dataclass
class ValidationResult:
    """Result of validating a single entity signal."""
    entity_id: str
    ticker: str
    timestamp: datetime
    
    # briefAI signal
    briefai_sentiment: float  # 0-10
    briefai_momentum: str
    briefai_confidence: float
    
    # Market reality
    current_price: float
    price_change_1d: float
    price_change_5d: float
    price_change_20d: float
    
    # Technical indicators
    rsi_14: Optional[float] = None
    macd_histogram: Optional[float] = None
    bb_position: Optional[str] = None  # "upper", "middle", "lower"
    sma_20_distance: Optional[float] = None  # % from SMA20
    
    # Validation scores
    direction_aligned: bool = False
    magnitude_aligned: bool = False
    technical_confirmed: bool = False
    
    # Overall validation
    validation_score: float = 0.0  # 0-1
    validation_grade: str = "F"    # A, B, C, D, F
    validation_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "ticker": self.ticker,
            "timestamp": self.timestamp.isoformat(),
            "briefai_signal": {
                "sentiment": float(self.briefai_sentiment),
                "momentum": self.briefai_momentum,
                "confidence": float(self.briefai_confidence),
            },
            "market_reality": {
                "current_price": float(self.current_price),
                "price_change_1d": f"{self.price_change_1d*100:.2f}%",
                "price_change_5d": f"{self.price_change_5d*100:.2f}%",
                "price_change_20d": f"{self.price_change_20d*100:.2f}%",
            },
            "technicals": {
                "rsi_14": round(float(self.rsi_14), 2) if self.rsi_14 else None,
                "macd_histogram": round(float(self.macd_histogram), 4) if self.macd_histogram else None,
                "bollinger_position": self.bb_position,
                "sma_20_distance": f"{self.sma_20_distance*100:.2f}%" if self.sma_20_distance else None,
            },
            "validation": {
                "direction_aligned": bool(self.direction_aligned),
                "magnitude_aligned": bool(self.magnitude_aligned),
                "technical_confirmed": bool(self.technical_confirmed),
                "score": round(float(self.validation_score), 3),
                "grade": self.validation_grade,
                "notes": self.validation_notes,
            }
        }


class RealtimeValidator:
    """
    Validates briefAI signals against real-time market data.
    
    This pipeline:
    1. Takes a briefAI entity signal
    2. Fetches current price data
    3. Calculates native technical indicators
    4. Compares sentiment with price movement
    5. Logs validation results
    """
    
    # Default AI companies for testing
    DEFAULT_AI_COMPANIES = [
        ("nvidia", "NVDA"),
        ("microsoft", "MSFT"),
        ("google", "GOOGL"),
        ("meta", "META"),
        ("amd", "AMD"),
    ]
    
    def __init__(self, asset_mapping_path: Optional[Path] = None):
        """Initialize validator."""
        if asset_mapping_path is None:
            asset_mapping_path = Path(__file__).parent.parent / "data" / "asset_mapping.json"
        
        self.asset_mapping = self._load_asset_mapping(asset_mapping_path)
        self.results_dir = Path(__file__).parent.parent / "data" / "validation_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("RealtimeValidator initialized")
    
    def _load_asset_mapping(self, path: Path) -> Dict[str, Any]:
        """Load asset mapping configuration."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load asset mapping: {e}")
            return {"entities": {}}
    
    def get_ticker_for_entity(self, entity_id: str) -> Optional[str]:
        """Get primary ticker for an entity.
        
        Supports lookup by:
        - entity key (e.g., "nvidia")
        - ticker symbol (e.g., "NVDA")
        - company name (e.g., "NVIDIA")
        """
        entities = self.asset_mapping.get("entities", {})
        
        # Direct key lookup
        entity = entities.get(entity_id)
        if not entity:
            # Case-insensitive key match
            for key, val in entities.items():
                if key.lower() == entity_id.lower():
                    entity = val
                    break
        
        # Reverse lookup by ticker symbol (e.g., "NVDA" -> nvidia entity)
        # Prioritize primary tickers over proxy tickers
        if not entity:
            entity_id_upper = entity_id.upper()
            proxy_match = None
            for key, val in entities.items():
                if entity_id_upper in val.get("tickers", []):
                    entity = val
                    break
                if proxy_match is None and entity_id_upper in val.get("proxy_tickers", []):
                    proxy_match = val
            if not entity and proxy_match:
                entity = proxy_match
        
        # Lookup by company name (e.g., "NVIDIA")
        if not entity:
            for key, val in entities.items():
                if val.get("name", "").lower() == entity_id.lower():
                    entity = val
                    break
        
        if not entity:
            return None
        
        if entity.get("status") == "public" and entity.get("tickers"):
            return entity["tickers"][0]
        
        if entity.get("proxy_tickers"):
            return entity["proxy_tickers"][0]
        
        return None
    
    def fetch_price_data(self, ticker: str, period: str = "3mo") -> Dict[str, Any]:
        """Fetch price data from Yahoo Finance."""
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            
            if hist.empty:
                logger.warning(f"No data for {ticker}")
                return {}
            
            current_price = hist['Close'].iloc[-1]
            
            # Calculate price changes
            changes = {}
            for days, label in [(1, "1d"), (5, "5d"), (20, "20d")]:
                if len(hist) > days:
                    past_price = hist['Close'].iloc[-(days+1)]
                    changes[label] = (current_price - past_price) / past_price
                else:
                    changes[label] = 0.0
            
            return {
                "ticker": ticker,
                "current_price": float(current_price),
                "changes": changes,
                "history": hist,
                "volume_current": int(hist['Volume'].iloc[-1]),
                "volume_avg_20": float(hist['Volume'].tail(20).mean()),
            }
            
        except Exception as e:
            logger.error(f"Error fetching {ticker}: {e}")
            return {}
    
    def calculate_technicals(self, hist) -> Dict[str, Any]:
        """Calculate technical indicators."""
        if hist is None or len(hist) < 20:
            return {}
        
        close = hist['Close']
        high = hist['High']
        low = hist['Low']
        
        result = {}
        
        # RSI (14)
        if ta is not None:
            try:
                rsi = ta.rsi(close, length=14)
                result['rsi_14'] = float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else None
            except:
                result['rsi_14'] = self._manual_rsi(close.values, 14)
        else:
            result['rsi_14'] = self._manual_rsi(close.values, 14)
        
        # MACD
        if ta is not None:
            try:
                macd_df = ta.macd(close, fast=12, slow=26, signal=9)
                if macd_df is not None and not macd_df.empty:
                    result['macd_histogram'] = float(macd_df.iloc[-1, 1])
                    result['macd_line'] = float(macd_df.iloc[-1, 0])
            except:
                pass
        
        # Bollinger Bands
        if ta is not None:
            try:
                bb = ta.bbands(close, length=20, std=2)
                if bb is not None and not bb.empty:
                    upper = bb.iloc[-1, 0]
                    middle = bb.iloc[-1, 1]
                    lower = bb.iloc[-1, 2]
                    current = close.iloc[-1]
                    
                    if current > upper:
                        result['bb_position'] = "above_upper"
                    elif current > middle:
                        result['bb_position'] = "upper_half"
                    elif current > lower:
                        result['bb_position'] = "lower_half"
                    else:
                        result['bb_position'] = "below_lower"
            except:
                pass
        
        # SMA 20 distance
        sma_20 = close.tail(20).mean()
        current = close.iloc[-1]
        result['sma_20'] = float(sma_20)
        result['sma_20_distance'] = (current - sma_20) / sma_20
        
        # SMA 50
        if len(close) >= 50:
            result['sma_50'] = float(close.tail(50).mean())
        
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
    
    def generate_mock_briefai_signal(
        self, 
        entity_id: str,
        price_change_5d: float
    ) -> Dict[str, Any]:
        """
        Generate mock briefAI signal for testing.
        
        In production, this would come from the actual briefAI pipeline.
        Here we generate synthetic signals to demonstrate validation.
        """
        # Generate somewhat realistic signal
        # In practice, these would come from actual sentiment analysis
        
        # Base sentiment on recent price action with some noise
        base_sentiment = 5.0 + (price_change_5d * 30)  # Scale price change
        noise = np.random.normal(0, 1)  # Add randomness
        sentiment = max(1.0, min(10.0, base_sentiment + noise))
        
        # Momentum based on sentiment
        if sentiment > 6.5:
            momentum = "bullish"
        elif sentiment < 3.5:
            momentum = "bearish"
        else:
            momentum = "neutral"
        
        # Confidence varies
        confidence = 0.5 + np.random.uniform(0, 0.4)
        
        return {
            "entity_id": entity_id,
            "sentiment": sentiment,
            "momentum": momentum,
            "confidence": confidence,
        }
    
    def validate_signal(
        self,
        entity_id: str,
        briefai_sentiment: float,
        briefai_momentum: str,
        briefai_confidence: float,
        ticker: Optional[str] = None
    ) -> Optional[ValidationResult]:
        """
        Validate a single briefAI signal against market data.
        
        Args:
            entity_id: Entity identifier
            briefai_sentiment: briefAI sentiment score (0-10)
            briefai_momentum: briefAI momentum ("bullish", "bearish", "neutral")
            briefai_confidence: briefAI confidence level
            ticker: Optional ticker override
            
        Returns:
            ValidationResult with detailed validation
        """
        if ticker is None:
            ticker = self.get_ticker_for_entity(entity_id)
        
        if not ticker:
            logger.warning(f"No ticker found for {entity_id}")
            return None
        
        # Fetch market data
        market_data = self.fetch_price_data(ticker)
        if not market_data:
            return None
        
        # Calculate technicals
        technicals = self.calculate_technicals(market_data.get('history'))
        
        # Create result
        result = ValidationResult(
            entity_id=entity_id,
            ticker=ticker,
            timestamp=datetime.now(),
            briefai_sentiment=briefai_sentiment,
            briefai_momentum=briefai_momentum,
            briefai_confidence=briefai_confidence,
            current_price=market_data['current_price'],
            price_change_1d=market_data['changes']['1d'],
            price_change_5d=market_data['changes']['5d'],
            price_change_20d=market_data['changes']['20d'],
            rsi_14=technicals.get('rsi_14'),
            macd_histogram=technicals.get('macd_histogram'),
            bb_position=technicals.get('bb_position'),
            sma_20_distance=technicals.get('sma_20_distance'),
        )
        
        # Validate direction alignment
        result = self._validate_direction(result)
        
        # Validate magnitude alignment
        result = self._validate_magnitude(result)
        
        # Check technical confirmation
        result = self._validate_technicals(result)
        
        # Calculate overall score
        result = self._calculate_score(result)
        
        return result
    
    def _validate_direction(self, result: ValidationResult) -> ValidationResult:
        """Check if briefAI direction matches price direction."""
        # briefAI interpretation
        briefai_bullish = result.briefai_sentiment > 6.0 or result.briefai_momentum == "bullish"
        briefai_bearish = result.briefai_sentiment < 4.0 or result.briefai_momentum == "bearish"
        
        # Price interpretation (use 5d for more stable signal)
        price_bullish = result.price_change_5d > 0.01
        price_bearish = result.price_change_5d < -0.01
        
        # Check alignment
        if (briefai_bullish and price_bullish) or (briefai_bearish and price_bearish):
            result.direction_aligned = True
            result.validation_notes.append("Direction aligned with price action")
        elif (briefai_bullish and price_bearish):
            result.validation_notes.append("DIVERGENCE: Bullish signal but price down")
        elif (briefai_bearish and price_bullish):
            result.validation_notes.append("DIVERGENCE: Bearish signal but price up")
        else:
            result.validation_notes.append("Neutral conditions")
        
        return result
    
    def _validate_magnitude(self, result: ValidationResult) -> ValidationResult:
        """Check if signal strength matches price magnitude."""
        # Signal strength (distance from neutral 5.0)
        signal_strength = abs(result.briefai_sentiment - 5.0) / 5.0
        
        # Price magnitude (use absolute value)
        price_magnitude = abs(result.price_change_5d)
        
        # Rough alignment check
        # Strong signal (>0.5 strength) should correspond to significant move (>2%)
        # Weak signal (<0.2 strength) should correspond to small move (<1%)
        
        if signal_strength > 0.5 and price_magnitude > 0.02:
            result.magnitude_aligned = True
            result.validation_notes.append("Strong signal matched by significant price move")
        elif signal_strength < 0.2 and price_magnitude < 0.01:
            result.magnitude_aligned = True
            result.validation_notes.append("Weak signal matched by small price move")
        elif signal_strength > 0.5 and price_magnitude < 0.01:
            result.validation_notes.append("Strong signal but minimal price action")
        elif signal_strength < 0.2 and price_magnitude > 0.03:
            result.validation_notes.append("Weak signal but significant price move")
        else:
            # Middle ground - partial alignment
            result.magnitude_aligned = abs(signal_strength - price_magnitude * 10) < 0.3
        
        return result
    
    def _validate_technicals(self, result: ValidationResult) -> ValidationResult:
        """Check if technicals confirm the signal."""
        confirmations = 0
        total_checks = 0
        
        briefai_bullish = result.briefai_sentiment > 5.5
        
        # RSI check
        if result.rsi_14 is not None:
            total_checks += 1
            if briefai_bullish and result.rsi_14 < 70:  # Not overbought
                confirmations += 1
            elif not briefai_bullish and result.rsi_14 > 30:  # Not oversold
                confirmations += 1
            
            # Add RSI note
            if result.rsi_14 > 70:
                result.validation_notes.append(f"RSI overbought ({result.rsi_14:.1f})")
            elif result.rsi_14 < 30:
                result.validation_notes.append(f"RSI oversold ({result.rsi_14:.1f})")
        
        # MACD check
        if result.macd_histogram is not None:
            total_checks += 1
            if briefai_bullish and result.macd_histogram > 0:
                confirmations += 1
            elif not briefai_bullish and result.macd_histogram < 0:
                confirmations += 1
        
        # Bollinger position
        if result.bb_position:
            total_checks += 1
            if briefai_bullish and result.bb_position in ["lower_half", "below_lower"]:
                confirmations += 1  # Room to run
            elif not briefai_bullish and result.bb_position in ["upper_half", "above_upper"]:
                confirmations += 1  # Room to fall
        
        # SMA distance
        if result.sma_20_distance is not None:
            total_checks += 1
            if briefai_bullish and result.sma_20_distance > 0:
                confirmations += 1  # Above SMA is bullish
            elif not briefai_bullish and result.sma_20_distance < 0:
                confirmations += 1  # Below SMA is bearish
        
        result.technical_confirmed = total_checks > 0 and (confirmations / total_checks) > 0.5
        
        if result.technical_confirmed:
            result.validation_notes.append(f"Technical confirmation ({confirmations}/{total_checks})")
        
        return result
    
    def _calculate_score(self, result: ValidationResult) -> ValidationResult:
        """Calculate overall validation score and grade."""
        score = 0.0
        
        # Direction alignment (40%)
        if result.direction_aligned:
            score += 0.4
        
        # Magnitude alignment (30%)
        if result.magnitude_aligned:
            score += 0.3
        
        # Technical confirmation (30%)
        if result.technical_confirmed:
            score += 0.3
        
        # Confidence modifier
        score *= (0.5 + result.briefai_confidence * 0.5)
        
        result.validation_score = min(1.0, score)
        
        # Grade
        if result.validation_score >= 0.8:
            result.validation_grade = "A"
        elif result.validation_score >= 0.65:
            result.validation_grade = "B"
        elif result.validation_score >= 0.5:
            result.validation_grade = "C"
        elif result.validation_score >= 0.35:
            result.validation_grade = "D"
        else:
            result.validation_grade = "F"
        
        return result
    
    def get_real_briefai_sentiment(self, entity_id: str) -> Optional[Dict[str, Any]]:
        """
        Get REAL sentiment from briefAI database, not mock data.
        Reads from signal_observations table.
        
        FIXED:
        - Use exact entity name match or alias lookup (no fuzzy LIKE)
        - Filter by category='media' to get actual sentiment scores
        - Filter raw_value to 0-10 range (sentiment scores, not GitHub stars)
        """
        import sqlite3
        db_path = Path(__file__).parent.parent / "data" / "signals.db"
        
        if not db_path.exists():
            logger.warning(f"Database not found: {db_path}")
            return None
        
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        try:
            # FIXED: Map common names to exact entity names
            entity_name_map = {
                'nvidia': 'NVIDIA',
                'nvda': 'NVIDIA',
                'meta': 'Meta',
                'facebook': 'Meta',
                'google': 'Google/Alphabet',
                'googl': 'Google/Alphabet',
                'alphabet': 'Google/Alphabet',
                'microsoft': 'Microsoft',
                'msft': 'Microsoft',
                'amd': 'AMD',
                'openai': 'OpenAI',
                'anthropic': 'Anthropic',
                'amazon': 'Amazon',
                'amzn': 'Amazon',
                'apple': 'Apple',
                'aapl': 'Apple',
                'tesla': 'Tesla',
                'tsla': 'Tesla',
            }
            
            # Get canonical name
            canonical_name = entity_name_map.get(entity_id.lower(), entity_id)
            
            # FIXED: Use exact name match and filter by media category with sentiment-range raw_values
            c.execute("""
                SELECT so.raw_value, so.observed_at, so.category, e.name
                FROM signal_observations so
                JOIN entities e ON so.entity_id = e.id
                WHERE (LOWER(e.name) = LOWER(?) OR e.aliases LIKE ?)
                  AND so.observed_at > datetime('now', '-7 days')
                  AND so.raw_value IS NOT NULL
                  AND so.raw_value >= 0 AND so.raw_value <= 10
                  AND so.category = 'media'
                ORDER BY so.observed_at DESC
                LIMIT 50
            """, (canonical_name, f'%{entity_id}%'))
            
            rows = c.fetchall()
            
            if not rows:
                # Fallback: try with partial match but strict filters
                logger.debug(f"No exact match for {entity_id}, trying broader search...")
                c.execute("""
                    SELECT so.raw_value, so.observed_at, so.category, e.name
                    FROM signal_observations so
                    JOIN entities e ON so.entity_id = e.id
                    WHERE LOWER(e.name) LIKE ?
                      AND so.observed_at > datetime('now', '-7 days')
                      AND so.raw_value IS NOT NULL
                      AND so.raw_value >= 0 AND so.raw_value <= 10
                      AND so.category = 'media'
                    ORDER BY so.observed_at DESC
                    LIMIT 50
                """, (f'{entity_id.lower()}%',))  # Starts with, not contains
                rows = c.fetchall()
            
            if not rows:
                logger.warning(f"No recent media signals for {entity_id}")
                return None
            
            # Log which entity we actually matched
            matched_entity = rows[0][3] if rows else "unknown"
            logger.debug(f"Entity '{entity_id}' matched to '{matched_entity}'")
            
            # Calculate average sentiment from raw_value
            sentiments = [float(r[0]) for r in rows if r[0] is not None]
            
            if not sentiments:
                return None
            
            avg_sentiment = sum(sentiments) / len(sentiments)
            
            # Determine momentum from sentiment distribution
            recent_5 = sentiments[:5] if len(sentiments) >= 5 else sentiments
            older_5 = sentiments[5:10] if len(sentiments) >= 10 else sentiments[len(recent_5):]
            
            if older_5:
                recent_avg = sum(recent_5) / len(recent_5)
                older_avg = sum(older_5) / len(older_5)
                momentum_delta = recent_avg - older_avg
                
                if momentum_delta > 0.5:
                    momentum = "bullish"
                elif momentum_delta < -0.5:
                    momentum = "bearish"
                else:
                    momentum = "neutral"
            else:
                momentum = "bullish" if avg_sentiment > 6 else "bearish" if avg_sentiment < 4 else "neutral"
            
            # Confidence based on signal count and consistency
            std_dev = (sum((s - avg_sentiment)**2 for s in sentiments) / len(sentiments)) ** 0.5
            consistency = 1 - min(std_dev / 3, 1)  # Lower std = higher consistency
            volume_factor = min(len(sentiments) / 20, 1)  # More signals = more confidence
            confidence = (consistency + volume_factor) / 2
            
            return {
                "entity_id": entity_id,
                "sentiment": avg_sentiment,
                "momentum": momentum,
                "confidence": confidence,
                "signal_count": len(sentiments),
                "latest_observation": rows[0][1] if rows else None
            }
            
        except Exception as e:
            logger.error(f"Error getting sentiment for {entity_id}: {e}")
            return None
        finally:
            conn.close()

    async def validate_multiple(
        self,
        entities: List[Tuple[str, str]]  # (entity_id, ticker)
    ) -> List[ValidationResult]:
        """
        Validate multiple entities using REAL briefAI data with price calibration.
        
        Args:
            entities: List of (entity_id, ticker) tuples
            
        Returns:
            List of ValidationResults
        """
        results = []
        
        # Import calibrator for price-adjusted sentiment
        try:
            from utils.signal_calibrator import CalibratedValidator
            calibrator = CalibratedValidator()
            use_calibration = True
        except ImportError:
            logger.warning("Could not import CalibratedValidator, using raw sentiment")
            use_calibration = False
        
        for entity_id, ticker in entities:
            # Get REAL briefAI signal from database
            signal = self.get_real_briefai_sentiment(entity_id)
            
            if not signal:
                # Fallback: try ticker as entity name
                signal = self.get_real_briefai_sentiment(ticker)
            
            if not signal:
                logger.warning(f"No briefAI signals for {entity_id}/{ticker}, skipping")
                continue
            
            # Get price data for calibration
            raw_sentiment = signal['sentiment']
            calibrated_sentiment = raw_sentiment
            
            if use_calibration:
                # Fetch price data and calibrate sentiment using price momentum
                price_data = self.fetch_price_data(ticker)
                if price_data:
                    # Generate calibrated signal that combines news + price momentum
                    calibrated = calibrator.generate_calibrated_signal(
                        entity_id=entity_id,
                        price_data=price_data,
                        news_sentiment=raw_sentiment
                    )
                    calibrated_sentiment = calibrated['sentiment']
                    signal['momentum'] = calibrated['momentum']
                    signal['confidence'] = calibrated['confidence']
                    logger.debug(f"Calibrated {entity_id}: raw={raw_sentiment:.1f} -> calibrated={calibrated_sentiment:.1f}")
            
            logger.info(f"Got real signal for {entity_id}: sentiment={calibrated_sentiment:.1f}, n={signal['signal_count']}")
            
            result = self.validate_signal(
                entity_id=entity_id,
                briefai_sentiment=calibrated_sentiment,
                briefai_momentum=signal['momentum'],
                briefai_confidence=signal['confidence'],
                ticker=ticker
            )
            
            if result:
                results.append(result)
        
        return results
    
    def generate_report(
        self,
        results: List[ValidationResult],
        output_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """
        Generate validation report.
        
        Args:
            results: List of validation results
            output_path: Optional path to save report
            
        Returns:
            Report as dictionary
        """
        if not results:
            return {"error": "No results to report"}
        
        # Summary statistics
        avg_score = sum(r.validation_score for r in results) / len(results)
        aligned_count = sum(1 for r in results if r.direction_aligned)
        confirmed_count = sum(1 for r in results if r.technical_confirmed)
        
        # Grade distribution
        grades = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for r in results:
            grades[r.validation_grade] += 1
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "total_entities": len(results),
            "summary": {
                "average_validation_score": round(avg_score, 3),
                "direction_aligned_pct": round(aligned_count / len(results) * 100, 1),
                "technical_confirmed_pct": round(confirmed_count / len(results) * 100, 1),
            },
            "grade_distribution": grades,
            "top_validated": [
                r.to_dict() for r in sorted(results, key=lambda x: x.validation_score, reverse=True)[:3]
            ],
            "lowest_validated": [
                r.to_dict() for r in sorted(results, key=lambda x: x.validation_score)[:3]
            ],
            "all_results": [r.to_dict() for r in results],
        }
        
        # Save if path provided
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)
            logger.info(f"Report saved to {output_path}")
        
        return report
    
    def print_result(self, result: ValidationResult):
        """Pretty print a single validation result."""
        print(f"\n{'='*60}")
        print(f"{result.entity_id.upper()} ({result.ticker})")
        print(f"{'='*60}")
        
        print(f"\n[SIGNAL] briefAI Signal:")
        print(f"   Sentiment: {result.briefai_sentiment:.1f}/10")
        print(f"   Momentum:  {result.briefai_momentum}")
        print(f"   Confidence: {result.briefai_confidence:.0%}")
        
        print(f"\n[MARKET] Market Reality:")
        print(f"   Current Price: ${result.current_price:.2f}")
        print(f"   1D Change: {result.price_change_1d*100:+.2f}%")
        print(f"   5D Change: {result.price_change_5d*100:+.2f}%")
        print(f"   20D Change: {result.price_change_20d*100:+.2f}%")
        
        print(f"\n[TECH] Technicals:")
        if result.rsi_14:
            rsi_status = "[!] Overbought" if result.rsi_14 > 70 else "[+] Oversold" if result.rsi_14 < 30 else "[-] Neutral"
            print(f"   RSI(14): {result.rsi_14:.1f} {rsi_status}")
        if result.macd_histogram:
            macd_status = "[+]" if result.macd_histogram > 0 else "[-]"
            print(f"   MACD Hist: {result.macd_histogram:.4f} {macd_status}")
        if result.bb_position:
            print(f"   Bollinger: {result.bb_position}")
        if result.sma_20_distance:
            print(f"   SMA20 Distance: {result.sma_20_distance*100:+.2f}%")
        
        print(f"\n[VALIDATION] Validation:")
        print(f"   Direction Aligned: {'YES' if result.direction_aligned else 'NO'}")
        print(f"   Magnitude Aligned: {'YES' if result.magnitude_aligned else 'NO'}")
        print(f"   Technical Confirmed: {'YES' if result.technical_confirmed else 'NO'}")
        print(f"   Score: {result.validation_score:.1%}")
        print(f"   Grade: {result.validation_grade}")
        
        print(f"\n[NOTES] Notes:")
        for note in result.validation_notes:
            print(f"   - {note}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate briefAI signals against market data")
    parser.add_argument("--entities", type=str, help="Comma-separated entity IDs")
    parser.add_argument("--tickers", type=str, help="Comma-separated tickers")
    parser.add_argument("--all-ai", action="store_true", help="Test all default AI companies")
    parser.add_argument("--entity", type=str, help="Single entity for detailed analysis")
    parser.add_argument("--detailed", action="store_true", help="Show detailed output")
    parser.add_argument("--output", type=str, help="Output file for report (JSON)")
    
    args = parser.parse_args()
    
    validator = RealtimeValidator()
    
    # Determine entities to validate
    entities = []
    
    if args.all_ai or (not args.entities and not args.tickers and not args.entity):
        # Use default AI companies
        entities = validator.DEFAULT_AI_COMPANIES
        print("\n[AI] Validating Default AI Companies")
    elif args.entities:
        # Parse entity list - supports both entity names (nvidia) and ticker symbols (NVDA)
        for entity_id in args.entities.split(","):
            entity_id = entity_id.strip()
            ticker = validator.get_ticker_for_entity(entity_id)
            if ticker:
                entities.append((entity_id, ticker))
            else:
                # If entity looks like a ticker (all uppercase, 1-5 chars), use it directly
                if entity_id.isupper() and 1 <= len(entity_id) <= 5:
                    entities.append((entity_id.lower(), entity_id))
                    logger.info(f"Using '{entity_id}' as ticker directly (no asset mapping match)")
    elif args.tickers:
        # Parse ticker list
        for ticker in args.tickers.split(","):
            ticker = ticker.strip().upper()
            entities.append((ticker.lower(), ticker))
    elif args.entity:
        # Single entity
        ticker = validator.get_ticker_for_entity(args.entity)
        if ticker:
            entities = [(args.entity, ticker)]
    
    if not entities:
        print("No valid entities to validate")
        return
    
    print(f"\n[INFO] Validating {len(entities)} entities...")
    print("-" * 60)
    
    # Run validation
    results = await validator.validate_multiple(entities)
    
    # Print results
    if args.detailed or args.entity:
        for result in results:
            validator.print_result(result)
    else:
        # Summary view
        print(f"\n{'Entity':<15} {'Ticker':<8} {'Sentiment':<12} {'5D Change':<12} {'Score':<8} {'Grade'}")
        print("-" * 70)
        for r in sorted(results, key=lambda x: x.validation_score, reverse=True):
            sentiment_str = f"{r.briefai_sentiment:.1f} ({r.briefai_momentum[:3]})"
            change_str = f"{r.price_change_5d*100:+.2f}%"
            print(f"{r.entity_id:<15} {r.ticker:<8} {sentiment_str:<12} {change_str:<12} {r.validation_score:.1%}    {r.validation_grade}")
    
    # Generate report
    output_path = None
    if args.output:
        output_path = Path(args.output)
    else:
        # Default output
        output_path = validator.results_dir / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    report = validator.generate_report(results, output_path)
    
    # Print summary
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Total Entities: {report['total_entities']}")
    print(f"Average Score: {report['summary']['average_validation_score']:.1%}")
    print(f"Direction Aligned: {report['summary']['direction_aligned_pct']:.1f}%")
    print(f"Technical Confirmed: {report['summary']['technical_confirmed_pct']:.1f}%")
    print(f"\nGrade Distribution: {report['grade_distribution']}")
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
