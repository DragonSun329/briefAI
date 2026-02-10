"""
Price Alert System - Real-Time Price Movement Detection

Monitors tracked tickers for significant price moves and triggers
correlation checks against recent news.

Features:
- Real-time price monitoring via RealtimeFeed
- Configurable alert thresholds (default: > 2% in 5 min)
- Automatic news correlation on alerts
- SQLite persistence in data/alerts.db
- Alert history and analytics

Architecture:
    PriceAlertSystem
        ├── AlertMonitor (price tracking)
        ├── CorrelationChecker (news matching)
        ├── AlertStore (SQLite persistence)
        └── AlertNotifier (callbacks)

Usage:
    alert_system = PriceAlertSystem()
    await alert_system.start()
    
    # Register alert handler
    alert_system.on_alert(handle_alert)
    
    # Alerts auto-trigger on > 2% moves
"""

import asyncio
import inspect
import sqlite3
import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import our modules
try:
    from integrations.realtime_feed import RealtimeFeed, PriceTick, SignalEvent
except ImportError:
    from realtime_feed import RealtimeFeed, PriceTick, SignalEvent

try:
    from integrations.signal_queue import SignalQueue, QueuedSignal
except ImportError:
    from signal_queue import SignalQueue, QueuedSignal


class AlertType(Enum):
    """Types of price alerts."""
    SURGE = "surge"          # > threshold up
    PLUNGE = "plunge"        # > threshold down  
    VOLUME_SPIKE = "volume"  # Unusual volume
    VOLATILITY = "volatility"  # High volatility detected


class CorrelationStrength(Enum):
    """Strength of news-price correlation."""
    STRONG = "strong"      # Clear causal link
    MODERATE = "moderate"  # Likely related
    WEAK = "weak"          # Possibly related
    NONE = "none"          # No correlation found


@dataclass
class PriceAlert:
    """A price movement alert."""
    alert_id: str
    ticker: str
    alert_type: AlertType
    price_change_pct: float
    price_at_alert: float
    price_before: float
    volume_ratio: float
    window_minutes: int
    triggered_at: datetime
    
    # Correlation data (populated after correlation check)
    correlated_signals: List[Dict[str, Any]] = field(default_factory=list)
    correlation_strength: Optional[CorrelationStrength] = None
    correlation_summary: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "ticker": self.ticker,
            "alert_type": self.alert_type.value,
            "price_change_pct": self.price_change_pct,
            "price_at_alert": self.price_at_alert,
            "price_before": self.price_before,
            "volume_ratio": self.volume_ratio,
            "window_minutes": self.window_minutes,
            "triggered_at": self.triggered_at.isoformat(),
            "correlated_signals": self.correlated_signals,
            "correlation_strength": self.correlation_strength.value if self.correlation_strength else None,
            "correlation_summary": self.correlation_summary,
        }


