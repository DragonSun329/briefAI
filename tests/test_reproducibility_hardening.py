"""
Tests for Reproducibility Hardening v1.1

Tests the research-grade integrity features:
- Engine freeze (exact commit requirement)
- Hash chain tamper detection
- Experiment path enforcement
- Environment fingerprint in metadata

Run with: pytest tests/test_reproducibility_hardening.py -v
"""

import json
import hashlib
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_ledger_dir():
    """Create a temporary ledger directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_prediction():
    """Sample prediction for testing."""
    return {
        'prediction_id': 'test_pred_001',
        'experiment_id': 'test_experiment',
        'engine_version': 'TEST_v1.0',
        'commit_hash': 'abc123',
        'generation_timestamp': datetime.utcnow().isoformat() + 'Z',
        'entity': 'test_company',
        'expected_direction': 'up',
        'confidence': 0.75,
    }


# =============================================================================
# TEST: ENGINE FREEZE (EXACT COMMIT)
# =============================================================================

class TestEngineFreeze:
    """Tests for exact engine commit requirement."""
    
    def test_is_exact_engine_commit_at_tag(self):
        """Test that exact match returns True."""
        from utils.run_lock import is_exact_engine_commit
        
        # Mock git commands to simulate exact match
        with patch('utils.run_lock._run_git_command') as mock_git:
            mock_git.side_effect = [
                (True, ''),  # tag exists
                (True, 'abc123def456'),  # tag commit
                (True, 'abc123def456'),  # HEAD commit (same)
            ]
            
            is_exact, tag_commit, msg = is_exact_engine_commit('ENGINE_v2.1_DAY0')
            
            assert is_exact is True
            assert tag_commit == 'abc123def456'
            assert 'exactly at' in msg.lower()
    
    def test_is_exact_engine_commit_ahead_of_tag(self):
        """Test that descendant commit returns False with helpful message."""
        from utils.run_lock import is_exact_engine_commit
        
        with patch('utils.run_lock._run_git_command') as mock_git:
            mock_git.side_effect = [
                (True, ''),  # tag exists
                (True, 'abc123'),  # tag commit
                (True, 'def456'),  # HEAD commit (different)
                (True, ''),  # merge-base --is-ancestor succeeds
                (True, '3'),  # 3 commits ahead
            ]
            
            is_exact, tag_commit, msg = is_exact_engine_commit('ENGINE_v2.1_DAY0')
            
            assert is_exact is False
            assert 'ahead' in msg.lower()
            assert 'checkout' in msg.lower()
    
    def test_verify_run_integrity_requires_exact_commit(self):
        """Test that verify_run_integrity fails on descendant commits."""
        from utils.run_lock import verify_run_integrity, LockFailureReason
        
        # Mock experiment manager and git
        mock_experiment = MagicMock()
        mock_experiment.experiment_id = 'test_exp'
        mock_experiment.engine_tag = 'ENGINE_v2.1_DAY0'
        mock_experiment.status = 'active'
        
        with patch('utils.run_lock.get_current_commit', return_value='def456789'):
            with patch('utils.run_lock.get_current_commit_short', return_value='def4567'):
                with patch('utils.experiment_manager.get_active_experiment', return_value=mock_experiment):
                    with patch('utils.run_lock.is_exact_engine_commit') as mock_exact:
                        mock_exact.return_value = (False, 'abc123', 'HEAD is 3 commits ahead')
                        with patch('utils.run_lock.get_dirty_files', return_value=[]):
                            
                            report = verify_run_integrity(
                                require_clean_tree=True,
                                require_exact_commit=True,
                            )
                            
                            assert report.valid is False
                            assert report.failure_reason == LockFailureReason.ENGINE_TAG_MISMATCH


# =============================================================================
# TEST: HASH CHAIN
# =============================================================================

class TestHashChain:
    """Tests for ledger hash chain tamper detection."""
    
    def test_compute_entry_hash_deterministic(self, sample_prediction):
        """Test that hash computation is deterministic."""
        from utils.public_forecast_logger import compute_entry_hash
        
        prev_hash = 'genesis'
        
        hash1 = compute_entry_hash(sample_prediction, prev_hash)
        hash2 = compute_entry_hash(sample_prediction, prev_hash)
        
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex
    
    def test_hash_changes_with_content(self, sample_prediction):
        """Test that hash changes when content changes."""
        from utils.public_forecast_logger import compute_entry_hash
        
        prev_hash = 'genesis'
        
        hash_original = compute_entry_hash(sample_prediction, prev_hash)
        
        # Modify prediction
        modified = sample_prediction.copy()
        modified['confidence'] = 0.80
        
        hash_modified = compute_entry_hash(modified, prev_hash)
        
        assert hash_original != hash_modified
    
    def test_hash_chain_verifies_valid_ledger(self, temp_ledger_dir):
        """Test that a valid ledger passes verification."""
        from utils.public_forecast_logger import (
            verify_hash_chain,
            compute_entry_hash,
            GENESIS_HASH,
        )
        
        history_path = temp_ledger_dir / 'forecast_history.jsonl'
        
        # Write valid chain
        entries = []
        prev_hash = GENESIS_HASH
        
        for i in range(5):
            entry = {
                'prediction_id': f'pred_{i}',
                'experiment_id': 'test',
                'value': i,
            }
            entry_hash = compute_entry_hash(entry, prev_hash)
            entry['prev_hash'] = prev_hash
            entry['entry_hash'] = entry_hash
            entries.append(entry)
            prev_hash = entry_hash
        
        with open(history_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        
        is_valid, count, error = verify_hash_chain(history_path)
        
        assert is_valid is True
        assert count == 5
        assert error is None
    
    def test_hash_chain_detects_tamper(self, temp_ledger_dir):
        """Test that modified entries break the chain."""
        from utils.public_forecast_logger import (
            verify_hash_chain,
            compute_entry_hash,
            GENESIS_HASH,
        )
        
        history_path = temp_ledger_dir / 'forecast_history.jsonl'
        
        # Write valid chain
        entries = []
        prev_hash = GENESIS_HASH
        
        for i in range(5):
            entry = {
                'prediction_id': f'pred_{i}',
                'experiment_id': 'test',
                'value': i,
            }
            entry_hash = compute_entry_hash(entry, prev_hash)
            entry['prev_hash'] = prev_hash
            entry['entry_hash'] = entry_hash
            entries.append(entry)
            prev_hash = entry_hash
        
        # TAMPER: Modify entry 2's value
        entries[2]['value'] = 999
        
        with open(history_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        
        is_valid, count, error = verify_hash_chain(history_path)
        
        assert is_valid is False
        assert 'tampered' in error.lower() or 'mismatch' in error.lower()
    
    def test_hash_chain_detects_broken_link(self, temp_ledger_dir):
        """Test that broken prev_hash link is detected."""
        from utils.public_forecast_logger import (
            verify_hash_chain,
            compute_entry_hash,
            GENESIS_HASH,
        )
        
        history_path = temp_ledger_dir / 'forecast_history.jsonl'
        
        # Write chain with broken link
        entries = []
        prev_hash = GENESIS_HASH
        
        for i in range(3):
            entry = {
                'prediction_id': f'pred_{i}',
                'experiment_id': 'test',
                'value': i,
            }
            entry_hash = compute_entry_hash(entry, prev_hash)
            entry['prev_hash'] = prev_hash
            entry['entry_hash'] = entry_hash
            entries.append(entry)
            prev_hash = entry_hash
        
        # BREAK LINK: Change prev_hash of entry 2
        entries[2]['prev_hash'] = 'wrong_hash'
        
        with open(history_path, 'w') as f:
            for entry in entries:
                f.write(json.dumps(entry) + '\n')
        
        is_valid, count, error = verify_hash_chain(history_path)
        
        assert is_valid is False
        assert 'chain broken' in error.lower()


# =============================================================================
# TEST: EXPERIMENT PATH ENFORCEMENT
# =============================================================================

class TestExperimentPathEnforcement:
    """Tests for experiment-isolated artifact paths."""
    
    def test_validate_artifact_path_correct_experiment(self, temp_ledger_dir):
        """Test that correct paths pass validation."""
        from utils.run_artifact_contract import (
            validate_artifact_path,
            EXPERIMENTS_BASE_PATH,
        )
        
        # Mock the experiments base path
        experiments_base = temp_ledger_dir / 'data' / 'public' / 'experiments'
        v21_path = experiments_base / 'v2_1_forward_test'
        v21_path.mkdir(parents=True)
        
        artifact_path = v21_path / 'forecast_history.jsonl'
        
        with patch.object(
            __import__('utils.run_artifact_contract', fromlist=['EXPERIMENTS_BASE_PATH']),
            'EXPERIMENTS_BASE_PATH',
            experiments_base
        ):
            # This should pass (artifact in correct experiment)
            result = validate_artifact_path(
                artifact_path,
                'v2_1_forward_test',
                raise_on_violation=False,
            )
            
            assert result is True
    
    def test_validate_artifact_path_wrong_experiment(self, temp_ledger_dir):
        """Test that cross-experiment paths are rejected."""
        from utils.run_artifact_contract import (
            validate_artifact_path,
            ExperimentPathViolation,
        )
        
        # Create experiment directories
        experiments_base = temp_ledger_dir / 'data' / 'public' / 'experiments'
        v21_path = experiments_base / 'v2_1_forward_test'
        v30_path = experiments_base / 'v3_0_action_test'
        v21_path.mkdir(parents=True)
        v30_path.mkdir(parents=True)
        
        # Artifact in v3.0 path
        artifact_path = v30_path / 'forecast_history.jsonl'
        
        # Patch the base path
        import utils.run_artifact_contract as rac
        original_base = rac.EXPERIMENTS_BASE_PATH
        rac.EXPERIMENTS_BASE_PATH = experiments_base
        
        try:
            # Try to validate for v2.1 (should fail)
            with pytest.raises(ExperimentPathViolation) as exc_info:
                validate_artifact_path(
                    artifact_path,
                    'v2_1_forward_test',
                    raise_on_violation=True,
                )
            
            assert 'v3_0_action_test' in str(exc_info.value)
            assert 'cross-experiment' in str(exc_info.value).lower()
        finally:
            rac.EXPERIMENTS_BASE_PATH = original_base


# =============================================================================
# TEST: ENVIRONMENT FINGERPRINT
# =============================================================================

class TestEnvironmentFingerprint:
    """Tests for run_metadata environment fingerprint."""
    
    def test_metadata_contains_environment(self):
        """Test that built metadata includes environment fingerprint."""
        from utils.run_artifact_contract import RunMetadataBuilder
        
        # Create builder with mocked context
        with patch('utils.experiment_manager.get_experiment_context') as mock_ctx:
            mock_ctx.return_value = MagicMock(
                experiment=MagicMock(
                    experiment_id='test_exp',
                    engine_tag='ENGINE_TEST',
                ),
                commit_hash='abc123',
            )
            
            builder = RunMetadataBuilder(
                run_date='2026-02-10',
                experiment_id='test_exp',
            )
            
            metadata = builder.build()
            
            # Check required environment fields
            assert 'environment' in metadata
            env = metadata['environment']
            
            assert 'python_version' in env
            assert 'platform' in env
            assert 'platform_machine' in env
    
    def test_metadata_contains_config_hash(self):
        """Test that built metadata includes config directory hash."""
        from utils.run_artifact_contract import RunMetadataBuilder
        
        with patch('utils.experiment_manager.get_experiment_context') as mock_ctx:
            mock_ctx.return_value = MagicMock(
                experiment=MagicMock(
                    experiment_id='test_exp',
                    engine_tag='ENGINE_TEST',
                ),
                commit_hash='abc123',
            )
            
            builder = RunMetadataBuilder(
                run_date='2026-02-10',
                experiment_id='test_exp',
            )
            
            metadata = builder.build()
            
            assert 'config_dir_hash' in metadata
            assert len(metadata['config_dir_hash']) == 16  # Truncated hash
    
    def test_metadata_contains_engine_commit_hash(self):
        """Test that metadata includes resolved engine commit hash."""
        from utils.run_artifact_contract import RunMetadataBuilder
        
        with patch('utils.experiment_manager.get_experiment_context') as mock_ctx:
            mock_ctx.return_value = MagicMock(
                experiment=MagicMock(
                    experiment_id='test_exp',
                    engine_tag='ENGINE_TEST',
                ),
                commit_hash='abc123',
            )
            
            builder = RunMetadataBuilder(
                run_date='2026-02-10',
                experiment_id='test_exp',
            )
            
            # Mock git to return engine commit
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout='engine_commit_hash_123\n',
                )
                
                metadata = builder.build()
            
            assert 'engine_commit_hash' in metadata


# =============================================================================
# TEST: METHODOLOGY FIXED PARAMETERS
# =============================================================================

class TestMethodologyFixedParameters:
    """Tests for auto-generated fixed parameters in methodology."""
    
    def test_fixed_parameters_section_generated(self):
        """Test that fixed parameters section is generated."""
        from scripts.generate_experiment_methodology import generate_fixed_parameters_section
        
        section = generate_fixed_parameters_section()
        
        # Check section header
        assert '## 6. Fixed Parameters' in section
        
        # Check subsections
        assert 'Clustering Thresholds' in section
        assert 'Evidence Weights' in section
        assert 'Verification Thresholds' in section
        assert 'Confidence Formula' in section
    
    def test_methodology_includes_hash_chain_info(self):
        """Test that methodology documents the hash chain."""
        from scripts.generate_experiment_methodology import generate_reproducibility_section
        
        experiment = {
            'engine_tag': 'ENGINE_v2.1_DAY0',
            'experiment_id': 'test',
        }
        
        section = generate_reproducibility_section(experiment)
        
        assert 'hash chain' in section.lower()
        assert 'prev_hash' in section
        assert 'entry_hash' in section
        assert 'tamper' in section.lower()
    
    def test_methodology_includes_environment_fingerprint(self):
        """Test that methodology documents environment fingerprint."""
        from scripts.generate_experiment_methodology import generate_reproducibility_section
        
        experiment = {
            'engine_tag': 'ENGINE_v2.1_DAY0',
            'experiment_id': 'test',
        }
        
        section = generate_reproducibility_section(experiment)
        
        assert 'Environment Fingerprint' in section
        assert 'pip_freeze_hash' in section
        assert 'config_dir_hash' in section


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests for the full reproducibility flow."""
    
    def test_full_prediction_logging_with_hash_chain(self, temp_ledger_dir):
        """Test end-to-end prediction logging with hash chain."""
        from utils.public_forecast_logger import (
            add_hash_chain,
            get_last_hash,
            save_last_hash,
            verify_hash_chain,
            GENESIS_HASH,
        )
        
        history_path = temp_ledger_dir / 'forecast_history.jsonl'
        
        # Log multiple predictions
        predictions = [
            {'id': 'p1', 'value': 'first'},
            {'id': 'p2', 'value': 'second'},
            {'id': 'p3', 'value': 'third'},
        ]
        
        with open(history_path, 'w') as f:
            for pred in predictions:
                hashed = add_hash_chain(pred, temp_ledger_dir)
                f.write(json.dumps(hashed) + '\n')
                save_last_hash(temp_ledger_dir, hashed['entry_hash'])
        
        # Verify chain
        is_valid, count, error = verify_hash_chain(history_path)
        
        assert is_valid is True
        assert count == 3
        
        # Check sidecar was updated
        last_hash = get_last_hash(temp_ledger_dir)
        assert last_hash != GENESIS_HASH
        assert len(last_hash) == 64


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
