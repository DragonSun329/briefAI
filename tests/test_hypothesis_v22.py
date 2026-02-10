"""
Tests for Hypothesis Engine v2.2 - Observable Query Binder & Measurability Fixes.

Test Coverage:
1. No placeholders in observable_query.query
2. At least 2/3 predictions for infra_scaling have non-custom_metric
3. No description mutation on observable gate failure
4. Measurable and measurable_reason fields work correctly
5. Query term resolution from meta context
6. WatchItem includes timeframe_days numeric and measurable
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.hypothesis_engine import (
    # v2.2 imports
    MeasurableReason,
    resolve_query_terms,
    has_unbound_placeholders,
    build_observable_query,
    
    # Data structures
    PredictedSignal,
    WatchItem,
    Hypothesis,
    MetaHypothesisBundle,
    HypothesisEngine,
    
    # v2.1 functions still used
    get_canonical_metric,
    normalize_direction,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_infra_scaling_meta():
    """Create an infra_scaling meta-signal for testing."""
    return {
        'meta_id': 'meta_infra_test',
        'concept_slug': 'infra-scaling-test',
        'concept_name': 'NVIDIA Agent Chip Demand Surge',
        'description': 'Multiple sources report increasing demand for NVIDIA chips specifically for AI agent workloads.',
        'maturity_stage': 'trending',
        'concept_confidence': 0.72,
        'persistence_days': 4,
        'independence_score': 0.78,
        'acceleration': 0.65,
        'category_diversity': {
            'categories': ['technical', 'financial', 'media'],
            'category_count': 3,
        },
        'review_required': False,
        'mechanism': 'compute-infrastructure',
        'naming_reason': {
            'mechanism_terms': ['demand', 'chips', 'compute', 'infrastructure'],
            'mechanism_bucket': 'compute-infrastructure',
        },
        'supporting_signals': ['sig_nvda_1', 'sig_nvda_2', 'sig_nvda_3'],
        'supporting_insights': [
            {
                'signal_id': 'sig_nvda_1',
                'signal_name': 'Cloud Provider Orders',
                'insight_text': 'Hyperscalers doubling orders for H100/B100 GPUs to support agent inference.',
                'entities': ['nvidia', 'microsoft', 'google'],
                'buckets': ['compute', 'infrastructure', 'enterprise'],
            },
            {
                'signal_id': 'sig_nvda_2',
                'signal_name': 'Agent Inference Demand',
                'insight_text': 'Agent workloads require 10x more inference compute than chatbot use cases.',
                'entities': ['anthropic', 'openai'],
                'buckets': ['inference', 'agents'],
            },
        ],
    }


def make_weak_meta():
    """Create a weak meta-signal for testing observable gate failure."""
    return {
        'meta_id': 'meta_weak_v22',
        'concept_slug': 'weak-signal-test',
        'concept_name': 'AI Buzz',
        'description': 'General AI discussion in media.',
        'maturity_stage': 'weak',
        'concept_confidence': 0.35,
        'persistence_days': 1,
        'independence_score': 0.2,
        'category_diversity': {
            'categories': ['media'],
            'category_count': 1,
        },
        'review_required': True,
        'supporting_signals': ['sig_weak'],
        'supporting_insights': [
            {
                'signal_id': 'sig_weak',
                'signal_name': 'Media Buzz',
                'insight_text': 'Coverage of AI.',
                'entities': [],
                'buckets': ['media'],
            },
        ],
    }


# =============================================================================
# TEST: NO PLACEHOLDERS IN OBSERVABLE QUERIES
# =============================================================================

class TestNoPlaceholders:
    """Test that observable queries have no unbound placeholders (v2.2 Part 1)."""
    
    def test_has_unbound_placeholders_detection(self):
        """Should detect placeholders correctly."""
        assert has_unbound_placeholders("filings:{entity} type:{filing_type}") == True
        assert has_unbound_placeholders("(capex OR datacenter) AND (nvidia)") == False
        assert has_unbound_placeholders("search:ai") == False
        assert has_unbound_placeholders("{keyword}") == True
    
    def test_no_placeholders_in_infra_scaling_bundle(self):
        """Observable queries should have no placeholders for infra_scaling."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    query = pred.observable_query.query
                    assert not has_unbound_placeholders(query), \
                        f"Found placeholder in query: {query}"
    
    def test_no_placeholders_in_weak_bundle(self):
        """Even weak bundles should have no placeholders."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    query = pred.observable_query.query
                    assert not has_unbound_placeholders(query), \
                        f"Found placeholder in query: {query}"


# =============================================================================
# TEST: INFRA_SCALING NON-CUSTOM METRIC RATE
# =============================================================================

class TestInfraScalingMetrics:
    """Test that infra_scaling predictions use real canonical metrics (v2.2 Part 2)."""
    
    def test_at_least_two_non_custom_metrics(self):
        """At least 2/3 predictions should have canonical_metric != custom_metric."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Find infra_scaling hypothesis
        infra_hyp = None
        for hyp in bundle.hypotheses:
            if hyp.mechanism == 'infra_scaling':
                infra_hyp = hyp
                break
        
        assert infra_hyp is not None, "Should have infra_scaling hypothesis"
        
        non_custom_count = 0
        for pred in infra_hyp.predicted_next_signals:
            if pred.canonical_metric and pred.canonical_metric != 'custom_metric':
                non_custom_count += 1
        
        total_predictions = len(infra_hyp.predicted_next_signals)
        assert non_custom_count >= 2, \
            f"Expected at least 2 non-custom metrics, got {non_custom_count}/{total_predictions}"
    
    def test_specific_canonical_metrics_used(self):
        """Check that expected canonical metrics are used for infra_scaling."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        infra_hyp = None
        for hyp in bundle.hypotheses:
            if hyp.mechanism == 'infra_scaling':
                infra_hyp = hyp
                break
        
        assert infra_hyp is not None
        
        canonical_metrics = {p.canonical_metric for p in infra_hyp.predicted_next_signals}
        
        # Should include at least one of these expected metrics
        expected_metrics = {'filing_mentions', 'repo_activity', 'article_count'}
        found = canonical_metrics & expected_metrics
        
        assert len(found) >= 2, \
            f"Expected at least 2 of {expected_metrics}, found {found}"


# =============================================================================
# TEST: NO DESCRIPTION MUTATION
# =============================================================================

class TestNoDescriptionMutation:
    """Test that descriptions are not mutated on observable gate failure (v2.2 Part 3)."""
    
    def test_descriptions_stable(self):
        """Descriptions should match template exactly (no appended text)."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                # Should NOT contain the old mutation patterns
                assert "(watch for metric changes)" not in pred.description, \
                    f"Found mutation in description: {pred.description}"
                assert "indicating increase or decline" not in pred.description, \
                    f"Found mutation in description: {pred.description}"
    
    def test_weak_meta_descriptions_stable(self):
        """Even for weak metas, descriptions should not be mutated."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                assert "(watch for metric changes)" not in pred.description
                assert "indicating increase or decline" not in pred.description


# =============================================================================
# TEST: MEASURABLE AND MEASURABLE_REASON FIELDS
# =============================================================================

class TestMeasurableFields:
    """Test measurable and measurable_reason fields (v2.2 Part 4)."""
    
    def test_measurable_field_present(self):
        """All predictions should have measurable field."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                assert hasattr(pred, 'measurable'), "Should have measurable field"
                assert isinstance(pred.measurable, bool)
    
    def test_measurable_reason_when_false(self):
        """measurable_reason should be set when measurable=False."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if not pred.measurable:
                    assert pred.measurable_reason != MeasurableReason.OK, \
                        "Should have non-OK reason when not measurable"
    
    def test_measurable_reason_values(self):
        """measurable_reason should be one of the defined values."""
        valid_reasons = {
            MeasurableReason.OK,
            MeasurableReason.NO_CANONICAL_METRIC_MATCH,
            MeasurableReason.UNBOUND_PLACEHOLDERS,
            MeasurableReason.INSUFFICIENT_QUERY_TERMS,
            MeasurableReason.UNSUPPORTED_SOURCE,
            MeasurableReason.OBSERVABLE_GATE_FAILED,
        }
        
        engine = HypothesisEngine()
        for meta in [make_infra_scaling_meta(), make_weak_meta()]:
            bundle = engine.process_meta_signal(meta)
            for hyp in bundle.hypotheses:
                for pred in hyp.predicted_next_signals:
                    assert pred.measurable_reason in valid_reasons, \
                        f"Invalid reason: {pred.measurable_reason}"
    
    def test_serialization_includes_measurable(self):
        """Serialization should include measurable and measurable_reason."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        bundle_dict = bundle.to_dict()
        
        for hyp_dict in bundle_dict['hypotheses']:
            for pred_dict in hyp_dict['predicted_next_signals']:
                assert 'measurable' in pred_dict
                # measurable_reason only included if not OK
                if not pred_dict['measurable']:
                    assert 'measurable_reason' in pred_dict