class AlertStore:
    """
    SQLite-based alert storage.
    
    Stores alerts with correlation data for analysis.
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent / "data" / "alerts.db"
        
        self.db_path = db_path
        self._ensure_tables()
    
    def _ensure_tables(self) -> None:
        """Create tables if they don't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    price_change_pct REAL NOT NULL,
                    price_at_alert REAL NOT NULL,
                    price_before REAL NOT NULL,
                    volume_ratio REAL,
                    window_minutes INTEGER,
                    triggered_at TEXT NOT NULL,
                    correlation_strength TEXT,
                    correlation_summary TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id TEXT NOT NULL,
                    signal_id TEXT,
                    entity_id TEXT,
                    headline TEXT,
                    source TEXT,
                    sentiment REAL,
                    signal_timestamp TEXT,
                    FOREIGN KEY (alert_id) REFERENCES alerts(alert_id)
                )
            """)
            
            # Create indexes
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_ticker ON alerts(ticker)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON alerts(triggered_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_signals_alert ON alert_signals(alert_id)")
            
            conn.commit()
    
    def save_alert(self, alert: PriceAlert) -> bool:
        """Save an alert to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO alerts (
                        alert_id, ticker, alert_type, price_change_pct,
                        price_at_alert, price_before, volume_ratio,
                        window_minutes, triggered_at, correlation_strength,
                        correlation_summary
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    alert.alert_id,
                    alert.ticker,
                    alert.alert_type.value,
                    alert.price_change_pct,
                    alert.price_at_alert,
                    alert.price_before,
                    alert.volume_ratio,
                    alert.window_minutes,
                    alert.triggered_at.isoformat(),
                    alert.correlation_strength.value if alert.correlation_strength else None,
                    alert.correlation_summary,
                ))
                
                # Save correlated signals
                for sig in alert.correlated_signals:
                    conn.execute("""
                        INSERT INTO alert_signals (
                            alert_id, signal_id, entity_id, headline,
                            source, sentiment, signal_timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        alert.alert_id,
                        sig.get("signal_id"),
                        sig.get("entity_id"),
                        sig.get("headline"),
                        sig.get("source"),
                        sig.get("sentiment"),
                        sig.get("timestamp"),
                    ))
                
                conn.commit()
                return True
                
        except Exception as e:
            logger.error(f"Error saving alert: {e}")
            return False
    
    def get_alert(self, alert_id: str) -> Optional[PriceAlert]:
        """Retrieve an alert by ID."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                row = conn.execute(
                    "SELECT * FROM alerts WHERE alert_id = ?",
                    (alert_id,)
                ).fetchone()
                
                if not row:
                    return None
                
                # Get correlated signals
                signals = conn.execute(
                    "SELECT * FROM alert_signals WHERE alert_id = ?",
                    (alert_id,)
                ).fetchall()
                
                return PriceAlert(
                    alert_id=row["alert_id"],
                    ticker=row["ticker"],
                    alert_type=AlertType(row["alert_type"]),
                    price_change_pct=row["price_change_pct"],
                    price_at_alert=row["price_at_alert"],
                    price_before=row["price_before"],
                    volume_ratio=row["volume_ratio"] or 1.0,
                    window_minutes=row["window_minutes"] or 5,
                    triggered_at=datetime.fromisoformat(row["triggered_at"]),
                    correlated_signals=[dict(s) for s in signals],
                    correlation_strength=CorrelationStrength(row["correlation_strength"]) if row["correlation_strength"] else None,
                    correlation_summary=row["correlation_summary"],
                )
                
        except Exception as e:
            logger.error(f"Error getting alert: {e}")
            return None
    
    def get_alerts_for_ticker(
        self,
        ticker: str,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[PriceAlert]:
        """Get alerts for a specific ticker."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if since:
                    rows = conn.execute("""
                        SELECT * FROM alerts 
                        WHERE ticker = ? AND triggered_at >= ?
                        ORDER BY triggered_at DESC
                        LIMIT ?
                    """, (ticker, since.isoformat(), limit)).fetchall()
                else:
                    rows = conn.execute("""
                        SELECT * FROM alerts 
                        WHERE ticker = ?
                        ORDER BY triggered_at DESC
                        LIMIT ?
                    """, (ticker, limit)).fetchall()
                
                return [self._row_to_alert(row, conn) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting alerts: {e}")
            return []
    
    def get_recent_alerts(
        self,
        hours: int = 24,
        limit: int = 100,
    ) -> List[PriceAlert]:
        """Get recent alerts across all tickers."""
        since = datetime.now() - timedelta(hours=hours)
        
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                rows = conn.execute("""
                    SELECT * FROM alerts 
                    WHERE triggered_at >= ?
                    ORDER BY triggered_at DESC
                    LIMIT ?
                """, (since.isoformat(), limit)).fetchall()
                
                return [self._row_to_alert(row, conn) for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting recent alerts: {e}")
            return []
    
    def _row_to_alert(self, row: sqlite3.Row, conn: sqlite3.Connection) -> PriceAlert:
        """Convert a database row to PriceAlert."""
        signals = conn.execute(
            "SELECT * FROM alert_signals WHERE alert_id = ?",
            (row["alert_id"],)
        ).fetchall()
        
        return PriceAlert(
            alert_id=row["alert_id"],
            ticker=row["ticker"],
            alert_type=AlertType(row["alert_type"]),
            price_change_pct=row["price_change_pct"],
            price_at_alert=row["price_at_alert"],
            price_before=row["price_before"],
            volume_ratio=row["volume_ratio"] or 1.0,
            window_minutes=row["window_minutes"] or 5,
            triggered_at=datetime.fromisoformat(row["triggered_at"]),
            correlated_signals=[{
                "signal_id": s["signal_id"],
                "entity_id": s["entity_id"],
                "headline": s["headline"],
                "source": s["source"],
                "sentiment": s["sentiment"],
                "timestamp": s["signal_timestamp"],
            } for s in signals],
            correlation_strength=CorrelationStrength(row["correlation_strength"]) if row["correlation_strength"] else None,
            correlation_summary=row["correlation_summary"],
        )
    
    def get_alert_stats(self) -> Dict[str, Any]:
        """Get alert statistics."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
                
                by_type = conn.execute("""
                    SELECT alert_type, COUNT(*) as count
                    FROM alerts
                    GROUP BY alert_type
                """).fetchall()
                
                by_ticker = conn.execute("""
                    SELECT ticker, COUNT(*) as count
                    FROM alerts
                    GROUP BY ticker
                    ORDER BY count DESC
                    LIMIT 10
                """).fetchall()
                
                correlated = conn.execute("""
                    SELECT correlation_strength, COUNT(*) as count
                    FROM alerts
                    WHERE correlation_strength IS NOT NULL
                    GROUP BY correlation_strength
                """).fetchall()
                
                return {
                    "total_alerts": total,
                    "by_type": {row[0]: row[1] for row in by_type},
                    "top_tickers": {row[0]: row[1] for row in by_ticker},
                    "correlations": {row[0]: row[1] for row in correlated},
                }
                
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"error": str(e)}


