"""
Market Regime Classifier Module

Classifies market regimes: bull, bear, sideways, crisis
Uses multiple indicators for robust classification:
- Price momentum (S&P 500, Nasdaq)
- Volatility (VIX)
- Credit spreads
- Yield curve
- Sector rotation

Stores regime history for backtesting and analysis.
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import numpy as np

from loguru import logger

try:
    import yfinance as yf
except ImportError:
    yf = None
    logger.warning("yfinance not installed - regime classifier limited")


class MarketRegime(Enum):
    """Market regime classification."""
    BULL = "bull"              # Strong uptrend, risk-on
    BEAR = "bear"              # Strong downtrend, risk-off
    SIDEWAYS = "sideways"      # Range-bound, choppy
    CRISIS = "crisis"          # Extreme volatility/drawdowns
    RECOVERY = "recovery"      # Transitioning from bear to bull


@dataclass
class RegimeSnapshot:
    """Point-in-time regime classification."""
    timestamp: str
    regime: str
    confidence: float
    
    # Component scores
    momentum_score: float = 0.0      # -1 (bearish) to +1 (bullish)
    volatility_score: float = 0.0   # 0 (calm) to 1 (extreme)
    trend_score: float = 0.0        # -1 to +1
    breadth_score: float = 0.0      # Market breadth
    
    # Supporting data
    sp500_return_1m: float = 0.0
    sp500_return_3m: float = 0.0
    vix_level: float = 0.0
    vix_percentile: float = 0.0
    yield_curve_10y2y: float = 0.0
    
    # Sector context
    tech_vs_spy_1m: float = 0.0
    semis_vs_spy_1m: float = 0.0
    defensive_vs_spy_1m: float = 0.0
    
    notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RegimeTransition:
    """Records a regime change."""
    from_regime: str
    to_regime: str
    transition_date: str
    confidence: float
    trigger_reason: str


class RegimeClassifier:
    """
    Classifies market regimes using multiple indicators.
    
    Regime definitions:
    - BULL: SPX > 200MA, +momentum, VIX < 20
    - BEAR: SPX < 200MA, -momentum, risk-off rotation
    - SIDEWAYS: Range-bound, mixed signals
    - CRISIS: VIX > 30, extreme drawdowns
    - RECOVERY: SPX crossing above 200MA from below
    """
    
    # Tickers for regime analysis
    TICKERS = {
        'sp500': '^GSPC',
        'nasdaq': '^IXIC',
        'vix': '^VIX',
        'treasury_20y': 'TLT',      # Long-term bonds
        'tech_etf': 'XLK',
        'semi_etf': 'SMH',
        'software_etf': 'IGV',
        'defensive_etf': 'XLU',     # Utilities (defensive)
        'growth_etf': 'IWF',
        'value_etf': 'IWD',
    }
    
    # Regime thresholds
    THRESHOLDS = {
        'vix_crisis': 30,
        'vix_elevated': 25,
        'vix_calm': 15,
        'momentum_bull': 0.03,       # 3% monthly
        'momentum_bear': -0.03,
        'trend_bull': 0.05,          # 5% above 200MA
        'trend_bear': -0.05,
    }
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        Initialize regime classifier.
        
        Args:
            data_dir: Directory for regime history storage
        """
        self.data_dir = data_dir or Path(__file__).parent.parent / "data"
        self.history_file = self.data_dir / "regime_history.json"
        
        self._cache: Dict[str, Any] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(hours=1)
        
        logger.info("RegimeClassifier initialized")
    
    def _get_market_data(
        self, 
        ticker: str, 
        period: str = "6mo"
    ) -> Optional[Dict[str, Any]]:
        """Fetch market data with caching."""
        if yf is None:
            return None
        
        cache_key = f"{ticker}_{period}"
        now = datetime.now()
        
        # Check cache
        if (self._cache_time and 
            now - self._cache_time < self._cache_ttl and
            cache_key in self._cache):
            return self._cache[cache_key]
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            
            if hist.empty:
                return None
            
            result = {
                'prices': hist['Close'].values.tolist(),
                'dates': [d.strftime('%Y-%m-%d') for d in hist.index],
                'current': float(hist['Close'].iloc[-1]),
                'high': float(hist['High'].max()),
                'low': float(hist['Low'].min()),
            }
            
            # Calculate returns
            if len(hist) >= 5:
                result['return_1w'] = float((hist['Close'].iloc[-1] / hist['Close'].iloc[-5] - 1))
            if len(hist) >= 21:
                result['return_1m'] = float((hist['Close'].iloc[-1] / hist['Close'].iloc[-21] - 1))
            if len(hist) >= 63:
                result['return_3m'] = float((hist['Close'].iloc[-1] / hist['Close'].iloc[-63] - 1))
            
            # 200-day MA approximation (use available data)
            if len(hist) >= 100:
                result['ma_200'] = float(hist['Close'].tail(100).mean())
                result['vs_ma_200'] = (result['current'] - result['ma_200']) / result['ma_200']
            
            # 50-day MA
            if len(hist) >= 50:
                result['ma_50'] = float(hist['Close'].tail(50).mean())
            
            self._cache[cache_key] = result
            self._cache_time = now
            
            return result
            
        except Exception as e:
            logger.warning(f"Error fetching {ticker}: {e}")
            return None
    
    def _calculate_momentum_score(
        self, 
        sp500: Dict, 
        nasdaq: Optional[Dict] = None
    ) -> float:
        """
        Calculate momentum score from -1 (bearish) to +1 (bullish).
        """
        scores = []
        
        # S&P 500 momentum
        ret_1m = sp500.get('return_1m', 0)
        ret_3m = sp500.get('return_3m', 0)
        
        # Normalize returns to score
        if ret_1m > 0.05:
            scores.append(1.0)
        elif ret_1m > 0.02:
            scores.append(0.5)
        elif ret_1m < -0.05:
            scores.append(-1.0)
        elif ret_1m < -0.02:
            scores.append(-0.5)
        else:
            scores.append(0.0)
        
        # 3-month trend weight
        if ret_3m > 0.10:
            scores.append(1.0)
        elif ret_3m > 0.05:
            scores.append(0.5)
        elif ret_3m < -0.10:
            scores.append(-1.0)
        elif ret_3m < -0.05:
            scores.append(-0.5)
        else:
            scores.append(0.0)
        
        # Nasdaq momentum (if available)
        if nasdaq:
            nas_ret = nasdaq.get('return_1m', 0)
            if nas_ret > 0.05:
                scores.append(0.8)
            elif nas_ret < -0.05:
                scores.append(-0.8)
        
        return np.mean(scores) if scores else 0.0
    
    def _calculate_volatility_score(self, vix: Optional[Dict]) -> float:
        """
        Calculate volatility score from 0 (calm) to 1 (extreme).
        """
        if not vix:
            return 0.5
        
        vix_level = vix.get('current', 20)
        
        if vix_level >= 40:
            return 1.0
        elif vix_level >= 30:
            return 0.8
        elif vix_level >= 25:
            return 0.6
        elif vix_level >= 20:
            return 0.4
        elif vix_level >= 15:
            return 0.2
        else:
            return 0.1
    
    def _calculate_trend_score(self, sp500: Dict) -> float:
        """
        Calculate trend score based on MA relationship.
        """
        vs_ma = sp500.get('vs_ma_200', 0)
        
        # Normalize to -1 to +1
        if vs_ma > 0.10:
            return 1.0
        elif vs_ma > 0.05:
            return 0.6
        elif vs_ma > 0:
            return 0.3
        elif vs_ma > -0.05:
            return -0.3
        elif vs_ma > -0.10:
            return -0.6
        else:
            return -1.0
    
    def _calculate_sector_rotation(
        self,
        tech: Optional[Dict],
        semis: Optional[Dict],
        defensive: Optional[Dict],
        sp500: Dict
    ) -> Tuple[float, float, float]:
        """
        Calculate sector rotation metrics.
        
        Returns:
            Tuple of (tech_vs_spy, semis_vs_spy, defensive_vs_spy)
        """
        spy_ret = sp500.get('return_1m', 0)
        
        tech_vs = (tech.get('return_1m', 0) - spy_ret) if tech else 0
        semis_vs = (semis.get('return_1m', 0) - spy_ret) if semis else 0
        defensive_vs = (defensive.get('return_1m', 0) - spy_ret) if defensive else 0
        
        return tech_vs, semis_vs, defensive_vs
    
    def classify_regime(self) -> RegimeSnapshot:
        """
        Classify current market regime.
        
        Returns:
            RegimeSnapshot with classification and supporting data
        """
        now = datetime.now()
        notes = []
        
        # Fetch data
        sp500 = self._get_market_data(self.TICKERS['sp500'])
        nasdaq = self._get_market_data(self.TICKERS['nasdaq'])
        vix = self._get_market_data(self.TICKERS['vix'])
        tech = self._get_market_data(self.TICKERS['tech_etf'])
        semis = self._get_market_data(self.TICKERS['semi_etf'])
        defensive = self._get_market_data(self.TICKERS['defensive_etf'])
        
        if not sp500:
            logger.warning("Could not fetch S&P 500 data")
            return RegimeSnapshot(
                timestamp=now.isoformat(),
                regime=MarketRegime.SIDEWAYS.value,
                confidence=0.3,
                notes=["Insufficient data for classification"]
            )
        
        # Calculate component scores
        momentum_score = self._calculate_momentum_score(sp500, nasdaq)
        volatility_score = self._calculate_volatility_score(vix)
        trend_score = self._calculate_trend_score(sp500)
        tech_vs, semis_vs, def_vs = self._calculate_sector_rotation(
            tech, semis, defensive, sp500
        )
        
        # VIX metrics
        vix_level = vix.get('current', 20) if vix else 20
        vix_percentile = min(100, vix_level / 40 * 100)  # Rough percentile
        
        # Classify regime
        regime = MarketRegime.SIDEWAYS
        confidence = 0.5
        
        # Crisis detection (highest priority)
        if vix_level >= self.THRESHOLDS['vix_crisis']:
            regime = MarketRegime.CRISIS
            confidence = 0.85
            notes.append(f"VIX at crisis level ({vix_level:.1f})")
        
        # Bear market
        elif (momentum_score < -0.5 and 
              trend_score < -0.3 and 
              volatility_score > 0.5):
            regime = MarketRegime.BEAR
            confidence = 0.7 + abs(momentum_score) * 0.2
            notes.append("Negative momentum + below MA + elevated volatility")
        
        # Bull market
        elif (momentum_score > 0.5 and 
              trend_score > 0.3 and 
              volatility_score < 0.5):
            regime = MarketRegime.BULL
            confidence = 0.7 + momentum_score * 0.2
            notes.append("Positive momentum + above MA + low volatility")
        
        # Recovery
        elif (momentum_score > 0.3 and 
              trend_score > 0 and 
              trend_score < 0.3):
            regime = MarketRegime.RECOVERY
            confidence = 0.6
            notes.append("Transitioning from bear - momentum improving")
        
        # Sideways (default)
        else:
            regime = MarketRegime.SIDEWAYS
            confidence = 0.5
            notes.append("Mixed signals - range-bound")
        
        # Sector rotation context
        if tech_vs > 0.02 and semis_vs > 0.02:
            notes.append("Risk-on rotation: Tech/semis outperforming")
        elif def_vs > 0.02:
            notes.append("Risk-off rotation: Defensive outperforming")
        
        return RegimeSnapshot(
            timestamp=now.isoformat(),
            regime=regime.value,
            confidence=round(min(0.95, confidence), 2),
            momentum_score=round(momentum_score, 3),
            volatility_score=round(volatility_score, 3),
            trend_score=round(trend_score, 3),
            breadth_score=0.0,  # Would need advance/decline data
            sp500_return_1m=round(sp500.get('return_1m', 0), 4),
            sp500_return_3m=round(sp500.get('return_3m', 0), 4),
            vix_level=round(vix_level, 2),
            vix_percentile=round(vix_percentile, 1),
            yield_curve_10y2y=0.0,  # Would need Treasury data
            tech_vs_spy_1m=round(tech_vs, 4),
            semis_vs_spy_1m=round(semis_vs, 4),
            defensive_vs_spy_1m=round(def_vs, 4),
            notes=notes
        )
    
    def get_regime_for_ai_signals(self) -> Dict[str, Any]:
        """
        Get regime classification optimized for AI signal interpretation.
        
        Returns dict with:
        - regime classification
        - signal reliability adjustment factors
        - key considerations
        """
        snapshot = self.classify_regime()
        
        # Base adjustments by regime
        adjustments = {
            MarketRegime.BULL.value: {
                'sentiment_reliability': 0.9,
                'bullish_signal_boost': 0.1,
                'bearish_signal_penalty': 0.1,
                'note': 'Bullish signals more reliable in uptrends'
            },
            MarketRegime.BEAR.value: {
                'sentiment_reliability': 0.7,
                'bullish_signal_boost': -0.15,
                'bearish_signal_penalty': 0.0,
                'note': 'Caution on bullish signals against trend'
            },
            MarketRegime.SIDEWAYS.value: {
                'sentiment_reliability': 0.8,
                'bullish_signal_boost': 0.0,
                'bearish_signal_penalty': 0.0,
                'note': 'Mixed environment - selective signals'
            },
            MarketRegime.CRISIS.value: {
                'sentiment_reliability': 0.5,
                'bullish_signal_boost': -0.2,
                'bearish_signal_penalty': 0.1,
                'note': 'High volatility distorts all signals'
            },
            MarketRegime.RECOVERY.value: {
                'sentiment_reliability': 0.75,
                'bullish_signal_boost': 0.05,
                'bearish_signal_penalty': 0.05,
                'note': 'Early recovery - trend confirmation needed'
            },
        }
        
        regime_adj = adjustments.get(snapshot.regime, adjustments[MarketRegime.SIDEWAYS.value])
        
        # AI sector specific considerations
        ai_specific = {
            'risk_on_environment': snapshot.regime in [MarketRegime.BULL.value, MarketRegime.RECOVERY.value],
            'sector_rotation_favorable': snapshot.tech_vs_spy_1m > 0 or snapshot.semis_vs_spy_1m > 0,
            'growth_friendly': snapshot.vix_level < 20,
        }
        
        return {
            'regime': snapshot.regime,
            'confidence': snapshot.confidence,
            'snapshot': snapshot.to_dict(),
            'signal_adjustments': regime_adj,
            'ai_sector': ai_specific,
            'classification_time': snapshot.timestamp,
        }
    
    def save_regime_snapshot(self, snapshot: Optional[RegimeSnapshot] = None) -> None:
        """
        Save regime snapshot to history file.
        """
        if snapshot is None:
            snapshot = self.classify_regime()
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Load existing history
        history = []
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    history = json.load(f)
            except (json.JSONDecodeError, IOError):
                history = []
        
        # Append new snapshot
        history.append(snapshot.to_dict())
        
        # Keep last 365 days
        cutoff = (datetime.now() - timedelta(days=365)).isoformat()
        history = [h for h in history if h.get('timestamp', '') > cutoff]
        
        # Save
        with open(self.history_file, 'w') as f:
            json.dump(history, f, indent=2)
        
        logger.info(f"Saved regime snapshot: {snapshot.regime} (confidence={snapshot.confidence})")
    
    def get_regime_history(
        self, 
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get regime history for the specified period.
        """
        if not self.history_file.exists():
            return []
        
        try:
            with open(self.history_file, 'r') as f:
                history = json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
        
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return [h for h in history if h.get('timestamp', '') > cutoff]
    
    def detect_regime_transition(self) -> Optional[RegimeTransition]:
        """
        Detect if a regime transition occurred.
        
        Compares current regime with recent history.
        """
        history = self.get_regime_history(days=7)
        
        if len(history) < 2:
            return None
        
        current = self.classify_regime()
        previous = history[-2] if len(history) >= 2 else history[-1]
        
        if current.regime != previous.get('regime'):
            return RegimeTransition(
                from_regime=previous.get('regime', 'unknown'),
                to_regime=current.regime,
                transition_date=current.timestamp,
                confidence=current.confidence,
                trigger_reason='; '.join(current.notes)
            )
        
        return None


def get_current_regime() -> Dict[str, Any]:
    """Convenience function to get current regime."""
    classifier = RegimeClassifier()
    return classifier.get_regime_for_ai_signals()


def classify_and_save() -> RegimeSnapshot:
    """Classify and save current regime."""
    classifier = RegimeClassifier()
    snapshot = classifier.classify_regime()
    classifier.save_regime_snapshot(snapshot)
    return snapshot


if __name__ == "__main__":
    print("=" * 60)
    print("Market Regime Classifier Test")
    print("=" * 60)
    
    classifier = RegimeClassifier()
    
    # Classify current regime
    print("\n[CURRENT REGIME]")
    snapshot = classifier.classify_regime()
    print(f"  Regime: {snapshot.regime}")
    print(f"  Confidence: {snapshot.confidence:.2f}")
    print(f"  Momentum Score: {snapshot.momentum_score:+.3f}")
    print(f"  Volatility Score: {snapshot.volatility_score:.3f}")
    print(f"  Trend Score: {snapshot.trend_score:+.3f}")
    print(f"  VIX: {snapshot.vix_level:.1f}")
    print(f"  S&P 500 1M Return: {snapshot.sp500_return_1m*100:+.2f}%")
    print(f"  Tech vs SPY 1M: {snapshot.tech_vs_spy_1m*100:+.2f}%")
    print(f"  Semis vs SPY 1M: {snapshot.semis_vs_spy_1m*100:+.2f}%")
    print(f"  Notes: {snapshot.notes}")
    
    # Get AI-specific context
    print("\n[AI SIGNAL CONTEXT]")
    ai_context = classifier.get_regime_for_ai_signals()
    adj = ai_context['signal_adjustments']
    print(f"  Sentiment Reliability: {adj['sentiment_reliability']:.2f}")
    print(f"  Bullish Signal Boost: {adj['bullish_signal_boost']:+.2f}")
    print(f"  Recommendation: {adj['note']}")
    print(f"  Risk-On Environment: {ai_context['ai_sector']['risk_on_environment']}")
    print(f"  Sector Rotation Favorable: {ai_context['ai_sector']['sector_rotation_favorable']}")
    
    # Save snapshot
    print("\n[SAVING SNAPSHOT]")
    classifier.save_regime_snapshot(snapshot)
    print(f"  Saved to: {classifier.history_file}")
    
    print("\n" + "=" * 60)
