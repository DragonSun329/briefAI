"""
Tests for Belief Updater.

Test Coverage:
1. BeliefState dataclass
2. Belief update calculation
3. Safety caps enforcement
4. Belief store operations
5. Batch processing
6. Confidence trajectory
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.belief_updater import (
    BeliefState,
    BeliefStore,
    BeliefUpdater,
)
from utils.evidence_engine import (
    EvidenceResult,
    EvidenceDirection,
    EvidenceWeights,
)


# =============================================================================
# TEST: BELIEF STATE
# =============================================================================

class TestBeliefState:
    """Test BeliefState dataclass."""
    
    def test_creation(self):
        """Should create belief state with defaults."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.65,
            posterior_confidence=0.65,
        )
        
        assert state.confidence_change == 0.0
        assert state.evidence_count == 0
        assert state.support_ratio is None
    
    def test_confidence_change(self):
        """Should calculate confidence change."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.75,
        )
        
        assert abs(state.confidence_change - 0.15) < 0.001
    
    def test_evidence_count(self):
        """Should count all evidence types."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
            support_count=3,
            contradict_count=1,
            neutral_count=2,
        )
        
        assert state.evidence_count == 6
    
    def test_support_ratio(self):
        """Should calculate support ratio."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
            support_count=3,
            contradict_count=1,
        )
        
        assert state.support_ratio == 0.75
    
    def test_support_ratio_no_informative(self):
        """Support ratio None when no informative evidence."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
            neutral_count=5,
        )
        
        assert state.support_ratio is None
    
    def test_history_snapshot(self):
        """Should add history snapshot."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.72,
            support_count=2,
        )
        
        state.add_history_snapshot()
        
        assert len(state.history) == 1
        assert state.history[0]['posterior'] == 0.72
        assert state.history[0]['support_count'] == 2
    
    def test_trajectory(self):
        """Should return confidence trajectory."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.72,
            history=[
                {'date': '2026-02-08', 'posterior': 0.62},
                {'date': '2026-02-09', 'posterior': 0.68},
                {'date': '2026-02-10', 'posterior': 0.72},
            ],
        )
        
        trajectory = state.get_trajectory()
        assert trajectory == [0.62, 0.68, 0.72]
    
    def test_serialization(self):
        """Should serialize and deserialize."""
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.72,
            support_count=3,
        )
        
        d = state.to_dict()
        restored = BeliefState.from_dict(d)
        
        assert restored.hypothesis_id == state.hypothesis_id
        assert restored.posterior_confidence == state.posterior_confidence


# =============================================================================
# TEST: BELIEF UPDATE
# =============================================================================

