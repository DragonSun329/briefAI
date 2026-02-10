"""
Tests for Hypothesis Engine v2.1 - Observability & Auditability Upgrade.

Test Coverage:
1. Canonical metric mapping works
2. Observable query exists for every prediction
3. Watch items sorted correctly
4. Confidence transparency fields exist
5. Primary vs secondary evidence separation
6. Falsifiers contain observable structure
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.hypothesis_engine import (
    # v2.1 Data structures
    ConfidenceInputs,
    ConfidenceDebug,
    ObservableQuery,
    WatchItem,
    FalsifierObservable,
    MeasurableFalsifier,
    
    # v2.0 + v2.1 Data structures
    MechanismTrace,
    PredictedSignal,
    Hypothesis,
    MetaHypothesisBundle,
    HypothesisEngine,
    
    # v2.1 Functions
    get_canonical_metric,
    get_metric_defaults,
    build_observable_query,
    normalize_direction,
    get_timeframe_bucket,
    classify_evidence_sources,
    build_watch_items,
    load_observable_metrics,
    
    # Constants
    PRIMARY_EVIDENCE_SOURCES,
    SECONDARY_EVIDENCE_SOURCES,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_strong_meta():
    """Create a strong meta-signal for testing."""
    return {
        'meta_id': 'meta_strong_v21',
        'concept_slug': 'slug_strong_v21',
        'concept_name': 'Enterprise AI Adoption Accelerating',
        'description': 'Multiple signals indicate enterprise adoption of AI is accelerating.',
        'maturity_stage': 'trending',
        'concept_confidence': 0.78,
        'persistence_days': 5,
        'independence_score': 0.85,
        'acceleration': 0.8,
        'category_diversity': {
            'categories': ['technical', 'financial', 'media'],
            'category_count': 3,
        },
        'review_required': False,
        'mechanism': 'enterprise-adoption',
        'naming_reason': {
            'mechanism_terms': ['enterprise', 'adoption'],
            'mechanism_bucket': 'enterprise-adoption',
        },
        'supporting_signals': ['sig1', 'sig2'],
        'supporting_insights': [
            {
                'signal_id': 'sig1',
                'signal_name': 'Enterprise Signal',
                'insight_text': 'Enterprise AI contract volume increasing.',
                'entities': ['company_a'],
                'buckets': ['enterprise', 'deployment'],
            },
        ],
    }


def make_weak_meta():
    """Create a weak meta-signal for testing."""
    return {
        'meta_id': 'meta_weak_v21',
        'concept_slug': 'slug_weak_v21',
        'concept_name': 'AI Buzz',
        'description': 'Media attention on AI.',
        'maturity_stage': 'weak',
        'concept_confidence': 0.42,
        'persistence_days': 1,
        'independence_score': 0.3,
        'category_diversity': {
            'categories': ['media'],
            'category_count': 1,
        },
        'review_required': True,
        'supporting_signals': ['sig5'],
        'supporting_insights': [
            {
                'signal_id': 'sig5',
                'signal_name': 'Media Buzz',
                'insight_text': 'News coverage of AI.',
                'entities': [],
                'buckets': ['media'],
            },
        ],
    }


# =============================================================================
# TEST: CANONICAL METRIC MAPPING
# =============================================================================

class TestCanonicalMetricMapping:
    """Test canonical metric type mapping (v2.1 Part 2)."""
    
    def test_direct_match(self):
        """Direct metric names should map correctly."""
        canonical, cat = get_canonical_metric("arr", "financial")
        assert canonical == "arr"
        assert cat == "financial"
    
    def test_alias_match(self):
        """Alias names should map to canonical."""
        canonical, cat = get_canonical_metric("revenue", "financial")
        assert canonical == "arr"
        
        canonical, cat = get_canonical_metric("stars", "technical")
        assert canonical == "repo_stars"
    
    def test_cross_category_search(self):
        """Should search all categories if none specified."""
        canonical, cat = get_canonical_metric("repo_stars", None)
        assert canonical == "repo_stars"
        assert cat == "technical"
    
    def test_fallback_to_custom(self):
        """Unknown metrics should fall back to custom_metric."""
        canonical, cat = get_canonical_metric("unknown_xyz_metric", None)
        assert canonical == "custom_metric"
    
    def test_metric_defaults(self):
        """Should get correct defaults for canonical metrics."""
        defaults = get_metric_defaults("arr", "financial")
        assert 'default_source' in defaults
        assert 'default_aggregation' in defaults
        assert 'default_window_days' in defaults


# =============================================================================
# TEST: OBSERVABLE QUERY
# =============================================================================

class TestObservableQuery:
    """Test observable query generation (v2.1 Part 3)."""
    
    def test_observable_query_creation(self):
        """Observable query should be created correctly."""
        query = build_observable_query(
            category='financial',
            metric='revenue',
            direction='increase',
            sources=['sec', 'earnings_call'],
            timeframe_days=30,
        )
        
        assert isinstance(query, ObservableQuery)
        assert query.source in ['sec', 'earnings_call']
        assert query.window_days == 30
        assert query.expected_direction in ['up', 'down', 'increase', 'decrease']
    
    def test_direction_normalization(self):
        """Direction should be normalized."""
        assert normalize_direction("increase") == "up"
        assert normalize_direction("rise") == "up"
        assert normalize_direction("grow") == "up"
        assert normalize_direction("decline") == "down"
        assert normalize_direction("drop") == "down"
        assert normalize_direction("fall") == "down"
    
    def test_every_prediction_has_observable(self):
        """Every prediction should have observable_query."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                assert pred.observable_query is not None, \
                    f"Prediction '{pred.description}' missing observable_query"
                assert isinstance(pred.observable_query, ObservableQuery)
    
    def test_observable_query_serialization(self):
        """Observable query should serialize/deserialize."""
        query = ObservableQuery(
            source='github',
            query='repo:test stars',
            aggregation='count',
            window_days=14,
            expected_direction='up',
        )
        
        d = query.to_dict()
        restored = ObservableQuery.from_dict(d)
        
        assert restored.source == query.source
        assert restored.query == query.query
        assert restored.window_days == query.window_days


