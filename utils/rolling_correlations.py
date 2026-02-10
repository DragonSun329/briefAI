"""
Rolling Correlations with Regime Change Detection

Tracks how correlations between entities change over time:
- 7-day, 30-day, 90-day rolling windows
- Detect correlation breakdowns (regime changes)
- Alert when historically correlated entities diverge
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger
import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class RollingCorrelation:
    """A single rolling correlation value."""
    entity_a: str
    entity_b: str
    signal_type: str
    window_days: int
    correlation: float
    date: date
    sample_size: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "signal_type": self.signal_type,
            "window_days": self.window_days,
            "correlation": round(self.correlation, 4),
            "date": self.date.isoformat(),
            "sample_size": self.sample_size,
        }


@dataclass
class CorrelationRegimeChange:
    """Detected regime change in correlation."""
    entity_a: str
    entity_b: str
    signal_type: str
    change_type: str  # "breakdown", "emergence", "reversal"
    previous_correlation: float
    current_correlation: float
    change_magnitude: float
    detected_date: date
    window_days: int
    significance: str  # "high", "medium", "low"
    actionable_insight: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "signal_type": self.signal_type,
            "change_type": self.change_type,
            "previous_correlation": round(self.previous_correlation, 4),
            "current_correlation": round(self.current_correlation, 4),
            "change_magnitude": round(self.change_magnitude, 4),
            "detected_date": self.detected_date.isoformat(),
            "window_days": self.window_days,
            "significance": self.significance,
            "actionable_insight": self.actionable_insight,
        }


@dataclass
class CorrelationDivergenceAlert:
    """Alert when historically correlated entities diverge."""
    entity_a: str
    entity_b: str
    signal_type: str
    historical_correlation: float  # Long-term correlation
    recent_correlation: float  # Short-term correlation
    divergence_magnitude: float
    direction: str  # "weakening", "strengthening", "reversing"
    alert_level: str  # "warning", "critical"
    alert_message: str
    detected_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "signal_type": self.signal_type,
            "historical_correlation": round(self.historical_correlation, 4),
            "recent_correlation": round(self.recent_correlation, 4),
            "divergence_magnitude": round(self.divergence_magnitude, 4),
            "direction": self.direction,
            "alert_level": self.alert_level,
            "alert_message": self.alert_message,
            "detected_at": self.detected_at.isoformat(),
        }


class RollingCorrelationTracker:
    """
    Tracks rolling correlations and detects regime changes.
    
    Key capabilities:
    - Calculate rolling correlations at multiple windows
    - Detect correlation breakdowns and emergences
    - Generate alerts for diverging entity pairs
    - Store historical correlation snapshots
    """
    
    # Standard window configurations
    WINDOWS = {
        "short": 7,
        "medium": 30,
        "long": 90,
    }
    
    # Thresholds for regime change detection
    REGIME_THRESHOLDS = {
        "breakdown": -0.4,  # Correlation drops by this much
        "emergence": 0.4,   # Correlation increases by this much
        "reversal": 0.6,    # Correlation flips sign by this much
    }
    
    # Thresholds for divergence alerts
    DIVERGENCE_THRESHOLDS = {
        "warning": 0.3,     # Short vs long term differs by this
        "critical": 0.5,    # Severe divergence
    }
    
    def __init__(
        self,
        signals_db_path: Optional[Path] = None,
        correlations_db_path: Optional[Path] = None,
    ):
        """
        Initialize rolling correlation tracker.
        
        Args:
            signals_db_path: Path to signals.db
            correlations_db_path: Path to correlations.db
        """
        base_path = Path(__file__).parent.parent / "data"
        
        self.signals_db_path = signals_db_path or (base_path / "signals.db")
        self.correlations_db_path = correlations_db_path or (base_path / "correlations.db")
        
        self._ensure_tables()
        logger.info("RollingCorrelationTracker initialized")

    def _ensure_tables(self):
        """Create required tables if they don't exist."""
        conn = sqlite3.connect(self.correlations_db_path)
        cursor = conn.cursor()
        
        # Rolling correlations history
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rolling_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a TEXT NOT NULL,
                entity_b TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                window_days INTEGER NOT NULL,
                correlation REAL NOT NULL,
                sample_size INTEGER DEFAULT 0,
                calculation_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_a, entity_b, signal_type, window_days, calculation_date)
            )
        """)
        
        # Regime changes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS correlation_regime_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a TEXT NOT NULL,
                entity_b TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                change_type TEXT NOT NULL,
                previous_correlation REAL NOT NULL,
                current_correlation REAL NOT NULL,
                change_magnitude REAL NOT NULL,
                detected_date DATE NOT NULL,
                window_days INTEGER NOT NULL,
                significance TEXT NOT NULL,
                actionable_insight TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Divergence alerts
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS correlation_divergence_alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a TEXT NOT NULL,
                entity_b TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                historical_correlation REAL NOT NULL,
                recent_correlation REAL NOT NULL,
                divergence_magnitude REAL NOT NULL,
                direction TEXT NOT NULL,
                alert_level TEXT NOT NULL,
                alert_message TEXT,
                detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rc_pair ON rolling_correlations(entity_a, entity_b)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rc_date ON rolling_correlations(calculation_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_regime_date ON correlation_regime_changes(detected_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alert_active ON correlation_divergence_alerts(is_active)")
        
        conn.commit()
        conn.close()

    def _get_signals_connection(self) -> sqlite3.Connection:
        """Get connection to signals database."""
        conn = sqlite3.connect(self.signals_db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _get_correlations_connection(self) -> sqlite3.Connection:
        """Get connection to correlations database."""
        conn = sqlite3.connect(self.correlations_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_entity_signal_series(
        self,
        entity_id: str,
        signal_type: str,
        start_date: date,
        end_date: date
    ) -> pd.Series:
        """Get signal time series for an entity."""
        conn = self._get_signals_connection()
        
        column_map = {
            "technical": "technical_score",
            "company": "company_score",
            "financial": "financial_score",
            "product": "product_score",
            "media": "media_score",
            "composite": "composite_score",
        }
        
        score_column = column_map.get(signal_type, "composite_score")
        
        query = f"""
            SELECT DATE(as_of) as date, {score_column} as value
            FROM signal_profiles
            WHERE entity_id = ? AND DATE(as_of) BETWEEN ? AND ?
            ORDER BY as_of ASC
        """
        
        df = pd.read_sql_query(
            query, conn, 
            params=(entity_id, start_date.isoformat(), end_date.isoformat())
        )
        conn.close()
        
        if df.empty:
            return pd.Series(dtype=float)
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')['value']
        
        # Resample to daily with forward fill
        df = df.resample('D').last().ffill()
        
        return df

    def calculate_rolling_correlation(
        self,
        entity_a: str,
        entity_b: str,
        signal_type: str = "composite",
        window_days: int = 30,
        end_date: Optional[date] = None
    ) -> Optional[RollingCorrelation]:
        """
        Calculate rolling correlation for a single window ending at a date.
        
        Args:
            entity_a: First entity
            entity_b: Second entity
            signal_type: Signal type
            window_days: Rolling window size
            end_date: End date of window (default: today)
            
        Returns:
            RollingCorrelation or None if insufficient data
        """
        if end_date is None:
            end_date = date.today()
        
        start_date = end_date - timedelta(days=window_days + 5)  # Extra buffer
        
        series_a = self._get_entity_signal_series(entity_a, signal_type, start_date, end_date)
        series_b = self._get_entity_signal_series(entity_b, signal_type, start_date, end_date)
        
        if series_a.empty or series_b.empty:
            return None
        
        # Align series
        combined = pd.concat([series_a, series_b], axis=1)
        combined.columns = ['a', 'b']
        combined = combined.dropna()
        
        # Use only the last window_days
        combined = combined.tail(window_days)
        
        if len(combined) < max(window_days // 2, 5):
            return None
        
        # Calculate correlation
        corr = combined['a'].corr(combined['b'])
        
        if pd.isna(corr):
            return None
        
        return RollingCorrelation(
            entity_a=entity_a,
            entity_b=entity_b,
            signal_type=signal_type,
            window_days=window_days,
            correlation=float(corr),
            date=end_date,
            sample_size=len(combined)
        )

    def calculate_rolling_correlation_series(
        self,
        entity_a: str,
        entity_b: str,
        signal_type: str = "composite",
        window_days: int = 30,
        history_days: int = 180
    ) -> List[RollingCorrelation]:
        """
        Calculate rolling correlations over a time period.
        
        Args:
            entity_a: First entity
            entity_b: Second entity
            signal_type: Signal type
            window_days: Rolling window size
            history_days: How far back to calculate
            
        Returns:
            List of RollingCorrelation objects
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=history_days)
        
        # Get full series
        full_start = start_date - timedelta(days=window_days + 5)
        series_a = self._get_entity_signal_series(entity_a, signal_type, full_start, end_date)
        series_b = self._get_entity_signal_series(entity_b, signal_type, full_start, end_date)
        
        if series_a.empty or series_b.empty:
            return []
        
        # Align series
        combined = pd.concat([series_a, series_b], axis=1)
        combined.columns = ['a', 'b']
        combined = combined.dropna()
        
        if len(combined) < window_days:
            return []
        
        # Calculate rolling correlation
        rolling_corr = combined['a'].rolling(window=window_days).corr(combined['b'])
        rolling_corr = rolling_corr.dropna()
        
        results = []
        for dt, corr in rolling_corr.items():
            if pd.isna(corr):
                continue
            if isinstance(dt, pd.Timestamp):
                dt = dt.date()
            
            results.append(RollingCorrelation(
                entity_a=entity_a,
                entity_b=entity_b,
                signal_type=signal_type,
                window_days=window_days,
                correlation=float(corr),
                date=dt,
                sample_size=window_days
            ))
        
        # Store results
        self._store_rolling_correlations(results)
        
        return results

    def _store_rolling_correlations(self, correlations: List[RollingCorrelation]):
        """Store rolling correlations to database."""
        if not correlations:
            return
            
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        for rc in correlations:
            cursor.execute("""
                INSERT OR REPLACE INTO rolling_correlations
                (entity_a, entity_b, signal_type, window_days, correlation, sample_size, calculation_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (rc.entity_a, rc.entity_b, rc.signal_type, rc.window_days,
                  rc.correlation, rc.sample_size, rc.date.isoformat()))
        
        conn.commit()
        conn.close()

    def detect_regime_changes(
        self,
        entity_a: str,
        entity_b: str,
        signal_type: str = "composite",
        window_days: int = 30,
        lookback_periods: int = 3
    ) -> List[CorrelationRegimeChange]:
        """
        Detect regime changes in correlation between entities.
        
        Looks for:
        - Breakdowns: Strong correlation weakening significantly
        - Emergences: Weak correlation strengthening significantly
        - Reversals: Correlation flipping sign
        
        Args:
            entity_a: First entity
            entity_b: Second entity
            signal_type: Signal type
            window_days: Rolling window
            lookback_periods: How many periods back to compare
            
        Returns:
            List of detected regime changes
        """
        # Calculate recent rolling correlations
        correlations = self.calculate_rolling_correlation_series(
            entity_a, entity_b, signal_type, window_days,
            history_days=window_days * (lookback_periods + 1)
        )
        
        if len(correlations) < lookback_periods + 1:
            return []
        
        regime_changes = []
        
        # Compare most recent to historical
        recent = correlations[-1]
        historical = correlations[-(lookback_periods + 1):-1]
        
        avg_historical = np.mean([c.correlation for c in historical])
        change = recent.correlation - avg_historical
        
        # Detect breakdown
        if avg_historical > 0.5 and change < self.REGIME_THRESHOLDS["breakdown"]:
            significance = "high" if change < -0.6 else "medium"
            insight = self._generate_breakdown_insight(entity_a, entity_b, avg_historical, recent.correlation)
            
            regime_changes.append(CorrelationRegimeChange(
                entity_a=entity_a,
                entity_b=entity_b,
                signal_type=signal_type,
                change_type="breakdown",
                previous_correlation=avg_historical,
                current_correlation=recent.correlation,
                change_magnitude=change,
                detected_date=recent.date,
                window_days=window_days,
                significance=significance,
                actionable_insight=insight
            ))
        
        # Detect emergence
        elif avg_historical < 0.3 and change > self.REGIME_THRESHOLDS["emergence"]:
            significance = "high" if change > 0.6 else "medium"
            insight = self._generate_emergence_insight(entity_a, entity_b, avg_historical, recent.correlation)
            
            regime_changes.append(CorrelationRegimeChange(
                entity_a=entity_a,
                entity_b=entity_b,
                signal_type=signal_type,
                change_type="emergence",
                previous_correlation=avg_historical,
                current_correlation=recent.correlation,
                change_magnitude=change,
                detected_date=recent.date,
                window_days=window_days,
                significance=significance,
                actionable_insight=insight
            ))
        
        # Detect reversal
        elif (avg_historical > 0.3 and recent.correlation < -0.3) or \
             (avg_historical < -0.3 and recent.correlation > 0.3):
            significance = "high"
            insight = self._generate_reversal_insight(entity_a, entity_b, avg_historical, recent.correlation)
            
            regime_changes.append(CorrelationRegimeChange(
                entity_a=entity_a,
                entity_b=entity_b,
                signal_type=signal_type,
                change_type="reversal",
                previous_correlation=avg_historical,
                current_correlation=recent.correlation,
                change_magnitude=abs(change),
                detected_date=recent.date,
                window_days=window_days,
                significance=significance,
                actionable_insight=insight
            ))
        
        # Store regime changes
        self._store_regime_changes(regime_changes)
        
        return regime_changes

    def _generate_breakdown_insight(
        self,
        entity_a: str,
        entity_b: str,
        old_corr: float,
        new_corr: float
    ) -> str:
        """Generate actionable insight for correlation breakdown."""
        return (
            f"{entity_a.upper()} and {entity_b.upper()} signals have decoupled. "
            f"Historically correlated ({old_corr:.2f}), now diverging ({new_corr:.2f}). "
            f"This may indicate independent drivers - evaluate each separately."
        )

    def _generate_emergence_insight(
        self,
        entity_a: str,
        entity_b: str,
        old_corr: float,
        new_corr: float
    ) -> str:
        """Generate actionable insight for correlation emergence."""
        return (
            f"New correlation emerging between {entity_a.upper()} and {entity_b.upper()}. "
            f"Previously uncorrelated ({old_corr:.2f}), now moving together ({new_corr:.2f}). "
            f"Consider: shared sector exposure, competitive dynamics, or common news drivers."
        )

    def _generate_reversal_insight(
        self,
        entity_a: str,
        entity_b: str,
        old_corr: float,
        new_corr: float
    ) -> str:
        """Generate actionable insight for correlation reversal."""
        return (
            f"CRITICAL: {entity_a.upper()} and {entity_b.upper()} correlation has reversed. "
            f"From {old_corr:.2f} to {new_corr:.2f}. "
            f"This is rare and significant - investigate underlying cause immediately."
        )

    def _store_regime_changes(self, changes: List[CorrelationRegimeChange]):
        """Store regime changes to database."""
        if not changes:
            return
            
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        for rc in changes:
            cursor.execute("""
                INSERT INTO correlation_regime_changes
                (entity_a, entity_b, signal_type, change_type, previous_correlation,
                 current_correlation, change_magnitude, detected_date, window_days,
                 significance, actionable_insight)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (rc.entity_a, rc.entity_b, rc.signal_type, rc.change_type,
                  rc.previous_correlation, rc.current_correlation, rc.change_magnitude,
                  rc.detected_date.isoformat(), rc.window_days, rc.significance,
                  rc.actionable_insight))
        
        conn.commit()
        conn.close()

    def check_divergence_alerts(
        self,
        entity_a: str,
        entity_b: str,
        signal_type: str = "composite"
    ) -> Optional[CorrelationDivergenceAlert]:
        """
        Check if historically correlated entities are now diverging.
        
        Compares short-term (7-day) vs long-term (90-day) correlations.
        
        Args:
            entity_a: First entity
            entity_b: Second entity
            signal_type: Signal type
            
        Returns:
            CorrelationDivergenceAlert if divergence detected, None otherwise
        """
        # Calculate short and long term correlations
        short_corr = self.calculate_rolling_correlation(
            entity_a, entity_b, signal_type, 
            window_days=self.WINDOWS["short"]
        )
        long_corr = self.calculate_rolling_correlation(
            entity_a, entity_b, signal_type,
            window_days=self.WINDOWS["long"]
        )
        
        if short_corr is None or long_corr is None:
            return None
        
        # Calculate divergence
        divergence = abs(short_corr.correlation - long_corr.correlation)
        
        # Determine if this is significant
        if divergence < self.DIVERGENCE_THRESHOLDS["warning"]:
            return None
        
        # Determine direction
        if short_corr.correlation < long_corr.correlation - 0.2:
            direction = "weakening"
        elif short_corr.correlation > long_corr.correlation + 0.2:
            direction = "strengthening"
        elif (long_corr.correlation > 0 and short_corr.correlation < 0) or \
             (long_corr.correlation < 0 and short_corr.correlation > 0):
            direction = "reversing"
        else:
            direction = "shifting"
        
        # Determine alert level
        if divergence >= self.DIVERGENCE_THRESHOLDS["critical"]:
            alert_level = "critical"
        else:
            alert_level = "warning"
        
        # Generate message
        message = self._generate_divergence_message(
            entity_a, entity_b, long_corr.correlation,
            short_corr.correlation, direction, alert_level
        )
        
        alert = CorrelationDivergenceAlert(
            entity_a=entity_a,
            entity_b=entity_b,
            signal_type=signal_type,
            historical_correlation=long_corr.correlation,
            recent_correlation=short_corr.correlation,
            divergence_magnitude=divergence,
            direction=direction,
            alert_level=alert_level,
            alert_message=message
        )
        
        # Store alert
        self._store_divergence_alert(alert)
        
        return alert

    def _generate_divergence_message(
        self,
        entity_a: str,
        entity_b: str,
        hist_corr: float,
        recent_corr: float,
        direction: str,
        level: str
    ) -> str:
        """Generate human-readable divergence alert message."""
        severity = "⚠️" if level == "warning" else "🚨"
        
        if direction == "weakening":
            action = "Consider whether past patterns still hold"
        elif direction == "strengthening":
            action = "New correlation may signal shared exposure"
        elif direction == "reversing":
            action = "Investigate fundamental change immediately"
        else:
            action = "Monitor for continuation"
        
        return (
            f"{severity} {entity_a.upper()}-{entity_b.upper()} correlation is {direction}. "
            f"Long-term: {hist_corr:.2f}, Recent: {recent_corr:.2f}. "
            f"{action}."
        )

    def _store_divergence_alert(self, alert: CorrelationDivergenceAlert):
        """Store divergence alert to database."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        # First, deactivate any existing active alerts for this pair
        cursor.execute("""
            UPDATE correlation_divergence_alerts
            SET is_active = 0, resolved_at = ?
            WHERE entity_a = ? AND entity_b = ? AND signal_type = ? AND is_active = 1
        """, (datetime.utcnow().isoformat(), alert.entity_a, alert.entity_b, alert.signal_type))
        
        # Insert new alert
        cursor.execute("""
            INSERT INTO correlation_divergence_alerts
            (entity_a, entity_b, signal_type, historical_correlation, recent_correlation,
             divergence_magnitude, direction, alert_level, alert_message, detected_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (alert.entity_a, alert.entity_b, alert.signal_type, alert.historical_correlation,
              alert.recent_correlation, alert.divergence_magnitude, alert.direction,
              alert.alert_level, alert.alert_message, alert.detected_at.isoformat()))
        
        conn.commit()
        conn.close()

    def get_active_divergence_alerts(
        self,
        alert_level: Optional[str] = None
    ) -> List[CorrelationDivergenceAlert]:
        """Get all active divergence alerts."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        if alert_level:
            cursor.execute("""
                SELECT * FROM correlation_divergence_alerts
                WHERE is_active = 1 AND alert_level = ?
                ORDER BY detected_at DESC
            """, (alert_level,))
        else:
            cursor.execute("""
                SELECT * FROM correlation_divergence_alerts
                WHERE is_active = 1
                ORDER BY alert_level DESC, detected_at DESC
            """)
        
        alerts = []
        for row in cursor.fetchall():
            alerts.append(CorrelationDivergenceAlert(
                entity_a=row["entity_a"],
                entity_b=row["entity_b"],
                signal_type=row["signal_type"],
                historical_correlation=row["historical_correlation"],
                recent_correlation=row["recent_correlation"],
                divergence_magnitude=row["divergence_magnitude"],
                direction=row["direction"],
                alert_level=row["alert_level"],
                alert_message=row["alert_message"],
                detected_at=datetime.fromisoformat(row["detected_at"])
            ))
        
        conn.close()
        return alerts

    def get_recent_regime_changes(
        self,
        days: int = 7,
        significance: Optional[str] = None
    ) -> List[CorrelationRegimeChange]:
        """Get recent regime changes."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        cutoff = (date.today() - timedelta(days=days)).isoformat()
        
        if significance:
            cursor.execute("""
                SELECT * FROM correlation_regime_changes
                WHERE detected_date >= ? AND significance = ?
                ORDER BY detected_date DESC
            """, (cutoff, significance))
        else:
            cursor.execute("""
                SELECT * FROM correlation_regime_changes
                WHERE detected_date >= ?
                ORDER BY significance DESC, detected_date DESC
            """, (cutoff,))
        
        changes = []
        for row in cursor.fetchall():
            changes.append(CorrelationRegimeChange(
                entity_a=row["entity_a"],
                entity_b=row["entity_b"],
                signal_type=row["signal_type"],
                change_type=row["change_type"],
                previous_correlation=row["previous_correlation"],
                current_correlation=row["current_correlation"],
                change_magnitude=row["change_magnitude"],
                detected_date=date.fromisoformat(row["detected_date"]),
                window_days=row["window_days"],
                significance=row["significance"],
                actionable_insight=row["actionable_insight"] or ""
            ))
        
        conn.close()
        return changes

    def get_rolling_correlation_history(
        self,
        entity_a: str,
        entity_b: str,
        signal_type: str = "composite",
        window_days: int = 30,
        history_days: int = 90
    ) -> pd.DataFrame:
        """
        Get historical rolling correlations for a pair.
        
        Returns DataFrame suitable for time series visualization.
        """
        conn = self._get_correlations_connection()
        
        cutoff = (date.today() - timedelta(days=history_days)).isoformat()
        
        df = pd.read_sql_query("""
            SELECT calculation_date as date, correlation
            FROM rolling_correlations
            WHERE entity_a = ? AND entity_b = ?
              AND signal_type = ? AND window_days = ?
              AND calculation_date >= ?
            ORDER BY calculation_date ASC
        """, conn, params=(entity_a, entity_b, signal_type, window_days, cutoff))
        
        conn.close()
        
        if df.empty:
            return df
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        return df


