"""
Tests for Prediction Verification Engine.

Test Coverage:
1. PredictionRecord creation and serialization
2. Direction evaluation logic
3. Percent change calculation
4. PredictionStore operations
5. Prediction registration from bundles
6. Calibration report generation
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.prediction_verifier import (
    PredictionRecord,
    PredictionStatus,
    PredictionVerdict,
    PredictionStore,
    generate_prediction_id,
    calculate_percent_change,
    evaluate_direction,
    evaluate_prediction,
    create_prediction_from_signal,
    register_predictions_from_bundle,
)

from utils.calibration_engine import (
    CalibrationEngine,
    CalibrationReport,
    calculate_accuracy,
    calculate_brier_score,
    build_calibration_curve,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_sample_prediction_signal():
    """Create a sample predicted signal for testing."""
    return {
        'category': 'financial',
        'description': 'CapEx and datacenter investment mentions increase in SEC filings',
        'example_sources': ['sec', 'earnings_call'],
        'expected_timeframe_days': 30,
        'metric': 'filing_mentions',
        'direction': 'up',
        'canonical_metric': 'filing_mentions',
        'measurable': True,
        'observable_query': {
            'source': 'sec',
            'query': '(capex OR datacenter) AND (nvidia)',
            'aggregation': 'count',
            'window_days': 30,
            'expected_direction': 'up',
            'query_terms': {
                'entities': ['nvidia'],
                'primary_entity': 'nvidia',
                'concept_entity': 'nvidia',
                'mechanism_terms': ['gpu', 'compute'],
            },
        },
    }


def make_sample_hypothesis():
    """Create a sample hypothesis for testing."""
    return {
        'hypothesis_id': 'test_hyp_001',
        'title': 'Infrastructure Scaling',
        'mechanism': 'infra_scaling',
        'confidence': 0.78,
        'predicted_next_signals': [
            make_sample_prediction_signal(),
        ],
    }


def make_sample_bundle():
    """Create a sample hypothesis bundle for testing."""
    return {
        'meta_id': 'test_meta_001',
        'concept_name': 'NVIDIA Chip Demand',
        'hypotheses': [make_sample_hypothesis()],
    }


# =============================================================================
# TEST: PREDICTION RECORD
# =============================================================================

class TestPredictionRecord:
    """Test PredictionRecord dataclass."""
    
    def test_record_creation(self):
        """Should create record with required fields."""
        now = datetime.now()
        
        record = PredictionRecord(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Article count should increase',
            window_days=14,
            created_at=now.isoformat(),
            evaluation_due=(now + timedelta(days=14)).isoformat(),
        )
        
        assert record.prediction_id == 'pred_001'
        assert record.status == PredictionStatus.PENDING.value
        assert record.verdict == PredictionVerdict.PENDING.value
    
    def test_record_serialization(self):
        """Should serialize and deserialize correctly."""
        now = datetime.now()
        
        record = PredictionRecord(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Test',
            window_days=14,
            created_at=now.isoformat(),
            evaluation_due=(now + timedelta(days=14)).isoformat(),
        )
        
        # Serialize to dict
        d = record.to_dict()
        assert isinstance(d, dict)
        assert d['prediction_id'] == 'pred_001'
        
        # Deserialize
        restored = PredictionRecord.from_dict(d)
        assert restored.prediction_id == record.prediction_id
        assert restored.entity == record.entity
    
    def test_record_jsonl(self):
        """Should serialize and deserialize JSONL."""
        now = datetime.now()
        
        record = PredictionRecord(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Test',
            window_days=14,
            created_at=now.isoformat(),
            evaluation_due=(now + timedelta(days=14)).isoformat(),
        )
        
        jsonl = record.to_jsonl()
        assert isinstance(jsonl, str)
        
        restored = PredictionRecord.from_jsonl(jsonl)
        assert restored.prediction_id == record.prediction_id
    
    def test_is_due(self):
        """Should correctly check if record is due."""
        now = datetime.now()
        
        # Due record
        past_due = PredictionRecord(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Test',
            window_days=14,
            created_at=(now - timedelta(days=20)).isoformat(),
            evaluation_due=(now - timedelta(days=6)).isoformat(),
        )
        
        assert past_due.is_due(now) == True
        
        # Not due yet
        future_due = PredictionRecord(
            prediction_id='pred_002',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Test',
            window_days=14,
            created_at=now.isoformat(),
            evaluation_due=(now + timedelta(days=14)).isoformat(),
        )
        
        assert future_due.is_due(now) == False


# =============================================================================
# TEST: EVALUATION LOGIC
# =============================================================================

class TestEvaluationLogic:
    """Test prediction evaluation logic."""
    
    def test_percent_change_calculation(self):
        """Should calculate percent change correctly."""
        assert calculate_percent_change(100, 115) == 0.15
        assert calculate_percent_change(100, 85) == -0.15
        assert calculate_percent_change(100, 100) == 0.0
        assert calculate_percent_change(0, 10) == 1.0
        assert calculate_percent_change(0, 0) is None
    
    def test_direction_up_verified_true(self):
        """Up direction with significant increase = verified_true."""
        assert evaluate_direction('up', 0.20) == PredictionVerdict.VERIFIED_TRUE.value
        assert evaluate_direction('up', 0.15) == PredictionVerdict.VERIFIED_TRUE.value
    
    def test_direction_up_verified_false(self):
        """Up direction with significant decrease = verified_false."""
        assert evaluate_direction('up', -0.20) == PredictionVerdict.VERIFIED_FALSE.value
        assert evaluate_direction('up', -0.15) == PredictionVerdict.VERIFIED_FALSE.value
    
    def test_direction_up_inconclusive(self):
        """Up direction with small change = inconclusive."""
        assert evaluate_direction('up', 0.10) == PredictionVerdict.INCONCLUSIVE.value
        assert evaluate_direction('up', -0.05) == PredictionVerdict.INCONCLUSIVE.value
    
    def test_direction_down_verified_true(self):
        """Down direction with significant decrease = verified_true."""
        assert evaluate_direction('down', -0.20) == PredictionVerdict.VERIFIED_TRUE.value
    
    def test_direction_down_verified_false(self):
        """Down direction with significant increase = verified_false."""
        assert evaluate_direction('down', 0.20) == PredictionVerdict.VERIFIED_FALSE.value
    
    def test_direction_flat(self):
        """Flat direction checks."""
        assert evaluate_direction('flat', 0.05) == PredictionVerdict.VERIFIED_TRUE.value
        assert evaluate_direction('flat', 0.20) == PredictionVerdict.VERIFIED_FALSE.value
    
    def test_evaluate_prediction(self):
        """Should evaluate prediction with observed data."""
        now = datetime.now()
        
        record = PredictionRecord(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Test',
            window_days=14,
            created_at=now.isoformat(),
            evaluation_due=(now + timedelta(days=14)).isoformat(),
            confidence_at_prediction=0.8,
        )
        
        # Evaluate with increase
        evaluated = evaluate_prediction(record, 100, 120)
        
        assert evaluated.status == PredictionStatus.EVALUATED.value
        assert evaluated.verdict == PredictionVerdict.VERIFIED_TRUE.value
        assert evaluated.observed_value_start == 100
        assert evaluated.observed_value_end == 120
        assert evaluated.percent_change == 0.2
    
    def test_evaluate_prediction_data_missing(self):
        """Should handle missing data."""
        now = datetime.now()
        
        record = PredictionRecord(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            expected_direction='up',
            category='media',
            description='Test',
            window_days=14,
            created_at=now.isoformat(),
            evaluation_due=(now + timedelta(days=14)).isoformat(),
        )
        
        evaluated = evaluate_prediction(record, None, None)
        
        assert evaluated.verdict == PredictionVerdict.DATA_MISSING.value


# =============================================================================
# TEST: PREDICTION STORE
# =============================================================================

class TestPredictionStore:
    """Test PredictionStore persistence."""
    
    def test_save_and_load(self):
        """Should save and load records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = PredictionStore(Path(tmpdir))
            now = datetime.now()
            
            record = PredictionRecord(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='article_count',
                expected_direction='up',
                category='media',
                description='Test',
                window_days=14,
                created_at=now.isoformat(),
                evaluation_due=(now + timedelta(days=14)).isoformat(),
            )
            
            store.save_record(record)
            
            loaded = store.load_all_records()
            assert len(loaded) == 1
            assert loaded[0].prediction_id == 'pred_001'
    
    def test_load_pending(self):
        """Should filter pending records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = PredictionStore(Path(tmpdir))
            now = datetime.now()
            
            # Pending record
            pending = PredictionRecord(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='article_count',
                expected_direction='up',
                category='media',
                description='Test',
                window_days=14,
                created_at=now.isoformat(),
                evaluation_due=(now + timedelta(days=14)).isoformat(),
                status=PredictionStatus.PENDING.value,
            )
            
            # Evaluated record
            evaluated = PredictionRecord(
                prediction_id='pred_002',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='repo_activity',
                expected_direction='up',
                category='technical',
                description='Test 2',
                window_days=14,
                created_at=now.isoformat(),
                evaluation_due=(now + timedelta(days=14)).isoformat(),
                status=PredictionStatus.EVALUATED.value,
            )
            
            store.save_records([pending, evaluated])
            
            pending_records = store.load_pending_records()
            assert len(pending_records) == 1
            assert pending_records[0].prediction_id == 'pred_001'
    
    def test_update_record(self):
        """Should update existing record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = PredictionStore(Path(tmpdir))
            now = datetime.now()
            
            record = PredictionRecord(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='article_count',
                expected_direction='up',
                category='media',
                description='Test',
                window_days=14,
                created_at=now.isoformat(),
                evaluation_due=(now + timedelta(days=14)).isoformat(),
            )
            
            store.save_record(record)
            
            # Update
            record.status = PredictionStatus.EVALUATED.value
            record.verdict = PredictionVerdict.VERIFIED_TRUE.value
            store.update_record(record)
            
            # Reload
            loaded = store.load_all_records()
            assert len(loaded) == 1
            assert loaded[0].status == PredictionStatus.EVALUATED.value