# =============================================================================
# TEST: RANKED WATCHLIST
# =============================================================================

class TestRankedWatchlist:
    """Test ranked watchlist with priority scoring (v2.1 Part 4)."""
    
    def test_watch_items_sorted_by_score(self):
        """Watch items should be sorted by priority score."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        if len(bundle.watch_items) > 1:
            scores = [w.watch_priority_score for w in bundle.watch_items]
            assert scores == sorted(scores, reverse=True), \
                "Watch items not sorted by score"
    
    def test_watch_item_structure(self):
        """Watch items should have correct structure."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for item in bundle.watch_items:
            assert isinstance(item, WatchItem)
            assert hasattr(item, 'description')
            assert hasattr(item, 'watch_priority_score')
            assert hasattr(item, 'watch_priority_reason')
            assert hasattr(item, 'timeframe_bucket')
            assert item.timeframe_bucket in ['7d', '14d', '30d', '60d']
    
    def test_timeframe_bucket_assignment(self):
        """Timeframe buckets should be assigned correctly."""
        assert get_timeframe_bucket(5) == '7d'
        assert get_timeframe_bucket(7) == '7d'
        assert get_timeframe_bucket(10) == '14d'
        assert get_timeframe_bucket(14) == '14d'
        assert get_timeframe_bucket(20) == '30d'
        assert get_timeframe_bucket(30) == '30d'
        assert get_timeframe_bucket(45) == '60d'
        assert get_timeframe_bucket(60) == '60d'
    
    def test_what_to_watch_next_populated(self):
        """Legacy what_to_watch_next should still be populated."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        assert len(bundle.what_to_watch_next) > 0
        # Should match watch_items descriptions
        watch_descs = [w.description for w in bundle.watch_items]
        for desc in bundle.what_to_watch_next:
            assert desc in watch_descs
    
    def test_watch_item_serialization(self):
        """Watch items should serialize correctly."""
        item = WatchItem(
            description='Test item',
            watch_priority_score=0.75,
            watch_priority_reason=['reason1', 'reason2'],
            timeframe_bucket='14d',
        )
        
        d = item.to_dict()
        restored = WatchItem.from_dict(d)
        
        assert restored.description == item.description
        assert restored.watch_priority_score == item.watch_priority_score
        assert restored.timeframe_bucket == item.timeframe_bucket


# =============================================================================
# TEST: CONFIDENCE TRANSPARENCY
# =============================================================================

class TestConfidenceTransparency:
    """Test confidence transparency fields (v2.1 Part 1)."""
    
    def test_confidence_inputs_present(self):
        """Hypotheses should have confidence_inputs."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            assert hyp.confidence_inputs is not None
            assert isinstance(hyp.confidence_inputs, ConfidenceInputs)
    
    def test_confidence_debug_present(self):
        """Hypotheses should have confidence_debug."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            assert hyp.confidence_debug is not None
            assert isinstance(hyp.confidence_debug, ConfidenceDebug)
    
    def test_confidence_inputs_values(self):
        """Confidence inputs should have correct values."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        hyp = bundle.hypotheses[0]
        
        # meta_confidence_raw should match original
        assert hyp.confidence_inputs.meta_confidence_raw == meta['concept_confidence']
        
        # scaling factor should be the weight
        assert hyp.confidence_inputs.meta_to_hypothesis_scaling == 0.55
    
    def test_confidence_debug_consistency(self):
        """Confidence debug should be consistent with breakdown."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        hyp = bundle.hypotheses[0]
        
        # base_scaled should match breakdown
        expected_base = hyp.confidence_inputs.meta_confidence_raw * hyp.confidence_inputs.meta_to_hypothesis_scaling
        assert abs(hyp.confidence_debug.base_scaled - expected_base) < 0.001
    
    def test_confidence_serialization(self):
        """Confidence fields should serialize correctly."""
        inputs = ConfidenceInputs(
            meta_confidence_raw=0.75,
            meta_to_hypothesis_scaling=0.55,
        )
        
        d = inputs.to_dict()
        restored = ConfidenceInputs.from_dict(d)
        
        assert restored.meta_confidence_raw == inputs.meta_confidence_raw
        assert restored.meta_to_hypothesis_scaling == inputs.meta_to_hypothesis_scaling


# =============================================================================
# TEST: EVIDENCE SOURCE SEPARATION
# =============================================================================

class TestEvidenceSourceSeparation:
    """Test primary vs secondary evidence sources (v2.1 Part 5)."""
    
    def test_classify_evidence_sources(self):
        """Sources should be classified correctly."""
        sources = ['concept_name', 'meta_insight', 'naming_reason', 'mechanism_bucket', 'bucket_tags']
        primary, secondary = classify_evidence_sources(sources)
        
        assert 'concept_name' in primary
        assert 'meta_insight' in primary
        assert 'bucket_tags' in primary
        assert 'naming_reason' in secondary
        assert 'mechanism_bucket' in secondary
    
    def test_mechanism_trace_has_split_sources(self):
        """Mechanism trace should have primary/secondary sources."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            if hyp.mechanism_trace:
                # Should have both lists (may be empty)
                assert hasattr(hyp.mechanism_trace, 'evidence_sources_primary')
                assert hasattr(hyp.mechanism_trace, 'evidence_sources_secondary')
                # Legacy field should still exist
                assert hasattr(hyp.mechanism_trace, 'evidence_sources')
    
    def test_primary_sources_are_valid(self):
        """Primary sources should only contain allowed values."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            if hyp.mechanism_trace:
                for src in hyp.mechanism_trace.evidence_sources_primary:
                    assert src in PRIMARY_EVIDENCE_SOURCES, \
                        f"'{src}' not a valid primary source"
    
    def test_secondary_sources_are_valid(self):
        """Secondary sources should only contain allowed values."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            if hyp.mechanism_trace:
                for src in hyp.mechanism_trace.evidence_sources_secondary:
                    assert src in SECONDARY_EVIDENCE_SOURCES, \
                        f"'{src}' not a valid secondary source"