def run_rolling_correlation_scan(
    entity_pairs: List[Tuple[str, str]],
    signal_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Run rolling correlation scan for entity pairs.
    
    Args:
        entity_pairs: List of (entity_a, entity_b) tuples
        signal_types: Signal types to analyze
        
    Returns:
        Summary of scan results
    """
    tracker = RollingCorrelationTracker()
    
    if signal_types is None:
        signal_types = ["composite", "media"]
    
    results = {
        "pairs_scanned": len(entity_pairs),
        "regime_changes": [],
        "divergence_alerts": [],
    }
    
    for entity_a, entity_b in entity_pairs:
        for signal_type in signal_types:
            # Check for regime changes
            changes = tracker.detect_regime_changes(entity_a, entity_b, signal_type)
            for change in changes:
                results["regime_changes"].append(change.to_dict())
            
            # Check for divergence
            alert = tracker.check_divergence_alerts(entity_a, entity_b, signal_type)
            if alert:
                results["divergence_alerts"].append(alert.to_dict())
    
    logger.info(f"Rolling correlation scan complete: {len(results['regime_changes'])} regime changes, "
                f"{len(results['divergence_alerts'])} divergence alerts")
    
    return results


if __name__ == "__main__":
    # Test rolling correlation tracker
    print("Testing RollingCorrelationTracker")
    print("=" * 50)
    
    tracker = RollingCorrelationTracker()
    
    # Test rolling correlation calculation
    print("\nCalculating NVDA-AMD rolling correlations...")
    correlations = tracker.calculate_rolling_correlation_series(
        "nvidia", "amd", "composite", window_days=30, history_days=90
    )
    print(f"Generated {len(correlations)} correlation points")
    
    if correlations:
        print(f"Latest correlation: {correlations[-1].correlation:.3f}")
    
    # Test regime change detection
    print("\nChecking for regime changes...")
    changes = tracker.detect_regime_changes("nvidia", "amd")
    print(f"Found {len(changes)} regime changes")
    
    for change in changes:
        print(f"  {change.change_type}: {change.actionable_insight}")
    
    # Test divergence alerts
    print("\nChecking for divergence alerts...")
    alert = tracker.check_divergence_alerts("nvidia", "amd")
    if alert:
        print(f"  Alert: {alert.alert_message}")
    else:
        print("  No divergence detected")
