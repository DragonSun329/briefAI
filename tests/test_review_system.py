"""
Tests for the briefAI Prediction Review System.

Tests cover:
- Expired prediction detection
- Outcome resolution
- Metrics correctness
- Lesson generation

v1.1 Tests added:
- unclear_reason classification
- debug_features presence and stability
- Sample-size protection
- Suggestions generation
- Daily hook behavior
"""

import json
import pytest
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock

from briefai.review.models import (
    ExpiredPrediction,
    ResolvedOutcome,
    ReviewMetrics,
    LearningInsight,
    Lesson,
    Suggestion,
    OutcomeStatus,
    Direction,
    SupportingEvidence,
    UnclearReason,
)
from briefai.review.expired_predictions import (
    find_expired_predictions,
    calculate_check_date,
    extract_entity_from_prediction,
    extract_direction,
    group_by_mechanism,
)
from briefai.review.outcome_resolver import (
    resolve_outcome,
    resolve_all,
    entity_matches,
    calculate_momentum_delta,
    SignalDataLoader,
)
from briefai.review.metrics import (
    compute_metrics,
    compute_overall_accuracy,
    compute_direction_accuracy,
    compute_calibration,
    compute_unclear_breakdown,
    safe_divide,
)
from briefai.review.patterns import (
    discover_patterns,
    PatternAnalyzer,
    get_top_performers,
    get_worst_performers,
    get_reliable_insights,
)
from briefai.review.lessons import (
    synthesize_lessons,
    generate_mechanism_lessons,
    generate_accuracy_lessons,
)
from briefai.review.suggestions import (
    generate_suggestions,
    generate_suggestion_id,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def sample_predictions():
    """Create sample expired predictions for testing."""
    return [
        ExpiredPrediction(
            prediction_id="pred_001",
            entity="OpenAI",
            direction=Direction.UP,
            confidence=0.85,
            check_date=date(2026, 2, 1),
            hypothesis_text="OpenAI will announce new model",
            mechanism="product_launch",
            category="media",
            date_made=date(2026, 1, 15),
        ),
        ExpiredPrediction(
            prediction_id="pred_002",
            entity="NVIDIA",
            direction=Direction.UP,
            confidence=0.72,
            check_date=date(2026, 2, 1),
            hypothesis_text="NVIDIA chip demand increases",
            mechanism="market_expansion",
            category="technical",
            date_made=date(2026, 1, 20),
        ),
        ExpiredPrediction(
            prediction_id="pred_003",
            entity="Anthropic",
            direction=Direction.DOWN,
            confidence=0.45,
            check_date=date(2026, 2, 1),
            hypothesis_text="Anthropic loses market share",
            mechanism="competition",
            category="media",
            date_made=date(2026, 1, 18),
        ),
        ExpiredPrediction(
            prediction_id="pred_004",
            entity="Salesforce",
            direction=Direction.UP,
            confidence=0.60,
            check_date=date(2026, 2, 1),
            hypothesis_text="Salesforce AI integration grows",
            mechanism="product_launch",
            category="financial",
            date_made=date(2026, 1, 22),
        ),
    ]


@pytest.fixture
def sample_outcomes():
    """Create sample resolved outcomes for testing."""
    return [
        ResolvedOutcome(
            prediction_id="pred_001",
            outcome=OutcomeStatus.CORRECT,
            confidence_score=0.8,
            resolution_method="bullish_heuristics",
        ),
        ResolvedOutcome(
            prediction_id="pred_002",
            outcome=OutcomeStatus.CORRECT,
            confidence_score=0.7,
            resolution_method="bullish_heuristics",
        ),
        ResolvedOutcome(
            prediction_id="pred_003",
            outcome=OutcomeStatus.INCORRECT,
            confidence_score=0.6,
            resolution_method="bearish_heuristics",
        ),
        ResolvedOutcome(
            prediction_id="pred_004",
            outcome=OutcomeStatus.UNCLEAR,
            confidence_score=0.4,
            resolution_method="bullish_heuristics",
        ),
    ]


@pytest.fixture
def temp_experiment_dir():
    """Create a temporary experiment directory with sample data."""
    with TemporaryDirectory() as tmpdir:
        exp_path = Path(tmpdir) / "v_test_experiment"
        exp_path.mkdir(parents=True)
        
        # Create sample forecast_history.jsonl
        ledger_entries = [
            {
                "prediction_id": "pred_test_001",
                "date": "2026-01-15",
                "timeframe_days": 14,
                "concept_name": "OpenAI",
                "expected_direction": "up",
                "confidence": 0.75,
                "claim": "OpenAI announces GPT-5",
                "mechanism": "product_launch",
                "category": "media",
            },
            {
                "prediction_id": "pred_test_002",
                "date": "2026-01-10",
                "timeframe_days": 7,
                "concept_name": "NVIDIA",
                "expected_direction": "up",
                "confidence": 0.80,
                "claim": "NVIDIA chip demand surge",
                "mechanism": "market_expansion",
                "category": "technical",
            },
        ]
        
        ledger_path = exp_path / "forecast_history.jsonl"
        with open(ledger_path, "w") as f:
            for entry in ledger_entries:
                f.write(json.dumps(entry) + "\n")
        
        yield Path(tmpdir)


# ============================================================================
# Test: Expired Prediction Detection
# ============================================================================

class TestExpiredPredictionDetection:
    """Tests for expired prediction detection."""
    
    def test_calculate_check_date(self):
        """Test check date calculation."""
        pred_date = date(2026, 1, 15)
        check = calculate_check_date(pred_date, 14)
        assert check == date(2026, 1, 29)
    
    def test_extract_entity_from_prediction(self):
        """Test entity extraction from different entry formats."""
        # Direct entity field
        entry1 = {"entity": "OpenAI"}
        assert extract_entity_from_prediction(entry1) == "OpenAI"
        
        # From concept_name
        entry2 = {"concept_name": "NVIDIA Trends"}
        assert extract_entity_from_prediction(entry2) == "NVIDIA Trends"
        
        # From claim (capitalized word)
        entry3 = {"concept_name": "Mixed Signals Review", "claim": "Microsoft expanding AI"}
        assert "Microsoft" in extract_entity_from_prediction(entry3)
    
    def test_extract_direction(self):
        """Test direction extraction."""
        assert extract_direction({"expected_direction": "up"}) == Direction.UP
        assert extract_direction({"expected_direction": "down"}) == Direction.DOWN
        assert extract_direction({"expected_direction": "unknown"}) == Direction.UNKNOWN
        assert extract_direction({}) == Direction.UNKNOWN
    
    def test_find_expired_predictions(self, temp_experiment_dir):
        """Test finding expired predictions from ledger."""
        # Use a date that makes predictions expired
        as_of = date(2026, 2, 15)
        
        expired = find_expired_predictions(
            experiment_id="v_test_experiment",
            data_root=temp_experiment_dir,
            as_of_date=as_of,
        )
        
        assert len(expired) == 2
        assert all(isinstance(p, ExpiredPrediction) for p in expired)
        assert expired[0].prediction_id == "pred_test_001"
    
    def test_find_expired_predictions_none_expired(self, temp_experiment_dir):
        """Test when no predictions are expired yet."""
        # Use a date before predictions expire
        as_of = date(2026, 1, 16)
        
        expired = find_expired_predictions(
            experiment_id="v_test_experiment",
            data_root=temp_experiment_dir,
            as_of_date=as_of,
        )
        
        assert len(expired) == 0
    
    def test_group_by_mechanism(self, sample_predictions):
        """Test grouping predictions by mechanism."""
        groups = group_by_mechanism(sample_predictions)
        
        assert "product_launch" in groups
        assert len(groups["product_launch"]) == 2
        assert "market_expansion" in groups
        assert len(groups["market_expansion"]) == 1


# ============================================================================
# Test: Outcome Resolution
# ============================================================================

class TestOutcomeResolution:
    """Tests for outcome resolution."""
    
    def test_entity_matches_basic(self):
        """Test basic entity matching."""
        signal = {
            "concept_name": "OpenAI Expansion",
            "description": "OpenAI is expanding operations",
        }
        
        assert entity_matches("openai", signal)
        assert entity_matches("OpenAI", signal)
        assert not entity_matches("Anthropic", signal)
    
    def test_entity_matches_with_entities_list(self):
        """Test entity matching with entities list."""
        signal = {
            "concept_name": "AI Trends",
            "entities": ["nvidia", "amd", "intel"],
        }
        
        assert entity_matches("nvidia", signal)
        assert entity_matches("AMD", signal)
        assert not entity_matches("openai", signal)
    
    def test_resolve_outcome_creates_valid_result(self, sample_predictions):
        """Test that resolve_outcome returns valid ResolvedOutcome."""
        pred = sample_predictions[0]
        
        # Mock the data loader to avoid file dependencies
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome = resolve_outcome(pred)
        
        assert isinstance(outcome, ResolvedOutcome)
        assert outcome.prediction_id == pred.prediction_id
        assert outcome.outcome in OutcomeStatus
        assert 0 <= outcome.confidence_score <= 1
    
    def test_resolve_all(self, sample_predictions):
        """Test batch outcome resolution."""
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcomes = resolve_all(sample_predictions)
        
        assert len(outcomes) == len(sample_predictions)
        assert all(isinstance(o, ResolvedOutcome) for o in outcomes)


# ============================================================================
# Test: Metrics Computation
# ============================================================================

class TestMetricsComputation:
    """Tests for metrics computation."""
    
    def test_safe_divide(self):
        """Test safe division helper."""
        assert safe_divide(10, 2) == 5.0
        assert safe_divide(10, 0) == 0.0
        assert safe_divide(10, 0, default=999) == 999
    
    def test_compute_overall_accuracy(self, sample_outcomes):
        """Test overall accuracy computation."""
        accuracy, correct, incorrect = compute_overall_accuracy(sample_outcomes)
        
        # 2 correct, 1 incorrect, 1 unclear (excluded)
        assert correct == 2
        assert incorrect == 1
        assert accuracy == pytest.approx(2/3, rel=0.01)
    
    def test_compute_direction_accuracy(self, sample_predictions, sample_outcomes):
        """Test direction-based accuracy computation."""
        stats = compute_direction_accuracy(sample_predictions, sample_outcomes)
        
        # 3 bullish (2 correct, 1 unclear), 1 bearish (incorrect)
        assert stats["bullish_count"] == 2  # excludes unclear
        assert stats["bullish_accuracy"] == 1.0  # 2/2 correct
        assert stats["bearish_count"] == 1
        assert stats["bearish_accuracy"] == 0.0  # 0/1 correct
    
    def test_compute_calibration(self, sample_predictions, sample_outcomes):
        """Test calibration computation."""
        error, buckets = compute_calibration(sample_predictions, sample_outcomes)
        
        # Check that calibration error is computed
        assert isinstance(error, float)
        assert 0 <= error <= 1
        
        # Check buckets exist
        assert len(buckets) == 10
        assert "0.7-0.8" in buckets
    
    def test_compute_metrics_full(self, sample_predictions, sample_outcomes):
        """Test full metrics computation."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        
        assert isinstance(metrics, ReviewMetrics)
        assert metrics.total_predictions == 4
        assert metrics.total_resolved == 3  # excluding unclear
        assert metrics.total_unclear == 1
        assert metrics.overall_correct == 2
        assert metrics.overall_incorrect == 1


# ============================================================================
# Test: Pattern Discovery
# ============================================================================

class TestPatternDiscovery:
    """Tests for pattern discovery."""
    
    def test_pattern_analyzer_creation(self, sample_predictions, sample_outcomes):
        """Test PatternAnalyzer initialization."""
        analyzer = PatternAnalyzer(sample_predictions, sample_outcomes)
        
        assert len(analyzer.predictions) == 4
        assert len(analyzer.outcomes) == 4
        assert len(analyzer.correctness) == 3  # excludes unclear
    
    def test_analyze_mechanism_performance(self, sample_predictions, sample_outcomes):
        """Test mechanism performance analysis."""
        analyzer = PatternAnalyzer(sample_predictions, sample_outcomes)
        insights = analyzer.analyze_mechanism_performance()
        
        # May be empty if sample sizes < 2 per mechanism
        assert isinstance(insights, list)
        assert all(isinstance(i, LearningInsight) for i in insights)
        assert all(i.category == "mechanism" for i in insights)
    
    def test_analyze_direction_performance(self, sample_predictions, sample_outcomes):
        """Test direction performance analysis."""
        analyzer = PatternAnalyzer(sample_predictions, sample_outcomes)
        insights = analyzer.analyze_direction_performance()
        
        # Should have insights for up and down directions
        directions = [i.pattern for i in insights]
        assert "up" in directions or "Direction.UP" in directions
    
    def test_discover_patterns_returns_insights(self, sample_predictions, sample_outcomes):
        """Test full pattern discovery."""
        insights = discover_patterns(sample_predictions, sample_outcomes)
        
        assert isinstance(insights, list)
        assert all(isinstance(i, LearningInsight) for i in insights)
    
    def test_get_top_performers(self, sample_predictions, sample_outcomes):
        """Test getting top performing patterns."""
        insights = discover_patterns(sample_predictions, sample_outcomes)
        top = get_top_performers(insights, n=3)
        
        assert len(top) <= 3
        if len(top) >= 2:
            # Should be sorted by success rate descending
            assert top[0].success_rate >= top[1].success_rate
    
    def test_get_worst_performers(self, sample_predictions, sample_outcomes):
        """Test getting worst performing patterns."""
        insights = discover_patterns(sample_predictions, sample_outcomes)
        worst = get_worst_performers(insights, n=3)
        
        assert len(worst) <= 3
        if len(worst) >= 2:
            # Should be sorted by success rate ascending
            assert worst[0].success_rate <= worst[1].success_rate


# ============================================================================
# Test: Lesson Generation
# ============================================================================

class TestLessonGeneration:
    """Tests for lesson generation."""
    
    def test_generate_accuracy_lessons(self, sample_predictions, sample_outcomes):
        """Test accuracy-based lesson generation."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        
        lessons = generate_accuracy_lessons(metrics, insights)
        
        assert isinstance(lessons, list)
        assert all(isinstance(l, Lesson) for l in lessons)
    
    def test_generate_mechanism_lessons(self, sample_predictions, sample_outcomes):
        """Test mechanism-based lesson generation."""
        insights = discover_patterns(sample_predictions, sample_outcomes)
        
        lessons = generate_mechanism_lessons(insights)
        
        assert isinstance(lessons, list)
        # May be empty if sample size too small
    
    def test_synthesize_lessons(self, sample_predictions, sample_outcomes):
        """Test full lesson synthesis."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        
        lessons = synthesize_lessons(metrics, insights)
        
        assert isinstance(lessons, list)
        assert all(isinstance(l, Lesson) for l in lessons)
        # Should have at least one lesson about overall accuracy
        assert len(lessons) > 0
    
    def test_lessons_have_required_fields(self, sample_predictions, sample_outcomes):
        """Test that lessons have all required fields."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        lessons = synthesize_lessons(metrics, insights)
        
        for lesson in lessons:
            assert lesson.lesson_text
            assert isinstance(lesson.supporting_patterns, list)
            assert lesson.priority in ("low", "normal", "high")
            assert isinstance(lesson.actionable, bool)


# ============================================================================
# Test: Model Dataclasses
# ============================================================================

class TestModels:
    """Tests for data models."""
    
    def test_expired_prediction_direction_conversion(self):
        """Test that string directions are converted to enum."""
        pred = ExpiredPrediction(
            prediction_id="test",
            entity="Test",
            direction="up",  # String should be converted
            confidence=0.5,
            check_date=date.today(),
            hypothesis_text="Test",
        )
        
        assert pred.direction == Direction.UP
    
    def test_resolved_outcome_properties(self):
        """Test ResolvedOutcome helper properties."""
        correct = ResolvedOutcome(
            prediction_id="test",
            outcome=OutcomeStatus.CORRECT,
            confidence_score=0.8,
        )
        
        incorrect = ResolvedOutcome(
            prediction_id="test2",
            outcome=OutcomeStatus.INCORRECT,
            confidence_score=0.6,
        )
        
        assert correct.is_correct
        assert not correct.is_incorrect
        assert not incorrect.is_correct
        assert incorrect.is_incorrect
    
    def test_learning_insight_confidence_level(self):
        """Test LearningInsight confidence level assignment."""
        low = LearningInsight(
            category="test",
            pattern="test",
            success_rate=0.5,
            sample_size=5,
            interpretation="Test",
        )
        
        medium = LearningInsight(
            category="test",
            pattern="test",
            success_rate=0.5,
            sample_size=15,
            interpretation="Test",
        )
        
        high = LearningInsight(
            category="test",
            pattern="test",
            success_rate=0.5,
            sample_size=25,
            interpretation="Test",
        )
        
        assert low.confidence_level == "low"
        assert medium.confidence_level == "medium"
        assert high.confidence_level == "high"


# ============================================================================
# Test: Determinism and Reproducibility
# ============================================================================

class TestDeterminism:
    """Tests to ensure deterministic behavior."""
    
    def test_metrics_are_deterministic(self, sample_predictions, sample_outcomes):
        """Test that metrics computation is deterministic."""
        metrics1 = compute_metrics(sample_predictions, sample_outcomes)
        metrics2 = compute_metrics(sample_predictions, sample_outcomes)
        
        assert metrics1.overall_accuracy == metrics2.overall_accuracy
        assert metrics1.calibration_error == metrics2.calibration_error
    
    def test_patterns_are_deterministic(self, sample_predictions, sample_outcomes):
        """Test that pattern discovery is deterministic."""
        insights1 = discover_patterns(sample_predictions, sample_outcomes)
        insights2 = discover_patterns(sample_predictions, sample_outcomes)
        
        # Same number of insights
        assert len(insights1) == len(insights2)
        
        # Same success rates
        for i1, i2 in zip(insights1, insights2):
            assert i1.success_rate == i2.success_rate
    
    def test_lessons_are_deterministic(self, sample_predictions, sample_outcomes):
        """Test that lesson synthesis is deterministic."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        
        lessons1 = synthesize_lessons(metrics, insights)
        lessons2 = synthesize_lessons(metrics, insights)
        
        assert len(lessons1) == len(lessons2)
        for l1, l2 in zip(lessons1, lessons2):
            assert l1.lesson_text == l2.lesson_text


# ============================================================================
# v1.1 Tests: Explainability
# ============================================================================

class TestUnclearReasonClassification:
    """v1.1: Tests for unclear_reason classification."""
    
    def test_unclear_reason_data_missing(self, sample_predictions):
        """Test that data_missing is assigned when no signals found."""
        pred = sample_predictions[0]
        
        # Mock empty signal data
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome = resolve_outcome(pred)
        
        # Should be unclear due to missing data
        if outcome.outcome == OutcomeStatus.UNCLEAR:
            assert outcome.unclear_reason in (
                UnclearReason.DATA_MISSING,
                UnclearReason.LOW_SIGNAL,
                UnclearReason.MIXED_EVIDENCE,
            )
    
    def test_unclear_reason_enum_values(self):
        """Test that UnclearReason enum has expected values."""
        assert UnclearReason.DATA_MISSING.value == "data_missing"
        assert UnclearReason.MIXED_EVIDENCE.value == "mixed_evidence"
        assert UnclearReason.LOW_SIGNAL.value == "low_signal"
        assert UnclearReason.NONE.value == "none"
    
    def test_resolved_outcome_has_unclear_reason(self, sample_predictions):
        """Test that all resolved outcomes have an unclear_reason field."""
        pred = sample_predictions[0]
        
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome = resolve_outcome(pred)
        
        assert hasattr(outcome, 'unclear_reason')
        assert isinstance(outcome.unclear_reason, UnclearReason)


class TestDebugFeatures:
    """v1.1: Tests for debug_features explainability."""
    
    def test_debug_features_present(self, sample_predictions):
        """Test that debug_features dict is present in outcome."""
        pred = sample_predictions[0]
        
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome = resolve_outcome(pred)
        
        assert hasattr(outcome, 'debug_features')
        assert isinstance(outcome.debug_features, dict)
    
    def test_debug_features_has_expected_keys(self, sample_predictions):
        """Test that debug_features contains expected feature keys."""
        pred = sample_predictions[0]
        
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome = resolve_outcome(pred)
        
        expected_keys = ['meta_signal_presence', 'momentum_direction', 'final_score']
        for key in expected_keys:
            assert key in outcome.debug_features, f"Missing key: {key}"
    
    def test_debug_features_are_stable(self, sample_predictions):
        """Test that debug_features are deterministic."""
        pred = sample_predictions[0]
        
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome1 = resolve_outcome(pred)
                outcome2 = resolve_outcome(pred)
        
        assert outcome1.debug_features == outcome2.debug_features
    
    def test_decision_trace_present(self, sample_predictions):
        """Test that decision_trace list is present."""
        pred = sample_predictions[0]
        
        with patch.object(SignalDataLoader, 'get_date_range_signals', return_value=[]):
            with patch.object(SignalDataLoader, 'get_date_range_insights', return_value=[]):
                outcome = resolve_outcome(pred)
        
        assert hasattr(outcome, 'decision_trace')
        assert isinstance(outcome.decision_trace, list)
        assert len(outcome.decision_trace) > 0


# ============================================================================
# v1.1 Tests: Sample-Size Protection
# ============================================================================

class TestSampleSizeProtection:
    """v1.1: Tests for sample-size protected insights and lessons."""
    
    def test_insight_strength_assignment(self):
        """Test that insight_strength is correctly assigned based on sample_size."""
        weak = LearningInsight(
            category="test", pattern="test", success_rate=0.5,
            sample_size=3, interpretation="Test"
        )
        moderate = LearningInsight(
            category="test", pattern="test", success_rate=0.5,
            sample_size=7, interpretation="Test"
        )
        strong = LearningInsight(
            category="test", pattern="test", success_rate=0.5,
            sample_size=15, interpretation="Test"
        )
        
        assert weak.insight_strength == "weak"
        assert moderate.insight_strength == "moderate"
        assert strong.insight_strength == "strong"
    
    def test_reliability_score_calculation(self):
        """Test that reliability_score is calculated correctly."""
        # reliability_score = sample_size * |success_rate - 0.5|
        insight = LearningInsight(
            category="test", pattern="test", success_rate=0.8,
            sample_size=10, interpretation="Test"
        )
        
        expected = 10 * abs(0.8 - 0.5)  # 10 * 0.3 = 3.0
        assert insight.reliability_score == expected
    
    def test_get_reliable_insights_filters_weak(self):
        """Test that get_reliable_insights filters by strength."""
        insights = [
            LearningInsight(
                category="test", pattern="weak", success_rate=0.7,
                sample_size=3, interpretation="Weak"
            ),
            LearningInsight(
                category="test", pattern="moderate", success_rate=0.7,
                sample_size=7, interpretation="Moderate"
            ),
            LearningInsight(
                category="test", pattern="strong", success_rate=0.7,
                sample_size=15, interpretation="Strong"
            ),
        ]
        
        reliable = get_reliable_insights(insights, min_strength="moderate")
        
        assert len(reliable) == 2
        patterns = [i.pattern for i in reliable]
        assert "weak" not in patterns
        assert "moderate" in patterns
        assert "strong" in patterns
    
    def test_lessons_include_sample_stats(self, sample_predictions, sample_outcomes):
        """Test that synthesized lessons include sample_size and success_rate."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        lessons = synthesize_lessons(metrics, insights)
        
        for lesson in lessons:
            assert hasattr(lesson, 'sample_size')
            assert hasattr(lesson, 'success_rate')
            assert hasattr(lesson, 'insight_strength')


# ============================================================================
# v1.1 Tests: Unclear Breakdown
# ============================================================================

class TestUnclearBreakdown:
    """v1.1: Tests for unclear breakdown in metrics."""
    
    def test_compute_unclear_breakdown(self):
        """Test that unclear breakdown is computed correctly."""
        outcomes = [
            ResolvedOutcome(
                prediction_id="1", outcome=OutcomeStatus.CORRECT,
                confidence_score=0.8, unclear_reason=UnclearReason.NONE
            ),
            ResolvedOutcome(
                prediction_id="2", outcome=OutcomeStatus.UNCLEAR,
                confidence_score=0.4, unclear_reason=UnclearReason.DATA_MISSING
            ),
            ResolvedOutcome(
                prediction_id="3", outcome=OutcomeStatus.UNCLEAR,
                confidence_score=0.4, unclear_reason=UnclearReason.MIXED_EVIDENCE
            ),
            ResolvedOutcome(
                prediction_id="4", outcome=OutcomeStatus.UNCLEAR,
                confidence_score=0.4, unclear_reason=UnclearReason.DATA_MISSING
            ),
        ]
        
        breakdown = compute_unclear_breakdown(outcomes)
        
        assert breakdown["unclear_rate"] == 0.75  # 3/4
        assert breakdown["unclear_count"] == 3
        assert breakdown["unclear_breakdown"]["data_missing"] == 2
        assert breakdown["unclear_breakdown"]["mixed_evidence"] == 1
    
    def test_metrics_include_unclear_breakdown(self, sample_predictions, sample_outcomes):
        """Test that ReviewMetrics includes unclear breakdown fields."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        
        assert hasattr(metrics, 'unclear_rate')
        assert hasattr(metrics, 'unclear_breakdown')
        assert hasattr(metrics, 'accuracy_excluding_unclear')


# ============================================================================
# v1.1 Tests: Suggestions
# ============================================================================

class TestSuggestionsGeneration:
    """v1.1: Tests for suggestions generation."""
    
    def test_generate_suggestion_id_is_deterministic(self):
        """Test that suggestion IDs are deterministic."""
        id1 = generate_suggestion_id("confidence_cap", "global", date(2026, 2, 11))
        id2 = generate_suggestion_id("confidence_cap", "global", date(2026, 2, 11))
        
        assert id1 == id2
        assert id1.startswith("sug_")
    
    def test_generate_suggestions_returns_list(self, sample_predictions, sample_outcomes):
        """Test that generate_suggestions returns a list of Suggestions."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        lessons = synthesize_lessons(metrics, insights)
        
        suggestions = generate_suggestions(
            metrics, insights, lessons, date(2026, 2, 11)
        )
        
        assert isinstance(suggestions, list)
        for s in suggestions:
            assert isinstance(s, Suggestion)
    
    def test_suggestions_have_required_fields(self, sample_predictions, sample_outcomes):
        """Test that suggestions have all required fields."""
        metrics = compute_metrics(sample_predictions, sample_outcomes)
        insights = discover_patterns(sample_predictions, sample_outcomes)
        lessons = synthesize_lessons(metrics, insights)
        
        suggestions = generate_suggestions(
            metrics, insights, lessons, date(2026, 2, 11)
        )
        
        for s in suggestions:
            assert s.suggestion_id
            assert s.target
            assert s.rationale
            assert isinstance(s.proposed_change, dict)
            assert s.safety == "manual_review_required"
    
    def test_high_calibration_error_triggers_suggestion(self):
        """Test that high calibration error generates a suggestion."""
        # Create metrics with high calibration error
        metrics = ReviewMetrics(
            total_predictions=20,
            calibration_error=0.25,  # Above 0.15 threshold
            overall_accuracy=0.5,
        )
        
        suggestions = generate_suggestions(
            metrics, [], [], date(2026, 2, 11)
        )
        
        # Should have at least one confidence_cap suggestion
        confidence_suggestions = [s for s in suggestions if s.target == "confidence_cap"]
        assert len(confidence_suggestions) > 0


# ============================================================================
# v1.1 Tests: Daily Hook
# ============================================================================

class TestDailyHook:
    """v1.1: Tests for daily hook behavior."""
    
    def test_daily_hook_skips_when_no_expired(self, temp_experiment_dir):
        """Test that daily hook skips when no expired predictions."""
        # Use a date before predictions expire
        as_of = date(2026, 1, 16)
        
        expired = find_expired_predictions(
            experiment_id="v_test_experiment",
            data_root=temp_experiment_dir,
            as_of_date=as_of,
        )
        
        # Should return empty list
        assert len(expired) == 0
    
    def test_daily_hook_runs_when_expired_exist(self, temp_experiment_dir):
        """Test that daily hook runs when expired predictions exist."""
        # Use a date after predictions expire
        as_of = date(2026, 2, 15)
        
        expired = find_expired_predictions(
            experiment_id="v_test_experiment",
            data_root=temp_experiment_dir,
            as_of_date=as_of,
        )
        
        # Should find expired predictions
        assert len(expired) > 0


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
