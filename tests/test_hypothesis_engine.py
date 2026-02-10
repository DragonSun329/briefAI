"""
Tests for Hypothesis Engine v2.0.

v2.0 Test Coverage:
1. Strong diversity + persistence meta → high confidence hypothesis
2. Media-only + review_required meta → capped confidence, null hypothesis emitted
3. Mechanism keyword match → correct mechanism and predicted signals
4. Hypothesis ID stability
5. Title sanitization (no company names, no filler words)
6. Observable signal validation
7. Falsifiers populated from taxonomy
8. Confidence breakdown components

v2.0 New Tests:
9. Mechanism scoring trace (explainability)
10. Strength-conditioned predictions (weak/moderate/strong)
11. Observable gate (anti-vagueness filter)
12. Null hypothesis competition (attention_spike fallback)
13. Bundle watchlist output
14. Renderer helper functions
"""

import sys
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.hypothesis_engine import (
    # Data structures
    PredictedSignal,
    EvidenceUsed,
    ConfidenceBreakdown,
    DebugInfo,
    Hypothesis,
    MetaHypothesisBundle,
    MechanismTrace,
    HypothesisEngine,
    
    # Functions
    sanitize_title,
    truncate_to_words,
    is_observable,
    passes_observable_gate,
    extract_metric_and_direction,
    classify_evidence_strength,
    get_prediction_limits,
    generate_hypothesis_id,
    extract_key_quotes,
    detect_mechanisms,
    build_mechanism_trace,
    get_primary_mechanism,
    get_alternative_mechanism,
    build_why_now,
    build_claim,
    build_predicted_signals,
    build_falsifiers,
    build_watchlist,
    compute_hypothesis_confidence,
    generate_hypothesis,
    generate_attention_spike_hypothesis,
    generate_null_hypothesis,
    should_emit_attention_spike,
    load_mechanism_taxonomy,
    load_entity_names,
    
    # Constants
    MIN_MECHANISM_KEYWORDS,
    REVIEW_REQUIRED_CAP,
    MEDIA_ONLY_CAP,
    MEASURABLE_TERMS,
    DIRECTION_TERMS,
    TITLE_FILLER_WORDS,
)

