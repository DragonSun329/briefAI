"""
Unit Tests for Backtesting Framework

Tests prediction store, outcome tracking, and accuracy scoring.
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.prediction_store import (
    Prediction, PredictionStore, PredictionType, PredictionStatus, PredictionMode,
    create_prediction_from_divergence
)
from utils.outcome_tracker import OutcomeTracker, OutcomeDefinitions
from utils.accuracy_scorer import AccuracyScorer, AccuracyBucket


class TestPredictionStore(unittest.TestCase):
    """Tests for PredictionStore."""
    
    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_predictions.db")
        self.store = PredictionStore(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_add_and_get_prediction(self):
        """Test adding and retrieving a prediction."""
        pred = Prediction(
            id="test-1",
            entity_id="entity-1",
            entity_name="Test Entity",
            signal_type="divergence",
            prediction_type=PredictionType.RISING,
            predicted_outcome="Will rise",
            confidence=0.75,
            horizon_days=30,
        )
        
        self.store.add_prediction(pred)
        
        retrieved = self.store.get_prediction("test-1")
        
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.id, "test-1")
        self.assertEqual(retrieved.entity_name, "Test Entity")
        self.assertEqual(retrieved.prediction_type, PredictionType.RISING)
        self.assertEqual(retrieved.confidence, 0.75)
        self.assertEqual(retrieved.status, PredictionStatus.PENDING)
    
    def test_update_prediction(self):
        """Test updating a prediction status."""
        pred = Prediction(
            id="test-2",
            entity_id="entity-2",
            entity_name="Test Entity 2",
            signal_type="divergence",
            prediction_type=PredictionType.FALLING,
            predicted_outcome="Will fall",
            confidence=0.8,
            horizon_days=7,
        )
        
        self.store.add_prediction(pred)
        
        # Update status
        pred.status = PredictionStatus.CORRECT
        pred.resolved_at = datetime.utcnow()
        pred.actual_outcome = "It fell 20%"
        
        self.store.update_prediction(pred)
        
        retrieved = self.store.get_prediction("test-2")
        
        self.assertEqual(retrieved.status, PredictionStatus.CORRECT)
        self.assertEqual(retrieved.actual_outcome, "It fell 20%")
        self.assertIsNotNone(retrieved.resolved_at)
    
    def test_get_pending_predictions(self):
        """Test retrieving pending predictions."""
        # Add some predictions
        for i in range(5):
            status = PredictionStatus.PENDING if i < 3 else PredictionStatus.CORRECT
            pred = Prediction(
                id=f"test-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                status=status,
            )
            self.store.add_prediction(pred)
        
        pending = self.store.get_pending_predictions()
        
        self.assertEqual(len(pending), 3)
        for p in pending:
            self.assertEqual(p.status, PredictionStatus.PENDING)
    
    def test_get_pending_past_horizon(self):
        """Test retrieving only predictions past their horizon."""
        now = datetime.utcnow()
        
        # Past horizon
        past = Prediction(
            id="past-1",
            entity_id="entity-past",
            entity_name="Past Entity",
            signal_type="test",
            prediction_type=PredictionType.RISING,
            predicted_outcome="Will rise",
            confidence=0.7,
            horizon_days=7,
            predicted_at=now - timedelta(days=14),  # 14 days ago
        )
        
        # Future horizon
        future = Prediction(
            id="future-1",
            entity_id="entity-future",
            entity_name="Future Entity",
            signal_type="test",
            prediction_type=PredictionType.RISING,
            predicted_outcome="Will rise",
            confidence=0.7,
            horizon_days=30,
            predicted_at=now,  # Today
        )
        
        self.store.add_prediction(past)
        self.store.add_prediction(future)
        
        past_horizon = self.store.get_pending_predictions(past_horizon_only=True)
        
        self.assertEqual(len(past_horizon), 1)
        self.assertEqual(past_horizon[0].id, "past-1")
    
    def test_get_predictions_by_signal_type(self):
        """Test retrieving predictions by signal type."""
        for signal_type in ["divergence", "momentum", "divergence", "breakout"]:
            pred = Prediction(
                id=f"sig-{signal_type}-{datetime.utcnow().timestamp()}",
                entity_id="entity-1",
                entity_name="Test Entity",
                signal_type=signal_type,
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
            )
            self.store.add_prediction(pred)
        
        divergence_preds = self.store.get_predictions_by_signal_type("divergence")
        
        self.assertEqual(len(divergence_preds), 2)
        for p in divergence_preds:
            self.assertEqual(p.signal_type, "divergence")
    
    def test_get_stats(self):
        """Test getting prediction statistics."""
        # Add various predictions
        configs = [
            (PredictionStatus.CORRECT, "sig-a", 0.9),
            (PredictionStatus.CORRECT, "sig-a", 0.8),
            (PredictionStatus.INCORRECT, "sig-a", 0.7),
            (PredictionStatus.CORRECT, "sig-b", 0.6),
            (PredictionStatus.PENDING, "sig-b", 0.5),
        ]
        
        for i, (status, sig_type, conf) in enumerate(configs):
            pred = Prediction(
                id=f"stat-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type=sig_type,
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=conf,
                horizon_days=30,
                status=status,
            )
            self.store.add_prediction(pred)
        
        stats = self.store.get_stats()
        
        self.assertEqual(stats["total_predictions"], 5)
        self.assertEqual(stats["correct"], 3)
        self.assertEqual(stats["incorrect"], 1)
        self.assertEqual(stats["pending"], 1)
        self.assertAlmostEqual(stats["overall_accuracy"], 0.75)  # 3/4 resolved


class TestOutcomeDefinitions(unittest.TestCase):
    """Tests for OutcomeDefinitions."""
    
    def test_evaluate_rising_correct(self):
        """Test rising evaluation when prediction is correct."""
        is_correct, msg = OutcomeDefinitions.evaluate_rising(50, 60)
        
        self.assertTrue(is_correct)
        self.assertIn("rose", msg.lower())
    
    def test_evaluate_rising_incorrect(self):
        """Test rising evaluation when prediction is incorrect."""
        is_correct, msg = OutcomeDefinitions.evaluate_rising(50, 52)
        
        self.assertFalse(is_correct)
        self.assertIn("incorrect", msg.lower())
    
    def test_evaluate_falling_correct(self):
        """Test falling evaluation when prediction is correct."""
        is_correct, msg = OutcomeDefinitions.evaluate_falling(50, 40)
        
        self.assertTrue(is_correct)
        self.assertIn("fell", msg.lower())
    
    def test_evaluate_falling_incorrect(self):
        """Test falling evaluation when prediction is incorrect."""
        is_correct, msg = OutcomeDefinitions.evaluate_falling(50, 48)
        
        self.assertFalse(is_correct)
        self.assertIn("incorrect", msg.lower())
    
    def test_evaluate_breakout_correct(self):
        """Test breakout evaluation when prediction is correct."""
        is_correct, msg = OutcomeDefinitions.evaluate_breakout(5)
        
        self.assertTrue(is_correct)
        self.assertIn("mainstream", msg.lower())
    
    def test_evaluate_breakout_incorrect(self):
        """Test breakout evaluation when prediction is incorrect."""
        is_correct, msg = OutcomeDefinitions.evaluate_breakout(1)
        
        self.assertFalse(is_correct)
        self.assertIn("incorrect", msg.lower())
    
    def test_evaluate_decline_correct(self):
        """Test decline evaluation when prediction is correct."""
        is_correct, msg = OutcomeDefinitions.evaluate_decline(20)
        
        self.assertTrue(is_correct)
        self.assertIn("correct", msg.lower())
    
    def test_evaluate_decline_incorrect(self):
        """Test decline evaluation when prediction is incorrect."""
        is_correct, msg = OutcomeDefinitions.evaluate_decline(50)
        
        self.assertFalse(is_correct)
        self.assertIn("incorrect", msg.lower())
    
    def test_zero_baseline_handling(self):
        """Test handling of zero baseline values."""
        is_correct, msg = OutcomeDefinitions.evaluate_rising(0, 10)
        
        self.assertFalse(is_correct)
        self.assertIn("cannot evaluate", msg.lower())


class TestOutcomeTracker(unittest.TestCase):
    """Tests for OutcomeTracker."""
    
    def setUp(self):
        """Create temporary store and tracker."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_tracker.db")
        self.store = PredictionStore(db_path=self.db_path)
        self.tracker = OutcomeTracker(self.store)
    
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_resolve_rising_prediction_correct(self):
        """Test resolving a correct rising prediction."""
        pred = Prediction(
            id="resolve-1",
            entity_id="entity-1",
            entity_name="Test Entity",
            signal_type="test",
            prediction_type=PredictionType.RISING,
            predicted_outcome="Will rise",
            confidence=0.75,
            horizon_days=30,
            baseline_value=50.0,
            predicted_at=datetime.utcnow() - timedelta(days=35),
        )
        self.store.add_prediction(pred)
        
        current_data = {"current_value": 65.0}  # 30% increase
        
        resolved, msg = self.tracker.resolve_prediction(pred, current_data, dry_run=True)
        
        self.assertEqual(resolved.status, PredictionStatus.CORRECT)
        self.assertIn("✓", msg)
    
    def test_resolve_rising_prediction_incorrect(self):
        """Test resolving an incorrect rising prediction."""
        pred = Prediction(
            id="resolve-2",
            entity_id="entity-2",
            entity_name="Test Entity 2",
            signal_type="test",
            prediction_type=PredictionType.RISING,
            predicted_outcome="Will rise",
            confidence=0.75,
            horizon_days=30,
            baseline_value=50.0,
            predicted_at=datetime.utcnow() - timedelta(days=35),
        )
        self.store.add_prediction(pred)
        
        current_data = {"current_value": 52.0}  # Only 4% increase
        
        resolved, msg = self.tracker.resolve_prediction(pred, current_data, dry_run=True)
        
        self.assertEqual(resolved.status, PredictionStatus.INCORRECT)
        self.assertIn("✗", msg)
    
    def test_generate_resolution_report(self):
        """Test generating a resolution report."""
        predictions = []
        for i in range(3):
            pred = Prediction(
                id=f"report-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                status=PredictionStatus.CORRECT if i < 2 else PredictionStatus.INCORRECT,
                actual_outcome="Test outcome",
            )
            predictions.append(pred)
        
        report = self.tracker.generate_resolution_report(predictions)
        
        self.assertIn("Resolution Report", report)  # Title case
        self.assertIn("Correct: 2", report)
        self.assertIn("Incorrect: 1", report)


