"""
Cross-Entity Correlation Analysis

Identifies signal relationships between entities for actionable insights:
- Entity-Entity: How do NVDA signals correlate with AMD signals?
- Signal-Signal: How does media sentiment correlate with price movement?
- Sector correlations: AI infrastructure vs AI applications
- Lead-lag relationships: Which entity signals lead others?
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
from scipy.signal import correlate

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    HAS_YFINANCE = False


@dataclass
class EntityCorrelation:
    """Correlation between two entities on a specific signal type."""
    entity_a: str
    entity_b: str
    signal_type: str  # e.g., "media", "technical", "composite"
    correlation: float
    p_value: Optional[float] = None
    sample_size: int = 0
    window_days: int = 30
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_a": self.entity_a,
            "entity_b": self.entity_b,
            "signal_type": self.signal_type,
            "correlation": round(self.correlation, 4),
            "p_value": round(self.p_value, 4) if self.p_value else None,
            "sample_size": self.sample_size,
            "window_days": self.window_days,
            "calculated_at": self.calculated_at.isoformat(),
        }


@dataclass
class SignalCorrelation:
    """Correlation between two signal types for a single entity."""
    entity_id: str
    signal_a: str
    signal_b: str
    correlation: float
    p_value: Optional[float] = None
    sample_size: int = 0
    lag_days: int = 0  # Positive = signal_a leads signal_b
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "signal_a": self.signal_a,
            "signal_b": self.signal_b,
            "correlation": round(self.correlation, 4),
            "p_value": round(self.p_value, 4) if self.p_value else None,
            "sample_size": self.sample_size,
            "lag_days": self.lag_days,
            "calculated_at": self.calculated_at.isoformat(),
        }


@dataclass
class LeadLagRelationship:
    """Lead-lag relationship between two entities."""
    leader_entity: str
    follower_entity: str
    signal_type: str
    optimal_lag_days: int
    correlation_at_lag: float
    correlation_at_zero: float
    predictive_power: float  # 0-1, how much better the lagged correlation is
    confidence: str  # "high", "medium", "low"
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "leader_entity": self.leader_entity,
            "follower_entity": self.follower_entity,
            "signal_type": self.signal_type,
            "optimal_lag_days": self.optimal_lag_days,
            "correlation_at_lag": round(self.correlation_at_lag, 4),
            "correlation_at_zero": round(self.correlation_at_zero, 4),
            "predictive_power": round(self.predictive_power, 4),
            "confidence": self.confidence,
            "calculated_at": self.calculated_at.isoformat(),
        }


@dataclass 
class SectorCorrelation:
    """Correlation between sector groupings."""
    sector_a: str
    sector_b: str
    correlation: float
    entities_a: List[str] = field(default_factory=list)
    entities_b: List[str] = field(default_factory=list)
    calculated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector_a": self.sector_a,
            "sector_b": self.sector_b,
            "correlation": round(self.correlation, 4),
            "entities_a": self.entities_a,
            "entities_b": self.entities_b,
            "calculated_at": self.calculated_at.isoformat(),
        }


# Sector definitions for AI companies
SECTOR_DEFINITIONS = {
    "ai_infrastructure": {
        "entities": ["nvidia", "amd", "intel", "tsmc", "asml", "broadcom"],
        "description": "AI chip and infrastructure providers"
    },
    "ai_hyperscalers": {
        "entities": ["microsoft", "google", "amazon", "meta", "oracle"],
        "description": "Cloud and AI platform providers"
    },
    "ai_applications": {
        "entities": ["salesforce", "servicenow", "workday", "adobe", "snowflake"],
        "description": "Enterprise AI application providers"
    },
    "ai_pure_play": {
        "entities": ["openai", "anthropic", "cohere", "stability-ai", "mistral"],
        "description": "Pure-play AI model companies"
    },
    "ai_security": {
        "entities": ["crowdstrike", "palo-alto", "fortinet", "zscaler", "sentinelone"],
        "description": "AI-powered security companies"
    },
    "ai_data": {
        "entities": ["palantir", "databricks", "datadog", "mongodb", "elastic"],
        "description": "AI data infrastructure companies"
    },
    "ai_robotics": {
        "entities": ["tesla", "boston-dynamics", "intuitive-surgical", "symbotic"],
        "description": "AI robotics and automation"
    },
}


class CorrelationAnalyzer:
    """
    Analyzes correlations between entities and signals for actionable insights.
    
    Key capabilities:
    - Entity-to-entity correlation matrices
    - Within-entity signal correlations
    - Lead-lag relationship discovery
    - Sector-level correlation analysis
    - Signal propagation prediction
    """
    
    def __init__(
        self,
        signals_db_path: Optional[Path] = None,
        correlations_db_path: Optional[Path] = None,
        asset_mapping_path: Optional[Path] = None,
    ):
        """
        Initialize the correlation analyzer.
        
        Args:
            signals_db_path: Path to signals.db for signal data
            correlations_db_path: Path to correlations.db for storing results
            asset_mapping_path: Path to asset mapping for tickers
        """
        base_path = Path(__file__).parent.parent / "data"
        
        self.signals_db_path = signals_db_path or (base_path / "signals.db")
        self.correlations_db_path = correlations_db_path or (base_path / "correlations.db")
        self.asset_mapping_path = asset_mapping_path or (base_path / "asset_mapping.json")
        
        self.asset_mapping = self._load_asset_mapping()
        self._ensure_correlation_tables()
        
        # Cache for price data
        self._price_cache: Dict[str, pd.DataFrame] = {}
        
        logger.info(f"CorrelationAnalyzer initialized")

    def _load_asset_mapping(self) -> Dict[str, Any]:
        """Load asset mapping for ticker lookups."""
        try:
            with open(self.asset_mapping_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Could not load asset mapping: {e}")
            return {"entities": {}}

    def _ensure_correlation_tables(self):
        """Create correlation database tables if they don't exist."""
        conn = sqlite3.connect(self.correlations_db_path)
        cursor = conn.cursor()
        
        # Entity pair correlations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a TEXT NOT NULL,
                entity_b TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                correlation REAL NOT NULL,
                p_value REAL,
                sample_size INTEGER DEFAULT 0,
                window_days INTEGER DEFAULT 30,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_a, entity_b, signal_type, window_days)
            )
        """)
        
        # Signal type correlations (within entity)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT NOT NULL,
                signal_a TEXT NOT NULL,
                signal_b TEXT NOT NULL,
                correlation REAL NOT NULL,
                p_value REAL,
                sample_size INTEGER DEFAULT 0,
                lag_days INTEGER DEFAULT 0,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(entity_id, signal_a, signal_b, lag_days)
            )
        """)
        
        # Lead-lag relationships
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lead_lag_relationships (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                leader_entity TEXT NOT NULL,
                follower_entity TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                optimal_lag_days INTEGER NOT NULL,
                correlation_at_lag REAL NOT NULL,
                correlation_at_zero REAL NOT NULL,
                predictive_power REAL NOT NULL,
                confidence TEXT NOT NULL,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(leader_entity, follower_entity, signal_type)
            )
        """)
        
        # Sector correlations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sector_correlations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sector_a TEXT NOT NULL,
                sector_b TEXT NOT NULL,
                correlation REAL NOT NULL,
                entities_a TEXT,
                entities_b TEXT,
                calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sector_a, sector_b)
            )
        """)
        
        # Historical correlation snapshots (for rolling correlations)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS correlation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_a TEXT NOT NULL,
                entity_b TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                correlation REAL NOT NULL,
                window_days INTEGER NOT NULL,
                snapshot_date DATE NOT NULL,
                UNIQUE(entity_a, entity_b, signal_type, window_days, snapshot_date)
            )
        """)
        
        # Create indices
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ec_entities ON entity_correlations(entity_a, entity_b)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ec_signal ON entity_correlations(signal_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_sc_entity ON signal_correlations(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ll_leader ON lead_lag_relationships(leader_entity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ch_date ON correlation_history(snapshot_date)")
        
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

    def _get_entity_signal_history(
        self,
        entity_id: str,
        signal_type: str,
        days: int = 90
    ) -> pd.DataFrame:
        """
        Get historical signal values for an entity.
        
        Args:
            entity_id: Entity canonical ID
            signal_type: One of 'technical', 'company', 'financial', 'product', 'media', 'composite'
            days: Number of days of history
            
        Returns:
            DataFrame with date index and signal values
        """
        conn = self._get_signals_connection()
        
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
        
        # Map signal type to column
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
            WHERE entity_id = ? AND as_of >= ?
            ORDER BY as_of ASC
        """
        
        df = pd.read_sql_query(query, conn, params=(entity_id, cutoff))
        conn.close()
        
        if df.empty:
            return pd.DataFrame(columns=['date', 'value'])
        
        df['date'] = pd.to_datetime(df['date'])
        df = df.set_index('date')
        
        # Resample to daily, forward fill missing days
        df = df.resample('D').last().ffill()
        
        return df

    def entity_correlation_matrix(
        self,
        entities: List[str],
        signal_type: str = "composite",
        window_days: int = 30,
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix between entities on a signal type.
        
        Args:
            entities: List of entity canonical IDs
            signal_type: Signal type to correlate
            window_days: Historical window
            
        Returns:
            DataFrame correlation matrix
        """
        # Fetch data for all entities
        data = {}
        for entity_id in entities:
            df = self._get_entity_signal_history(entity_id, signal_type, window_days)
            if not df.empty:
                data[entity_id] = df['value']
        
        if len(data) < 2:
            logger.warning("Not enough entities with data for correlation matrix")
            return pd.DataFrame()
        
        # Combine into single DataFrame
        combined = pd.DataFrame(data)
        combined = combined.dropna(how='all')
        
        if len(combined) < 5:
            logger.warning("Not enough data points for correlation matrix")
            return pd.DataFrame()
        
        # Calculate correlation matrix
        corr_matrix = combined.corr(method='pearson')
        
        # Store results
        self._store_entity_correlations(corr_matrix, signal_type, window_days)
        
        return corr_matrix

    def _store_entity_correlations(
        self,
        corr_matrix: pd.DataFrame,
        signal_type: str,
        window_days: int
    ):
        """Store entity correlations to database."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        for entity_a in corr_matrix.index:
            for entity_b in corr_matrix.columns:
                if entity_a >= entity_b:  # Only store upper triangle
                    continue
                    
                corr = corr_matrix.loc[entity_a, entity_b]
                if pd.isna(corr):
                    continue
                
                cursor.execute("""
                    INSERT OR REPLACE INTO entity_correlations
                    (entity_a, entity_b, signal_type, correlation, window_days, calculated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (entity_a, entity_b, signal_type, float(corr), window_days, 
                      datetime.utcnow().isoformat()))
        
        conn.commit()
        conn.close()

    def signal_correlation(
        self,
        entity_id: str,
        signal_a: str,
        signal_b: str,
        lag_days: int = 0,
        window_days: int = 90
    ) -> SignalCorrelation:
        """
        Calculate correlation between two signal types for an entity.
        
        Args:
            entity_id: Entity canonical ID
            signal_a: First signal type
            signal_b: Second signal type
            lag_days: Days to lag signal_a (positive = a leads b)
            window_days: Historical window
            
        Returns:
            SignalCorrelation result
        """
        df_a = self._get_entity_signal_history(entity_id, signal_a, window_days)
        df_b = self._get_entity_signal_history(entity_id, signal_b, window_days)
        
        if df_a.empty or df_b.empty:
            return SignalCorrelation(
                entity_id=entity_id,
                signal_a=signal_a,
                signal_b=signal_b,
                correlation=0.0,
                sample_size=0,
                lag_days=lag_days
            )
        
        # Apply lag
        if lag_days != 0:
            df_a = df_a.shift(lag_days)
        
        # Align series
        combined = pd.concat([df_a['value'], df_b['value']], axis=1)
        combined.columns = ['a', 'b']
        combined = combined.dropna()
        
        if len(combined) < 10:
            return SignalCorrelation(
                entity_id=entity_id,
                signal_a=signal_a,
                signal_b=signal_b,
                correlation=0.0,
                sample_size=len(combined),
                lag_days=lag_days
            )
        
        # Calculate correlation
        corr, p_value = stats.pearsonr(combined['a'], combined['b'])
        
        result = SignalCorrelation(
            entity_id=entity_id,
            signal_a=signal_a,
            signal_b=signal_b,
            correlation=float(corr),
            p_value=float(p_value),
            sample_size=len(combined),
            lag_days=lag_days
        )
        
        # Store result
        self._store_signal_correlation(result)
        
        return result

    def _store_signal_correlation(self, result: SignalCorrelation):
        """Store signal correlation to database."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO signal_correlations
            (entity_id, signal_a, signal_b, correlation, p_value, sample_size, lag_days, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (result.entity_id, result.signal_a, result.signal_b, result.correlation,
              result.p_value, result.sample_size, result.lag_days, result.calculated_at.isoformat()))
        
        conn.commit()
        conn.close()

    def find_lead_lag(
        self,
        entity_a: str,
        entity_b: str,
        signal_type: str = "composite",
        max_lag_days: int = 30
    ) -> LeadLagRelationship:
        """
        Find lead-lag relationship between two entities.
        
        Tests different lags to find if one entity's signals lead another's.
        
        Args:
            entity_a: First entity
            entity_b: Second entity
            signal_type: Signal type to analyze
            max_lag_days: Maximum lag to test
            
        Returns:
            LeadLagRelationship result
        """
        df_a = self._get_entity_signal_history(entity_a, signal_type, max_lag_days * 3)
        df_b = self._get_entity_signal_history(entity_b, signal_type, max_lag_days * 3)
        
        if df_a.empty or df_b.empty:
            return LeadLagRelationship(
                leader_entity=entity_a,
                follower_entity=entity_b,
                signal_type=signal_type,
                optimal_lag_days=0,
                correlation_at_lag=0.0,
                correlation_at_zero=0.0,
                predictive_power=0.0,
                confidence="low"
            )
        
        # Align series
        combined = pd.concat([df_a['value'], df_b['value']], axis=1)
        combined.columns = ['a', 'b']
        combined = combined.dropna()
        
        if len(combined) < max_lag_days + 10:
            return LeadLagRelationship(
                leader_entity=entity_a,
                follower_entity=entity_b,
                signal_type=signal_type,
                optimal_lag_days=0,
                correlation_at_lag=0.0,
                correlation_at_zero=0.0,
                predictive_power=0.0,
                confidence="low"
            )
        
        # Test different lags
        correlations = {}
        for lag in range(-max_lag_days, max_lag_days + 1):
            if lag == 0:
                aligned_a = combined['a']
                aligned_b = combined['b']
            elif lag > 0:
                # A leads B (shift A forward)
                aligned_a = combined['a'].shift(lag)
                aligned_b = combined['b']
            else:
                # B leads A (shift B forward)
                aligned_a = combined['a']
                aligned_b = combined['b'].shift(-lag)
            
            valid = pd.concat([aligned_a, aligned_b], axis=1).dropna()
            if len(valid) < 10:
                continue
                
            corr, _ = stats.pearsonr(valid.iloc[:, 0], valid.iloc[:, 1])
            correlations[lag] = float(corr)
        
        if not correlations:
            return LeadLagRelationship(
                leader_entity=entity_a,
                follower_entity=entity_b,
                signal_type=signal_type,
                optimal_lag_days=0,
                correlation_at_lag=0.0,
                correlation_at_zero=0.0,
                predictive_power=0.0,
                confidence="low"
            )
        
        # Find optimal lag
        optimal_lag = max(correlations.keys(), key=lambda k: abs(correlations[k]))
        corr_at_lag = correlations[optimal_lag]
        corr_at_zero = correlations.get(0, 0.0)
        
        # Calculate predictive power
        if abs(corr_at_lag) > abs(corr_at_zero):
            predictive_power = abs(corr_at_lag) - abs(corr_at_zero)
        else:
            predictive_power = 0.0
        
        # Determine confidence
        if abs(corr_at_lag) > 0.6 and predictive_power > 0.2:
            confidence = "high"
        elif abs(corr_at_lag) > 0.4 and predictive_power > 0.1:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Determine leader/follower
        if optimal_lag > 0:
            leader, follower = entity_a, entity_b
        else:
            leader, follower = entity_b, entity_a
            optimal_lag = -optimal_lag
        
        result = LeadLagRelationship(
            leader_entity=leader,
            follower_entity=follower,
            signal_type=signal_type,
            optimal_lag_days=optimal_lag,
            correlation_at_lag=corr_at_lag,
            correlation_at_zero=corr_at_zero,
            predictive_power=predictive_power,
            confidence=confidence
        )
        
        # Store result
        self._store_lead_lag(result)
        
        return result

    def _store_lead_lag(self, result: LeadLagRelationship):
        """Store lead-lag relationship to database."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO lead_lag_relationships
            (leader_entity, follower_entity, signal_type, optimal_lag_days,
             correlation_at_lag, correlation_at_zero, predictive_power, confidence, calculated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (result.leader_entity, result.follower_entity, result.signal_type,
              result.optimal_lag_days, result.correlation_at_lag, result.correlation_at_zero,
              result.predictive_power, result.confidence, result.calculated_at.isoformat()))
        
        conn.commit()
        conn.close()

    def sector_heatmap(
        self,
        signal_type: str = "composite",
        window_days: int = 30
    ) -> pd.DataFrame:
        """
        Calculate correlation matrix between sectors.
        
        Aggregates entity signals by sector and computes correlations.
        
        Args:
            signal_type: Signal type to use
            window_days: Historical window
            
        Returns:
            DataFrame sector correlation matrix
        """
        sector_signals = {}
        
        for sector_name, sector_config in SECTOR_DEFINITIONS.items():
            sector_data = []
            
            for entity_id in sector_config["entities"]:
                df = self._get_entity_signal_history(entity_id, signal_type, window_days)
                if not df.empty:
                    sector_data.append(df['value'])
            
            if sector_data:
                # Average signals across sector entities
                combined = pd.concat(sector_data, axis=1)
                sector_signals[sector_name] = combined.mean(axis=1)
        
        if len(sector_signals) < 2:
            logger.warning("Not enough sectors with data for heatmap")
            return pd.DataFrame()
        
        # Build DataFrame and calculate correlations
        combined = pd.DataFrame(sector_signals)
        combined = combined.dropna(how='all')
        
        if len(combined) < 5:
            return pd.DataFrame()
        
        corr_matrix = combined.corr(method='pearson')
        
        # Store sector correlations
        self._store_sector_correlations(corr_matrix)
        
        return corr_matrix

    def _store_sector_correlations(self, corr_matrix: pd.DataFrame):
        """Store sector correlations to database."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        for sector_a in corr_matrix.index:
            for sector_b in corr_matrix.columns:
                if sector_a >= sector_b:
                    continue
                    
                corr = corr_matrix.loc[sector_a, sector_b]
                if pd.isna(corr):
                    continue
                
                entities_a = SECTOR_DEFINITIONS.get(sector_a, {}).get("entities", [])
                entities_b = SECTOR_DEFINITIONS.get(sector_b, {}).get("entities", [])
                
                cursor.execute("""
                    INSERT OR REPLACE INTO sector_correlations
                    (sector_a, sector_b, correlation, entities_a, entities_b, calculated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (sector_a, sector_b, float(corr), json.dumps(entities_a),
                      json.dumps(entities_b), datetime.utcnow().isoformat()))
        
        conn.commit()
        conn.close()

    def get_entity_correlations(
        self,
        entity_id: str,
        signal_type: str = "composite",
        min_correlation: float = 0.3
    ) -> List[EntityCorrelation]:
        """
        Get all significant correlations for an entity.
        
        Args:
            entity_id: Entity to query
            signal_type: Signal type filter
            min_correlation: Minimum absolute correlation
            
        Returns:
            List of EntityCorrelation objects
        """
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM entity_correlations
            WHERE (entity_a = ? OR entity_b = ?)
              AND signal_type = ?
              AND ABS(correlation) >= ?
            ORDER BY ABS(correlation) DESC
        """, (entity_id, entity_id, signal_type, min_correlation))
        
        results = []
        for row in cursor.fetchall():
            results.append(EntityCorrelation(
                entity_a=row["entity_a"],
                entity_b=row["entity_b"],
                signal_type=row["signal_type"],
                correlation=row["correlation"],
                p_value=row["p_value"],
                sample_size=row["sample_size"],
                window_days=row["window_days"],
                calculated_at=datetime.fromisoformat(row["calculated_at"]) if row["calculated_at"] else datetime.utcnow()
            ))
        
        conn.close()
        return results

    def get_lead_lag_for_entity(self, entity_id: str) -> Dict[str, List[LeadLagRelationship]]:
        """
        Get lead-lag relationships where entity is leader or follower.
        
        Args:
            entity_id: Entity to query
            
        Returns:
            Dict with 'as_leader' and 'as_follower' lists
        """
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        results = {"as_leader": [], "as_follower": []}
        
        # As leader
        cursor.execute("""
            SELECT * FROM lead_lag_relationships
            WHERE leader_entity = ?
            ORDER BY predictive_power DESC
        """, (entity_id,))
        
        for row in cursor.fetchall():
            results["as_leader"].append(LeadLagRelationship(
                leader_entity=row["leader_entity"],
                follower_entity=row["follower_entity"],
                signal_type=row["signal_type"],
                optimal_lag_days=row["optimal_lag_days"],
                correlation_at_lag=row["correlation_at_lag"],
                correlation_at_zero=row["correlation_at_zero"],
                predictive_power=row["predictive_power"],
                confidence=row["confidence"],
                calculated_at=datetime.fromisoformat(row["calculated_at"]) if row["calculated_at"] else datetime.utcnow()
            ))
        
        # As follower
        cursor.execute("""
            SELECT * FROM lead_lag_relationships
            WHERE follower_entity = ?
            ORDER BY predictive_power DESC
        """, (entity_id,))
        
        for row in cursor.fetchall():
            results["as_follower"].append(LeadLagRelationship(
                leader_entity=row["leader_entity"],
                follower_entity=row["follower_entity"],
                signal_type=row["signal_type"],
                optimal_lag_days=row["optimal_lag_days"],
                correlation_at_lag=row["correlation_at_lag"],
                correlation_at_zero=row["correlation_at_zero"],
                predictive_power=row["predictive_power"],
                confidence=row["confidence"],
                calculated_at=datetime.fromisoformat(row["calculated_at"]) if row["calculated_at"] else datetime.utcnow()
            ))
        
        conn.close()
        return results

    def get_full_correlation_matrix(self, signal_type: str = "composite") -> pd.DataFrame:
        """Get the full entity correlation matrix from database."""
        conn = self._get_correlations_connection()
        
        df = pd.read_sql_query("""
            SELECT entity_a, entity_b, correlation
            FROM entity_correlations
            WHERE signal_type = ?
            ORDER BY entity_a, entity_b
        """, conn, params=(signal_type,))
        
        conn.close()
        
        if df.empty:
            return pd.DataFrame()
        
        # Build symmetric matrix
        entities = sorted(set(df['entity_a'].tolist() + df['entity_b'].tolist()))
        matrix = pd.DataFrame(1.0, index=entities, columns=entities)
        
        for _, row in df.iterrows():
            matrix.loc[row['entity_a'], row['entity_b']] = row['correlation']
            matrix.loc[row['entity_b'], row['entity_a']] = row['correlation']
        
        return matrix

    def get_sector_heatmap(self) -> pd.DataFrame:
        """Get the stored sector correlation matrix."""
        conn = self._get_correlations_connection()
        
        df = pd.read_sql_query("""
            SELECT sector_a, sector_b, correlation
            FROM sector_correlations
            ORDER BY sector_a, sector_b
        """, conn)
        
        conn.close()
        
        if df.empty:
            return pd.DataFrame()
        
        # Build symmetric matrix
        sectors = sorted(set(df['sector_a'].tolist() + df['sector_b'].tolist()))
        matrix = pd.DataFrame(1.0, index=sectors, columns=sectors)
        
        for _, row in df.iterrows():
            matrix.loc[row['sector_a'], row['sector_b']] = row['correlation']
            matrix.loc[row['sector_b'], row['sector_a']] = row['correlation']
        
        return matrix

    def get_all_lead_lag_relationships(
        self,
        min_predictive_power: float = 0.1,
        min_confidence: str = "medium"
    ) -> List[LeadLagRelationship]:
        """
        Get all lead-lag relationships meeting criteria.
        
        Args:
            min_predictive_power: Minimum predictive power
            min_confidence: Minimum confidence level ('low', 'medium', 'high')
            
        Returns:
            List of LeadLagRelationship objects
        """
        confidence_order = {"low": 0, "medium": 1, "high": 2}
        min_conf_value = confidence_order.get(min_confidence, 0)
        
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM lead_lag_relationships
            WHERE predictive_power >= ?
            ORDER BY predictive_power DESC
        """, (min_predictive_power,))
        
        results = []
        for row in cursor.fetchall():
            conf_value = confidence_order.get(row["confidence"], 0)
            if conf_value >= min_conf_value:
                results.append(LeadLagRelationship(
                    leader_entity=row["leader_entity"],
                    follower_entity=row["follower_entity"],
                    signal_type=row["signal_type"],
                    optimal_lag_days=row["optimal_lag_days"],
                    correlation_at_lag=row["correlation_at_lag"],
                    correlation_at_zero=row["correlation_at_zero"],
                    predictive_power=row["predictive_power"],
                    confidence=row["confidence"],
                    calculated_at=datetime.fromisoformat(row["calculated_at"]) if row["calculated_at"] else datetime.utcnow()
                ))
        
        conn.close()
        return results


def run_full_correlation_analysis(
    entities: Optional[List[str]] = None,
    signal_types: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Run complete correlation analysis for all or specified entities.
    
    Args:
        entities: List of entities to analyze (None = all)
        signal_types: Signal types to analyze
        
    Returns:
        Dict with analysis results summary
    """
    analyzer = CorrelationAnalyzer()
    
    if signal_types is None:
        signal_types = ["composite", "media", "technical", "financial"]
    
    if entities is None:
        # Get all entities from signals database
        conn = analyzer._get_signals_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT entity_id FROM signal_profiles")
        entities = [row[0] for row in cursor.fetchall()]
        conn.close()
    
    results = {
        "entities_analyzed": len(entities),
        "signal_types": signal_types,
        "correlation_matrices": {},
        "lead_lag_count": 0,
        "sector_correlations_computed": False,
    }
    
    # Entity correlation matrices
    for signal_type in signal_types:
        logger.info(f"Computing entity correlations for {signal_type}...")
        matrix = analyzer.entity_correlation_matrix(entities, signal_type)
        results["correlation_matrices"][signal_type] = matrix.shape if not matrix.empty else (0, 0)
    
    # Lead-lag analysis for top entity pairs
    logger.info("Computing lead-lag relationships...")
    for i, entity_a in enumerate(entities[:20]):  # Limit to top 20 for performance
        for entity_b in entities[i+1:20]:
            for signal_type in signal_types[:2]:  # Only top signal types
                result = analyzer.find_lead_lag(entity_a, entity_b, signal_type)
                if result.confidence in ("medium", "high"):
                    results["lead_lag_count"] += 1
    
    # Sector correlations
    logger.info("Computing sector correlations...")
    sector_matrix = analyzer.sector_heatmap()
    results["sector_correlations_computed"] = not sector_matrix.empty
    
    logger.info(f"Correlation analysis complete: {results}")
    return results


if __name__ == "__main__":
    # Test correlation analyzer
    print("Testing CorrelationAnalyzer")
    print("=" * 50)
    
    analyzer = CorrelationAnalyzer()
    
    # Test entity correlation matrix
    test_entities = ["nvidia", "amd", "intel", "microsoft", "google"]
    matrix = analyzer.entity_correlation_matrix(test_entities, "composite")
    print(f"\nEntity correlation matrix shape: {matrix.shape}")
    if not matrix.empty:
        print(matrix)
    
    # Test signal correlation
    result = analyzer.signal_correlation("nvidia", "media", "financial")
    print(f"\nNVDA media vs financial: {result.correlation:.3f}")
    
    # Test lead-lag
    lead_lag = analyzer.find_lead_lag("nvidia", "amd")
    print(f"\nNVDA vs AMD lead-lag:")
    print(f"  Leader: {lead_lag.leader_entity}")
    print(f"  Lag: {lead_lag.optimal_lag_days} days")
    print(f"  Confidence: {lead_lag.confidence}")
    
    # Test sector heatmap
    sector_matrix = analyzer.sector_heatmap()
    print(f"\nSector heatmap shape: {sector_matrix.shape}")
    if not sector_matrix.empty:
        print(sector_matrix)