class TestBeliefUpdate:
    """Test belief update calculation."""
    
    def test_support_increases_belief(self):
        """Supporting evidence should increase posterior."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
        )
        
        evidence = [
            EvidenceResult(
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
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        assert updated.posterior_confidence > updated.prior_confidence
        assert updated.support_count == 1
        assert updated.contradict_count == 0
    
    def test_contradict_decreases_belief(self):
        """Contradicting evidence should decrease posterior."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
        )
        
        evidence = [
            EvidenceResult(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                direction=EvidenceDirection.CONTRADICT.value,
                evidence_score=-0.8,
                effect_size=0.25,
                weight=0.9,
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        assert updated.posterior_confidence < updated.prior_confidence
        assert updated.contradict_count == 1
    
    def test_neutral_no_change(self):
        """Neutral evidence should not change posterior significantly."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
        )
        
        evidence = [
            EvidenceResult(
                prediction_id='pred_001',
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
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        # Posterior unchanged (no informative evidence)
        assert updated.posterior_confidence == updated.prior_confidence
        assert updated.neutral_count == 1
    
    def test_mixed_evidence(self):
        """Mixed evidence should partially update."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.60,
            posterior_confidence=0.60,
        )
        
        # 2 support, 1 contradict
        evidence = [
            EvidenceResult(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                direction=EvidenceDirection.SUPPORT.value,
                evidence_score=0.5,
                effect_size=0.2,
                weight=0.9,
            ),
            EvidenceResult(
                prediction_id='pred_002',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='article_count',
                category='media',
                expected_direction='up',
                direction=EvidenceDirection.SUPPORT.value,
                evidence_score=0.3,
                effect_size=0.15,
                weight=0.5,
            ),
            EvidenceResult(
                prediction_id='pred_003',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='repo_activity',
                category='technical',
                expected_direction='up',
                direction=EvidenceDirection.CONTRADICT.value,
                evidence_score=-0.4,
                effect_size=0.2,
                weight=0.7,
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        # Should slightly increase (2 support > 1 contradict weighted)
        assert updated.posterior_confidence > updated.prior_confidence
        assert updated.support_count == 2
        assert updated.contradict_count == 1


# =============================================================================
# TEST: SAFETY CAPS
# =============================================================================

class TestSafetyCaps:
    """Test safety caps enforcement."""
    
    def test_review_required_cap(self):
        """Review required should cap at 0.60."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.55,
            posterior_confidence=0.55,
            review_required=True,
        )
        
        # Very strong evidence
        evidence = [
            EvidenceResult(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                direction=EvidenceDirection.SUPPORT.value,
                evidence_score=1.0,
                effect_size=0.5,
                weight=1.0,
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        assert updated.posterior_confidence <= 0.60
    
    def test_weakly_validated_cap(self):
        """Weakly validated should cap at 0.75."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.70,
            posterior_confidence=0.70,
            weakly_validated=True,
        )
        
        evidence = [
            EvidenceResult(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                direction=EvidenceDirection.SUPPORT.value,
                evidence_score=1.0,
                effect_size=0.5,
                weight=1.0,
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        assert updated.posterior_confidence <= 0.75
    
    def test_min_confidence_floor(self):
        """Posterior should not go below minimum."""
        updater = BeliefUpdater()
        
        state = BeliefState(
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            prior_confidence=0.10,
            posterior_confidence=0.10,
        )
        
        # Strong contradiction
        evidence = [
            EvidenceResult(
                prediction_id='pred_001',
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                direction=EvidenceDirection.CONTRADICT.value,
                evidence_score=-1.0,
                effect_size=0.5,
                weight=1.0,
            ),
        ]
        
        updated = updater.update_belief(state, evidence)
        
        assert updated.posterior_confidence >= 0.05


# =============================================================================
# TEST: BELIEF STORE
# =============================================================================

class TestBeliefStore:
    """Test belief store operations."""
    
    def test_save_and_load(self):
        """Should save and load beliefs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BeliefStore(Path(tmpdir))
            
            state = BeliefState(
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                prior_confidence=0.60,
                posterior_confidence=0.72,
            )
            
            store.update_belief(state)
            
            loaded = store.get_belief('hyp_001')
            assert loaded is not None
            assert loaded.posterior_confidence == 0.72
    
    def test_load_all(self):
        """Should load all beliefs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BeliefStore(Path(tmpdir))
            
            for i in range(3):
                state = BeliefState(
                    hypothesis_id=f'hyp_{i}',
                    meta_id='meta_001',
                    prior_confidence=0.60 + i * 0.05,
                    posterior_confidence=0.60 + i * 0.05,
                )
                store.update_belief(state)
            
            all_beliefs = store.load_beliefs()
            assert len(all_beliefs) == 3
    
    def test_history_append(self):
        """Should append to history log."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = BeliefStore(Path(tmpdir))
            
            state = BeliefState(
                hypothesis_id='hyp_001',
                meta_id='meta_001',
                prior_confidence=0.60,
                posterior_confidence=0.72,
            )
            
            store.append_history(state)
            store.append_history(state)
            
            history = store.load_history('hyp_001')
            assert len(history) == 2


# =============================================================================
# TEST: BATCH PROCESSING
# =============================================================================

class TestBatchProcessing:
    """Test batch evidence processing."""
    
    def test_process_batch(self):
        """Should process batch of evidence and update beliefs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            updater = BeliefUpdater(Path(tmpdir))
            
            evidence = [
                EvidenceResult(
                    prediction_id='pred_001',
                    hypothesis_id='hyp_001',
                    meta_id='meta_001',
                    entity='nvidia',
                    canonical_metric='filing_mentions',
                    category='financial',
                    expected_direction='up',
                    direction=EvidenceDirection.SUPPORT.value,
                    evidence_score=0.7,
                    effect_size=0.25,
                    weight=0.9,
                ),
                EvidenceResult(
                    prediction_id='pred_002',
                    hypothesis_id='hyp_002',
                    meta_id='meta_002',
                    entity='openai',
                    canonical_metric='article_count',
                    category='media',
                    expected_direction='up',
                    direction=EvidenceDirection.CONTRADICT.value,
                    evidence_score=-0.5,
                    effect_size=0.2,
                    weight=0.5,
                ),
            ]
            
            hypothesis_priors = {
                'hyp_001': {'prior_confidence': 0.65, 'meta_id': 'meta_001'},
                'hyp_002': {'prior_confidence': 0.55, 'meta_id': 'meta_002'},
            }
            
            updated = updater.process_evidence_batch(evidence, hypothesis_priors)
            
            assert len(updated) == 2
            assert 'hyp_001' in updated
            assert 'hyp_002' in updated
            
            # hyp_001 should have increased
            assert updated['hyp_001'].posterior_confidence > 0.65
            
            # hyp_002 should have decreased
            assert updated['hyp_002'].posterior_confidence < 0.55


# =============================================================================
# RUN TESTS
# =============================================================================

def run_tests():
    """Run all belief updater tests."""
    print("\n=== BELIEF UPDATER TESTS ===\n")
    
    # BeliefState tests
    t = TestBeliefState()
    t.test_creation()
    t.test_confidence_change()
    t.test_evidence_count()
    t.test_support_ratio()
    t.test_support_ratio_no_informative()
    t.test_history_snapshot()
    t.test_trajectory()
    t.test_serialization()
    print("[PASS] BeliefState tests")
    
    # Update tests
    t = TestBeliefUpdate()
    t.test_support_increases_belief()
    t.test_contradict_decreases_belief()
    t.test_neutral_no_change()
    t.test_mixed_evidence()
    print("[PASS] Belief update tests")
    
    # Safety cap tests
    t = TestSafetyCaps()
    t.test_review_required_cap()
    t.test_weakly_validated_cap()
    t.test_min_confidence_floor()
    print("[PASS] Safety cap tests")
    
    # Store tests
    t = TestBeliefStore()
    t.test_save_and_load()
    t.test_load_all()
    t.test_history_append()
    print("[PASS] Belief store tests")
    
    # Batch tests
    t = TestBatchProcessing()
    t.test_process_batch()
    print("[PASS] Batch processing tests")
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
