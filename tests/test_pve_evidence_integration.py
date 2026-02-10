"""
Integration test for PVE + Evidence Engine.

Tests the full workflow:
1. Create hypothesis bundles
2. Register predictions
3. Simulate observations
4. Evaluate predictions
5. Generate evidence
6. Update beliefs
7. Verify belief evolution

This demonstrates:
- Partial evidence accumulation
- Belief trajectories over time
- Safety cap enforcement
- Correct support/contradict scoring
"""

import sys
import json
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.prediction_verifier import (
    PredictionStore,
    PredictionRecord,
    register_predictions_from_bundle,
    evaluate_prediction_with_evidence,
)
from utils.evidence_engine import (
    EvidenceDirection,
    EvidenceResult,
    EvidenceStore,
    EvidenceGenerator,
)
from utils.belief_updater import (
    BeliefState,
    BeliefStore,
    BeliefUpdater,
)
from utils.calibration_engine import CalibrationEngine


def make_test_bundles():
    """Create test hypothesis bundles simulating enterprise AI adoption."""
    now = datetime.now()
    
    return [
        {
            'meta_id': 'meta_nvidia_enterprise',
            'concept_name': 'Enterprise AI Adoption Accelerating',
            'hypotheses': [
                {
                    'hypothesis_id': 'hyp_enterprise_001',
                    'title': 'Infrastructure Scaling',
                    'mechanism': 'infra_scaling',
                    'confidence': 0.62,
                    'review_required': False,
                    'predicted_next_signals': [
                        {
                            'category': 'technical',
                            'description': 'Job postings increase',
                            'expected_timeframe_days': 7,
                            'direction': 'up',
                            'canonical_metric': 'job_postings_count',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {'primary_entity': 'nvidia'},
                                'expected_direction': 'up',
                                'window_days': 7,
                                'source': 'jobs',
                            },
                        },
                        {
                            'category': 'technical',
                            'description': 'GitHub SDK activity increases',
                            'expected_timeframe_days': 14,
                            'direction': 'up',
                            'canonical_metric': 'repo_activity',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {'primary_entity': 'nvidia'},
                                'expected_direction': 'up',
                                'window_days': 14,
                                'source': 'github',
                            },
                        },
                        {
                            'category': 'financial',
                            'description': 'ARR mentions in filings',
                            'expected_timeframe_days': 30,
                            'direction': 'up',
                            'canonical_metric': 'arr',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {'primary_entity': 'nvidia'},
                                'expected_direction': 'up',
                                'window_days': 30,
                                'source': 'sec',
                            },
                        },
                        {
                            'category': 'media',
                            'description': 'News coverage',
                            'expected_timeframe_days': 7,
                            'direction': 'up',
                            'canonical_metric': 'article_count',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {'primary_entity': 'nvidia'},
                                'expected_direction': 'up',
                                'window_days': 7,
                                'source': 'news',
                            },
                        },
                    ],
                },
            ],
        },
    ]


def simulate_market_observations():
    """
    Simulate market observations over time.
    
    Day 1: Job postings ↑ (support - crosses 15% threshold)
    Day 3: GitHub SDK ↑ (strong support)
    Day 7: ARR ↑ (strong support)
    Day 10: Media ↓ (contradiction)
    
    Expected trajectory: 0.62 → increases → increases → increases → decreases
    """
    return [
        {
            'day': 1,
            'metric': 'job_postings_count',
            'baseline': 100,
            'current': 118,  # +18% (above 15% threshold)
            'expected_direction': 'SUPPORT',
        },
        {
            'day': 3,
            'metric': 'repo_activity',
            'baseline': 50,
            'current': 70,  # +40% (strong support)
            'expected_direction': 'SUPPORT',
        },
        {
            'day': 7,
            'metric': 'arr',
            'baseline': 1000,
            'current': 1350,  # +35% (strong support)
            'expected_direction': 'SUPPORT',
        },
        {
            'day': 10,
            'metric': 'article_count',
            'baseline': 80,
            'current': 62,  # -22.5% (contradiction)
            'expected_direction': 'CONTRADICT',
        },
    ]


