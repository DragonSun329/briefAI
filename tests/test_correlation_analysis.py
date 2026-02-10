"""
Tests for Correlation Analysis System

Tests for:
- CorrelationAnalyzer
- RollingCorrelationTracker
- SignalPropagationEngine
"""

import pytest
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.correlation_analysis import (
    CorrelationAnalyzer,
    EntityCorrelation,
    SignalCorrelation,
    LeadLagRelationship,
    SECTOR_DEFINITIONS
)
from utils.rolling_correlations import (
    RollingCorrelationTracker,
    RollingCorrelation,
    CorrelationRegimeChange,
    CorrelationDivergenceAlert
)
from utils.signal_propagation import (
    SignalPropagationEngine,
    PropagationNode,
    PropagationPrediction,
    EarlyWarningSignal
)


class TestCorrelationAnalyzer:
    """Tests for CorrelationAnalyzer class."""
    
    @pytest.fixture
    def analyzer(self, tmp_path):
        """Create analyzer with temp databases."""
        signals_db = tmp_path / "signals.db"
        corr_db = tmp_path / "correlations.db"
        
        # Create minimal signals database
        conn = sqlite3.connect(signals_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE signal_profiles (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                as_of TIMESTAMP NOT NULL,
                technical_score REAL,
                company_score REAL,
                financial_score REAL,
                product_score REAL,
                media_score REAL,
                composite_score REAL NOT NULL
            )
        """)
        
        # Insert test data
        entities = ["nvidia", "amd", "intel"]
        for i, entity in enumerate(entities):
            for day in range(30):
                dt = (datetime.utcnow() - timedelta(days=day)).isoformat()
                # Create correlated patterns
                base_score = 50 + 10 * np.sin(day * 0.5) + (i * 5)
                cursor.execute("""
                    INSERT INTO signal_profiles (id, entity_id, entity_name, entity_type, as_of, composite_score)
                    VALUES (?, ?, ?, 'company', ?, ?)
                """, (f"{entity}_{day}", entity, entity.upper(), dt, base_score))
        
        conn.commit()
        conn.close()
        
        return CorrelationAnalyzer(
            signals_db_path=signals_db,
            correlations_db_path=corr_db
        )
    
    def test_entity_correlation_matrix(self, analyzer):
        """Test entity correlation matrix calculation."""
        entities = ["nvidia", "amd", "intel"]
        matrix = analyzer.entity_correlation_matrix(entities, "composite", 30)
        
        assert not matrix.empty
        assert list(matrix.index) == entities
        assert list(matrix.columns) == entities
        
        # Diagonal should be 1.0
        for entity in entities:
            assert matrix.loc[entity, entity] == 1.0
    
    def test_signal_correlation(self, analyzer):
        """Test signal-to-signal correlation."""
        result = analyzer.signal_correlation("nvidia", "composite", "composite")
        
        assert isinstance(result, SignalCorrelation)
        assert result.entity_id == "nvidia"
        assert result.correlation == 1.0  # Same signal should be 1.0
    
    def test_find_lead_lag(self, analyzer):
        """Test lead-lag relationship detection."""
        result = analyzer.find_lead_lag("nvidia", "amd", "composite", max_lag_days=10)
        
        assert isinstance(result, LeadLagRelationship)
        assert result.leader_entity in ["nvidia", "amd"]
        assert result.follower_entity in ["nvidia", "amd"]
        assert -10 <= result.optimal_lag_days <= 10
    
    def test_sector_heatmap(self, analyzer):
        """Test sector correlation heatmap."""
        # This will likely be empty with our test data
        matrix = analyzer.sector_heatmap()
        # Just verify it returns a DataFrame
        assert isinstance(matrix, pd.DataFrame)
    
    def test_get_entity_correlations(self, analyzer):
        """Test getting correlations for a single entity."""
        # First create some correlations
        entities = ["nvidia", "amd", "intel"]
        analyzer.entity_correlation_matrix(entities, "composite", 30)
        
        # Then retrieve
        correlations = analyzer.get_entity_correlations("nvidia", "composite", 0.0)
        
        assert isinstance(correlations, list)


class TestRollingCorrelationTracker:
    """Tests for RollingCorrelationTracker class."""
    
    @pytest.fixture
    def tracker(self, tmp_path):
        """Create tracker with temp databases."""
        signals_db = tmp_path / "signals.db"
        corr_db = tmp_path / "correlations.db"
        
        # Create minimal signals database
        conn = sqlite3.connect(signals_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE signal_profiles (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                as_of TIMESTAMP NOT NULL,
                composite_score REAL NOT NULL
            )
        """)
        
        # Insert test data with some correlation
        for entity in ["nvidia", "amd"]:
            for day in range(90):
                dt = (datetime.utcnow() - timedelta(days=day)).isoformat()
                base = 50 + 10 * np.sin(day * 0.3)
                noise = np.random.normal(0, 2) if entity == "amd" else 0
                cursor.execute("""
                    INSERT INTO signal_profiles (id, entity_id, as_of, composite_score)
                    VALUES (?, ?, ?, ?)
                """, (f"{entity}_{day}", entity, dt, base + noise))
        
        conn.commit()
        conn.close()
        
        return RollingCorrelationTracker(
            signals_db_path=signals_db,
            correlations_db_path=corr_db
        )
    
    def test_calculate_rolling_correlation(self, tracker):
        """Test single rolling correlation calculation."""
        result = tracker.calculate_rolling_correlation(
            "nvidia", "amd", "composite", 30
        )
        
        if result is not None:
            assert isinstance(result, RollingCorrelation)
            assert -1 <= result.correlation <= 1
            assert result.window_days == 30
    
    def test_calculate_rolling_series(self, tracker):
        """Test rolling correlation series calculation."""
        correlations = tracker.calculate_rolling_correlation_series(
            "nvidia", "amd", "composite", 
            window_days=30, history_days=60
        )
        
        assert isinstance(correlations, list)
        for corr in correlations:
            assert isinstance(corr, RollingCorrelation)
            assert -1 <= corr.correlation <= 1
    
    def test_detect_regime_changes(self, tracker):
        """Test regime change detection."""
        changes = tracker.detect_regime_changes(
            "nvidia", "amd", "composite", 30
        )
        
        assert isinstance(changes, list)
        for change in changes:
            assert isinstance(change, CorrelationRegimeChange)
            assert change.change_type in ["breakdown", "emergence", "reversal"]
    
    def test_check_divergence_alerts(self, tracker):
        """Test divergence alert checking."""
        alert = tracker.check_divergence_alerts("nvidia", "amd", "composite")
        
        # May or may not have an alert depending on data
        if alert is not None:
            assert isinstance(alert, CorrelationDivergenceAlert)
            assert alert.alert_level in ["warning", "critical"]