# =============================================================================
# TEST: MEASURABLE FALSIFIERS
# =============================================================================

class TestMeasurableFalsifiers:
    """Test measurable falsifiers (v2.1 Part 6)."""
    
    def test_falsifiers_v2_present(self):
        """Hypotheses should have falsifiers_v2."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            assert hasattr(hyp, 'falsifiers_v2')
            assert len(hyp.falsifiers_v2) > 0
    
    def test_falsifier_structure(self):
        """Falsifiers should have correct structure."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for f in hyp.falsifiers_v2:
                assert isinstance(f, MeasurableFalsifier)
                assert hasattr(f, 'text')
                assert len(f.text) > 0
                assert hasattr(f, 'observable')
    
    def test_falsifier_observable_structure(self):
        """Falsifier observables should have correct structure."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for f in hyp.falsifiers_v2:
                if f.observable:
                    assert hasattr(f.observable, 'metric')
                    assert hasattr(f.observable, 'direction')
                    assert hasattr(f.observable, 'window_days')
                    assert hasattr(f.observable, 'available')
                    assert f.observable.direction in ['up', 'down']
    
    def test_legacy_falsifiers_preserved(self):
        """Legacy falsifiers list should still exist."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            assert hasattr(hyp, 'falsifiers')
            assert isinstance(hyp.falsifiers, list)
            # Should match v2 text
            v2_texts = [f.text for f in hyp.falsifiers_v2]
            for f in hyp.falsifiers:
                assert f in v2_texts
    
    def test_falsifier_serialization(self):
        """Falsifiers should serialize correctly."""
        observable = FalsifierObservable(
            metric='contract_count',
            direction='down',
            window_days=30,
            available=True,
        )
        
        falsifier = MeasurableFalsifier(
            text='Pilots fail to convert',
            observable=observable,
        )
        
        d = falsifier.to_dict()
        restored = MeasurableFalsifier.from_dict(d)
        
        assert restored.text == falsifier.text
        assert restored.observable.metric == observable.metric
        assert restored.observable.available == observable.available