class TestAccuracyScorer(unittest.TestCase):
    """Tests for AccuracyScorer."""
    
    def setUp(self):
        """Create temporary store and scorer."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_accuracy.db")
        self.store = PredictionStore(db_path=self.db_path)
        self.scorer = AccuracyScorer(self.store)
    
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_brier_score_perfect(self):
        """Test Brier score with perfect predictions."""
        predictions = [
            Prediction(
                id=f"brier-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=1.0,  # 100% confident
                horizon_days=30,
                status=PredictionStatus.CORRECT,  # All correct
            )
            for i in range(10)
        ]
        
        brier = self.scorer.calculate_brier_score(predictions)
        
        # Perfect predictions with 100% confidence = 0 Brier score
        self.assertEqual(brier, 0.0)
    
    def test_brier_score_worst(self):
        """Test Brier score with worst predictions."""
        predictions = [
            Prediction(
                id=f"brier-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=1.0,  # 100% confident
                horizon_days=30,
                status=PredictionStatus.INCORRECT,  # All wrong
            )
            for i in range(10)
        ]
        
        brier = self.scorer.calculate_brier_score(predictions)
        
        # 100% confident but all wrong = 1.0 Brier score
        self.assertEqual(brier, 1.0)
    
    def test_brier_score_calibrated(self):
        """Test Brier score with calibrated predictions."""
        # 70% confidence, 70% correct = well calibrated
        predictions = []
        for i in range(10):
            predictions.append(Prediction(
                id=f"cal-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                status=PredictionStatus.CORRECT if i < 7 else PredictionStatus.INCORRECT,
            ))
        
        brier = self.scorer.calculate_brier_score(predictions)
        
        # Well calibrated should have low Brier score
        # 7 correct: (0.7-1)^2 * 7 = 0.09 * 7 = 0.63
        # 3 incorrect: (0.7-0)^2 * 3 = 0.49 * 3 = 1.47
        # Total: (0.63 + 1.47) / 10 = 0.21
        self.assertAlmostEqual(brier, 0.21, places=2)
    
    def test_calibration_buckets(self):
        """Test calibration bucket calculation."""
        predictions = []
        
        # Low confidence (0.3), 50% correct
        for i in range(4):
            predictions.append(Prediction(
                id=f"low-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.3,
                horizon_days=30,
                status=PredictionStatus.CORRECT if i < 2 else PredictionStatus.INCORRECT,
            ))
        
        # High confidence (0.9), 100% correct
        for i in range(4):
            predictions.append(Prediction(
                id=f"high-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.9,
                horizon_days=30,
                status=PredictionStatus.CORRECT,
            ))
        
        buckets = self.scorer.calculate_calibration_buckets(predictions)
        
        # Check that we have buckets
        self.assertTrue(len(buckets) > 0)
        
        # Find the buckets with data
        populated_buckets = [b for b in buckets if b.predictions > 0]
        self.assertTrue(len(populated_buckets) >= 2)
    
    def test_generate_report(self):
        """Test generating accuracy report."""
        # Add some predictions to the store
        for i in range(10):
            pred = Prediction(
                id=f"report-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="divergence" if i < 6 else "momentum",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7 + (i * 0.02),
                horizon_days=30,
                status=PredictionStatus.CORRECT if i < 7 else PredictionStatus.INCORRECT,
                resolved_at=datetime.utcnow() if i < 9 else None,
            )
            if i == 9:
                pred.status = PredictionStatus.PENDING
            self.store.add_prediction(pred)
        
        report = self.scorer.generate_report()
        
        self.assertEqual(report.total_predictions, 10)
        self.assertEqual(report.resolved_predictions, 9)
        self.assertIn("divergence", report.by_signal_type)
    
    def test_format_report(self):
        """Test formatting accuracy report."""
        # Add some predictions
        for i in range(5):
            pred = Prediction(
                id=f"format-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                status=PredictionStatus.CORRECT if i < 3 else PredictionStatus.INCORRECT,
                resolved_at=datetime.utcnow(),
            )
            self.store.add_prediction(pred)
        
        report = self.scorer.generate_report()
        formatted = self.scorer.format_report(report)
        
        self.assertIn("PREDICTION ACCURACY REPORT", formatted)
        self.assertIn("Overall Accuracy", formatted)
        self.assertIn("Brier Score", formatted)
    
    def test_signal_recommendation(self):
        """Test getting signal recommendation."""
        # Add predictions for signal type
        for i in range(15):
            pred = Prediction(
                id=f"rec-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test_signal",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                status=PredictionStatus.CORRECT if i < 10 else PredictionStatus.INCORRECT,
                resolved_at=datetime.utcnow(),
            )
            self.store.add_prediction(pred)
        
        rec = self.scorer.get_signal_recommendation("test_signal")
        
        # 10/15 = 66.7% accuracy = should be recommended
        self.assertTrue(rec["should_use"])
        self.assertEqual(rec["status"], "recommended")
    
    def test_signal_recommendation_insufficient_data(self):
        """Test recommendation with insufficient data."""
        # Only add 5 predictions
        for i in range(5):
            pred = Prediction(
                id=f"insuf-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="new_signal",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                status=PredictionStatus.CORRECT,
                resolved_at=datetime.utcnow(),
            )
            self.store.add_prediction(pred)
        
        rec = self.scorer.get_signal_recommendation("new_signal", min_predictions=10)
        
        self.assertEqual(rec["status"], "insufficient_data")
        self.assertEqual(rec["confidence_adjustment"], 0.7)


class TestPredictionFromDivergence(unittest.TestCase):
    """Tests for creating predictions from divergences."""
    
    def test_create_from_opportunity_divergence(self):
        """Test creating prediction from opportunity divergence."""
        from utils.signal_models import (
            SignalDivergence, DivergenceType, DivergenceInterpretation, SignalCategory
        )
        
        divergence = SignalDivergence(
            entity_id="test-entity",
            entity_name="Test Company",
            divergence_type=DivergenceType.TECHNICAL_VS_FINANCIAL,
            high_signal_category=SignalCategory.TECHNICAL,
            high_signal_score=80,
            low_signal_category=SignalCategory.FINANCIAL,
            low_signal_score=40,
            divergence_magnitude=40,
            confidence=0.8,
            interpretation=DivergenceInterpretation.OPPORTUNITY,
            interpretation_rationale="Technical leads financial",
        )
        
        pred = create_prediction_from_divergence(
            divergence,
            horizon_days=30,
            confidence_multiplier=1.0,
            mode=PredictionMode.PRODUCTION,
        )
        
        self.assertEqual(pred.entity_id, "test-entity")
        self.assertEqual(pred.prediction_type, PredictionType.RISING)
        self.assertEqual(pred.confidence, 0.8)
        self.assertEqual(pred.horizon_days, 30)
        self.assertEqual(pred.mode, PredictionMode.PRODUCTION)
        self.assertIn("technical", pred.predicted_outcome.lower())
    
    def test_create_from_risk_divergence(self):
        """Test creating prediction from risk divergence."""
        from utils.signal_models import (
            SignalDivergence, DivergenceType, DivergenceInterpretation, SignalCategory
        )
        
        divergence = SignalDivergence(
            entity_id="hype-entity",
            entity_name="Hype Company",
            divergence_type=DivergenceType.TECHNICAL_VS_MEDIA,
            high_signal_category=SignalCategory.MEDIA_SENTIMENT,
            high_signal_score=90,
            low_signal_category=SignalCategory.TECHNICAL,
            low_signal_score=30,
            divergence_magnitude=60,
            confidence=0.85,
            interpretation=DivergenceInterpretation.RISK,
            interpretation_rationale="Media hype without substance",
        )
        
        pred = create_prediction_from_divergence(
            divergence,
            horizon_days=14,
            confidence_multiplier=0.5,  # Discount for shadow mode
            mode=PredictionMode.SHADOW,
        )
        
        self.assertEqual(pred.prediction_type, PredictionType.DECLINE)
        self.assertEqual(pred.confidence, 0.425)  # 0.85 * 0.5
        self.assertEqual(pred.mode, PredictionMode.SHADOW)
        self.assertIn("hype", pred.predicted_outcome.lower())


class TestPredictionModes(unittest.TestCase):
    """Tests for production vs shadow modes."""
    
    def setUp(self):
        """Create temporary store."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_modes.db")
        self.store = PredictionStore(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_filter_by_mode(self):
        """Test filtering predictions by mode."""
        # Add production predictions
        for i in range(3):
            pred = Prediction(
                id=f"prod-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                mode=PredictionMode.PRODUCTION,
            )
            self.store.add_prediction(pred)
        
        # Add shadow predictions
        for i in range(2):
            pred = Prediction(
                id=f"shadow-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                mode=PredictionMode.SHADOW,
            )
            self.store.add_prediction(pred)
        
        prod_pending = self.store.get_pending_predictions(mode=PredictionMode.PRODUCTION)
        shadow_pending = self.store.get_pending_predictions(mode=PredictionMode.SHADOW)
        
        self.assertEqual(len(prod_pending), 3)
        self.assertEqual(len(shadow_pending), 2)
    
    def test_stats_by_mode(self):
        """Test getting stats filtered by mode."""
        # Add predictions with different modes
        for i, mode in enumerate([PredictionMode.PRODUCTION] * 3 + [PredictionMode.SHADOW] * 2):
            pred = Prediction(
                id=f"stat-{i}",
                entity_id=f"entity-{i}",
                entity_name=f"Entity {i}",
                signal_type="test",
                prediction_type=PredictionType.RISING,
                predicted_outcome="Will rise",
                confidence=0.7,
                horizon_days=30,
                mode=mode,
                status=PredictionStatus.CORRECT if i < 3 else PredictionStatus.INCORRECT,
            )
            self.store.add_prediction(pred)
        
        prod_stats = self.store.get_stats(mode=PredictionMode.PRODUCTION)
        shadow_stats = self.store.get_stats(mode=PredictionMode.SHADOW)
        
        self.assertEqual(prod_stats["total_predictions"], 3)
        self.assertEqual(shadow_stats["total_predictions"], 2)


if __name__ == "__main__":
    unittest.main()