class CorrelationChecker:
    """
    Checks for correlations between price moves and recent signals.
    """
    
    def __init__(
        self,
        signal_lookback_minutes: int = 60,
        entity_ticker_map: Optional[Dict[str, str]] = None,
    ):
        self.signal_lookback_minutes = signal_lookback_minutes
        self.entity_ticker_map = entity_ticker_map or {}
        
        # Reverse map: ticker -> entity_ids
        self.ticker_entities: Dict[str, List[str]] = {}
        for entity, ticker in self.entity_ticker_map.items():
            if ticker not in self.ticker_entities:
                self.ticker_entities[ticker] = []
            self.ticker_entities[ticker].append(entity)
        
        # Recent signals cache
        self._recent_signals: List[QueuedSignal] = []
        self._max_signals = 1000
    
    def add_signal(self, signal: QueuedSignal) -> None:
        """Add a signal to the recent signals cache."""
        self._recent_signals.append(signal)
        
        # Trim old signals
        cutoff = datetime.now() - timedelta(minutes=self.signal_lookback_minutes)
        self._recent_signals = [
            s for s in self._recent_signals
            if s.enqueued_at >= cutoff
        ][-self._max_signals:]
    
    def find_correlations(
        self,
        ticker: str,
        price_move_direction: str,  # "up" or "down"
        lookback_minutes: Optional[int] = None,
    ) -> Tuple[List[Dict[str, Any]], CorrelationStrength]:
        """
        Find signals that might correlate with a price move.
        
        Returns (correlated_signals, strength)
        """
        lookback = lookback_minutes or self.signal_lookback_minutes
        cutoff = datetime.now() - timedelta(minutes=lookback)
        
        # Get entities for this ticker
        relevant_entities = set(self.ticker_entities.get(ticker.upper(), []))
        
        # Also check for direct ticker matches
        relevant_entities.add(ticker.lower())
        
        # Find matching signals
        matches = []
        for signal in self._recent_signals:
            if signal.enqueued_at < cutoff:
                continue
            
            # Check entity match
            if signal.entity_id.lower() in relevant_entities:
                matches.append(signal)
                continue
            
            # Check ticker match
            if signal.ticker and signal.ticker.upper() == ticker.upper():
                matches.append(signal)
                continue
            
            # Check headline for ticker mention
            if ticker.upper() in signal.headline.upper():
                matches.append(signal)
        
        if not matches:
            return [], CorrelationStrength.NONE
        
        # Convert to dicts
        correlated = []
        aligned_count = 0
        
        for sig in matches:
            sig_dict = {
                "signal_id": sig.signal_id,
                "entity_id": sig.entity_id,
                "headline": sig.headline,
                "source": sig.source,
                "sentiment": sig.sentiment,
                "timestamp": sig.enqueued_at.isoformat(),
            }
            correlated.append(sig_dict)
            
            # Check alignment
            bullish_signal = sig.sentiment > 6.0
            bearish_signal = sig.sentiment < 4.0
            
            if (price_move_direction == "up" and bullish_signal) or \
               (price_move_direction == "down" and bearish_signal):
                aligned_count += 1
        
        # Determine correlation strength
        alignment_ratio = aligned_count / len(matches) if matches else 0
        
        if alignment_ratio >= 0.7 and len(matches) >= 2:
            strength = CorrelationStrength.STRONG
        elif alignment_ratio >= 0.5 or len(matches) >= 3:
            strength = CorrelationStrength.MODERATE
        elif len(matches) >= 1:
            strength = CorrelationStrength.WEAK
        else:
            strength = CorrelationStrength.NONE
        
        return correlated, strength