from utils.hypothesis_renderer import (
    render_hypothesis_summary,
    render_daily_report,
    render_watchlist_aggregate,
    render_mechanism_breakdown,
    render_confidence_tiers,
    render_evidence_quality_report,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_strong_meta():
    """
    Create a strong meta-signal with high diversity + persistence.
    Should produce high confidence hypothesis.
    """
    return {
        'meta_id': 'meta_strong_123',
        'concept_slug': 'slug_strong_123',
        'concept_name': 'Enterprise AI Adoption Accelerating',
        'description': 'Multiple signals indicate enterprise adoption of AI is accelerating across sectors.',
        'maturity_stage': 'trending',
        'concept_confidence': 0.78,
        'persistence_days': 5,
        'independence_score': 0.85,
        'acceleration': 0.8,
        'entity_diversity': 4,
        'bucket_diversity': 3,
        'category_diversity': {
            'categories': ['technical', 'financial', 'media'],
            'category_count': 3,
            'weighted_diversity': 2.5,
        },
        'validation_status': 'validated',
        'review_required': False,
        'mechanism': 'enterprise-adoption',
        'naming_reason': {
            'was_generic': False,
            'mechanism_terms': ['enterprise', 'adoption', 'deployment'],
            'mechanism_bucket': 'enterprise-adoption',
        },
        'supporting_signals': ['sig1', 'sig2', 'sig3', 'sig4'],
        'supporting_insights': [
            {
                'signal_id': 'sig1',
                'signal_name': 'Enterprise Deployment Signal',
                'insight_text': 'Enterprise AI contract volume increasing significantly.',
                'entities': ['company_a', 'company_b'],
                'buckets': ['enterprise', 'deployment'],
            },
            {
                'signal_id': 'sig2',
                'signal_name': 'B2B Growth Signal',
                'insight_text': 'B2B AI integration deals reaching new highs.',
                'entities': ['company_c'],
                'buckets': ['enterprise', 'b2b'],
            },
        ],
    }


def make_weak_meta():
    """
    Create a weak meta-signal with media-only + review_required.
    Should cap confidence and emit null hypothesis.
    """
    return {
        'meta_id': 'meta_weak_456',
        'concept_slug': 'slug_weak_456',
        'concept_name': 'AI Market Buzz',
        'description': 'Media attention on AI market developments.',
        'maturity_stage': 'weak',
        'concept_confidence': 0.45,
        'persistence_days': 1,
        'independence_score': 0.35,
        'acceleration': 0.1,
        'entity_diversity': 1,
        'bucket_diversity': 1,
        'category_diversity': {
            'categories': ['media'],
            'category_count': 1,
            'weighted_diversity': 0.7,
        },
        'validation_status': 'weakly_validated',
        'review_required': True,
        'mechanism': None,
        'naming_reason': {
            'was_generic': True,
            'mechanism_terms': [],
            'mechanism_bucket': None,
            'review_required': True,
        },
        'supporting_signals': ['sig5'],
        'supporting_insights': [
            {
                'signal_id': 'sig5',
                'signal_name': 'Media Buzz',
                'insight_text': 'News coverage of AI market trends.',
                'entities': [],
                'buckets': ['media'],
            },
        ],
    }


def make_pricing_meta():
    """
    Create a meta-signal with clear pricing mechanism keywords.
    Should detect pricing_cost_down mechanism.
    """
    return {
        'meta_id': 'meta_pricing_789',
        'concept_slug': 'slug_pricing_789',
        'concept_name': 'AI Pricing Compression',
        'description': 'Price cuts and margin compression across AI API providers.',
        'maturity_stage': 'emerging',
        'concept_confidence': 0.65,
        'persistence_days': 3,
        'independence_score': 0.70,
        'acceleration': 0.5,
        'entity_diversity': 3,
        'bucket_diversity': 2,
        'category_diversity': {
            'categories': ['financial', 'technical'],
            'category_count': 2,
            'weighted_diversity': 1.8,
        },
        'validation_status': 'validated',
        'review_required': False,
        'mechanism': 'pricing-monetization',
        'naming_reason': {
            'was_generic': False,
            'mechanism_terms': ['price', 'pricing', 'cost', 'cheaper'],
            'mechanism_bucket': 'pricing-monetization',
        },
        'supporting_signals': ['sig6', 'sig7'],
        'supporting_insights': [
            {
                'signal_id': 'sig6',
                'signal_name': 'Price Cut Signal',
                'insight_text': 'API pricing reduced significantly, race to bottom emerging.',
                'entities': ['provider_a', 'provider_b'],
                'buckets': ['pricing', 'api'],
            },
            {
                'signal_id': 'sig7',
                'signal_name': 'Cost Reduction Signal',
                'insight_text': 'Cost reduction through efficiency gains and commoditization.',
                'entities': ['provider_c'],
                'buckets': ['pricing', 'cost'],
            },
        ],
    }


def make_moderate_meta():
    """Create a moderate-strength meta-signal."""
    return {
        'meta_id': 'meta_moderate_111',
        'concept_slug': 'slug_moderate_111',
        'concept_name': 'Infrastructure Expansion',
        'description': 'Datacenter capacity growing for AI workloads.',
        'maturity_stage': 'emerging',
        'concept_confidence': 0.62,
        'persistence_days': 3,
        'independence_score': 0.65,
        'acceleration': 0.4,
        'entity_diversity': 2,
        'bucket_diversity': 2,
        'category_diversity': {
            'categories': ['financial', 'technical'],
            'category_count': 2,
            'weighted_diversity': 1.6,
        },
        'validation_status': 'validated',
        'review_required': False,
        'mechanism': 'infra-scaling',
        'naming_reason': {
            'was_generic': False,
            'mechanism_terms': ['datacenter', 'capacity', 'infrastructure', 'scaling'],
            'mechanism_bucket': 'infrastructure',
        },
        'supporting_signals': ['sig8', 'sig9'],
        'supporting_insights': [
            {
                'signal_id': 'sig8',
                'signal_name': 'GPU Capacity Signal',
                'insight_text': 'GPU cluster capacity expansion announced.',
                'entities': ['provider_d'],
                'buckets': ['infrastructure', 'compute'],
            },
        ],
    }


# =============================================================================
# DATA STRUCTURE TESTS
# =============================================================================

class TestMechanismTraceSerialization:
    """Test MechanismTrace serialization (v2.0)."""
    
    def test_to_dict_and_back(self):
        """MechanismTrace should roundtrip through dict."""
        trace = MechanismTrace(
            candidate_scores={'enterprise_adoption': 4, 'pricing_cost_down': 2},
            matched_terms=['enterprise', 'adoption', 'deployment'],
            evidence_sources=['meta_insight', 'bucket_tags'],
            selection_reason='highest_score',
        )
        
        d = trace.to_dict()
        restored = MechanismTrace.from_dict(d)
        
        assert restored.candidate_scores['enterprise_adoption'] == 4
        assert 'enterprise' in restored.matched_terms
        assert 'meta_insight' in restored.evidence_sources
        assert restored.selection_reason == 'highest_score'


class TestPredictedSignalSerialization:
    """Test PredictedSignal serialization."""
    
    def test_to_dict_and_back(self):
        """PredictedSignal should roundtrip through dict."""
        pred = PredictedSignal(
            category='technical',
            description='New benchmark results published',
            example_sources=['arxiv', 'github'],
            expected_timeframe_days=14,
        )
        
        d = pred.to_dict()
        restored = PredictedSignal.from_dict(d)
        
        assert restored.category == pred.category
        assert restored.description == pred.description
        assert restored.example_sources == pred.example_sources
        assert restored.expected_timeframe_days == pred.expected_timeframe_days
    
    def test_v2_fields(self):
        """PredictedSignal v2.0 fields should serialize."""
        pred = PredictedSignal(
            category='financial',
            description='Revenue growth increase expected',
            example_sources=['sec'],
            expected_timeframe_days=30,
            metric='revenue',
            direction='increase',
            speculative=True,
        )
        
        d = pred.to_dict()
        
        assert d['metric'] == 'revenue'
        assert d['direction'] == 'increase'
        assert d['speculative'] == True
        
        restored = PredictedSignal.from_dict(d)
        assert restored.metric == 'revenue'
        assert restored.direction == 'increase'
        assert restored.speculative == True


class TestHypothesisSerialization:
    """Test Hypothesis serialization."""
    
    def test_to_dict_and_back(self):
        """Hypothesis should roundtrip through dict."""
        hyp = Hypothesis(
            hypothesis_id='hyp123',
            title='Pricing Pressure Rising',
            mechanism='pricing_cost_up',
            claim='Prices are increasing due to demand.',
            why_now='Signal is persistent for 3 days.',
            evidence_used=EvidenceUsed(
                supporting_signals=['sig1', 'sig2'],
                source_categories=['technical', 'financial'],
                key_entities=['company_a'],
                key_quotes=['Quote one', 'Quote two'],
            ),
            predicted_next_signals=[
                PredictedSignal('technical', 'New releases', ['github'], 14),
            ],
            falsifiers=['Prices stabilize', 'Competition increases'],
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(
                base_from_meta_confidence=0.40,
                diversity_bonus=0.10,
                persistence_bonus=0.08,
                independence_bonus=0.08,
                specificity_bonus=0.09,
                penalties_applied=[],
                final=0.75,
            ),
            review_required=False,
            debug=DebugInfo(
                rules_fired=['rule1', 'rule2'],
                scoring_terms={'meta_confidence': 0.72},
                mechanism_keyword_hits=5,
                mechanism_keywords_matched=['price', 'pricing'],
            ),
        )
        
        d = hyp.to_dict()
        restored = Hypothesis.from_dict(d)
        
        assert restored.hypothesis_id == hyp.hypothesis_id
        assert restored.title == hyp.title
        assert restored.mechanism == hyp.mechanism
        assert restored.confidence == hyp.confidence
        assert len(restored.predicted_next_signals) == 1
        assert len(restored.falsifiers) == 2
    
    def test_mechanism_trace_serialization(self):
        """Hypothesis with mechanism_trace should serialize (v2.0)."""
        trace = MechanismTrace(
            candidate_scores={'test': 3},
            matched_terms=['test'],
            evidence_sources=['test_source'],
            selection_reason='test',
        )
        
        hyp = Hypothesis(
            hypothesis_id='hyp_trace',
            title='Test',
            mechanism='test',
            claim='Test claim',
            why_now='Now',
            evidence_used=EvidenceUsed([], [], [], []),
            predicted_next_signals=[],
            falsifiers=[],
            confidence=0.5,
            confidence_breakdown=ConfidenceBreakdown(0.3, 0.05, 0.05, 0.05, 0.05, [], 0.5),
            review_required=False,
            debug=DebugInfo([], {}, 0, []),
            mechanism_trace=trace,
        )
        
        d = hyp.to_dict()
        assert 'mechanism_trace' in d
        assert d['mechanism_trace']['candidate_scores']['test'] == 3
        
        restored = Hypothesis.from_dict(d)
        assert restored.mechanism_trace is not None
        assert restored.mechanism_trace.candidate_scores['test'] == 3


class TestMetaHypothesisBundleSerialization:
    """Test MetaHypothesisBundle serialization."""
    
    def test_to_dict_and_back(self):
        """MetaHypothesisBundle should roundtrip through dict."""
        bundle = MetaHypothesisBundle(
            meta_id='meta123',
            concept_slug='slug123',
            concept_name='Test Concept',
            maturity_stage='emerging',
            hypotheses=[],
            selected_hypothesis_id='',
            bundle_confidence=0.0,
            generated_at='2026-02-09T12:00:00',
            version='2.0',
            what_to_watch_next=['Watch item 1', 'Watch item 2'],
        )
        
        d = bundle.to_dict()
        restored = MetaHypothesisBundle.from_dict(d)
        
        assert restored.meta_id == bundle.meta_id
        assert restored.concept_slug == bundle.concept_slug
        assert restored.version == '2.0'
        assert restored.what_to_watch_next == ['Watch item 1', 'Watch item 2']


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestSanitizeTitle:
    """Test title sanitization."""
    
    def test_removes_company_names(self):
        """Should remove company names from title."""
        title = sanitize_title("OpenAI Pricing Strategy")
        assert 'openai' not in title.lower()
        
        title = sanitize_title("Google and Microsoft Competition")
        assert 'google' not in title.lower()
        assert 'microsoft' not in title.lower()
    
    def test_removes_model_names(self):
        """Should remove model names from title."""
        title = sanitize_title("GPT-4 Performance Improving")
        assert 'gpt' not in title.lower()
        
        title = sanitize_title("Claude vs Gemini Comparison")
        assert 'claude' not in title.lower()
        assert 'gemini' not in title.lower()
    
    def test_keeps_generic_terms(self):
        """Should keep generic/structural terms."""
        title = sanitize_title("Enterprise Adoption Rising")
        assert 'enterprise' in title.lower()
        assert 'adoption' in title.lower()
    
    def test_handles_empty_result(self):
        """Should return fallback if all words removed."""
        title = sanitize_title("OpenAI Google Microsoft")
        assert len(title) > 0
    
    def test_removes_filler_words(self):
        """Should remove filler words (v2.0)."""
        title = sanitize_title("Pricing Pressure Trend Strengthening Signal Dynamics")
        assert 'trend' not in title.lower()
        assert 'signal' not in title.lower()
        assert 'strengthening' not in title.lower()
        assert 'dynamics' not in title.lower()
        # Should keep meaningful words
        assert 'pricing' in title.lower()
        assert 'pressure' in title.lower()
    
    def test_truncates_to_8_words(self):
        """Should truncate to 8 words max (v2.0)."""
        title = sanitize_title("One Two Three Four Five Six Seven Eight Nine Ten Eleven")
        assert len(title.split()) <= 8


class TestObservableGate:
    """Test observable gate (anti-vagueness filter) (v2.0)."""
    
    def test_passes_with_measurable_and_direction(self):
        """Should pass when both measurable + direction present."""
        assert passes_observable_gate("Revenue growth reported")
        assert passes_observable_gate("Downloads increase expected")
        assert passes_observable_gate("Contract volume decline")
        assert passes_observable_gate("Funding surge anticipated")
    
    def test_fails_without_direction(self):
        """Should fail when direction missing."""
        assert not passes_observable_gate("New benchmark results")
        assert not passes_observable_gate("API release scheduled")
    
    def test_fails_without_measurable(self):
        """Should fail when measurable missing."""
        assert not passes_observable_gate("Things are increasing")
        assert not passes_observable_gate("Market dynamics shifting")
    
    def test_fails_for_vague_descriptions(self):
        """Should fail for vague descriptions."""
        assert not passes_observable_gate("Things are changing")
        assert not passes_observable_gate("Dynamics evolving rapidly")


class TestMetricDirectionExtraction:
    """Test metric and direction extraction (v2.0)."""
    
    def test_extracts_metric(self):
        """Should extract measurable terms."""
        metric, direction = extract_metric_and_direction("Revenue growth expected")
        # Either "revenue" or "growth" are valid measurable terms
        assert metric in ("revenue", "growth")
    
    def test_extracts_direction(self):
        """Should extract direction terms."""
        metric, direction = extract_metric_and_direction("Downloads increase sharply")
        assert direction == "increase"
    
    def test_extracts_both(self):
        """Should extract both when present."""
        metric, direction = extract_metric_and_direction("Contract volume decline observed")
        # Either "contract" or "volume" are valid measurable terms
        assert metric in ("contract", "volume")
        assert direction == "decline"


class TestEvidenceStrength:
    """Test evidence strength classification (v2.0)."""
    
    def test_weak_low_confidence(self):
        """Low confidence should be weak."""
        meta = {'concept_confidence': 0.45, 'category_diversity': {'category_count': 2}}
        assert classify_evidence_strength(meta) == 'weak'
    
    def test_weak_single_category(self):
        """Single category should be weak."""
        meta = {'concept_confidence': 0.8, 'category_diversity': {'category_count': 1}}
        assert classify_evidence_strength(meta) == 'weak'
    
    def test_strong_high_confidence_diverse(self):
        """High confidence + diversity should be strong."""
        meta = {'concept_confidence': 0.80, 'category_diversity': {'category_count': 3}}
        assert classify_evidence_strength(meta) == 'strong'
    
    def test_moderate_middle_ground(self):
        """Middle values should be moderate."""
        meta = {'concept_confidence': 0.65, 'category_diversity': {'category_count': 2}}
        assert classify_evidence_strength(meta) == 'moderate'


class TestPredictionLimits:
    """Test prediction limits (v2.0)."""
    
    def test_weak_limits(self):
        """Weak evidence should have strict limits."""
        min_p, max_p, max_tf = get_prediction_limits('weak')
        assert max_p == 2
        assert max_tf == 14
    
    def test_moderate_limits(self):
        """Moderate evidence should have moderate limits."""
        min_p, max_p, max_tf = get_prediction_limits('moderate')
        assert min_p == 3
        assert max_p == 4
        assert max_tf == 30
    
    def test_strong_limits(self):
        """Strong evidence should have generous limits."""
        min_p, max_p, max_tf = get_prediction_limits('strong')
        assert min_p == 4
        assert max_p == 6
        assert max_tf == 60


class TestIsObservable:
    """Test legacy observable detection."""
    
    def test_detects_observable_terms(self):
        """Should detect observable terms in predictions."""
        assert is_observable("New benchmark results published")
        assert is_observable("Funding round announced")
        assert is_observable("API release scheduled")
        assert is_observable("Download metrics increasing")
        assert is_observable("Revenue growth reported")
    
    def test_rejects_vague_descriptions(self):
        """Should reject vague, non-observable descriptions."""
        assert not is_observable("Things are changing")
        assert not is_observable("Market evolving")
        assert not is_observable("Dynamics shifting")


class TestHypothesisIdStability:
    """Test hypothesis ID generation stability."""
    
    def test_same_inputs_same_id(self):
        """Same inputs should produce same ID."""
        id1 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices are declining")
        id2 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices are declining")
        
        assert id1 == id2
    
    def test_whitespace_normalized(self):
        """Whitespace differences should not affect ID."""
        id1 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices are declining")
        id2 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices  are   declining")
        
        assert id1 == id2
    
    def test_different_mechanism_different_id(self):
        """Different mechanism should produce different ID."""
        id1 = generate_hypothesis_id("slug123", "pricing_cost_down", "Prices changing")
        id2 = generate_hypothesis_id("slug123", "pricing_cost_up", "Prices changing")
        
        assert id1 != id2


class TestTruncateToWords:
    """Test word truncation."""
    
    def test_truncates_long_text(self):
        """Should truncate to max words."""
        text = "One two three four five six seven eight nine ten"
        result = truncate_to_words(text, 5)
        assert len(result.split()) == 5
    
    def test_keeps_short_text(self):
        """Should keep text shorter than max."""
        text = "One two three"
        result = truncate_to_words(text, 5)
        assert result == text


# =============================================================================
# MECHANISM DETECTION TESTS
# =============================================================================

class TestMechanismDetection:
    """Test mechanism detection from meta-signals."""
    
    def test_detects_pricing_mechanism(self):
        """Should detect pricing mechanism from keywords."""
        taxonomy = load_mechanism_taxonomy()
        meta = make_pricing_meta()
        
        detections = detect_mechanisms(meta, taxonomy)
        
        assert len(detections) > 0
        primary_mech, hits, keywords, sources = detections[0]
        assert primary_mech in ['pricing_cost_down', 'pricing_cost_up']
        assert hits >= MIN_MECHANISM_KEYWORDS
    
    def test_detects_enterprise_mechanism(self):
        """Should detect enterprise mechanism from keywords."""
        taxonomy = load_mechanism_taxonomy()
        meta = make_strong_meta()
        
        detections = detect_mechanisms(meta, taxonomy)
        
        assert len(detections) > 0
        primary_mech, hits, keywords, sources = detections[0]
        assert primary_mech == 'enterprise_adoption'
    
    def test_weak_meta_low_hits(self):
        """Weak meta should have low mechanism hits."""
        taxonomy = load_mechanism_taxonomy()
        meta = make_weak_meta()
        
        detections = detect_mechanisms(meta, taxonomy)
        
        # May find some matches but should be weak
        if detections:
            _, hits, _, _ = detections[0]
            assert hits < 5
    
    def test_returns_evidence_sources(self):
        """Should track evidence sources (v2.0)."""
        taxonomy = load_mechanism_taxonomy()
        meta = make_pricing_meta()
        
        detections = detect_mechanisms(meta, taxonomy)
        
        assert len(detections) > 0
        _, _, _, sources = detections[0]
        assert len(sources) > 0


class TestMechanismTrace:
    """Test mechanism trace building (v2.0)."""
    
    def test_builds_trace_correctly(self):
        """Should build trace with all candidates."""
        detections = [
            ('enterprise_adoption', 4, ['enterprise', 'adoption', 'deployment', 'contract'], ['meta_insight', 'bucket_tags']),
            ('pricing_cost_down', 2, ['pricing', 'cost'], ['description']),
        ]
        
        trace = build_mechanism_trace(detections, 'enterprise_adoption', 'highest_score')
        
        assert trace.candidate_scores['enterprise_adoption'] == 4
        assert trace.candidate_scores['pricing_cost_down'] == 2
        assert 'enterprise' in trace.matched_terms
        assert 'meta_insight' in trace.evidence_sources
        assert trace.selection_reason == 'highest_score'


class TestNullHypothesisCompetition:
    """Test null hypothesis competition (v2.0)."""
    
    def test_should_emit_for_media_only(self):
        """Should emit attention_spike for media-only sources."""
        meta = make_weak_meta()
        assert should_emit_attention_spike(meta, 5)  # Even with good hits
    
    def test_should_emit_for_review_required(self):
        """Should emit attention_spike for review_required."""
        meta = make_pricing_meta()
        meta['review_required'] = True
        assert should_emit_attention_spike(meta, 5)
    
    def test_should_emit_for_weak_mechanism(self):
        """Should emit attention_spike for weak mechanism hits."""
        meta = make_strong_meta()
        assert should_emit_attention_spike(meta, 1)  # Low hits
    
    def test_should_not_emit_for_strong(self):
        """Should not emit for strong evidence."""
        meta = make_strong_meta()
        assert not should_emit_attention_spike(meta, 5)


# =============================================================================
# HYPOTHESIS GENERATION TESTS
# =============================================================================

class TestStrongMetaHighConfidence:
    """Test that strong meta produces high confidence hypothesis."""
    
    def test_generates_high_confidence(self):
        """Strong diversity + persistence should yield high confidence."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        
        assert len(bundle.hypotheses) >= 1
        top_hyp = bundle.hypotheses[0]
        
        # Should have decent confidence (not capped)
        assert top_hyp.confidence >= 0.50
        assert not top_hyp.review_required
    
    def test_predicted_signals_populated(self):
        """Should have predicted signals from taxonomy."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert len(top_hyp.predicted_next_signals) >= 3
        
        # All predictions should have metrics or be observable
        for pred in top_hyp.predicted_next_signals:
            assert pred.metric or is_observable(pred.description)
    
    def test_mechanism_trace_included(self):
        """Should include mechanism trace (v2.0)."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert top_hyp.mechanism_trace is not None
        assert len(top_hyp.mechanism_trace.candidate_scores) > 0
    
    def test_watchlist_populated(self):
        """Should populate watchlist (v2.0)."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        
        assert len(bundle.what_to_watch_next) > 0


class TestWeakMetaCappedConfidence:
    """Test that weak meta gets capped confidence and null hypothesis."""
    
    def test_confidence_capped(self):
        """Media-only + review_required should cap confidence."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        
        bundle = engine.process_meta_signal(meta)
        
        assert len(bundle.hypotheses) >= 1
        top_hyp = bundle.hypotheses[0]
        
        # Confidence should be capped
        assert top_hyp.confidence <= MEDIA_ONLY_CAP + 0.01
    
    def test_attention_spike_or_null_emitted(self):
        """Should emit attention_spike or null hypothesis when evidence weak (v2.0)."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        
        bundle = engine.process_meta_signal(meta)
        
        # Should include noise explanation
        mechanisms = [h.mechanism for h in bundle.hypotheses]
        assert 'null_hypothesis' in mechanisms or 'media_attention_spike' in mechanisms
    
    def test_review_required_set(self):
        """Should set review_required on hypotheses."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        
        bundle = engine.process_meta_signal(meta)
        
        # At least one hypothesis should require review
        assert any(h.review_required for h in bundle.hypotheses)
    
    def test_speculative_predictions(self):
        """Weak evidence should produce speculative predictions (v2.0)."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        # Predictions should be marked speculative
        speculative_count = sum(1 for p in top_hyp.predicted_next_signals if p.speculative)
        assert speculative_count > 0


class TestModerateMetaPredictions:
    """Test moderate evidence produces moderate predictions (v2.0)."""
    
    def test_moderate_prediction_count(self):
        """Moderate evidence should produce 3-4 predictions."""
        engine = HypothesisEngine()
        meta = make_moderate_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert 3 <= len(top_hyp.predicted_next_signals) <= 4
    
    def test_moderate_timeframes(self):
        """Moderate evidence should have 14-30 day timeframes."""
        engine = HypothesisEngine()
        meta = make_moderate_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        max_tf = max(p.expected_timeframe_days for p in top_hyp.predicted_next_signals)
        assert max_tf <= 30


class TestPricingMetaMechanismMatch:
    """Test that pricing meta matches pricing mechanism."""
    
    def test_correct_mechanism_selected(self):
        """Should select pricing mechanism."""
        engine = HypothesisEngine()
        meta = make_pricing_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert top_hyp.mechanism in ['pricing_cost_down', 'pricing_cost_up']
    
    def test_predicted_signals_from_template(self):
        """Should use pricing signal templates."""
        engine = HypothesisEngine()
        meta = make_pricing_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        # Should have financial and technical predictions
        categories = {p.category for p in top_hyp.predicted_next_signals}
        assert 'financial' in categories or 'technical' in categories
    
    def test_falsifiers_from_taxonomy(self):
        """Should have falsifiers from taxonomy."""
        engine = HypothesisEngine()
        meta = make_pricing_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert len(top_hyp.falsifiers) >= 1
        assert len(top_hyp.falsifiers) <= 3


class TestTitleSanitization:
    """Test that titles are properly sanitized."""
    
    def test_no_company_names_in_title(self):
        """Titles should not contain company names."""
        engine = HypothesisEngine()
        
        # Test with various metas
        for meta in [make_strong_meta(), make_weak_meta(), make_pricing_meta()]:
            bundle = engine.process_meta_signal(meta)
            
            for hyp in bundle.hypotheses:
                title_lower = hyp.title.lower()
                
                # Check common company names not in title
                assert 'openai' not in title_lower
                assert 'google' not in title_lower
                assert 'microsoft' not in title_lower
                assert 'anthropic' not in title_lower


class TestConfidenceBreakdown:
    """Test confidence breakdown components."""
    
    def test_breakdown_sums_correctly(self):
        """Breakdown components should relate to final score."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        bd = top_hyp.confidence_breakdown
        
        # All components should be >= 0
        assert bd.base_from_meta_confidence >= 0
        assert bd.diversity_bonus >= 0
        assert bd.persistence_bonus >= 0
        assert bd.independence_bonus >= 0
        assert bd.specificity_bonus >= 0
        
        # Final should be between 0 and 1
        assert 0 <= bd.final <= 1
    
    def test_penalties_tracked(self):
        """Penalties should be tracked in breakdown."""
        engine = HypothesisEngine()
        meta = make_weak_meta()
        
        bundle = engine.process_meta_signal(meta)
        
        # At least one hypothesis should have penalties
        has_penalties = any(
            len(h.confidence_breakdown.penalties_applied) > 0 
            for h in bundle.hypotheses
        )
        assert has_penalties


class TestDebugInfo:
    """Test debug information is populated."""
    
    def test_rules_fired_populated(self):
        """Debug should have rules_fired."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert len(top_hyp.debug.rules_fired) > 0
    
    def test_mechanism_keywords_tracked(self):
        """Debug should track mechanism keyword matches."""
        engine = HypothesisEngine()
        meta = make_pricing_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert top_hyp.debug.mechanism_keyword_hits > 0
        assert len(top_hyp.debug.mechanism_keywords_matched) > 0
    
    def test_evidence_strength_in_scoring_terms(self):
        """Debug should include evidence strength (v2.0)."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        top_hyp = bundle.hypotheses[0]
        
        assert 'evidence_strength' in top_hyp.debug.scoring_terms


class TestWatchlistBuilding:
    """Test watchlist building (v2.0)."""
    
    def test_builds_from_predictions(self):
        """Should build watchlist from hypothesis predictions."""
        hyp = Hypothesis(
            hypothesis_id='h1',
            title='Test',
            mechanism='test',
            claim='Claim',
            why_now='Now',
            evidence_used=EvidenceUsed([], [], [], []),
            predicted_next_signals=[
                PredictedSignal('technical', 'New SDK releases expected', ['github'], 14),
                PredictedSignal('financial', 'Revenue growth in earnings', ['sec'], 30),
            ],
            falsifiers=[],
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(0.4, 0.1, 0.08, 0.08, 0.09, [], 0.75),
            review_required=False,
            debug=DebugInfo([], {}, 0, []),
        )
        
        watchlist = build_watchlist([hyp], top_n=3)
        
        assert len(watchlist) >= 1
        assert any('SDK' in w or 'Revenue' in w for w in watchlist)
    
    def test_limits_to_top_n(self):
        """Should limit to top_n items."""
        hyp = Hypothesis(
            hypothesis_id='h1',
            title='Test',
            mechanism='test',
            claim='Claim',
            why_now='Now',
            evidence_used=EvidenceUsed([], [], [], []),
            predicted_next_signals=[
                PredictedSignal('technical', 'Item 1 increase', ['github'], 7),
                PredictedSignal('financial', 'Item 2 growth', ['sec'], 14),
                PredictedSignal('social', 'Item 3 rise', ['twitter'], 21),
                PredictedSignal('media', 'Item 4 surge', ['techmeme'], 28),
                PredictedSignal('predictive', 'Item 5 jump', ['polymarket'], 35),
            ],
            falsifiers=[],
            confidence=0.75,
            confidence_breakdown=ConfidenceBreakdown(0.4, 0.1, 0.08, 0.08, 0.09, [], 0.75),
            review_required=False,
            debug=DebugInfo([], {}, 0, []),
        )
        
        watchlist = build_watchlist([hyp], top_n=3)
        assert len(watchlist) <= 3


# =============================================================================
# ENGINE INTEGRATION TESTS
# =============================================================================

class TestHypothesisEngineIntegration:
    """Test HypothesisEngine end-to-end."""
    
    def test_processes_multiple_metas(self):
        """Should process multiple meta-signals."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_weak_meta(), make_pricing_meta()]
        
        result = engine.process_meta_signals(metas, date='2026-02-09')
        
        assert result['summary']['total_metas'] == 3
        assert result['summary']['total_bundles'] == 3
        assert len(result['bundles']) == 3
    
    def test_summary_stats_populated(self):
        """Should populate summary statistics."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_weak_meta()]
        
        result = engine.process_meta_signals(metas, date='2026-02-09')
        
        assert 'total_hypotheses' in result['summary']
        assert 'top_mechanisms' in result['summary']
        assert 'metas_requiring_review' in result['summary']
    
    def test_version_is_2_0(self):
        """Should output version 2.0."""
        engine = HypothesisEngine()
        metas = [make_strong_meta()]
        
        result = engine.process_meta_signals(metas, date='2026-02-09')
        
        assert result['version'] == '2.0'
    
    def test_bundles_have_watchlist(self):
        """Bundles should have what_to_watch_next (v2.0)."""
        engine = HypothesisEngine()
        metas = [make_strong_meta()]
        
        result = engine.process_meta_signals(metas, date='2026-02-09')
        
        for bundle in result['bundles']:
            assert 'what_to_watch_next' in bundle
    
    def test_bundles_have_mechanism_trace(self):
        """Bundles should have mechanism_trace (v2.0)."""
        engine = HypothesisEngine()
        metas = [make_strong_meta()]
        
        result = engine.process_meta_signals(metas, date='2026-02-09')
        
        for bundle in result['bundles']:
            for hyp in bundle['hypotheses']:
                assert 'mechanism_trace' in hyp
    
    def test_report_section_formatting(self):
        """Should format report section correctly."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        
        bundle = engine.process_meta_signal(meta)
        report = engine.format_report_section([bundle])
        
        assert '## Hypotheses from Meta-Signals' in report
        assert 'What to watch:' in report


# =============================================================================
# RENDERER TESTS (v2.0)
# =============================================================================

class TestHypothesisRenderer:
    """Test hypothesis renderer functions (v2.0)."""
    
    def test_render_hypothesis_summary(self):
        """Should render single bundle to summary."""
        engine = HypothesisEngine()
        meta = make_strong_meta()
        bundle = engine.process_meta_signal(meta)
        
        summary = render_hypothesis_summary(bundle.to_dict())
        
        assert 'concept_name' in summary
        assert 'confidence' in summary
        assert 'main_hypothesis' in summary
        assert summary['main_hypothesis'] is not None
        assert 'title' in summary['main_hypothesis']
        assert 'predicted_signals' in summary['main_hypothesis']
    
    def test_render_daily_report(self):
        """Should render multiple bundles to daily report."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_weak_meta()]
        
        bundles = [engine.process_meta_signal(m).to_dict() for m in metas]
        report = render_daily_report(bundles, date='2026-02-09')
        
        assert report['date'] == '2026-02-09'
        assert 'summary' in report
        assert 'hypotheses' in report
        assert len(report['hypotheses']) == 2
    
    def test_render_watchlist_aggregate(self):
        """Should aggregate watchlist across bundles."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_pricing_meta()]
        
        bundles = [engine.process_meta_signal(m).to_dict() for m in metas]
        watchlist = render_watchlist_aggregate(bundles, top_n=5)
        
        assert len(watchlist) <= 5
        assert all('item' in w for w in watchlist)
        assert all('source_concept' in w for w in watchlist)
    
    def test_render_mechanism_breakdown(self):
        """Should render mechanism breakdown."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_pricing_meta()]
        
        bundles = [engine.process_meta_signal(m).to_dict() for m in metas]
        breakdown = render_mechanism_breakdown(bundles)
        
        assert 'by_mechanism' in breakdown
        assert 'total' in breakdown
    
    def test_render_confidence_tiers(self):
        """Should render confidence tiers."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_weak_meta()]
        
        bundles = [engine.process_meta_signal(m).to_dict() for m in metas]
        tiers = render_confidence_tiers(bundles)
        
        assert 'high' in tiers
        assert 'medium' in tiers
        assert 'low' in tiers
    
    def test_render_evidence_quality_report(self):
        """Should render evidence quality report."""
        engine = HypothesisEngine()
        metas = [make_strong_meta(), make_weak_meta(), make_moderate_meta()]
        
        bundles = [engine.process_meta_signal(m).to_dict() for m in metas]
        quality = render_evidence_quality_report(bundles)
        
        assert 'strong_evidence' in quality
        assert 'moderate_evidence' in quality
        assert 'weak_evidence' in quality
        assert 'speculative_predictions_total' in quality
        assert 'observable_predictions_total' in quality


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all tests."""
    print("\n=== HYPOTHESIS ENGINE v2.0 TESTS ===\n")
    
    # Data structure tests
    t = TestMechanismTraceSerialization()
    t.test_to_dict_and_back()
    print("[PASS] MechanismTrace serialization")
    
    t = TestPredictedSignalSerialization()
    t.test_to_dict_and_back()
    t.test_v2_fields()
    print("[PASS] PredictedSignal serialization")
    
    t = TestHypothesisSerialization()
    t.test_to_dict_and_back()
    t.test_mechanism_trace_serialization()
    print("[PASS] Hypothesis serialization")
    
    t = TestMetaHypothesisBundleSerialization()
    t.test_to_dict_and_back()
    print("[PASS] MetaHypothesisBundle serialization")
    
    # Helper function tests
    t = TestSanitizeTitle()
    t.test_removes_company_names()
    t.test_removes_model_names()
    t.test_keeps_generic_terms()
    t.test_handles_empty_result()
    t.test_removes_filler_words()
    t.test_truncates_to_8_words()
    print("[PASS] Title sanitization tests")
    
    t = TestObservableGate()
    t.test_passes_with_measurable_and_direction()
    t.test_fails_without_direction()
    t.test_fails_without_measurable()
    t.test_fails_for_vague_descriptions()
    print("[PASS] Observable gate tests")
    
    t = TestMetricDirectionExtraction()
    t.test_extracts_metric()
    t.test_extracts_direction()
    t.test_extracts_both()
    print("[PASS] Metric/direction extraction tests")
    
    t = TestEvidenceStrength()
    t.test_weak_low_confidence()
    t.test_weak_single_category()
    t.test_strong_high_confidence_diverse()
    t.test_moderate_middle_ground()
    print("[PASS] Evidence strength tests")
    
    t = TestPredictionLimits()
    t.test_weak_limits()
    t.test_moderate_limits()
    t.test_strong_limits()
    print("[PASS] Prediction limits tests")
    
    t = TestIsObservable()
    t.test_detects_observable_terms()
    t.test_rejects_vague_descriptions()
    print("[PASS] Observable detection tests")
    
    t = TestHypothesisIdStability()
    t.test_same_inputs_same_id()
    t.test_whitespace_normalized()
    t.test_different_mechanism_different_id()
    print("[PASS] Hypothesis ID stability tests")
    
    t = TestTruncateToWords()
    t.test_truncates_long_text()
    t.test_keeps_short_text()
    print("[PASS] Truncate to words tests")
    
    # Mechanism detection tests
    t = TestMechanismDetection()
    t.test_detects_pricing_mechanism()
    t.test_detects_enterprise_mechanism()
    t.test_weak_meta_low_hits()
    t.test_returns_evidence_sources()
    print("[PASS] Mechanism detection tests")
    
    t = TestMechanismTrace()
    t.test_builds_trace_correctly()
    print("[PASS] Mechanism trace tests")
    
    t = TestNullHypothesisCompetition()
    t.test_should_emit_for_media_only()
    t.test_should_emit_for_review_required()
    t.test_should_emit_for_weak_mechanism()
    t.test_should_not_emit_for_strong()
    print("[PASS] Null hypothesis competition tests")
    
    # Hypothesis generation tests
    t = TestStrongMetaHighConfidence()
    t.test_generates_high_confidence()
    t.test_predicted_signals_populated()
    t.test_mechanism_trace_included()
    t.test_watchlist_populated()
    print("[PASS] Strong meta → high confidence tests")
    
    t = TestWeakMetaCappedConfidence()
    t.test_confidence_capped()
    t.test_attention_spike_or_null_emitted()
    t.test_review_required_set()
    t.test_speculative_predictions()
    print("[PASS] Weak meta → capped confidence tests")
    
    t = TestModerateMetaPredictions()
    t.test_moderate_prediction_count()
    t.test_moderate_timeframes()
    print("[PASS] Moderate meta → moderate predictions tests")
    
    t = TestPricingMetaMechanismMatch()
    t.test_correct_mechanism_selected()
    t.test_predicted_signals_from_template()
    t.test_falsifiers_from_taxonomy()
    print("[PASS] Pricing meta → mechanism match tests")
    
    t = TestTitleSanitization()
    t.test_no_company_names_in_title()
    print("[PASS] Title sanitization tests")
    
    t = TestConfidenceBreakdown()
    t.test_breakdown_sums_correctly()
    t.test_penalties_tracked()
    print("[PASS] Confidence breakdown tests")
    
    t = TestDebugInfo()
    t.test_rules_fired_populated()
    t.test_mechanism_keywords_tracked()
    t.test_evidence_strength_in_scoring_terms()
    print("[PASS] Debug info tests")
    
    t = TestWatchlistBuilding()
    t.test_builds_from_predictions()
    t.test_limits_to_top_n()
    print("[PASS] Watchlist building tests")
    
    # Integration tests
    t = TestHypothesisEngineIntegration()
    t.test_processes_multiple_metas()
    t.test_summary_stats_populated()
    t.test_version_is_2_0()
    t.test_bundles_have_watchlist()
    t.test_bundles_have_mechanism_trace()
    t.test_report_section_formatting()
    print("[PASS] Engine integration tests")
    
    # Renderer tests
    t = TestHypothesisRenderer()
    t.test_render_hypothesis_summary()
    t.test_render_daily_report()
    t.test_render_watchlist_aggregate()
    t.test_render_mechanism_breakdown()
    t.test_render_confidence_tiers()
    t.test_render_evidence_quality_report()
    print("[PASS] Renderer tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