class TestSignalPropagationEngine:
    """Tests for SignalPropagationEngine class."""
    
    @pytest.fixture
    def engine(self, tmp_path):
        """Create engine with temp databases."""
        signals_db = tmp_path / "signals.db"
        corr_db = tmp_path / "correlations.db"
        
        # Create signals database
        conn = sqlite3.connect(signals_db)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE signal_profiles (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                as_of TIMESTAMP NOT NULL,
                composite_score REAL NOT NULL
            )
        """)
        conn.commit()
        conn.close()
        
        # Create correlations database with test data
        conn = sqlite3.connect(corr_db)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute("""
            CREATE TABLE entity_correlations (
                id INTEGER PRIMARY KEY,
                entity_a TEXT,
                entity_b TEXT,
                signal_type TEXT,
                correlation REAL,
                window_days INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE lead_lag_relationships (
                id INTEGER PRIMARY KEY,
                leader_entity TEXT,
                follower_entity TEXT,
                signal_type TEXT,
                correlation_at_lag REAL,
                optimal_lag_days INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE propagation_predictions (
                id INTEGER PRIMARY KEY,
                trigger_entity TEXT,
                trigger_signal_type TEXT,
                trigger_direction TEXT,
                trigger_magnitude REAL,
                affected_entities TEXT,
                sector_impacts TEXT,
                generated_at TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE early_warning_signals (
                id INTEGER PRIMARY KEY,
                warning_entity TEXT,
                warning_signal_type TEXT,
                warning_direction TEXT,
                warning_magnitude REAL,
                target_entity TEXT,
                expected_lag_days INTEGER,
                historical_correlation REAL,
                confidence TEXT,
                warning_message TEXT,
                generated_at TIMESTAMP,
                resolved_at TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        """)
        
        # Insert test correlations
        cursor.execute("""
            INSERT INTO entity_correlations (entity_a, entity_b, signal_type, correlation, window_days)
            VALUES ('nvidia', 'amd', 'composite', 0.8, 30)
        """)
        cursor.execute("""
            INSERT INTO entity_correlations (entity_a, entity_b, signal_type, correlation, window_days)
            VALUES ('nvidia', 'intel', 'composite', 0.6, 30)
        """)
        cursor.execute("""
            INSERT INTO lead_lag_relationships 
            (leader_entity, follower_entity, signal_type, correlation_at_lag, optimal_lag_days)
            VALUES ('nvidia', 'amd', 'composite', 0.75, 3)
        """)
        
        conn.commit()
        conn.close()
        
        return SignalPropagationEngine(
            correlations_db_path=corr_db,
            signals_db_path=signals_db
        )
    
    def test_build_dependency_graph(self, engine):
        """Test dependency graph building."""
        graph = engine.build_dependency_graph("composite", force_refresh=True)
        
        assert isinstance(graph, dict)
        assert "nvidia" in graph
        # nvidia should have connections to amd and intel
        connections = graph.get("nvidia", [])
        connected_entities = [c[0] for c in connections]
        assert "amd" in connected_entities or "intel" in connected_entities
    
    def test_predict_propagation(self, engine):
        """Test signal propagation prediction."""
        prediction = engine.predict_propagation(
            trigger_entity="nvidia",
            trigger_direction="positive",
            trigger_magnitude=0.5
        )
        
        assert isinstance(prediction, PropagationPrediction)
        assert prediction.trigger_entity == "nvidia"
        assert prediction.trigger_direction == "positive"
        assert isinstance(prediction.affected_entities, list)
    
    def test_get_entity_dependencies(self, engine):
        """Test entity dependency retrieval."""
        deps = engine.get_entity_dependencies("nvidia")
        
        assert isinstance(deps, dict)
        assert "entity_id" in deps
        assert "affects" in deps
        assert "affected_by" in deps
        assert deps["entity_id"] == "nvidia"


class TestDataclasses:
    """Test dataclass serialization."""
    
    def test_entity_correlation_to_dict(self):
        """Test EntityCorrelation serialization."""
        corr = EntityCorrelation(
            entity_a="nvidia",
            entity_b="amd",
            signal_type="composite",
            correlation=0.75,
            p_value=0.01,
            sample_size=30
        )
        
        d = corr.to_dict()
        assert d["entity_a"] == "nvidia"
        assert d["entity_b"] == "amd"
        assert d["correlation"] == 0.75
    
    def test_lead_lag_to_dict(self):
        """Test LeadLagRelationship serialization."""
        rel = LeadLagRelationship(
            leader_entity="nvidia",
            follower_entity="amd",
            signal_type="composite",
            optimal_lag_days=3,
            correlation_at_lag=0.8,
            correlation_at_zero=0.6,
            predictive_power=0.2,
            confidence="high"
        )
        
        d = rel.to_dict()
        assert d["leader_entity"] == "nvidia"
        assert d["optimal_lag_days"] == 3
        assert d["confidence"] == "high"
    
    def test_propagation_node_to_dict(self):
        """Test PropagationNode serialization."""
        node = PropagationNode(
            entity_id="amd",
            depth=1,
            expected_impact=0.5,
            confidence=0.7,
            path=["nvidia", "amd"],
            lag_days=3
        )
        
        d = node.to_dict()
        assert d["entity_id"] == "amd"
        assert d["depth"] == 1
        assert d["path"] == ["nvidia", "amd"]


class TestSectorDefinitions:
    """Test sector definitions."""
    
    def test_sector_definitions_structure(self):
        """Test that sector definitions have required structure."""
        required_sectors = [
            "ai_infrastructure",
            "ai_hyperscalers",
            "ai_applications",
            "ai_pure_play"
        ]
        
        for sector in required_sectors:
            assert sector in SECTOR_DEFINITIONS
            assert "entities" in SECTOR_DEFINITIONS[sector]
            assert "description" in SECTOR_DEFINITIONS[sector]
            assert isinstance(SECTOR_DEFINITIONS[sector]["entities"], list)
    
    def test_key_entities_in_sectors(self):
        """Test that key entities are in their sectors."""
        assert "nvidia" in SECTOR_DEFINITIONS["ai_infrastructure"]["entities"]
        assert "microsoft" in SECTOR_DEFINITIONS["ai_hyperscalers"]["entities"]
        assert "openai" in SECTOR_DEFINITIONS["ai_pure_play"]["entities"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