# =============================================================================
# TEST: QUERY TERM RESOLUTION
# =============================================================================

class TestQueryTermResolution:
    """Test resolve_query_terms function (v2.2 Part 5)."""
    
    def test_entities_extracted(self):
        """Should extract entities from meta."""
        meta = make_infra_scaling_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['gpu', 'compute', 'infrastructure'],
            query_hints=['capex', 'datacenter'],
        )
        
        assert 'entities' in result
        assert len(result['entities']) > 0
        # Should include entities from supporting_insights
        assert any(e in result['entities'] for e in ['nvidia', 'microsoft', 'google', 'nvidia', 'agent', 'chip'])
    
    def test_mechanism_terms_included(self):
        """Should include mechanism terms."""
        meta = make_infra_scaling_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['gpu', 'compute', 'infrastructure', 'chip'],
            query_hints=[],
        )
        
        assert 'mechanism_terms' in result
        assert 'gpu' in result['mechanism_terms']
        assert 'compute' in result['mechanism_terms']
    
    def test_query_hints_prioritized(self):
        """Query hints should be prioritized in all_keywords."""
        meta = make_infra_scaling_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['gpu', 'compute'],
            query_hints=['capex', 'datacenter', 'infrastructure'],
        )
        
        assert 'query_hints' in result
        assert 'all_keywords' in result
        # Hints should appear before mechanism terms
        if result['all_keywords']:
            # First keywords should be from hints
            first_keywords = result['all_keywords'][:3]
            assert any(h in first_keywords for h in ['capex', 'datacenter', 'infrastructure'])
    
    def test_bucket_terms_extracted(self):
        """Should extract bucket terms from supporting_insights."""
        meta = make_infra_scaling_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=[],
            query_hints=[],
        )
        
        assert 'bucket_terms' in result
        # Should include buckets from supporting_insights
        expected_buckets = {'compute', 'infrastructure', 'enterprise', 'inference', 'agents'}
        found = set(result['bucket_terms']) & expected_buckets
        assert len(found) > 0, f"Should find some bucket terms from {expected_buckets}"


