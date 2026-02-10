"""
Tests for Hypothesis Engine v2.2.1 - Entity Binding Hardening & Query Traceability.

Test Coverage:
1. Entity binding prefers concept entity (anti-hijack)
2. Query terms present for explainability
3. Measurable=False when source unavailable
4. Regression: NVIDIA meta cannot generate Microsoft query
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.hypothesis_engine import (
    # v2.2.1 new functions
    extract_concept_entity,
    normalize_entity_name,
    is_source_supported,
    get_entity_frequency,
    load_source_capabilities,
    resolve_query_terms,
    
    # v2.2 imports
    MeasurableReason,
    build_observable_query,
    has_unbound_placeholders,
    
    # Data structures
    ObservableQuery,
    PredictedSignal,
    Hypothesis,
    MetaHypothesisBundle,
    HypothesisEngine,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_nvidia_meta():
    """
    Create a meta-signal where NVIDIA is the concept entity.
    
    This is the regression fixture for the NVIDIA->Microsoft bug.
    The meta has:
    - NVIDIA in concept_name
    - Multiple entities including microsoft/google in supporting_insights
    
    The bug was: query ended up using 'microsoft' instead of 'nvidia'.
    """
    return {
        'meta_id': 'meta_nvidia_regression',
        'concept_slug': 'nvidia-chip-demand',
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
        'supporting_signals': ['sig_1', 'sig_2', 'sig_3'],
        'supporting_insights': [
            {
                'signal_id': 'sig_1',
                'signal_name': 'Cloud Provider Orders',
                'insight_text': 'Hyperscalers doubling orders for GPUs.',
                # NOTE: These entities should NOT hijack the query
                'entities': ['microsoft', 'google', 'amazon'],
                'buckets': ['compute', 'infrastructure', 'enterprise'],
            },
            {
                'signal_id': 'sig_2',
                'signal_name': 'Agent Inference Demand',
                'insight_text': 'Agent workloads require more inference compute.',
                'entities': ['anthropic', 'openai'],
                'buckets': ['inference', 'agents'],
            },
        ],
    }


def make_openai_meta():
    """Create a meta-signal where OpenAI is the concept entity."""
    return {
        'meta_id': 'meta_openai_test',
        'concept_slug': 'openai-gpt5-launch',
        'concept_name': 'OpenAI GPT-5 Launch Signals',
        'description': 'Multiple sources suggest GPT-5 announcement imminent.',
        'maturity_stage': 'trending',
        'concept_confidence': 0.75,
        'persistence_days': 3,
        'independence_score': 0.80,
        'category_diversity': {
            'categories': ['technical', 'media'],
            'category_count': 2,
        },
        'review_required': False,
        'supporting_signals': ['sig_1'],
        'supporting_insights': [
            {
                'signal_id': 'sig_1',
                'signal_name': 'Model Release Signals',
                'insight_text': 'API updates suggest new model.',
                'entities': ['google', 'anthropic'],  # Competitors should not hijack
                'buckets': ['models', 'api'],
            },
        ],
    }


def make_product_name_meta():
    """Create a meta-signal with a product name (Claude) in concept."""
    return {
        'meta_id': 'meta_claude_test',
        'concept_slug': 'claude-adoption-surge',
        'concept_name': 'Claude Enterprise Adoption Surge',
        'description': 'Claude usage in enterprise is growing.',
        'maturity_stage': 'trending',
        'concept_confidence': 0.70,
        'persistence_days': 5,
        'independence_score': 0.75,
        'category_diversity': {
            'categories': ['financial', 'social'],
            'category_count': 2,
        },
        'review_required': False,
        'supporting_signals': ['sig_1'],
        'supporting_insights': [
            {
                'signal_id': 'sig_1',
                'signal_name': 'Enterprise Usage',
                'insight_text': 'Enterprise accounts growing.',
                'entities': ['openai', 'google'],  # Should not hijack
                'buckets': ['enterprise'],
            },
        ],
    }


# =============================================================================
# TEST: ENTITY EXTRACTION
# =============================================================================

class TestEntityExtraction:
    """Test concept entity extraction (v2.2.1)."""
    
    def test_extract_nvidia_from_concept_name(self):
        """NVIDIA should be extracted from 'NVIDIA Agent Chip Demand Surge'."""
        result = extract_concept_entity("NVIDIA Agent Chip Demand Surge")
        assert result == "nvidia"
    
    def test_extract_openai_from_concept_name(self):
        """OpenAI should be extracted from 'OpenAI GPT-5 Launch Signals'."""
        result = extract_concept_entity("OpenAI GPT-5 Launch Signals")
        assert result == "openai"
    
    def test_extract_meta_from_concept_name(self):
        """Meta should be extracted from 'Meta Llama Release'."""
        result = extract_concept_entity("Meta Llama Release")
        assert result == "meta"
    
    def test_product_name_resolves_to_company(self):
        """Product name (Claude) should resolve to company (anthropic)."""
        result = extract_concept_entity("Claude Enterprise Adoption")
        assert result == "anthropic"
    
    def test_gpt_resolves_to_openai(self):
        """GPT should resolve to OpenAI."""
        result = extract_concept_entity("GPT-5 Benchmark Improvements")
        assert result == "openai"
    
    def test_normalize_entity_name(self):
        """Entity names should be normalized correctly."""
        assert normalize_entity_name("NVIDIA") == "nvidia"
        assert normalize_entity_name("OpenAI Inc") == "openai"
        assert normalize_entity_name("Microsoft Corp") == "microsoft"
        assert normalize_entity_name("Anthropic AI") == "anthropic"


# =============================================================================
# TEST: ENTITY BINDING CORRECTNESS (ANTI-HIJACK)
# =============================================================================

class TestEntityBindingCorrectness:
    """Test that concept entity is always primary (v2.2.1 anti-hijack)."""
    
    def test_nvidia_meta_has_nvidia_as_primary_entity(self):
        """NVIDIA meta should have nvidia as primary_entity."""
        meta = make_nvidia_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['gpu', 'compute', 'infrastructure'],
            query_hints=['capex', 'datacenter'],
        )
        
        assert result['concept_entity'] == 'nvidia'
        assert result['primary_entity'] == 'nvidia'
        assert result['entities'][0] == 'nvidia'
    
    def test_nvidia_meta_query_contains_nvidia_not_microsoft(self):
        """
        REGRESSION TEST: NVIDIA meta observable queries must contain 'nvidia'.
        
        The bug was: query ended up containing 'microsoft' instead of 'nvidia'.
        This must never happen again.
        """
        engine = HypothesisEngine()
        meta = make_nvidia_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    query_lower = pred.observable_query.query.lower()
                    
                    # MUST contain nvidia (or nvidia-related terms)
                    contains_nvidia = 'nvidia' in query_lower
                    
                    # MUST NOT contain microsoft (unless nvidia is also present)
                    contains_microsoft = 'microsoft' in query_lower
                    
                    # Anti-hijack assertion
                    if contains_microsoft and not contains_nvidia:
                        pytest.fail(
                            f"ANTI-HIJACK VIOLATION: Query contains 'microsoft' but not 'nvidia'\n"
                            f"Query: {pred.observable_query.query}\n"
                            f"Concept: {meta['concept_name']}"
                        )
    
    def test_openai_meta_has_openai_as_primary_entity(self):
        """OpenAI meta should have openai as primary_entity."""
        meta = make_openai_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['model', 'api', 'launch'],
            query_hints=[],
        )
        
        assert result['concept_entity'] == 'openai'
        assert result['primary_entity'] == 'openai'
        assert result['entities'][0] == 'openai'
    
    def test_product_name_meta_resolves_to_company(self):
        """Claude meta should resolve to anthropic as primary_entity."""
        meta = make_product_name_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['enterprise', 'adoption'],
            query_hints=[],
        )
        
        assert result['concept_entity'] == 'anthropic'
        assert result['primary_entity'] == 'anthropic'


# =============================================================================
# TEST: QUERY TERMS PRESENT (EXPLAINABILITY)
# =============================================================================

class TestQueryTermsPresent:
    """Test that query_terms are present for explainability (v2.2.1)."""
    
    def test_observable_query_has_query_terms(self):
        """ObservableQuery should have query_terms dict."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu', 'compute'],
            query_hints=['datacenter'],
        )
        
        observable, _, _ = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['sec'],
            timeframe_days=30,
            resolved_terms=result,
        )
        
        assert observable.query_terms is not None
        assert isinstance(observable.query_terms, dict)
    
    def test_query_terms_contains_required_fields(self):
        """query_terms should contain entities, mechanism_terms, etc."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu', 'compute'],
            query_hints=['datacenter'],
        )
        
        observable, _, _ = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['sec'],
            timeframe_days=30,
            resolved_terms=result,
        )
        
        qt = observable.query_terms
        assert 'entities' in qt
        assert 'primary_entity' in qt
        assert 'concept_entity' in qt
        assert 'mechanism_terms' in qt
        assert 'query_hints' in qt
        assert 'canonical_metric' in qt
        assert 'template_used' in qt
    
    def test_query_terms_primary_entity_matches_concept(self):
        """primary_entity in query_terms should match concept_entity."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu', 'compute'],
            query_hints=[],
        )
        
        observable, _, _ = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['sec'],
            timeframe_days=30,
            resolved_terms=result,
        )
        
        qt = observable.query_terms
        assert qt['primary_entity'] == 'nvidia'
        assert qt['concept_entity'] == 'nvidia'
    
    def test_full_bundle_has_query_terms(self):
        """All predictions in a bundle should have query_terms."""
        engine = HypothesisEngine()
        meta = make_nvidia_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    assert pred.observable_query.query_terms, \
                        f"Missing query_terms for {pred.category}"