def test_full_evidence_workflow():
    """Test the complete evidence-based belief update workflow."""
    print("\n" + "=" * 60)
    print("EVIDENCE ENGINE INTEGRATION TEST")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        predictions_dir = tmpdir / "predictions"
        metrics_dir = tmpdir / "metrics"
        predictions_dir.mkdir()
        metrics_dir.mkdir()
        
        # Step 1: Register predictions
        print("\n[1] Registering predictions...")
        bundles = make_test_bundles()
        prediction_store = PredictionStore(predictions_dir)
        
        records = register_predictions_from_bundle(bundles[0], prediction_store)
        print(f"    Registered {len(records)} predictions")
        assert len(records) == 4
        
        # Step 2: Initialize evidence components
        print("\n[2] Initializing evidence engine...")
        evidence_store = EvidenceStore(predictions_dir)
        belief_updater = BeliefUpdater(predictions_dir)
        evidence_generator = EvidenceGenerator()
        
        # Get hypothesis priors
        hypothesis_priors = {
            'hyp_enterprise_001': {
                'meta_id': 'meta_nvidia_enterprise',
                'prior_confidence': 0.62,
                'review_required': False,
            },
        }
        
        # Step 3: Simulate observations over time
        print("\n[3] Simulating market observations...")
        observations = simulate_market_observations()
        
        belief_trajectory = [0.62]  # Start with prior
        
        for obs in observations:
            print(f"\n    Day {obs['day']}: {obs['metric']}")
            
            # Find matching prediction record
            matching = [r for r in records if r.canonical_metric == obs['metric']]
            if not matching:
                continue
            
            record = matching[0]
            
            # Generate evidence
            evidence = evidence_generator.generate_evidence(
                prediction_id=record.prediction_id,
                hypothesis_id=record.hypothesis_id,
                meta_id=record.meta_id,
                entity=record.entity,
                canonical_metric=record.canonical_metric,
                category=record.category,
                expected_direction=record.expected_direction,
                baseline=obs['baseline'],
                current=obs['current'],
                source=record.observable_query.get('source') if record.observable_query else None,
            )
            
            print(f"      Baseline: {obs['baseline']} → Current: {obs['current']}")
            print(f"      Evidence: {evidence.direction} (score={evidence.evidence_score:.2f}, weight={evidence.weight:.2f})")
            
            # Verify direction
            if obs['expected_direction'] == 'SUPPORT':
                assert evidence.direction == EvidenceDirection.SUPPORT.value, \
                    f"Expected SUPPORT, got {evidence.direction}"
            elif obs['expected_direction'] == 'CONTRADICT':
                assert evidence.direction == EvidenceDirection.CONTRADICT.value, \
                    f"Expected CONTRADICT, got {evidence.direction}"
            
            # Save evidence
            evidence_store.save_evidence(evidence)
            
            # Update belief
            updated_beliefs = belief_updater.process_evidence_batch(
                [evidence],
                hypothesis_priors,
            )
            
            if 'hyp_enterprise_001' in updated_beliefs:
                state = updated_beliefs['hyp_enterprise_001']
                print(f"      Belief: {state.prior_confidence:.2f} → {state.posterior_confidence:.2f}")
                belief_trajectory.append(state.posterior_confidence)
        
        # Step 4: Verify belief trajectory
        print("\n[4] Verifying belief trajectory...")
        print(f"    Trajectory: {' → '.join([f'{p:.2f}' for p in belief_trajectory])}")
        
        # Should generally increase (3 supports > 1 contradict)
        final_belief = belief_trajectory[-1]
        assert final_belief > 0.62, f"Final belief {final_belief} should be > prior 0.62"
        
        # The trajectory should show increases for support and decrease for contradict
        # Day 1: weak support → slight increase
        # Day 3: support → increase
        # Day 7: strong support → increase
        # Day 10: contradiction → decrease
        
        # Step 5: Verify evidence accumulation
        print("\n[5] Verifying evidence accumulation...")
        belief_state = belief_updater.store.get_belief('hyp_enterprise_001')
        
        assert belief_state is not None
        print(f"    Support count: {belief_state.support_count}")
        print(f"    Contradict count: {belief_state.contradict_count}")
        print(f"    Support ratio: {belief_state.support_ratio:.0%}")
        
        assert belief_state.support_count == 3, f"Expected 3 supports, got {belief_state.support_count}"
        assert belief_state.contradict_count == 1, f"Expected 1 contradict, got {belief_state.contradict_count}"
        
        # Step 6: Verify evidence log
        print("\n[6] Verifying evidence log...")
        daily_evidence = evidence_store.load_daily_evidence()
        print(f"    Evidence records: {len(daily_evidence)}")
        assert len(daily_evidence) == 4
        
        # Step 7: Generate summary
        print("\n[7] Final state...")
        summary = belief_updater.get_belief_summary()
        print(f"    Total hypotheses: {summary['total_hypotheses']}")
        print(f"    Average posterior: {summary['average_posterior']:.1%}")
        print(f"    Strengthened: {summary['strengthened_count']}")
        print(f"    Weakened: {summary['weakened_count']}")
        
        assert summary['strengthened_count'] == 1
        
        print("\n" + "=" * 60)
        print("ALL INTEGRATION TESTS PASSED")
        print("=" * 60)
        
        return True