class PriceAlertSystem:
    """
    Main price alert system.
    
    Monitors tracked tickers and triggers alerts on significant moves.
    """
    
    def __init__(
        self,
        feed: Optional[RealtimeFeed] = None,
        db_path: Optional[Path] = None,
        price_threshold_pct: float = 2.0,
        window_minutes: int = 5,
        volume_threshold: float = 2.0,
        entity_ticker_map: Optional[Dict[str, str]] = None,
    ):
        self.feed = feed
        self.price_threshold_pct = price_threshold_pct
        self.window_minutes = window_minutes
        self.volume_threshold = volume_threshold
        
        self.store = AlertStore(db_path)
        self.correlation_checker = CorrelationChecker(
            signal_lookback_minutes=60,
            entity_ticker_map=entity_ticker_map or {},
        )
        
        self._alert_callbacks: List[Callable[[PriceAlert], None]] = []
        self._tracked_tickers: set = set()
        self._running = False
        
        # Cooldown to prevent alert spam
        self._last_alert: Dict[str, datetime] = {}
        self._alert_cooldown = timedelta(minutes=5)
        
        # Metrics
        self._alerts_triggered = 0
        self._correlations_found = 0
    
    def on_alert(self, callback: Callable[[PriceAlert], None]) -> None:
        """Register an alert callback."""
        self._alert_callbacks.append(callback)
    
    async def start(
        self,
        tickers: Optional[List[str]] = None,
    ) -> None:
        """Start the alert system."""
        self._running = True
        
        # Create feed if not provided
        if self.feed is None:
            self.feed = RealtimeFeed(config={"poll_interval": 5.0})
            await self.feed.start()
        
        # Subscribe to tickers
        if tickers:
            await self.add_tickers(tickers)
        
        logger.info(f"Price alert system started (threshold: {self.price_threshold_pct}% in {self.window_minutes}min)")
    
    async def stop(self) -> None:
        """Stop the alert system."""
        self._running = False
        
        if self.feed:
            await self.feed.stop()
        
        logger.info("Price alert system stopped")
    
    async def add_tickers(self, tickers: List[str]) -> None:
        """Add tickers to monitor."""
        new_tickers = [t.upper() for t in tickers if t.upper() not in self._tracked_tickers]
        
        if new_tickers and self.feed:
            await self.feed.subscribe_prices(new_tickers, self._on_price_update)
            self._tracked_tickers.update(new_tickers)
            logger.info(f"Now tracking: {list(self._tracked_tickers)}")
    
    async def remove_tickers(self, tickers: List[str]) -> None:
        """Remove tickers from monitoring."""
        tickers_upper = [t.upper() for t in tickers]
        
        if self.feed:
            await self.feed.unsubscribe_prices(tickers_upper)
        
        self._tracked_tickers -= set(tickers_upper)
    
    def add_signal(self, signal: QueuedSignal) -> None:
        """Add a signal for correlation checking."""
        self.correlation_checker.add_signal(signal)
    
    async def _on_price_update(self, tick: PriceTick) -> None:
        """Handle price update from feed."""
        if not self._running:
            return
        
        symbol = tick.symbol.upper()
        
        # Check for significant move
        change = self.feed.calculate_price_change(symbol, self.window_minutes)
        
        if change is None:
            return
        
        # Check threshold
        change_pct = abs(change * 100)
        
        if change_pct >= self.price_threshold_pct:
            # Check cooldown
            if symbol in self._last_alert:
                if datetime.now() - self._last_alert[symbol] < self._alert_cooldown:
                    return
            
            # Trigger alert
            await self._trigger_alert(
                ticker=symbol,
                change_pct=change * 100,
                current_price=tick.price,
            )
    
    async def _trigger_alert(
        self,
        ticker: str,
        change_pct: float,
        current_price: float,
    ) -> None:
        """Trigger and process an alert."""
        self._alerts_triggered += 1
        self._last_alert[ticker] = datetime.now()
        
        # Get price before move
        history = self.feed.get_price_history(ticker, self.window_minutes) if self.feed else []
        price_before = history[0][1] if history else current_price
        
        # Determine alert type
        if change_pct > 0:
            alert_type = AlertType.SURGE
            direction = "up"
        else:
            alert_type = AlertType.PLUNGE
            direction = "down"
        
        # Create alert
        alert = PriceAlert(
            alert_id=f"alert_{int(datetime.now().timestamp())}_{ticker}",
            ticker=ticker,
            alert_type=alert_type,
            price_change_pct=change_pct,
            price_at_alert=current_price,
            price_before=price_before,
            volume_ratio=1.0,  # TODO: implement volume tracking
            window_minutes=self.window_minutes,
            triggered_at=datetime.now(),
        )
        
        logger.info(f"🚨 ALERT: {ticker} {alert_type.value} {change_pct:+.2f}% (${current_price:.2f})")
        
        # Check correlations
        correlated, strength = self.correlation_checker.find_correlations(
            ticker=ticker,
            price_move_direction=direction,
        )
        
        alert.correlated_signals = correlated
        alert.correlation_strength = strength
        
        if correlated:
            self._correlations_found += 1
            alert.correlation_summary = self._generate_correlation_summary(
                ticker, direction, correlated, strength
            )
            logger.info(f"  📊 Correlation: {strength.value} ({len(correlated)} signals)")
        
        # Save to database
        self.store.save_alert(alert)
        
        # Notify callbacks
        for callback in self._alert_callbacks:
            try:
                if inspect.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
    
    def _generate_correlation_summary(
        self,
        ticker: str,
        direction: str,
        signals: List[Dict[str, Any]],
        strength: CorrelationStrength,
    ) -> str:
        """Generate a human-readable correlation summary."""
        if not signals:
            return f"No recent signals found for {ticker}"
        
        top_signal = signals[0]
        summary = f"{ticker} {direction} move correlates ({strength.value}) with "
        summary += f"{len(signals)} recent signal(s). "
        summary += f"Most recent: '{top_signal['headline'][:60]}...' "
        summary += f"(sentiment: {top_signal['sentiment']:.1f}/10)"
        
        return summary
    
    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "alerts_triggered": self._alerts_triggered,
            "correlations_found": self._correlations_found,
            "tracked_tickers": list(self._tracked_tickers),
            "stats": self.store.get_alert_stats(),
        }
    
    def get_recent_alerts(
        self,
        hours: int = 24,
        limit: int = 50,
    ) -> List[PriceAlert]:
        """Get recent alerts."""
        return self.store.get_recent_alerts(hours=hours, limit=limit)
    
    def get_alerts_for_ticker(
        self,
        ticker: str,
        hours: int = 24,
    ) -> List[PriceAlert]:
        """Get alerts for a specific ticker."""
        since = datetime.now() - timedelta(hours=hours)
        return self.store.get_alerts_for_ticker(ticker, since=since)


