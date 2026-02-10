"""
Integration test for Prediction Verification Engine.

Tests the full workflow:
1. Create sample hypothesis bundle
2. Register predictions
3. Simulate observation
4. Evaluate predictions
5. Generate calibration report
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
    evaluate_prediction,
)
from utils.prediction_integration import (
    register_predictions,
    get_prediction_status_for_hypothesis,
)
from utils.calibration_engine import (
    CalibrationEngine,
    format_calibration_report,
)


def make_test_bundles():
    """Create test hypothesis bundles."""
    now = datetime.now()
    
    return [
        {
            'meta_id': 'meta_nvidia_001',
            'concept_name': 'NVIDIA Chip Demand',
            'hypotheses': [
                {
                    'hypothesis_id': 'hyp_001',
                    'title': 'Infrastructure Scaling',
                    'mechanism': 'infra_scaling',
                    'confidence': 0.85,
                    'predicted_next_signals': [
                        {
                            'category': 'financial',
                            'description': 'CapEx mentions increase',
                            'expected_timeframe_days': 14,
                            'metric': 'filing_mentions',
                            'direction': 'up',
                            'canonical_metric': 'filing_mentions',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {
                                    'primary_entity': 'nvidia',
                                },
                                'expected_direction': 'up',
                                'window_days': 14,
                            },
                        },
                        {
                            'category': 'media',
                            'description': 'News coverage increases',
                            'expected_timeframe_days': 7,
                            'metric': 'article_count',
                            'direction': 'up',
                            'canonical_metric': 'article_count',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {
                                    'primary_entity': 'nvidia',
                                },
                                'expected_direction': 'up',
                                'window_days': 7,
                            },
                        },
                    ],
                },
            ],
        },
        {
            'meta_id': 'meta_openai_001',
            'concept_name': 'OpenAI Pricing Strategy',
            'hypotheses': [
                {
                    'hypothesis_id': 'hyp_002',
                    'title': 'Enterprise Adoption',
                    'mechanism': 'enterprise_adoption',
                    'confidence': 0.65,
                    'predicted_next_signals': [
                        {
                            'category': 'technical',
                            'description': 'SDK downloads increase',
                            'expected_timeframe_days': 30,
                            'metric': 'repo_activity',
                            'direction': 'up',
                            'canonical_metric': 'repo_activity',
                            'measurable': True,
                            'observable_query': {
                                'query_terms': {
                                    'primary_entity': 'openai',
                                },
                                'expected_direction': 'up',
                                'window_days': 30,
                            },
                        },
                    ],
                },
            ],
        },
    ]


def test_full_workflow():
    """Test the complete PVE workflow."""
    print("\n" + "=" * 60)
    print("PVE INTEGRATION TEST")
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
        count = register_predictions(bundles, tmpdir)
        print(f"    Registered {count} predictions")
        assert count == 3, f"Expected 3 predictions, got {count}"
        
        # Step 2: Load and verify records
        print("\n[2] Verifying stored records...")
        store = PredictionStore(predictions_dir)
        records = store.load_all_records()
        print(f"    Found {len(records)} records")
        assert len(records) == 3
        
        # Step 3: Check hypothesis status
        print("\n[3] Checking hypothesis status...")
        status = get_prediction_status_for_hypothesis('hyp_001', tmpdir)
        print(f"    hyp_001: {status['predictions_count']} predictions, status={status['status']}")
        assert status['predictions_count'] == 2
        assert status['status'] == 'pending'
        
        # Step 4: Simulate evaluation
        print("\n[4] Simulating prediction evaluation...")
        
        # Evaluate with simulated observations
        evaluated_records = []
        for record in records:
            if record.entity == 'nvidia':
                # Simulate increase (verified true)
                evaluated = evaluate_prediction(record, 100, 125)
            else:
                # Simulate decrease (verified false for up direction)
                evaluated = evaluate_prediction(record, 100, 80)
            
            store.update_record(evaluated)
            evaluated_records.append(evaluated)
            print(f"    {record.prediction_id}: {evaluated.verdict} ({evaluated.percent_change:.1%} change)")
        
        # Step 5: Generate calibration report
        print("\n[5] Generating calibration report...")
        calibration = CalibrationEngine(metrics_dir)
        
        record_dicts = [r.to_dict() for r in store.load_all_records()]
        report = calibration.compute_report(record_dicts)
        
        print(f"    Total evaluated: {report.evaluated_predictions}")
        print(f"    Verified True: {report.verified_true}")
        print(f"    Verified False: {report.verified_false}")
        print(f"    Accuracy: {report.accuracy:.1%}")
        
        # Save report
        report_path = calibration.save_report(report)
        print(f"    Report saved to: {report_path}")
        
        # Verify report
        assert report.evaluated_predictions == 3
        assert report.verified_true == 2  # Both nvidia predictions
        assert report.verified_false == 1  # openai prediction
        assert abs(report.accuracy - 2/3) < 0.01  # Use approximate comparison
        
        # Step 6: Print full report
        print("\n[6] Full calibration report:")
        print(format_calibration_report(report))
        
        print("\n" + "=" * 60)
        print("ALL INTEGRATION TESTS PASSED")
        print("=" * 60)


if __name__ == "__main__":
    test_full_workflow()