def test_safety_caps_in_workflow():
    """Test that safety caps are enforced in the workflow."""
    print("\n" + "=" * 60)
    print("SAFETY CAPS TEST")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        belief_updater = BeliefUpdater(tmpdir)
        evidence_generator = EvidenceGenerator()
        
        # Create a review_required hypothesis
        hypothesis_priors = {
            'hyp_review_001': {
                'meta_id': 'meta_001',
                'prior_confidence': 0.55,
                'review_required': True,
            },
        }
        
        # Generate very strong evidence
        evidence = [
            evidence_generator.generate_evidence(
                prediction_id='pred_001',
                hypothesis_id='hyp_review_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='filing_mentions',
                category='financial',
                expected_direction='up',
                baseline=100,
                current=200,  # +100% = very strong
                source='sec',
            ),
            evidence_generator.generate_evidence(
                prediction_id='pred_002',
                hypothesis_id='hyp_review_001',
                meta_id='meta_001',
                entity='nvidia',
                canonical_metric='arr',
                category='financial',
                expected_direction='up',
                baseline=1000,
                current=1500,  # +50% = strong
                source='sec',
            ),
        ]
        
        print(f"\n    Prior: 0.55")
        print(f"    Evidence scores: {[e.evidence_score for e in evidence]}")
        
        updated = belief_updater.process_evidence_batch(evidence, hypothesis_priors)
        
        state = updated['hyp_review_001']
        print(f"    Posterior: {state.posterior_confidence:.2f}")
        print(f"    Safety cap: 0.60 (review_required)")
        
        assert state.posterior_confidence <= 0.60, \
            f"Posterior {state.posterior_confidence} exceeds review_required cap of 0.60"
        
        print("\n    SAFETY CAP ENFORCED [OK]")
        
        print("\n" + "=" * 60)
        print("SAFETY CAPS TEST PASSED")
        print("=" * 60)


def test_evidence_weights_matter():
    """Test that high-weight evidence influences beliefs more."""
    print("\n" + "=" * 60)
    print("EVIDENCE WEIGHTS TEST")
    print("=" * 60)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        
        evidence_generator = EvidenceGenerator()
        
        # SEC filing (high weight)
        sec_evidence = evidence_generator.generate_evidence(
            prediction_id='pred_sec',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            baseline=100,
            current=120,  # +20%
            source='sec',
        )
        
        # Social mentions (low weight)
        social_evidence = evidence_generator.generate_evidence(
            prediction_id='pred_social',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='social_mentions',
            category='social',
            expected_direction='up',
            baseline=100,
            current=120,  # Same +20%
            source='reddit',
        )
        
        print(f"\n    SEC evidence weight: {sec_evidence.weight:.2f}")
        print(f"    Social evidence weight: {social_evidence.weight:.2f}")
        
        assert sec_evidence.weight > social_evidence.weight, \
            "SEC evidence should have higher weight than social"
        
        print(f"\n    SEC weighted score: {sec_evidence.weighted_score:.3f}")
        print(f"    Social weighted score: {social_evidence.weighted_score:.3f}")
        
        assert sec_evidence.weighted_score > social_evidence.weighted_score, \
            "SEC weighted score should be higher"
        
        print("\n    HIGH-WEIGHT EVIDENCE MATTERS MORE [OK]")
        
        print("\n" + "=" * 60)
        print("EVIDENCE WEIGHTS TEST PASSED")
        print("=" * 60)


def run_all_tests():
    """Run all integration tests."""
    test_full_evidence_workflow()
    test_safety_caps_in_workflow()
    test_evidence_weights_matter()
    
    print("\n" + "=" * 60)
    print("ALL EVIDENCE ENGINE INTEGRATION TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