# =============================================================================
# TEST: PREDICTION REGISTRATION
# =============================================================================

class TestPredictionRegistration:
    """Test prediction registration from bundles."""
    
    def test_create_from_signal(self):
        """Should create prediction record from signal."""
        signal = make_sample_prediction_signal()
        hypothesis = make_sample_hypothesis()
        
        record = create_prediction_from_signal(signal, hypothesis, 'meta_001')
        
        assert record.hypothesis_id == 'test_hyp_001'
        assert record.meta_id == 'meta_001'
        assert record.entity == 'nvidia'
        assert record.canonical_metric == 'filing_mentions'
        assert record.expected_direction == 'up'
        assert record.window_days == 30
        assert record.confidence_at_prediction == 0.78
    
    def test_register_from_bundle(self):
        """Should register predictions from bundle."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = PredictionStore(Path(tmpdir))
            bundle = make_sample_bundle()
            
            records = register_predictions_from_bundle(bundle, store)
            
            assert len(records) == 1
            assert records[0].meta_id == 'test_meta_001'
            
            # Should be persisted
            loaded = store.load_all_records()
            assert len(loaded) == 1


# =============================================================================
# TEST: CALIBRATION
# =============================================================================

class TestCalibration:
    """Test calibration engine."""
    
    def test_accuracy_calculation(self):
        """Should calculate accuracy correctly."""
        assert calculate_accuracy(8, 10) == 0.8
        assert calculate_accuracy(0, 10) == 0.0
        assert calculate_accuracy(10, 0) == 0.0
    
    def test_brier_score(self):
        """Should calculate Brier score correctly."""
        # Perfect predictions
        perfect = [(1.0, 1.0), (0.0, 0.0)]
        assert calculate_brier_score(perfect) == 0.0
        
        # Worst predictions
        worst = [(1.0, 0.0), (0.0, 1.0)]
        assert calculate_brier_score(worst) == 1.0
    
    def test_calibration_curve(self):
        """Should build calibration curve."""
        predictions = [
            (0.1, 0.0),
            (0.3, 0.0),
            (0.7, 1.0),
            (0.9, 1.0),
        ]
        
        curve = build_calibration_curve(predictions)
        
        assert len(curve) == 5
        # High confidence bin should have high accuracy
        high_bin = curve[4]  # 0.8-1.0
        assert high_bin.actual_accuracy == 1.0
    
    def test_calibration_report(self):
        """Should generate calibration report."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = CalibrationEngine(Path(tmpdir))
            
            # Create sample records
            records = [
                {
                    'status': 'evaluated',
                    'verdict': 'verified_true',
                    'confidence_at_prediction': 0.8,
                    'mechanism': 'infra_scaling',
                    'category': 'financial',
                    'canonical_metric': 'filing_mentions',
                    'evaluated_at': datetime.now().isoformat(),
                },
                {
                    'status': 'evaluated',
                    'verdict': 'verified_false',
                    'confidence_at_prediction': 0.6,
                    'mechanism': 'infra_scaling',
                    'category': 'media',
                    'canonical_metric': 'article_count',
                    'evaluated_at': datetime.now().isoformat(),
                },
            ]
            
            report = engine.compute_report(records)
            
            assert report.total_predictions == 2
            assert report.evaluated_predictions == 2
            assert report.verified_true == 1
            assert report.verified_false == 1
            assert report.accuracy == 0.5


