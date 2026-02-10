"""
Signal Propagation Analysis

When NVDA moves, what else should move?
- Build dependency graph from correlations
- Predict cascading effects
- Use for early warning signals
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from loguru import logger
import numpy as np

from utils.correlation_analysis import (
    CorrelationAnalyzer,
    LeadLagRelationship,
    EntityCorrelation,
    SECTOR_DEFINITIONS
)


@dataclass
class PropagationNode:
    """A node in the signal propagation graph."""
    entity_id: str
    depth: int  # Distance from trigger entity
    expected_impact: float  # -1 to 1, expected directional impact
    confidence: float  # 0-1, confidence in this prediction
    path: List[str] = field(default_factory=list)  # Path from trigger
    lag_days: int = 0  # Expected lag time
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "depth": self.depth,
            "expected_impact": round(self.expected_impact, 4),
            "confidence": round(self.confidence, 4),
            "path": self.path,
            "lag_days": self.lag_days,
        }


@dataclass
class PropagationPrediction:
    """Prediction of cascading effects from a signal move."""
    trigger_entity: str
    trigger_signal_type: str
    trigger_direction: str  # "positive", "negative"
    trigger_magnitude: float  # Normalized 0-1
    affected_entities: List[PropagationNode]
    sector_impacts: Dict[str, float]
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_entity": self.trigger_entity,
            "trigger_signal_type": self.trigger_signal_type,
            "trigger_direction": self.trigger_direction,
            "trigger_magnitude": round(self.trigger_magnitude, 4),
            "affected_entities": [n.to_dict() for n in self.affected_entities],
            "sector_impacts": {k: round(v, 4) for k, v in self.sector_impacts.items()},
            "generated_at": self.generated_at.isoformat(),
        }


@dataclass
class EarlyWarningSignal:
    """Early warning based on lead-lag relationships."""
    warning_entity: str  # Entity showing movement
    warning_signal_type: str
    warning_direction: str
    warning_magnitude: float
    target_entity: str  # Entity likely to be affected
    expected_lag_days: int
    historical_correlation: float
    confidence: str  # "high", "medium", "low"
    warning_message: str
    generated_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "warning_entity": self.warning_entity,
            "warning_signal_type": self.warning_signal_type,
            "warning_direction": self.warning_direction,
            "warning_magnitude": round(self.warning_magnitude, 4),
            "target_entity": self.target_entity,
            "expected_lag_days": self.expected_lag_days,
            "historical_correlation": round(self.historical_correlation, 4),
            "confidence": self.confidence,
            "warning_message": self.warning_message,
            "generated_at": self.generated_at.isoformat(),
        }


class SignalPropagationEngine:
    """
    Predicts cascading effects when an entity's signals move.
    
    Uses correlation data and lead-lag relationships to:
    - Build a dependency graph
    - Predict which entities will be affected
    - Estimate timing and magnitude
    - Generate early warning signals
    """
    
    # Minimum correlation to consider as connected
    MIN_EDGE_CORRELATION = 0.3
    
    # Maximum depth to propagate
    MAX_PROPAGATION_DEPTH = 3
    
    # Decay factor for each hop
    PROPAGATION_DECAY = 0.7
    
    def __init__(
        self,
        correlations_db_path: Optional[Path] = None,
        signals_db_path: Optional[Path] = None
    ):
        """
        Initialize propagation engine.
        
        Args:
            correlations_db_path: Path to correlations.db
            signals_db_path: Path to signals.db
        """
        base_path = Path(__file__).parent.parent / "data"
        
        self.correlations_db_path = correlations_db_path or (base_path / "correlations.db")
        self.signals_db_path = signals_db_path or (base_path / "signals.db")
        
        self.analyzer = CorrelationAnalyzer()
        
        # Cache for dependency graph
        self._graph_cache: Dict[str, List[Tuple[str, float, int]]] = {}
        self._graph_cache_time: Optional[datetime] = None
        
        self._ensure_tables()
        logger.info("SignalPropagationEngine initialized")

    def _ensure_tables(self):
        """Create required tables if needed."""
        conn = sqlite3.connect(self.correlations_db_path)
        cursor = conn.cursor()
        
        # Propagation predictions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS propagation_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_entity TEXT NOT NULL,
                trigger_signal_type TEXT NOT NULL,
                trigger_direction TEXT NOT NULL,
                trigger_magnitude REAL NOT NULL,
                affected_entities TEXT NOT NULL,
                sector_impacts TEXT NOT NULL,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Early warning signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS early_warning_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                warning_entity TEXT NOT NULL,
                warning_signal_type TEXT NOT NULL,
                warning_direction TEXT NOT NULL,
                warning_magnitude REAL NOT NULL,
                target_entity TEXT NOT NULL,
                expected_lag_days INTEGER NOT NULL,
                historical_correlation REAL NOT NULL,
                confidence TEXT NOT NULL,
                warning_message TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ews_target ON early_warning_signals(target_entity)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ews_active ON early_warning_signals(is_active)")
        
        conn.commit()
        conn.close()

    def _get_correlations_connection(self) -> sqlite3.Connection:
        """Get connection to correlations database."""
        conn = sqlite3.connect(self.correlations_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _get_signals_connection(self) -> sqlite3.Connection:
        """Get connection to signals database."""
        conn = sqlite3.connect(self.signals_db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def build_dependency_graph(
        self,
        signal_type: str = "composite",
        min_correlation: float = 0.3,
        force_refresh: bool = False
    ) -> Dict[str, List[Tuple[str, float, int]]]:
        """
        Build dependency graph from correlation data.
        
        Returns adjacency list: entity -> [(connected_entity, correlation, lag_days)]
        
        Args:
            signal_type: Signal type to use
            min_correlation: Minimum correlation for an edge
            force_refresh: Force rebuild of graph
            
        Returns:
            Adjacency list representation of graph
        """
        # Check cache
        if not force_refresh and self._graph_cache and self._graph_cache_time:
            if (datetime.utcnow() - self._graph_cache_time).seconds < 3600:
                return self._graph_cache
        
        graph: Dict[str, List[Tuple[str, float, int]]] = defaultdict(list)
        
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        # Get entity correlations
        cursor.execute("""
            SELECT entity_a, entity_b, correlation
            FROM entity_correlations
            WHERE signal_type = ? AND ABS(correlation) >= ?
        """, (signal_type, min_correlation))
        
        for row in cursor.fetchall():
            # Add bidirectional edges
            graph[row["entity_a"]].append((row["entity_b"], row["correlation"], 0))
            graph[row["entity_b"]].append((row["entity_a"], row["correlation"], 0))
        
        # Enhance with lead-lag data
        cursor.execute("""
            SELECT leader_entity, follower_entity, correlation_at_lag, optimal_lag_days
            FROM lead_lag_relationships
            WHERE signal_type = ? AND ABS(correlation_at_lag) >= ?
        """, (signal_type, min_correlation))
        
        for row in cursor.fetchall():
            # Directed edge from leader to follower
            existing = [e for e in graph[row["leader_entity"]] if e[0] == row["follower_entity"]]
            if not existing:
                graph[row["leader_entity"]].append((
                    row["follower_entity"],
                    row["correlation_at_lag"],
                    row["optimal_lag_days"]
                ))
            else:
                # Update with lead-lag info if better correlation
                for i, (entity, corr, lag) in enumerate(graph[row["leader_entity"]]):
                    if entity == row["follower_entity"] and abs(row["correlation_at_lag"]) > abs(corr):
                        graph[row["leader_entity"]][i] = (
                            row["follower_entity"],
                            row["correlation_at_lag"],
                            row["optimal_lag_days"]
                        )
        
        conn.close()
        
        # Cache result
        self._graph_cache = dict(graph)
        self._graph_cache_time = datetime.utcnow()
        
        return dict(graph)

    def predict_propagation(
        self,
        trigger_entity: str,
        trigger_direction: str = "positive",
        trigger_magnitude: float = 0.5,
        signal_type: str = "composite",
        max_depth: int = None
    ) -> PropagationPrediction:
        """
        Predict cascading effects from a signal move.
        
        Args:
            trigger_entity: Entity showing the initial signal move
            trigger_direction: "positive" or "negative"
            trigger_magnitude: Normalized magnitude (0-1)
            signal_type: Signal type
            max_depth: Maximum propagation depth
            
        Returns:
            PropagationPrediction with affected entities
        """
        if max_depth is None:
            max_depth = self.MAX_PROPAGATION_DEPTH
        
        graph = self.build_dependency_graph(signal_type)
        
        direction_multiplier = 1.0 if trigger_direction == "positive" else -1.0
        
        # BFS to find affected entities
        affected: Dict[str, PropagationNode] = {}
        visited: Set[str] = {trigger_entity}
        
        # Initialize with trigger's direct connections
        queue: List[Tuple[str, int, float, List[str], int]] = []
        
        for connected, correlation, lag in graph.get(trigger_entity, []):
            if connected not in visited:
                impact = direction_multiplier * trigger_magnitude * correlation
                queue.append((connected, 1, impact, [trigger_entity, connected], lag))
        
        while queue:
            entity, depth, impact, path, total_lag = queue.pop(0)
            
            if entity in visited:
                continue
            
            visited.add(entity)
            
            # Calculate confidence based on depth
            confidence = self.PROPAGATION_DECAY ** depth
            
            affected[entity] = PropagationNode(
                entity_id=entity,
                depth=depth,
                expected_impact=impact,
                confidence=confidence,
                path=path,
                lag_days=total_lag
            )
            
            # Continue propagation if not at max depth
            if depth < max_depth:
                for connected, correlation, lag in graph.get(entity, []):
                    if connected not in visited:
                        # Impact decays and follows correlation direction
                        next_impact = impact * correlation * self.PROPAGATION_DECAY
                        queue.append((
                            connected,
                            depth + 1,
                            next_impact,
                            path + [connected],
                            total_lag + lag
                        ))
        
        # Calculate sector impacts
        sector_impacts = self._calculate_sector_impacts(affected, direction_multiplier)
        
        # Sort affected entities by absolute impact
        sorted_affected = sorted(
            affected.values(),
            key=lambda x: abs(x.expected_impact),
            reverse=True
        )
        
        prediction = PropagationPrediction(
            trigger_entity=trigger_entity,
            trigger_signal_type=signal_type,
            trigger_direction=trigger_direction,
            trigger_magnitude=trigger_magnitude,
            affected_entities=sorted_affected,
            sector_impacts=sector_impacts
        )
        
        # Store prediction
        self._store_prediction(prediction)
        
        return prediction

    def _calculate_sector_impacts(
        self,
        affected: Dict[str, PropagationNode],
        direction_multiplier: float
    ) -> Dict[str, float]:
        """Calculate aggregate impact by sector."""
        sector_impacts: Dict[str, float] = {}
        
        for sector_name, sector_config in SECTOR_DEFINITIONS.items():
            sector_entities = sector_config["entities"]
            
            impacts = []
            for entity in sector_entities:
                if entity in affected:
                    impacts.append(affected[entity].expected_impact)
            
            if impacts:
                sector_impacts[sector_name] = sum(impacts) / len(impacts)
            else:
                sector_impacts[sector_name] = 0.0
        
        return sector_impacts

    def _store_prediction(self, prediction: PropagationPrediction):
        """Store prediction to database."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO propagation_predictions
            (trigger_entity, trigger_signal_type, trigger_direction, trigger_magnitude,
             affected_entities, sector_impacts, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            prediction.trigger_entity,
            prediction.trigger_signal_type,
            prediction.trigger_direction,
            prediction.trigger_magnitude,
            json.dumps([e.to_dict() for e in prediction.affected_entities]),
            json.dumps(prediction.sector_impacts),
            prediction.generated_at.isoformat()
        ))
        
        conn.commit()
        conn.close()

    def generate_early_warnings(
        self,
        signal_changes: List[Dict[str, Any]],
        signal_type: str = "composite"
    ) -> List[EarlyWarningSignal]:
        """
        Generate early warning signals based on observed signal changes.
        
        Args:
            signal_changes: List of dicts with entity_id, direction, magnitude
            signal_type: Signal type
            
        Returns:
            List of early warning signals
        """
        warnings = []
        
        # Get all lead-lag relationships
        relationships = self.analyzer.get_all_lead_lag_relationships(
            min_predictive_power=0.1,
            min_confidence="medium"
        )
        
        # Build lookup from leader to followers
        leader_to_followers: Dict[str, List[LeadLagRelationship]] = defaultdict(list)
        for rel in relationships:
            if rel.signal_type == signal_type:
                leader_to_followers[rel.leader_entity].append(rel)
        
        # Check each signal change
        for change in signal_changes:
            entity = change.get("entity_id", "").lower()
            direction = change.get("direction", "positive")
            magnitude = change.get("magnitude", 0.5)
            
            # Check if this entity leads others
            for rel in leader_to_followers.get(entity, []):
                # Generate warning
                if abs(rel.correlation_at_lag) > 0.3:
                    expected_direction = direction if rel.correlation_at_lag > 0 else ("negative" if direction == "positive" else "positive")
                    
                    message = self._generate_warning_message(
                        entity, rel.follower_entity, direction,
                        rel.optimal_lag_days, rel.confidence, expected_direction
                    )
                    
                    warning = EarlyWarningSignal(
                        warning_entity=entity,
                        warning_signal_type=signal_type,
                        warning_direction=direction,
                        warning_magnitude=magnitude,
                        target_entity=rel.follower_entity,
                        expected_lag_days=rel.optimal_lag_days,
                        historical_correlation=rel.correlation_at_lag,
                        confidence=rel.confidence,
                        warning_message=message
                    )
                    
                    warnings.append(warning)
        
        # Store warnings
        self._store_warnings(warnings)
        
        return warnings

    def _generate_warning_message(
        self,
        leader: str,
        follower: str,
        direction: str,
        lag_days: int,
        confidence: str,
        expected_direction: str
    ) -> str:
        """Generate human-readable warning message."""
        confidence_emoji = "🔴" if confidence == "high" else "🟡" if confidence == "medium" else "⚪"
        direction_emoji = "📈" if direction == "positive" else "📉"
        
        return (
            f"{confidence_emoji} {leader.upper()} {direction_emoji} signal detected. "
            f"Based on historical patterns, {follower.upper()} typically follows "
            f"with {expected_direction} movement in ~{lag_days} days. "
            f"Confidence: {confidence}."
        )

    def _store_warnings(self, warnings: List[EarlyWarningSignal]):
        """Store warning signals to database."""
        if not warnings:
            return
            
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        for warning in warnings:
            cursor.execute("""
                INSERT INTO early_warning_signals
                (warning_entity, warning_signal_type, warning_direction, warning_magnitude,
                 target_entity, expected_lag_days, historical_correlation, confidence,
                 warning_message, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                warning.warning_entity,
                warning.warning_signal_type,
                warning.warning_direction,
                warning.warning_magnitude,
                warning.target_entity,
                warning.expected_lag_days,
                warning.historical_correlation,
                warning.confidence,
                warning.warning_message,
                warning.generated_at.isoformat()
            ))
        
        conn.commit()
        conn.close()

    def get_active_warnings(
        self,
        target_entity: Optional[str] = None
    ) -> List[EarlyWarningSignal]:
        """Get active early warning signals."""
        conn = self._get_correlations_connection()
        cursor = conn.cursor()
        
        if target_entity:
            cursor.execute("""
                SELECT * FROM early_warning_signals
                WHERE is_active = 1 AND target_entity = ?
                ORDER BY generated_at DESC
            """, (target_entity.lower(),))
        else:
            cursor.execute("""
                SELECT * FROM early_warning_signals
                WHERE is_active = 1
                ORDER BY confidence DESC, generated_at DESC
            """)
        
        warnings = []
        for row in cursor.fetchall():
            warnings.append(EarlyWarningSignal(
                warning_entity=row["warning_entity"],
                warning_signal_type=row["warning_signal_type"],
                warning_direction=row["warning_direction"],
                warning_magnitude=row["warning_magnitude"],
                target_entity=row["target_entity"],
                expected_lag_days=row["expected_lag_days"],
                historical_correlation=row["historical_correlation"],
                confidence=row["confidence"],
                warning_message=row["warning_message"],
                generated_at=datetime.fromisoformat(row["generated_at"])
            ))
        
        conn.close()
        return warnings

    def get_entity_dependencies(self, entity_id: str) -> Dict[str, Any]:
        """
        Get dependency information for a single entity.
        
        Returns what entities this one affects and is affected by.
        """
        graph = self.build_dependency_graph()
        
        # Direct connections
        direct = graph.get(entity_id.lower(), [])
        
        affects = []
        affected_by = []
        
        # Get lead-lag info to determine direction
        lead_lag = self.analyzer.get_lead_lag_for_entity(entity_id.lower())
        
        leads = {r.follower_entity for r in lead_lag.get("as_leader", [])}
        follows = {r.leader_entity for r in lead_lag.get("as_follower", [])}
        
        for connected, correlation, lag in direct:
            entry = {
                "entity": connected,
                "correlation": round(correlation, 3),
                "lag_days": lag
            }
            
            if connected in leads:
                affects.append(entry)
            elif connected in follows:
                affected_by.append(entry)
            else:
                # Bidirectional or unknown
                affects.append(entry)
                affected_by.append(entry)
        
        # Get sector membership
        entity_sectors = []
        for sector_name, sector_config in SECTOR_DEFINITIONS.items():
            if entity_id.lower() in sector_config["entities"]:
                entity_sectors.append(sector_name)
        
        return {
            "entity_id": entity_id,
            "affects": sorted(affects, key=lambda x: abs(x["correlation"]), reverse=True),
            "affected_by": sorted(affected_by, key=lambda x: abs(x["correlation"]), reverse=True),
            "sectors": entity_sectors,
            "total_connections": len(direct)
        }


def simulate_propagation(
    trigger_entity: str,
    trigger_direction: str = "positive",
    trigger_magnitude: float = 0.5
) -> Dict[str, Any]:
    """
    Convenience function to simulate signal propagation.
    
    Returns a summary suitable for API response.
    """
    engine = SignalPropagationEngine()
    prediction = engine.predict_propagation(
        trigger_entity=trigger_entity.lower(),
        trigger_direction=trigger_direction,
        trigger_magnitude=trigger_magnitude
    )
    
    return {
        "trigger": {
            "entity": trigger_entity,
            "direction": trigger_direction,
            "magnitude": trigger_magnitude
        },
        "affected_count": len(prediction.affected_entities),
        "top_affected": [
            {
                "entity": e.entity_id,
                "impact": round(e.expected_impact, 3),
                "lag_days": e.lag_days,
                "confidence": round(e.confidence, 3)
            }
            for e in prediction.affected_entities[:10]
        ],
        "sector_impacts": prediction.sector_impacts,
        "generated_at": prediction.generated_at.isoformat()
    }


if __name__ == "__main__":
    # Test signal propagation
    print("Testing SignalPropagationEngine")
    print("=" * 50)
    
    engine = SignalPropagationEngine()
    
    # Build dependency graph
    print("\nBuilding dependency graph...")
    graph = engine.build_dependency_graph()
    print(f"Graph has {len(graph)} entities")
    
    # Show sample connections
    if "nvidia" in graph:
        print(f"\nNVIDIA connections:")
        for entity, corr, lag in graph["nvidia"][:5]:
            print(f"  -> {entity}: corr={corr:.2f}, lag={lag}d")
    
    # Test propagation prediction
    print("\nSimulating NVDA positive signal...")
    prediction = engine.predict_propagation(
        "nvidia", 
        trigger_direction="positive",
        trigger_magnitude=0.7
    )
    
    print(f"\nAffected entities: {len(prediction.affected_entities)}")
    for entity in prediction.affected_entities[:5]:
        print(f"  {entity.entity_id}: impact={entity.expected_impact:.3f}, "
              f"lag={entity.lag_days}d, conf={entity.confidence:.2f}")
    
    print("\nSector impacts:")
    for sector, impact in prediction.sector_impacts.items():
        if abs(impact) > 0.01:
            print(f"  {sector}: {impact:+.3f}")
    
    # Test entity dependencies
    print("\nNVIDIA dependencies:")
    deps = engine.get_entity_dependencies("nvidia")
    print(f"  Affects: {len(deps['affects'])} entities")
    print(f"  Affected by: {len(deps['affected_by'])} entities")
    print(f"  Sectors: {deps['sectors']}")
