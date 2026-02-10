"""
Tests for Evidence Engine.

Test Coverage:
1. Evidence direction calculation
2. Evidence score calculation
3. Effect size calculation
4. Evidence generation
5. Evidence weighting
6. Evidence store operations
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.evidence_engine import (
    EvidenceDirection,
    EvidenceResult,
    EvidenceWeights,
    EvidenceGenerator,
    EvidenceStore,
    calculate_evidence_direction,
    calculate_evidence_score,
    calculate_effect_size,
)


# =============================================================================
# TEST: EVIDENCE DIRECTION
# =============================================================================

class TestEvidenceDirection:
    """Test evidence direction calculation."""
    
    def test_up_support(self):
        """Up direction with significant increase = SUPPORT."""
        assert calculate_evidence_direction('up', 0.20) == EvidenceDirection.SUPPORT
        assert calculate_evidence_direction('up', 0.15) == EvidenceDirection.SUPPORT
        assert calculate_evidence_direction('up', 0.50) == EvidenceDirection.SUPPORT
    
    def test_up_contradict(self):
        """Up direction with significant decrease = CONTRADICT."""
        assert calculate_evidence_direction('up', -0.20) == EvidenceDirection.CONTRADICT
        assert calculate_evidence_direction('up', -0.15) == EvidenceDirection.CONTRADICT
    
    def test_up_neutral(self):
        """Up direction with small change = NEUTRAL."""
        assert calculate_evidence_direction('up', 0.10) == EvidenceDirection.NEUTRAL
        assert calculate_evidence_direction('up', -0.10) == EvidenceDirection.NEUTRAL
        assert calculate_evidence_direction('up', 0.05) == EvidenceDirection.NEUTRAL
    
    def test_down_support(self):
        """Down direction with significant decrease = SUPPORT."""
        assert calculate_evidence_direction('down', -0.20) == EvidenceDirection.SUPPORT
        assert calculate_evidence_direction('down', -0.50) == EvidenceDirection.SUPPORT
    
    def test_down_contradict(self):
        """Down direction with significant increase = CONTRADICT."""
        assert calculate_evidence_direction('down', 0.20) == EvidenceDirection.CONTRADICT
    
    def test_flat_support(self):
        """Flat direction with small change = SUPPORT."""
        assert calculate_evidence_direction('flat', 0.05) == EvidenceDirection.SUPPORT
        assert calculate_evidence_direction('flat', -0.10) == EvidenceDirection.SUPPORT
    
    def test_flat_contradict(self):
        """Flat direction with large change = CONTRADICT."""
        assert calculate_evidence_direction('flat', 0.25) == EvidenceDirection.CONTRADICT
        assert calculate_evidence_direction('flat', -0.30) == EvidenceDirection.CONTRADICT
    
    def test_data_missing(self):
        """None percent change = DATA_MISSING."""
        assert calculate_evidence_direction('up', None) == EvidenceDirection.DATA_MISSING
        assert calculate_evidence_direction('down', None) == EvidenceDirection.DATA_MISSING


# =============================================================================
# TEST: EVIDENCE SCORE
# =============================================================================

class TestEvidenceScore:
    """Test evidence score calculation."""
    
    def test_support_score(self):
        """Support produces positive scores."""
        score = calculate_evidence_score(EvidenceDirection.SUPPORT, 0.15)
        assert score == 0.5  # 15% / 30% = 0.5
        
        score = calculate_evidence_score(EvidenceDirection.SUPPORT, 0.30)
        assert score == 1.0  # saturated
        
        score = calculate_evidence_score(EvidenceDirection.SUPPORT, 0.45)
        assert score == 1.0  # still saturated
    
    def test_contradict_score(self):
        """Contradict produces negative scores."""
        score = calculate_evidence_score(EvidenceDirection.CONTRADICT, 0.15)
        assert score == -0.5
        
        score = calculate_evidence_score(EvidenceDirection.CONTRADICT, 0.30)
        assert score == -1.0
    
    def test_neutral_score(self):
        """Neutral produces zero score."""
        score = calculate_evidence_score(EvidenceDirection.NEUTRAL, 0.10)
        assert score == 0.0
    
    def test_data_missing_score(self):
        """Data missing produces zero score."""
        score = calculate_evidence_score(EvidenceDirection.DATA_MISSING, 0.0)
        assert score == 0.0


# =============================================================================
# TEST: EFFECT SIZE
# =============================================================================

class TestEffectSize:
    """Test effect size calculation."""
    
    def test_positive_change(self):
        """Positive change produces positive effect size."""
        effect = calculate_effect_size(100, 125)
        assert effect == 0.25
    
    def test_negative_change(self):
        """Negative change produces positive effect size (absolute)."""
        effect = calculate_effect_size(100, 75)
        assert effect == 0.25
    
    def test_no_change(self):
        """No change produces zero effect size."""
        effect = calculate_effect_size(100, 100)
        assert effect == 0.0
    
    def test_zero_baseline(self):
        """Zero baseline with non-zero current = max effect."""
        effect = calculate_effect_size(0, 10)
        assert effect == 1.0
    
    def test_both_zero(self):
        """Both zero = no effect."""
        effect = calculate_effect_size(0, 0)
        assert effect == 0.0
    
    def test_missing_data(self):
        """Missing data = zero effect."""
        effect = calculate_effect_size(None, 100)
        assert effect == 0.0


# =============================================================================
# TEST: EVIDENCE WEIGHTS
# =============================================================================

class TestEvidenceWeights:
    """Test evidence weights loading and retrieval."""
    
    def test_load_weights(self):
        """Should load weights from config file."""
        weights = EvidenceWeights()
        
        # SEC filings should be high weight
        sec_weight = weights.get_metric_weight('filing_mentions')
        assert sec_weight >= 0.9
        
        # Social should be low weight
        social_weight = weights.get_metric_weight('social_mentions')
        assert social_weight <= 0.3
    
    def test_source_reliability(self):
        """Should return source reliability multipliers."""
        weights = EvidenceWeights()
        
        sec_reliability = weights.get_source_reliability('sec')
        assert sec_reliability >= 0.95
        
        reddit_reliability = weights.get_source_reliability('reddit')
        assert reddit_reliability <= 0.35
    
    def test_combined_weight(self):
        """Combined weight = metric × source."""
        weights = EvidenceWeights()
        
        combined = weights.get_combined_weight('filing_mentions', 'sec')
        # Should be high (both high)
        assert combined >= 0.9
        
        combined = weights.get_combined_weight('social_mentions', 'reddit')
        # Should be low (both low)
        assert combined <= 0.15
    
    def test_default_weight(self):
        """Unknown metrics get default weight."""
        weights = EvidenceWeights()
        
        weight = weights.get_metric_weight('unknown_metric_xyz')
        assert weight == 0.50  # Default


# =============================================================================
# TEST: EVIDENCE GENERATOR
# =============================================================================

class TestEvidenceGenerator:
    """Test evidence generation."""
    
    def test_generate_support(self):
        """Should generate support evidence for expected increase."""
        gen = EvidenceGenerator()
        
        evidence = gen.generate_evidence(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            baseline=100,
            current=125,
            source='sec',
        )
        
        assert evidence.direction == EvidenceDirection.SUPPORT.value
        assert evidence.evidence_score > 0
        assert evidence.percent_change == 0.25
        assert evidence.weight > 0.8
        assert 'supports_hypothesis' in evidence.notes
    
    def test_generate_contradict(self):
        """Should generate contradiction evidence for unexpected change."""
        gen = EvidenceGenerator()
        
        evidence = gen.generate_evidence(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            baseline=100,
            current=75,
            source='sec',
        )
        
        assert evidence.direction == EvidenceDirection.CONTRADICT.value
        assert evidence.evidence_score < 0
        assert 'contradicts_hypothesis' in evidence.notes
    
    def test_generate_neutral(self):
        """Should generate neutral evidence for small change."""
        gen = EvidenceGenerator()
        
        evidence = gen.generate_evidence(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='article_count',
            category='media',
            expected_direction='up',
            baseline=100,
            current=108,
        )
        
        assert evidence.direction == EvidenceDirection.NEUTRAL.value
        assert evidence.evidence_score == 0.0
        assert 'within_noise_band' in evidence.notes
    
    def test_generate_data_missing(self):
        """Should handle missing data."""
        gen = EvidenceGenerator()
        
        evidence = gen.generate_evidence(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            baseline=None,
            current=None,
        )
        
        assert evidence.direction == EvidenceDirection.DATA_MISSING.value
        assert evidence.weight == 0.0
        assert 'data_missing' in evidence.notes


# =============================================================================
# TEST: EVIDENCE STORE
# =============================================================================

class TestEvidenceStore:
    """Test evidence store operations."""
    
    def test_save_and_load(self):
        """Should save and load evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(Path(tmpdir))
            
            evidence = EvidenceResult(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                direction=EvidenceDirection.SUPPORT.value,
                evidence_score=0.8,
                effect_size=0.25,
                weight=0.9,
            )
            
            store.save_evidence(evidence)
            
            loaded = store.load_daily_evidence()
            assert len(loaded) == 1
            assert loaded[0].prediction_id == 'pred_001'
    
    def test_batch_save(self):
        """Should save batch of evidence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(Path(tmpdir))
            
            results = [
                EvidenceResult(
                    prediction_id=f'pred_{i}',
                    hypothesis_id='hyp_001',
                    meta_id='meta_001',
                    entity='nvidia',
                    canonical_metric='filing_mentions',
                    category='financial',
                    expected_direction='up',
                    direction=EvidenceDirection.SUPPORT.value,
                    evidence_score=0.5,
                    effect_size=0.2,
                    weight=0.8,
                )
                for i in range(5)
            ]
            
            store.save_evidence_batch(results)
            
            loaded = store.load_daily_evidence()
            assert len(loaded) == 5


# =============================================================================
# TEST: EVIDENCE RESULT
# =============================================================================

class TestEvidenceResult:
    """Test EvidenceResult dataclass."""
    
    def test_weighted_score(self):
        """Weighted score = evidence_score × weight."""
        evidence = EvidenceResult(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            direction=EvidenceDirection.SUPPORT.value,
            evidence_score=0.8,
            effect_size=0.25,
            weight=0.9,
        )
        
        assert evidence.weighted_score == 0.8 * 0.9
    
    def test_is_informative(self):
        """Support and contradict are informative."""
        support = EvidenceResult(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            direction=EvidenceDirection.SUPPORT.value,
            evidence_score=0.8,
            effect_size=0.25,
            weight=0.9,
        )
        
        assert support.is_informative == True
        
        neutral = EvidenceResult(
            prediction_id='pred_002',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            direction=EvidenceDirection.NEUTRAL.value,
            evidence_score=0.0,
            effect_size=0.05,
            weight=0.9,
        )
        
        assert neutral.is_informative == False
    
    def test_serialization(self):
        """Should serialize and deserialize."""
        evidence = EvidenceResult(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            direction=EvidenceDirection.SUPPORT.value,
            evidence_score=0.8,
            effect_size=0.25,
            weight=0.9,
        )
        
        jsonl = evidence.to_jsonl()
        restored = EvidenceResult.from_jsonl(jsonl)
        
        assert restored.prediction_id == evidence.prediction_id
        assert restored.evidence_score == evidence.evidence_score


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all evidence engine tests."""
    print("\n=== EVIDENCE ENGINE TESTS ===\n")
    
    # Direction tests
    t = TestEvidenceDirection()
    t.test_up_support()
    t.test_up_contradict()
    t.test_up_neutral()
    t.test_down_support()
    t.test_down_contradict()
    t.test_flat_support()
    t.test_flat_contradict()
    t.test_data_missing()
    print("[PASS] Evidence direction tests")
    
    # Score tests
    t = TestEvidenceScore()
    t.test_support_score()
    t.test_contradict_score()
    t.test_neutral_score()
    t.test_data_missing_score()
    print("[PASS] Evidence score tests")
    
    # Effect size tests
    t = TestEffectSize()
    t.test_positive_change()
    t.test_negative_change()
    t.test_no_change()
    t.test_zero_baseline()
    t.test_both_zero()
    t.test_missing_data()
    print("[PASS] Effect size tests")
    
    # Weight tests
    t = TestEvidenceWeights()
    t.test_load_weights()
    t.test_source_reliability()
    t.test_combined_weight()
    t.test_default_weight()
    print("[PASS] Evidence weight tests")
    
    # Generator tests
    t = TestEvidenceGenerator()
    t.test_generate_support()
    t.test_generate_contradict()
    t.test_generate_neutral()
    t.test_generate_data_missing()
    print("[PASS] Evidence generator tests")
    
    # Store tests
    t = TestEvidenceStore()
    t.test_save_and_load()
    t.test_batch_save()
    print("[PASS] Evidence store tests")
    
    # Result tests
    t = TestEvidenceResult()
    t.test_weighted_score()
    t.test_is_informative()
    t.test_serialization()
    print("[PASS] Evidence result tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