# =============================================================================
# Integration with SignalQueue
# =============================================================================

async def create_integrated_system(
    tickers: List[str],
    entity_ticker_map: Optional[Dict[str, str]] = None,
) -> Tuple[RealtimeFeed, SignalQueue, PriceAlertSystem]:
    """
    Create an integrated real-time system with all components connected.
    
    Returns (feed, queue, alert_system)
    """
    from integrations.signal_queue import SignalQueue
    
    # Create components
    feed = RealtimeFeed(config={"poll_interval": 5.0})
    queue = SignalQueue()
    
    alert_system = PriceAlertSystem(
        feed=feed,
        price_threshold_pct=2.0,
        window_minutes=5,
        entity_ticker_map=entity_ticker_map or {},
    )
    
    # Connect signal queue to correlation checker
    async def on_signal_queued(signal: QueuedSignal):
        alert_system.add_signal(signal)
    
    # Start components
    await feed.start()
    await alert_system.start(tickers=tickers)
    
    return feed, queue, alert_system


# =============================================================================
# Demo
# =============================================================================

async def demo():
    """Demonstrate price alert system."""
    print("=" * 60)
    print("Price Alert System Demo")
    print("=" * 60)
    
    # Entity-ticker mapping
    entity_ticker_map = {
        "nvidia": "NVDA",
        "meta": "META",
        "microsoft": "MSFT",
        "google": "GOOGL",
        "amd": "AMD",
    }
    
    # Create alert system
    alert_system = PriceAlertSystem(
        price_threshold_pct=0.5,  # Lower threshold for demo
        window_minutes=5,
        entity_ticker_map=entity_ticker_map,
    )
    
    alerts_received = []
    
    async def on_alert(alert: PriceAlert):
        alerts_received.append(alert)
        print(f"\n🚨 ALERT RECEIVED:")
        print(f"   Ticker: {alert.ticker}")
        print(f"   Type: {alert.alert_type.value}")
        print(f"   Change: {alert.price_change_pct:+.2f}%")
        print(f"   Price: ${alert.price_at_alert:.2f}")
        if alert.correlation_strength:
            print(f"   Correlation: {alert.correlation_strength.value}")
            print(f"   Summary: {alert.correlation_summary}")
    
    alert_system.on_alert(on_alert)
    
    # Add some test signals for correlation
    from integrations.signal_queue import QueuedSignal, SignalPriority
    
    test_signals = [
        QueuedSignal(
            signal_id="sig_001",
            entity_id="nvidia",
            ticker="NVDA",
            signal_type="news",
            sentiment=8.0,
            confidence=0.8,
            headline="NVIDIA announces breakthrough AI chip performance",
            source="TechCrunch",
            priority=SignalPriority.NORMAL,
            enqueued_at=datetime.now() - timedelta(minutes=30),
        ),
        QueuedSignal(
            signal_id="sig_002",
            entity_id="nvidia",
            ticker="NVDA",
            signal_type="news",
            sentiment=7.5,
            confidence=0.7,
            headline="NVIDIA data center revenue exceeds expectations",
            source="Bloomberg",
            priority=SignalPriority.NORMAL,
            enqueued_at=datetime.now() - timedelta(minutes=15),
        ),
    ]
    
    for sig in test_signals:
        alert_system.add_signal(sig)
    
    print(f"\nAdded {len(test_signals)} test signals")
    
    # Start monitoring
    test_tickers = ["NVDA", "META", "MSFT", "GOOGL", "AMD"]
    await alert_system.start(tickers=test_tickers)
    
    print(f"\nMonitoring: {test_tickers}")
    print(f"Threshold: {alert_system.price_threshold_pct}% in {alert_system.window_minutes}min")
    print("\nWaiting for price updates (30 seconds)...")
    
    await asyncio.sleep(30)
    
    # Print metrics
    print(f"\n{'='*60}")
    print("Metrics:")
    metrics = alert_system.metrics
    print(f"  Alerts triggered: {metrics['alerts_triggered']}")
    print(f"  Correlations found: {metrics['correlations_found']}")
    print(f"  Tracked tickers: {metrics['tracked_tickers']}")
    
    # Get recent alerts from database
    recent = alert_system.get_recent_alerts(hours=1)
    print(f"\nRecent alerts in database: {len(recent)}")
    
    await alert_system.stop()
    print("\nAlert system stopped.")


if __name__ == "__main__":
    asyncio.run(demo())
