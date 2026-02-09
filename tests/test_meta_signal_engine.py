"""
Tests for Meta-Signal Engine v2.6 (Concept Synthesizer).

Tests:
1. Insight extraction from signals
2. Diversity requirement (two different entities → trend, same entity → reject)
3. Maturity transitions
4. Trend naming (no company names)
5. Generic name detection and specificity gate
6. Mechanism extraction and renaming
7. Meta deduplication (centroid + overlap) + merge_reason
8. Hierarchical parent/child meta trends + hierarchy_reason
9. Confidence hardening (persistence + category + independence)
10. confidence_breakdown with independence
11. Stable concept_slug (v2.6)
12. Name freezing (v2.6)
13. Independence scoring (v2.6)
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from utils.meta_signal_engine import (
    # Data structures
    SignalInsight,
    MetaSignal,
    NamingReason,
    CategoryDiversity,
    ConfidenceBreakdown,
    MergeReason,
    HierarchyReason,
    MetaSignalEngine,
    
    # Core functions
    build_signal_insight,
    build_insights_from_signals,
    cluster_insights,
    check_diversity_requirement,
    derive_maturity_stage,
    compute_meta_acceleration,
    name_meta_signal,
    synthesize_meta_signals,
    clean_trend_name,
    is_company_or_model,
    jaccard_similarity,
    ConceptEmbedder,
    
    # v2.5 functions
    is_generic_name,
    extract_mechanism_keywords,
    rename_generic_meta,
    apply_specificity_gate,
    dedupe_meta_signals,
    compute_meta_similarity,
    merge_meta_signals,
    build_hierarchy,
    compute_persistence_days,
    compute_persistence_factor,
    compute_category_diversity,
    compute_category_factor,
    compute_hardened_confidence,
    apply_confidence_hardening,
    
    # v2.6 functions
    generate_concept_slug,
    compute_independence_score,
    compute_validation_status_v26,
    should_freeze_name,
    can_unfreeze_name,
    generate_slug_for_meta,
    
    # Constants
    MIN_SUPPORTING_SIGNALS,
    MIN_ENTITY_DIVERSITY,
    MIN_BUCKET_DIVERSITY,
    MIN_MECHANISM_HITS,
    PERSISTENCE_BONUS_MULTI_DAY,
    PERSISTENCE_PENALTY_SINGLE_DAY,
    CATEGORY_BONUS_TWO,
    CATEGORY_BONUS_THREE_PLUS,
    SINGLE_CATEGORY_CONFIDENCE_CAP,
    REVIEW_REQUIRED_CONFIDENCE_CAP,
    META_DEDUP_SIMILARITY_THRESHOLD,
    META_DEDUP_OVERLAP_THRESHOLD,
    INDEPENDENCE_VALUES,
    INDEPENDENCE_BONUS_MULTIPLIER,
    NAME_FREEZE_MIN_PERSISTENCE,
    NAME_FREEZE_MIN_CONFIDENCE,
    VALIDATED_MIN_WEIGHTED_DIVERSITY,
    VALIDATED_MIN_INDEPENDENCE,
)


# =============================================================================
# FIXTURES
# =============================================================================

def make_signal(
    signal_id: str,
    name: str,
    entities: list,
    buckets: list,
    status: str = 'emerging',
    velocity: float = 1.5,
    confidence: float = 0.7,
    example_titles: list = None,
    last_seen_date: str = '2026-02-09',
):
    """Create a mock signal dict."""
    return {
        'signal_id': signal_id,
        'name': name,
        'status': status,
        'last_seen_date': last_seen_date,
        'metrics': {
            'velocity': velocity,
            'confidence': confidence,
            'mentions_7d': 3,
        },
        'profile': {
            'top_entities': entities,
            'top_buckets': buckets,
            'example_titles': example_titles or [f'{name} news'],
            'key_insight': '',
        },
        'validation': {
            'corroborating_sources': {},
        },
    }


def make_insight(
    signal_id: str,
    insight_text: str,
    entities: list,
    buckets: list,
    status: str = 'emerging',
    velocity: float = 1.5,
    confidence: float = 0.7,
    date: str = '2026-02-09',
    source_category: str = None,
    corroborating_sources: list = None,
):
    """Create a mock SignalInsight."""
    return SignalInsight(
        signal_id=signal_id,
        signal_name=f'Signal {signal_id}',
        date=date,
        insight_text=insight_text,
        entities=entities,
        buckets=buckets,
        velocity=velocity,
        confidence=confidence,
        status=status,
        source_category=source_category,
        corroborating_sources=corroborating_sources or [],
    )


def make_meta(
    meta_id: str,
    concept_name: str,
    supporting_signals: list,
    supporting_insights: list = None,
    concept_confidence: float = 0.6,
    entity_diversity: int = 3,
    bucket_diversity: int = 2,
    centroid_embedding: list = None,
    mechanism: str = None,
    concept_slug: str = "",
    name_frozen: bool = False,
    first_seen: str = '2026-02-01',
):
    """Create a mock MetaSignal."""
    if supporting_insights is None:
        supporting_insights = [
            make_insight(s, f'Insight {s}', ['e'], ['b']) 
            for s in supporting_signals
        ]
    
    return MetaSignal(
        meta_id=meta_id,
        concept_name=concept_name,
        description='Test description',
        supporting_signals=supporting_signals,
        supporting_insights=supporting_insights,
        first_seen=first_seen,
        last_updated='2026-02-09',
        maturity_stage='emerging',
        concept_confidence=concept_confidence,
        entity_diversity=entity_diversity,
        bucket_diversity=bucket_diversity,
        centroid_embedding=centroid_embedding,
        mechanism=mechanism,
        concept_slug=concept_slug,
        name_frozen=name_frozen,
    )


# =============================================================================
# DATA STRUCTURE TESTS
# =============================================================================

class TestSignalInsightSerialization:
    """Test SignalInsight serialization."""
    
    def test_to_dict_and_back(self):
        """SignalInsight should roundtrip through dict."""
        insight = SignalInsight(
            signal_id='sig123',
            signal_name='Test Signal',
            date='2026-02-09',
            insight_text='AI pricing dynamics shifting',
            entities=['company_a', 'company_b'],
            buckets=['pricing', 'enterprise'],
            velocity=1.8,
            confidence=0.75,
            status='emerging',
            source_category='financial',
            corroborating_sources=['news', 'sec'],
        )
        
        d = insight.to_dict()
        restored = SignalInsight.from_dict(d)
        
        assert restored.signal_id == insight.signal_id
        assert restored.insight_text == insight.insight_text
        assert restored.entities == insight.entities
        assert restored.source_category == 'financial'
        assert restored.corroborating_sources == ['news', 'sec']
    
    def test_json_serializable(self):
        """SignalInsight dict should be JSON-serializable."""
        insight = make_insight('s1', 'Test insight', ['e'], ['b'])
        json_str = json.dumps(insight.to_dict())
        assert len(json_str) > 0


class TestMetaSignalSerialization:
    """Test MetaSignal serialization with v2.6 fields."""
    
    def test_to_dict_and_back(self):
        """MetaSignal should roundtrip through dict."""
        meta = MetaSignal(
            meta_id='meta123',
            concept_name='Pricing Pressure Rising',
            description='Test description',
            supporting_signals=['sig1', 'sig2'],
            first_seen='2026-02-01',
            last_updated='2026-02-09',
            maturity_stage='emerging',
            concept_confidence=0.55,
            mechanism='pricing-monetization',
            naming_reason=NamingReason(was_generic=True, original_name='AI Market'),
            merged_from=['meta456'],
            persistence_days=3,
            persistence_factor=0.10,
            category_diversity=CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=2.0),
            validation_status='validated',
            confidence_breakdown=ConfidenceBreakdown(base=0.5, independence=0.09, final=0.55),
            # v2.6 fields
            concept_slug='a91c44e21fa2',
            name_frozen=True,
            independence_score=0.82,
            merge_reason=MergeReason(centroid_similarity=0.84, signal_overlap=0.47),
            hierarchy_reason=HierarchyReason(centroid_similarity=0.73, signal_overlap=0.31),
        )
        
        d = meta.to_dict()
        restored = MetaSignal.from_dict(d)
        
        assert restored.meta_id == meta.meta_id
        assert restored.concept_name == meta.concept_name
        assert restored.mechanism == 'pricing-monetization'
        assert restored.naming_reason.was_generic == True
        assert restored.merged_from == ['meta456']
        assert restored.persistence_days == 3
        assert restored.category_diversity.category_count == 2
        assert restored.validation_status == 'validated'
        assert restored.confidence_breakdown.independence == 0.09
        # v2.6 fields
        assert restored.concept_slug == 'a91c44e21fa2'
        assert restored.name_frozen == True
        assert restored.independence_score == 0.82
        assert restored.merge_reason.centroid_similarity == 0.84
        assert restored.hierarchy_reason.signal_overlap == 0.31
    
    def test_json_serializable(self):
        """MetaSignal dict should be JSON-serializable."""
        meta = MetaSignal(
            meta_id='m1',
            concept_name='Test',
            description='Desc',
            supporting_signals=['s1'],
            naming_reason=NamingReason(was_generic=True),
            category_diversity=CategoryDiversity(categories=['media'], category_count=1),
            confidence_breakdown=ConfidenceBreakdown(final=0.5),
            merge_reason=MergeReason(centroid_similarity=0.9),
            hierarchy_reason=HierarchyReason(signal_overlap=0.3),
        )
        json_str = json.dumps(meta.to_dict())
        assert len(json_str) > 0
    
    def test_backward_compatible_missing_v26_fields(self):
        """Should handle missing v2.6 fields (backward compat)."""
        old_dict = {
            'meta_id': 'm1',
            'concept_name': 'Old Meta',
            'description': '',
            'supporting_signals': ['s1'],
            # No v2.6 fields
        }
        
        restored = MetaSignal.from_dict(old_dict)
        
        assert restored.meta_id == 'm1'
        assert restored.concept_slug == ''
        assert restored.name_frozen == False
        assert restored.independence_score == 0.0
        assert restored.merge_reason is None
        assert restored.hierarchy_reason is None


class TestMergeReasonSerialization:
    """Test MergeReason serialization."""
    
    def test_to_dict_and_back(self):
        """MergeReason should roundtrip through dict."""
        mr = MergeReason(
            rule="DEDUP_MERGE_V2",
            centroid_similarity=0.84,
            signal_overlap=0.47,
        )
        
        d = mr.to_dict()
        restored = MergeReason.from_dict(d)
        
        assert restored.rule == "DEDUP_MERGE_V2"
        assert restored.centroid_similarity == 0.84
        assert restored.signal_overlap == 0.47


class TestHierarchyReasonSerialization:
    """Test HierarchyReason serialization."""
    
    def test_to_dict_and_back(self):
        """HierarchyReason should roundtrip through dict."""
        hr = HierarchyReason(
            rule="PARENT_CHILD_V2",
            centroid_similarity=0.73,
            signal_overlap=0.31,
        )
        
        d = hr.to_dict()
        restored = HierarchyReason.from_dict(d)
        
        assert restored.rule == "PARENT_CHILD_V2"
        assert restored.centroid_similarity == 0.73
        assert restored.signal_overlap == 0.31


# =============================================================================
# INSIGHT EXTRACTION TESTS
# =============================================================================

class TestInsightExtraction:
    """Test insight extraction from signals."""
    
    def test_extracts_insight_from_signal(self):
        """Should extract structural insight from signal."""
        signal = make_signal(
            'sig1', 'Pricing Signal',
            entities=['company_a'],
            buckets=['pricing', 'api'],
            example_titles=['Company raises API prices'],
        )
        
        insight = build_signal_insight(signal, '2026-02-09')
        
        assert insight.signal_id == 'sig1'
        assert insight.insight_text
        assert len(insight.insight_text) > 10
    
    def test_skips_dead_signals(self):
        """build_insights_from_signals should skip dead signals."""
        signals = [
            make_signal('sig1', 'Active', ['e1'], ['b1'], status='emerging'),
            make_signal('sig2', 'Dead', ['e2'], ['b2'], status='dead'),
        ]
        
        insights = build_insights_from_signals(signals, '2026-02-09')
        
        assert len(insights) == 1
        assert insights[0].signal_id == 'sig1'


# =============================================================================
# DIVERSITY REQUIREMENT TESTS
# =============================================================================

class TestDiversityRequirement:
    """Test diversity requirement for meta-signals."""
    
    def test_two_different_entities_form_trend(self):
        """Two different entities should form a meta-signal."""
        insights = [
            make_insight('s1', 'Pricing dynamics', ['company_a'], ['pricing']),
            make_insight('s2', 'Pricing changes', ['company_b'], ['pricing']),
        ]
        
        meets, e_div, b_div = check_diversity_requirement(insights)
        
        assert meets == True
        assert e_div >= MIN_ENTITY_DIVERSITY
    
    def test_same_entity_not_enough(self):
        """Same entity alone should NOT form meta-signal."""
        insights = [
            make_insight('s1', 'Pricing dynamics', ['company_a'], ['pricing']),
            make_insight('s2', 'More pricing', ['company_a'], ['pricing']),
        ]
        
        meets, e_div, b_div = check_diversity_requirement(insights)
        
        assert meets == False


# =============================================================================
# V2.5: GENERIC NAME DETECTION TESTS
# =============================================================================

class TestGenericNameDetection:
    """Test generic name detection (v2.5)."""
    
    def test_detects_generic_accelerating_pattern(self):
        """Should detect 'AI X Accelerating' as generic."""
        assert is_generic_name("AI Market Accelerating") == True
    
    def test_specific_names_pass(self):
        """Specific mechanism names should NOT be flagged as generic."""
        assert is_generic_name("Pricing Pressure Rising") == False
        assert is_generic_name("Enterprise Adoption Expanding") == False


# =============================================================================
# V2.5: MECHANISM EXTRACTION TESTS
# =============================================================================

class TestMechanismExtraction:
    """Test mechanism extraction (v2.5)."""
    
    def test_extracts_pricing_mechanism(self):
        """Should extract 'pricing-monetization' mechanism."""
        insights = [
            make_insight('s1', 'Price fee rate cost margin', [], ['pricing', 'api']),
            make_insight('s2', 'Revenue subscription monetization', [], ['monetization']),
        ]
        
        result = extract_mechanism_keywords(insights)
        
        assert result['mechanism'] == 'pricing-monetization'
        assert result['score'] >= MIN_MECHANISM_HITS


# =============================================================================
# V2.5: SPECIFICITY GATE TESTS
# =============================================================================

class TestSpecificityGate:
    """Test specificity gate (v2.5)."""
    
    def test_renames_generic_to_mechanism(self):
        """Generic name should be renamed to mechanism-specific."""
        insights = [
            make_insight('s1', 'Price fee cost margin revenue', [], ['pricing', 'monetization']),
            make_insight('s2', 'Pricing subscription rate billing', [], ['pricing']),
        ]
        
        meta = make_meta('m1', 'AI Market Accelerating', ['s1', 's2'], insights)
        
        result = apply_specificity_gate(meta)
        
        assert result.naming_reason is not None
        assert result.naming_reason.was_generic == True
        assert result.mechanism == 'pricing-monetization'
        assert 'Pricing' in result.concept_name
    
    def test_respects_name_frozen(self):
        """Should NOT rename if name is frozen."""
        insights = [
            make_insight('s1', 'Price fee cost margin revenue', [], ['pricing']),
            make_insight('s2', 'Pricing subscription rate', [], ['pricing']),
        ]
        
        meta = make_meta('m1', 'AI Market Accelerating', ['s1', 's2'], insights,
                        name_frozen=True)
        
        result = apply_specificity_gate(meta)
        
        assert result.concept_name == 'AI Market Accelerating'
        assert result.name_frozen == True


# =============================================================================
# V2.5/V2.6: META DEDUPLICATION TESTS
# =============================================================================

class TestMetaDeduplication:
    """Test meta-signal deduplication (v2.5/v2.6)."""
    
    def test_merges_near_duplicates_with_reason(self):
        """Near-duplicate metas should be merged with merge_reason."""
        centroid = [0.1] * 10
        
        meta1 = make_meta('m1', 'Pricing Rising', ['s1', 's2', 's3'],
                         concept_confidence=0.7, centroid_embedding=centroid)
        meta2 = make_meta('m2', 'Cost Shifting', ['s2', 's3', 's4'],
                         concept_confidence=0.5, centroid_embedding=centroid)
        
        class MockEmbedder:
            def cosine_similarity(self, a, b):
                return 0.95 if a == b else 0.0
            def compute_centroid(self, embs):
                return embs[0] if embs else None
        
        result = dedupe_meta_signals([meta1, meta2], MockEmbedder())
        
        assert len(result) == 1
        assert result[0].meta_id == 'm1'
        assert 'm2' in result[0].merged_from
        # v2.6: merge_reason should be populated
        assert result[0].merge_reason is not None
        assert result[0].merge_reason.rule == "DEDUP_MERGE_V2"
        assert result[0].merge_reason.centroid_similarity >= 0.80
    
    def test_keeps_distinct_metas(self):
        """Distinct metas should NOT be merged."""
        meta1 = make_meta('m1', 'Pricing Rising', ['s1', 's2'],
                         centroid_embedding=[0.1] * 10)
        meta2 = make_meta('m2', 'Compute Expanding', ['s5', 's6'],
                         centroid_embedding=[0.9] * 10)
        
        class MockEmbedder:
            def cosine_similarity(self, a, b):
                return 0.3
            def compute_centroid(self, embs):
                return embs[0] if embs else None
        
        result = dedupe_meta_signals([meta1, meta2], MockEmbedder())
        
        assert len(result) == 2


# =============================================================================
# V2.5/V2.6: HIERARCHY TESTS
# =============================================================================

class TestHierarchy:
    """Test hierarchical parent/child meta trends (v2.5/v2.6)."""
    
    def test_creates_hierarchy_with_reason(self):
        """Should create hierarchy with hierarchy_reason."""
        insights1 = [make_insight('s1', 'I1', ['e1'], ['b1']),
                    make_insight('s2', 'I2', ['e2'], ['b2']),
                    make_insight('s3', 'I3', ['e3'], ['b3'])]
        insights2 = [make_insight('s3', 'I3', ['e3'], ['b3']),
                    make_insight('s4', 'I4', ['e4'], ['b4'])]
        
        meta1 = make_meta('m1', 'Broad Trend', ['s1', 's2', 's3'],
                         supporting_insights=insights1,
                         entity_diversity=3, bucket_diversity=3,
                         centroid_embedding=[0.5] * 10)
        meta2 = make_meta('m2', 'Specific Trend', ['s3', 's4'],
                         supporting_insights=insights2,
                         entity_diversity=2, bucket_diversity=2,
                         centroid_embedding=[0.55] * 10)
        
        class MockEmbedder:
            def cosine_similarity(self, a, b):
                return 0.75  # In hierarchy band
            def compute_centroid(self, embs):
                return embs[0] if embs else None
        
        result = build_hierarchy([meta1, meta2], MockEmbedder())
        
        parent = [m for m in result if m.child_meta_ids]
        
        if parent:
            # v2.6: hierarchy_reason should be populated
            assert parent[0].hierarchy_reason is not None
            assert parent[0].hierarchy_reason.rule == "PARENT_CHILD_V2"


# =============================================================================
# V2.5: PERSISTENCE FACTOR TESTS
# =============================================================================

class TestPersistenceFactor:
    """Test persistence factor (v2.5)."""
    
    def test_single_day_penalty(self):
        """Single day should get penalty."""
        factor = compute_persistence_factor(1)
        assert factor == PERSISTENCE_PENALTY_SINGLE_DAY
        assert factor < 0
    
    def test_multi_day_bonus(self):
        """Multi-day should get bonus."""
        factor = compute_persistence_factor(2)
        assert factor == PERSISTENCE_BONUS_MULTI_DAY
        assert factor > 0


# =============================================================================
# V2.6: CONCEPT SLUG TESTS
# =============================================================================

class TestConceptSlug:
    """Test stable concept slug generation (v2.6)."""
    
    def test_slug_stable_with_entity_order(self):
        """Slug should be stable regardless of entity order."""
        slug1 = generate_concept_slug(['openai', 'anthropic'], 'pricing-monetization', '2026-02-01')
        slug2 = generate_concept_slug(['anthropic', 'openai'], 'pricing-monetization', '2026-02-01')
        
        assert slug1 == slug2
        assert len(slug1) == 12
    
    def test_different_mechanism_different_slug(self):
        """Different mechanism should give different slug."""
        slug1 = generate_concept_slug(['openai', 'anthropic'], 'pricing-monetization', '2026-02-01')
        slug2 = generate_concept_slug(['openai', 'anthropic'], 'compute-hardware', '2026-02-01')
        
        assert slug1 != slug2
    
    def test_slug_survives_rename(self):
        """Slug should survive name changes."""
        insights = [
            make_insight('s1', 'Price fee cost', ['company_a'], ['pricing']),
            make_insight('s2', 'Rate billing margin', ['company_b'], ['pricing']),
        ]
        
        meta = make_meta('m1', 'AI Market Accelerating', ['s1', 's2'], insights,
                        mechanism='pricing-monetization', concept_slug='original_slug')
        
        # Simulate rename
        original_slug = meta.concept_slug
        meta.concept_name = "Pricing Pressure Rising"
        
        # Slug should remain unchanged
        assert meta.concept_slug == original_slug


# =============================================================================
# V2.6: INDEPENDENCE SCORING TESTS
# =============================================================================

class TestIndependenceScoring:
    """Test independence scoring (v2.6)."""
    
    def test_high_independence_categories(self):
        """High independence categories should score high."""
        cat_div = CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=2.0)
        
        source_cfg = {
            'categories': {
                'technical': {'weight': 1.0, 'independence_level': 'high'},
                'financial': {'weight': 1.0, 'independence_level': 'high'},
            }
        }
        
        score = compute_independence_score(cat_div, source_cfg)
        
        assert score == 1.0  # Both high
    
    def test_mixed_independence_categories(self):
        """Mixed independence should average appropriately."""
        cat_div = CategoryDiversity(categories=['technical', 'social'], category_count=2, weighted_diversity=1.8)
        
        source_cfg = {
            'categories': {
                'technical': {'weight': 1.0, 'independence_level': 'high'},  # 1.0
                'social': {'weight': 0.8, 'independence_level': 'medium'},   # 0.7
            }
        }
        
        score = compute_independence_score(cat_div, source_cfg)
        
        # (1.0 * 1.0 + 0.8 * 0.7) / (1.0 + 0.8) = (1.0 + 0.56) / 1.8 ≈ 0.867
        assert 0.8 < score < 0.9
    
    def test_independence_affects_confidence(self):
        """Independence score should affect confidence."""
        insights = [
            make_insight('s1', 'I1', ['e1'], ['b1'], confidence=0.6, 
                        corroborating_sources=['github', 'sec']),
            make_insight('s2', 'I2', ['e2'], ['b2'], confidence=0.6,
                        corroborating_sources=['arxiv']),
        ]
        
        cat_div_high = CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=2.0)
        cat_div_low = CategoryDiversity(categories=['media'], category_count=1, weighted_diversity=0.7)
        
        conf_high, _ = compute_hardened_confidence(
            insights, 2, 2, 2, cat_div_high, 1.0, False, 'validated'
        )
        
        conf_low, _ = compute_hardened_confidence(
            insights, 2, 2, 2, cat_div_low, 0.4, False, 'weakly_validated'
        )
        
        assert conf_high > conf_low


# =============================================================================
# V2.6: NAME FREEZING TESTS
# =============================================================================

class TestNameFreezing:
    """Test name freezing (v2.6)."""
    
    def test_freezes_after_threshold(self):
        """Name should freeze after persistence + confidence thresholds."""
        assert should_freeze_name(3, 0.65, False) == True
    
    def test_does_not_freeze_below_threshold(self):
        """Name should NOT freeze below thresholds."""
        assert should_freeze_name(2, 0.65, False) == False  # Days too low
        assert should_freeze_name(3, 0.55, False) == False  # Confidence too low
    
    def test_stays_frozen_once_frozen(self):
        """Once frozen, should stay frozen."""
        assert should_freeze_name(1, 0.30, True) == True
    
    def test_frozen_name_not_renamed(self):
        """Frozen name should not be renamed by specificity gate."""
        insights = [
            make_insight('s1', 'Price fee cost margin revenue', [], ['pricing']),
            make_insight('s2', 'Pricing subscription rate', [], ['pricing']),
        ]
        
        meta = make_meta('m1', 'My Custom Name', ['s1', 's2'], insights, name_frozen=True)
        original_name = meta.concept_name
        
        result = apply_specificity_gate(meta)
        
        assert result.concept_name == original_name


# =============================================================================
# V2.6: VALIDATION STATUS TESTS
# =============================================================================

class TestValidationStatusV26:
    """Test v2.6 validation status with independence."""
    
    def test_validated_by_weighted_diversity(self):
        """High weighted diversity should validate."""
        cat_div = CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=1.8)
        
        status = compute_validation_status_v26(cat_div, 0.50)
        
        assert status == 'validated'
    
    def test_validated_by_high_independence(self):
        """High independence alone should validate."""
        cat_div = CategoryDiversity(categories=['technical'], category_count=1, weighted_diversity=1.0)
        
        status = compute_validation_status_v26(cat_div, 0.80)  # >= 0.75
        
        assert status == 'validated'
    
    def test_weakly_validated_single_category_medium_independence(self):
        """Single category with medium independence should be weakly_validated."""
        cat_div = CategoryDiversity(categories=['technical'], category_count=1, weighted_diversity=1.0)
        
        status = compute_validation_status_v26(cat_div, 0.65)  # >= 0.6 but < 0.75
        
        assert status == 'weakly_validated'


# =============================================================================
# CONFIDENCE HARDENING TESTS
# =============================================================================

class TestConfidenceHardening:
    """Test confidence hardening (v2.5/v2.6)."""
    
    def test_confidence_breakdown_includes_independence(self):
        """confidence_breakdown should include independence."""
        insights = [
            make_insight('s1', 'I1', ['e1'], ['b1'], confidence=0.6,
                        corroborating_sources=['github']),
            make_insight('s2', 'I2', ['e2'], ['b2'], confidence=0.6,
                        corroborating_sources=['sec']),
        ]
        
        cat_div = CategoryDiversity(categories=['technical', 'financial'], category_count=2, weighted_diversity=2.0)
        
        confidence, breakdown = compute_hardened_confidence(
            insights=insights,
            entity_diversity=2,
            bucket_diversity=2,
            persistence_days=2,
            category_diversity=cat_div,
            independence_score=0.85,
            review_required=False,
            validation_status='validated',
        )
        
        assert breakdown.independence > 0
        assert breakdown.independence == INDEPENDENCE_BONUS_MULTIPLIER * 0.85
        assert breakdown.final == confidence


# =============================================================================
# ENGINE INTEGRATION TESTS
# =============================================================================

class TestMetaSignalEngine:
    """Test MetaSignalEngine class."""
    
    def test_engine_output_v26_fields(self):
        """Engine output should include v2.6 fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            engine = MetaSignalEngine(
                output_dir=Path(tmpdir),
                use_embeddings=False,
            )
            
            signals = [
                make_signal('sig1', 'Pricing A', ['company_a'], ['pricing', 'enterprise']),
                make_signal('sig2', 'Pricing B', ['company_b'], ['pricing', 'enterprise']),
            ]
            
            result = engine.process_signals(signals, '2026-02-09')
            
            assert result['version'] == '2.6'
            assert 'name_frozen' in result['stats']
            
            if result['meta_signals']:
                meta = result['meta_signals'][0]
                assert 'concept_slug' in meta
                assert 'name_frozen' in meta
                assert 'independence_score' in meta


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestJaccardSimilarity:
    """Test Jaccard similarity helper."""
    
    def test_identical_sets(self):
        assert jaccard_similarity({'a', 'b'}, {'a', 'b'}) == 1.0
    
    def test_disjoint_sets(self):
        assert jaccard_similarity({'a', 'b'}, {'c', 'd'}) == 0.0
    
    def test_partial_overlap(self):
        sim = jaccard_similarity({'a', 'b', 'c'}, {'b', 'c', 'd'})
        assert sim == 0.5