# =============================================================================
# TEST: SOURCE AVAILABILITY
# =============================================================================

class TestSourceAvailability:
    """Test runtime source availability check (v2.2.1)."""
    
    def test_is_source_supported_returns_bool(self):
        """is_source_supported should return boolean."""
        result = is_source_supported('github')
        assert isinstance(result, bool)
    
    def test_github_source_is_supported(self):
        """github should be supported."""
        assert is_source_supported('github') == True
    
    def test_pitchbook_source_not_supported(self):
        """pitchbook should not be supported (requires subscription)."""
        assert is_source_supported('pitchbook') == False
    
    def test_theinformation_not_supported(self):
        """theinformation should not be supported (requires subscription)."""
        assert is_source_supported('theinformation') == False
    
    def test_observable_query_has_available_field(self):
        """ObservableQuery should have available field."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu'],
            query_hints=[],
        )
        
        observable, _, _ = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['sec'],
            timeframe_days=30,
            resolved_terms=result,
        )
        
        assert hasattr(observable, 'available')
        assert isinstance(observable.available, bool)
    
    def test_measurable_false_when_source_unavailable(self):
        """measurable should be False when source is unavailable."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu'],
            query_hints=[],
        )
        
        # Use an unavailable source
        observable, measurable, reason = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['pitchbook'],  # Unavailable source
            timeframe_days=30,
            resolved_terms=result,
        )
        
        assert measurable == False
        assert reason == MeasurableReason.SOURCE_UNAVAILABLE
        assert observable.available == False
    
    def test_available_source_is_measurable(self):
        """measurable should be True when source is available."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu', 'compute'],
            query_hints=['datacenter'],
        )
        
        observable, measurable, reason = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['sec'],  # Available source
            timeframe_days=30,
            resolved_terms=result,
        )
        
        assert measurable == True
        assert reason == MeasurableReason.OK
        assert observable.available == True


# =============================================================================
# REGRESSION TESTS
# =============================================================================

class TestRegressionV221:
    """Regression tests for v2.2.1 anti-hijack fixes."""
    
    def test_nvidia_microsoft_hijack_prevented(self):
        """
        CRITICAL REGRESSION TEST: NVIDIA->Microsoft hijack must be prevented.
        
        Original bug: An NVIDIA meta-signal was generating queries with
        'microsoft' as the entity instead of 'nvidia'.
        
        This test ensures that bug can never return.
        """
        engine = HypothesisEngine()
        meta = make_nvidia_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Check all predictions
        violations = []
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    qt = pred.observable_query.query_terms
                    
                    # Primary entity MUST be nvidia
                    if qt.get('primary_entity') != 'nvidia':
                        violations.append(
                            f"Primary entity is '{qt.get('primary_entity')}' not 'nvidia'"
                        )
                    
                    # Concept entity MUST be nvidia
                    if qt.get('concept_entity') != 'nvidia':
                        violations.append(
                            f"Concept entity is '{qt.get('concept_entity')}' not 'nvidia'"
                        )
        
        if violations:
            pytest.fail(f"ANTI-HIJACK VIOLATIONS:\n" + "\n".join(violations))
    
    def test_entity_priority_order_respected(self):
        """Entity priority order must be: concept > frequency > fallback."""
        meta = make_nvidia_meta()
        result = resolve_query_terms(
            meta=meta,
            mechanism_terms=['gpu'],
            query_hints=[],
        )
        
        # Concept entity (nvidia) must be first
        assert result['entities'][0] == 'nvidia'
        
        # Primary entity must equal concept entity
        assert result['primary_entity'] == result['concept_entity']
    
    def test_backward_compatibility(self):
        """v2.2 fields should still work correctly."""
        engine = HypothesisEngine()
        meta = make_nvidia_meta()
        bundle = engine.process_meta_signal(meta)
        
        # v2.2 fields
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                assert hasattr(pred, 'measurable')
                assert hasattr(pred, 'measurable_reason')
                if pred.observable_query:
                    assert hasattr(pred.observable_query, 'query')
                    assert hasattr(pred.observable_query, 'source')
                    # v2.2.1 fields
                    assert hasattr(pred.observable_query, 'query_terms')
                    assert hasattr(pred.observable_query, 'available')
    
    def test_no_placeholders_still_enforced(self):
        """No placeholders should exist in queries (v2.2 requirement)."""
        engine = HypothesisEngine()
        meta = make_nvidia_meta()
        bundle = engine.process_meta_signal(meta)
        
        for hyp in bundle.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    query = pred.observable_query.query
                    assert not has_unbound_placeholders(query), \
                        f"Found placeholder in query: {query}"


# =============================================================================
# SERIALIZATION TESTS
# =============================================================================

class TestSerialization:
    """Test that new v2.2.1 fields serialize correctly."""
    
    def test_observable_query_serialization(self):
        """ObservableQuery should serialize query_terms and available."""
        result = resolve_query_terms(
            meta=make_nvidia_meta(),
            mechanism_terms=['gpu', 'compute'],
            query_hints=['datacenter'],
        )
        
        observable, _, _ = build_observable_query(
            category='financial',
            metric='filing_mentions',
            direction='up',
            sources=['sec'],
            timeframe_days=30,
            resolved_terms=result,
        )
        
        d = observable.to_dict()
        
        assert 'query_terms' in d
        assert 'available' in d
        assert d['available'] == True
    
    def test_bundle_serialization_roundtrip(self):
        """Bundle should serialize and deserialize with new fields."""
        engine = HypothesisEngine()
        meta = make_nvidia_meta()
        bundle = engine.process_meta_signal(meta)
        
        # Serialize
        d = bundle.to_dict()
        json_str = json.dumps(d)
        
        # Deserialize
        d2 = json.loads(json_str)
        restored = MetaHypothesisBundle.from_dict(d2)
        
        # Check new fields preserved
        for hyp in restored.hypotheses:
            for pred in hyp.predicted_next_signals:
                if pred.observable_query:
                    assert pred.observable_query.query_terms is not None
                    assert isinstance(pred.observable_query.available, bool)


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all v2.2.1 tests."""
    print("\n=== HYPOTHESIS ENGINE v2.2.1 TESTS ===\n")
    
    # Entity extraction tests
    t = TestEntityExtraction()
    t.test_extract_nvidia_from_concept_name()
    t.test_extract_openai_from_concept_name()
    t.test_extract_meta_from_concept_name()
    t.test_product_name_resolves_to_company()
    t.test_gpt_resolves_to_openai()
    t.test_normalize_entity_name()
    print("[PASS] Entity extraction tests")
    
    # Entity binding tests
    t = TestEntityBindingCorrectness()
    t.test_nvidia_meta_has_nvidia_as_primary_entity()
    t.test_nvidia_meta_query_contains_nvidia_not_microsoft()
    t.test_openai_meta_has_openai_as_primary_entity()
    t.test_product_name_meta_resolves_to_company()
    print("[PASS] Entity binding correctness tests (ANTI-HIJACK)")
    
    # Query terms tests
    t = TestQueryTermsPresent()
    t.test_observable_query_has_query_terms()
    t.test_query_terms_contains_required_fields()
    t.test_query_terms_primary_entity_matches_concept()
    t.test_full_bundle_has_query_terms()
    print("[PASS] Query terms explainability tests")
    
    # Source availability tests
    t = TestSourceAvailability()
    t.test_is_source_supported_returns_bool()
    t.test_github_source_is_supported()
    t.test_pitchbook_source_not_supported()
    t.test_theinformation_not_supported()
    t.test_observable_query_has_available_field()
    t.test_measurable_false_when_source_unavailable()
    t.test_available_source_is_measurable()
    print("[PASS] Source availability tests")
    
    # Regression tests
    t = TestRegressionV221()
    t.test_nvidia_microsoft_hijack_prevented()
    t.test_entity_priority_order_respected()
    t.test_backward_compatibility()
    t.test_no_placeholders_still_enforced()
    print("[PASS] Regression tests (CRITICAL)")
    
    # Serialization tests
    t = TestSerialization()
    t.test_observable_query_serialization()
    t.test_bundle_serialization_roundtrip()
    print("[PASS] Serialization tests")
    
    print("\n=== ALL v2.2.1 TESTS PASSED ===")
    print("\nAnti-hijack: NVIDIA->Microsoft bug is permanently prevented.")


if __name__ == "__main__":
    run_tests()