# =============================================================================
# TEST: WATCHITEM IMPROVEMENTS
# =============================================================================

class TestWatchItemImprovements:
    """Test WatchItem v2.2 improvements (v2.2 Part 6)."""
    
    def test_watch_item_has_timeframe_days(self):
        """WatchItem should have timeframe_days numeric field."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        for item in bundle.watch_items:
            assert hasattr(item, 'timeframe_days'), "Should have timeframe_days"
            assert isinstance(item.timeframe_days, int)
            assert item.timeframe_days > 0
    
    def test_watch_item_has_measurable(self):
        """WatchItem should have measurable field."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        for item in bundle.watch_items:
            assert hasattr(item, 'measurable'), "Should have measurable"
            assert isinstance(item.measurable, bool)
    
    def test_watch_item_serialization(self):
        """WatchItem serialization should include new fields."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        bundle_dict = bundle.to_dict()
        
        for item_dict in bundle_dict['watch_items']:
            assert 'timeframe_days' in item_dict
            assert 'measurable' in item_dict
            assert 'timeframe_bucket' in item_dict
    
    def test_watch_item_priority_reason_includes_measurable(self):
        """Watch priority reason should include measurable info."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        for item in bundle.watch_items:
            reasons = item.watch_priority_reason
            # Should include measurable in reasons
            measurable_reasons = [r for r in reasons if 'measurable' in r.lower()]
            assert len(measurable_reasons) > 0, \
                f"Should have measurable reason, got: {reasons}"


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestRegressionV22:
    """Regression tests for v2.2 fixes."""
    
    def test_sample_bundle_from_prompt(self):
        """
        Regression test: The NVIDIA bundle from the prompt should now have:
        - Non-custom canonical metrics
        - No placeholders in queries
        - Stable descriptions
        """
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Should have hypotheses
        assert len(bundle.hypotheses) > 0
        
        # Find infra_scaling hypothesis
        infra_hyp = None
        for hyp in bundle.hypotheses:
            if hyp.mechanism == 'infra_scaling':
                infra_hyp = hyp
                break
        
        assert infra_hyp is not None, "Should detect infra_scaling mechanism"
        
        # Count non-custom metrics
        non_custom = sum(
            1 for p in infra_hyp.predicted_next_signals 
            if p.canonical_metric != 'custom_metric'
        )
        
        assert non_custom >= 2, f"Expected at least 2 non-custom, got {non_custom}"
        
        # Check no placeholders
        for pred in infra_hyp.predicted_next_signals:
            if pred.observable_query:
                assert not has_unbound_placeholders(pred.observable_query.query)
        
        # Check descriptions stable
        for pred in infra_hyp.predicted_next_signals:
            assert "(watch for metric changes)" not in pred.description
    
    def test_backward_compatibility(self):
        """v2.1 fields should still be present."""
        engine = HypothesisEngine()
        meta = make_infra_scaling_meta()
        bundle = engine.process_meta_signal(meta)
        
        # v2.1 fields
        assert hasattr(bundle, 'what_to_watch_next')
        assert hasattr(bundle, 'watch_items')
        assert bundle.version == "2.1"  # Still 2.1 for compatibility
        
        for hyp in bundle.hypotheses:
            # v2.1 fields on hypothesis
            assert hasattr(hyp, 'confidence_inputs')
            assert hasattr(hyp, 'confidence_debug')
            assert hasattr(hyp, 'mechanism_trace')
            assert hasattr(hyp, 'falsifiers_v2')
            
            for pred in hyp.predicted_next_signals:
                # v2.1 fields on prediction
                assert hasattr(pred, 'canonical_metric')
                assert hasattr(pred, 'observable_query')
                # v2.2 fields
                assert hasattr(pred, 'measurable')
                assert hasattr(pred, 'measurable_reason')


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all v2.2 tests."""
    print("\n=== HYPOTHESIS ENGINE v2.2 TESTS ===\n")
    
    # No placeholders tests
    t = TestNoPlaceholders()
    t.test_has_unbound_placeholders_detection()
    t.test_no_placeholders_in_infra_scaling_bundle()
    t.test_no_placeholders_in_weak_bundle()
    print("[PASS] No placeholders tests")
    
    # Infra scaling metrics tests
    t = TestInfraScalingMetrics()
    t.test_at_least_two_non_custom_metrics()
    t.test_specific_canonical_metrics_used()
    print("[PASS] Infra scaling metrics tests")
    
    # No description mutation tests
    t = TestNoDescriptionMutation()
    t.test_descriptions_stable()
    t.test_weak_meta_descriptions_stable()
    print("[PASS] No description mutation tests")
    
    # Measurable fields tests
    t = TestMeasurableFields()
    t.test_measurable_field_present()
    t.test_measurable_reason_when_false()
    t.test_measurable_reason_values()
    t.test_serialization_includes_measurable()
    print("[PASS] Measurable fields tests")
    
    # Query term resolution tests
    t = TestQueryTermResolution()
    t.test_entities_extracted()
    t.test_mechanism_terms_included()
    t.test_query_hints_prioritized()
    t.test_bucket_terms_extracted()
    print("[PASS] Query term resolution tests")
    
    # WatchItem improvements tests
    t = TestWatchItemImprovements()
    t.test_watch_item_has_timeframe_days()
    t.test_watch_item_has_measurable()
    t.test_watch_item_serialization()
    t.test_watch_item_priority_reason_includes_measurable()
    print("[PASS] WatchItem improvements tests")
    
    # Regression tests
    t = TestRegressionV22()
    t.test_sample_bundle_from_prompt()
    t.test_backward_compatibility()
    print("[PASS] Regression tests")
    
    print("\n=== ALL v2.2 TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