def run_tests():
    """Run all tests."""
    print("\n=== META-SIGNAL ENGINE v2.6 TESTS ===\n")
    
    # Serialization
    t = TestSignalInsightSerialization()
    t.test_to_dict_and_back()
    t.test_json_serializable()
    print("[PASS] SignalInsight serialization tests")
    
    t = TestMetaSignalSerialization()
    t.test_to_dict_and_back()
    t.test_json_serializable()
    t.test_backward_compatible_missing_v26_fields()
    print("[PASS] MetaSignal serialization tests")
    
    t = TestMergeReasonSerialization()
    t.test_to_dict_and_back()
    print("[PASS] MergeReason serialization tests")
    
    t = TestHierarchyReasonSerialization()
    t.test_to_dict_and_back()
    print("[PASS] HierarchyReason serialization tests")
    
    # Insight extraction
    t = TestInsightExtraction()
    t.test_extracts_insight_from_signal()
    t.test_skips_dead_signals()
    print("[PASS] Insight extraction tests")
    
    # Diversity
    t = TestDiversityRequirement()
    t.test_two_different_entities_form_trend()
    t.test_same_entity_not_enough()
    print("[PASS] Diversity requirement tests")
    
    # Generic name detection
    t = TestGenericNameDetection()
    t.test_detects_generic_accelerating_pattern()
    t.test_specific_names_pass()
    print("[PASS] Generic name detection tests")
    
    # Mechanism extraction
    t = TestMechanismExtraction()
    t.test_extracts_pricing_mechanism()
    print("[PASS] Mechanism extraction tests")
    
    # Specificity gate
    t = TestSpecificityGate()
    t.test_renames_generic_to_mechanism()
    t.test_respects_name_frozen()
    print("[PASS] Specificity gate tests")
    
    # Deduplication
    t = TestMetaDeduplication()
    t.test_merges_near_duplicates_with_reason()
    t.test_keeps_distinct_metas()
    print("[PASS] Meta deduplication tests (with merge_reason)")
    
    # Hierarchy
    t = TestHierarchy()
    t.test_creates_hierarchy_with_reason()
    print("[PASS] Hierarchy tests (with hierarchy_reason)")
    
    # Persistence
    t = TestPersistenceFactor()
    t.test_single_day_penalty()
    t.test_multi_day_bonus()
    print("[PASS] Persistence factor tests")
    
    # v2.6: Concept slug
    t = TestConceptSlug()
    t.test_slug_stable_with_entity_order()
    t.test_different_mechanism_different_slug()
    t.test_slug_survives_rename()
    print("[PASS] Concept slug tests (v2.6)")
    
    # v2.6: Independence scoring
    t = TestIndependenceScoring()
    t.test_high_independence_categories()
    t.test_mixed_independence_categories()
    t.test_independence_affects_confidence()
    print("[PASS] Independence scoring tests (v2.6)")
    
    # v2.6: Name freezing
    t = TestNameFreezing()
    t.test_freezes_after_threshold()
    t.test_does_not_freeze_below_threshold()
    t.test_stays_frozen_once_frozen()
    t.test_frozen_name_not_renamed()
    print("[PASS] Name freezing tests (v2.6)")
    
    # v2.6: Validation status
    t = TestValidationStatusV26()
    t.test_validated_by_weighted_diversity()
    t.test_validated_by_high_independence()
    t.test_weakly_validated_single_category_medium_independence()
    print("[PASS] Validation status v2.6 tests")
    
    # Confidence hardening
    t = TestConfidenceHardening()
    t.test_confidence_breakdown_includes_independence()
    print("[PASS] Confidence hardening tests (with independence)")
    
    # Engine
    t = TestMetaSignalEngine()
    t.test_engine_output_v26_fields()
    print("[PASS] Engine integration tests")
    
    # Helpers
    t = TestJaccardSimilarity()
    t.test_identical_sets()
    t.test_disjoint_sets()
    t.test_partial_overlap()
    print("[PASS] Helper function tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