# =============================================================================
# TEST: VERSION AND BACKWARD COMPATIBILITY
# =============================================================================

class TestVersionAndCompatibility:
    """Test version and backward compatibility."""
    
    def test_version_is_2_1(self):
        """Output version should be 2.1."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        result = engine.process_meta_signals([meta], date='2026-02-10')
        
        assert result['version'] == '2.1'
    
    def test_bundle_version_is_2_1(self):
        """Bundle version should be 2.1."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        assert bundle.version == '2.1'
    
    def test_v2_fields_preserved(self):
        """V2.0 fields should still be present."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Check v2.0 fields
        assert hasattr(bundle, 'what_to_watch_next')
        
        for hyp in bundle.hypotheses:
            assert hasattr(hyp, 'mechanism_trace')
            for pred in hyp.predicted_next_signals:
                assert hasattr(pred, 'metric')
                assert hasattr(pred, 'direction')
                assert hasattr(pred, 'speculative')
    
    def test_all_predictions_have_canonical_metric(self):
        """All predictions should have canonical_metric."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                assert pred.canonical_metric, \
                    f"Prediction missing canonical_metric: {pred.description}"


# =============================================================================
# TEST: INTEGRATION
# =============================================================================

class TestIntegration:
    """Integration tests for v2.1."""
    
    def test_full_pipeline_strong_meta(self):
        """Full pipeline with strong meta."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Should generate hypotheses
        assert len(bundle.hypotheses) >= 1
        
        # Top hypothesis should have all v2.1 fields
        hyp = bundle.hypotheses[0]
        assert hyp.confidence_inputs is not None
        assert hyp.confidence_debug is not None
        assert len(hyp.falsifiers_v2) > 0
        
        for pred in hyp.predicted_next_signals:
            assert pred.observable_query is not None
            assert pred.canonical_metric
    
    def test_full_pipeline_weak_meta(self):
        """Full pipeline with weak meta."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Should generate hypotheses
        assert len(bundle.hypotheses) >= 1
        
        # Should have v2.1 fields even for weak metas
        hyp = bundle.hypotheses[0]
        assert hyp.confidence_inputs is not None
        assert hyp.confidence_debug is not None
    
    def test_serialization_roundtrip(self):
        """Bundle should survive serialization roundtrip."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Serialize
        d = bundle.to_dict()
        json_str = json.dumps(d)
        
        # Deserialize
        d2 = json.loads(json_str)
        restored = MetaHypothesisBundle.from_dict(d2)
        
        # Check key fields
        assert restored.version == bundle.version
        assert restored.concept_name == bundle.concept_name
        assert len(restored.hypotheses) == len(bundle.hypotheses)
        assert len(restored.watch_items) == len(bundle.watch_items)


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all v2.1 tests."""
    print("\n=== HYPOTHESIS ENGINE v2.1 TESTS ===\n")
    
    # Canonical metric tests
    t = TestCanonicalMetricMapping()
    t.test_direct_match()
    t.test_alias_match()
    t.test_cross_category_search()
    t.test_fallback_to_custom()
    t.test_metric_defaults()
    print("[PASS] Canonical metric mapping tests")
    
    # Observable query tests
    t = TestObservableQuery()
    t.test_observable_query_creation()
    t.test_direction_normalization()
    t.test_every_prediction_has_observable()
    t.test_observable_query_serialization()
    print("[PASS] Observable query tests")
    
    # Ranked watchlist tests
    t = TestRankedWatchlist()
    t.test_watch_items_sorted_by_score()
    t.test_watch_item_structure()
    t.test_timeframe_bucket_assignment()
    t.test_what_to_watch_next_populated()
    t.test_watch_item_serialization()
    print("[PASS] Ranked watchlist tests")
    
    # Confidence transparency tests
    t = TestConfidenceTransparency()
    t.test_confidence_inputs_present()
    t.test_confidence_debug_present()
    t.test_confidence_inputs_values()
    t.test_confidence_debug_consistency()
    t.test_confidence_serialization()
    print("[PASS] Confidence transparency tests")
    
    # Evidence source separation tests
    t = TestEvidenceSourceSeparation()
    t.test_classify_evidence_sources()
    t.test_mechanism_trace_has_split_sources()
    t.test_primary_sources_are_valid()
    t.test_secondary_sources_are_valid()
    print("[PASS] Evidence source separation tests")
    
    # Measurable falsifiers tests
    t = TestMeasurableFalsifiers()
    t.test_falsifiers_v2_present()
    t.test_falsifier_structure()
    t.test_falsifier_observable_structure()
    t.test_legacy_falsifiers_preserved()
    t.test_falsifier_serialization()
    print("[PASS] Measurable falsifiers tests")
    
    # Version and compatibility tests
    t = TestVersionAndCompatibility()
    t.test_version_is_2_1()
    t.test_bundle_version_is_2_1()
    t.test_v2_fields_preserved()
    t.test_all_predictions_have_canonical_metric()
    print("[PASS] Version and compatibility tests")
    
    # Integration tests
    t = TestIntegration()
    t.test_full_pipeline_strong_meta()
    t.test_full_pipeline_weak_meta()
    t.test_serialization_roundtrip()
    print("[PASS] Integration tests")
    
    print("\n=== ALL v2.1 TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