# =============================================================================
# TEST: PREDICTION ID
# =============================================================================

class TestPredictionId:
    """Test prediction ID generation."""
    
    def test_stable_id(self):
        """Same inputs should produce same ID."""
        id1 = generate_prediction_id("hyp1", "nvidia", "article_count", "media", "2026-02-10")
        id2 = generate_prediction_id("hyp1", "nvidia", "article_count", "media", "2026-02-10")
        
        assert id1 == id2
    
    def test_different_inputs(self):
        """Different inputs should produce different IDs."""
        id1 = generate_prediction_id("hyp1", "nvidia", "article_count", "media", "2026-02-10")
        id2 = generate_prediction_id("hyp2", "nvidia", "article_count", "media", "2026-02-10")
        
        assert id1 != id2
    
    def test_id_length(self):
        """ID should be 16 characters."""
        id1 = generate_prediction_id("hyp1", "nvidia", "article_count", "media", "2026-02-10")
        assert len(id1) == 16


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all prediction verifier tests."""
    print("\n=== PREDICTION VERIFICATION ENGINE TESTS ===\n")
    
    # PredictionRecord tests
    t = TestPredictionRecord()
    t.test_record_creation()
    t.test_record_serialization()
    t.test_record_jsonl()
    t.test_is_due()
    print("[PASS] PredictionRecord tests")
    
    # Evaluation logic tests
    t = TestEvaluationLogic()
    t.test_percent_change_calculation()
    t.test_direction_up_verified_true()
    t.test_direction_up_verified_false()
    t.test_direction_up_inconclusive()
    t.test_direction_down_verified_true()
    t.test_direction_down_verified_false()
    t.test_direction_flat()
    t.test_evaluate_prediction()
    t.test_evaluate_prediction_data_missing()
    print("[PASS] Evaluation logic tests")
    
    # PredictionStore tests
    t = TestPredictionStore()
    t.test_save_and_load()
    t.test_load_pending()
    t.test_update_record()
    print("[PASS] PredictionStore tests")
    
    # Registration tests
    t = TestPredictionRegistration()
    t.test_create_from_signal()
    t.test_register_from_bundle()
    print("[PASS] Registration tests")
    
    # Calibration tests
    t = TestCalibration()
    t.test_accuracy_calculation()
    t.test_brier_score()
    t.test_calibration_curve()
    t.test_calibration_report()
    print("[PASS] Calibration tests")
    
    # Prediction ID tests
    t = TestPredictionId()
    t.test_stable_id()
    t.test_different_inputs()
    t.test_id_length()
    print("[PASS] Prediction ID tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
