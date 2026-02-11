"""
Tests for Ledger Crash Recovery

Simulates crash scenarios and verifies the ledger recovers correctly:
- Crash before sidecar write
- Partial write (truncated entry)
- Sidecar corruption
- Missing sidecar

The ledger must NEVER lose entries due to crash recovery.

Run with: pytest tests/test_ledger_recovery.py -v
"""

import json
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from utils.canonical_json import canonical_dumps
from utils.public_forecast_logger import (
    GENESIS_HASH,
    HASH_SIDECAR_FILENAME,
    compute_entry_hash,
    get_last_hash,
    save_last_hash,
    add_hash_chain,
    two_phase_append,
    reconcile_ledger,
    verify_hash_chain,
    validate_ledger_integrity,
    append_entry_atomic,
    verify_last_entry,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def temp_ledger():
    """Create a temporary ledger directory."""
    temp_dir = tempfile.mkdtemp()
    ledger_path = Path(temp_dir)
    history_path = ledger_path / "forecast_history.jsonl"
    yield ledger_path, history_path
    shutil.rmtree(temp_dir)


def create_valid_entry(index: int, prev_hash: str) -> dict:
    """Create a valid entry with hash chain."""
    entry = {
        'prediction_id': f'pred_{index:03d}',
        'experiment_id': 'test_experiment',
        'value': index * 10,
    }
    entry_hash = compute_entry_hash(entry, prev_hash)
    entry['prev_hash'] = prev_hash
    entry['entry_hash'] = entry_hash
    return entry


def write_valid_chain(history_path: Path, ledger_path: Path, count: int) -> str:
    """Write a valid chain of entries and return last hash."""
    prev_hash = GENESIS_HASH
    
    with open(history_path, 'w', encoding='utf-8') as f:
        for i in range(count):
            entry = create_valid_entry(i, prev_hash)
            f.write(json.dumps(entry) + '\n')
            prev_hash = entry['entry_hash']
    
    # Also write sidecar
    save_last_hash(ledger_path, prev_hash)
    
    return prev_hash


# =============================================================================
# TEST: CRASH BEFORE SIDECAR WRITE
# =============================================================================

class TestCrashBeforeSidecarWrite:
    """
    Simulates crash after JSONL write but before sidecar update.
    
    Scenario:
    1. Write 5 entries with valid sidecar
    2. Write 6th entry to JSONL only (simulate crash before sidecar)
    3. Sidecar still points to entry 5
    4. reconcile_ledger() should repair sidecar to point to entry 6
    """
    
    def test_sidecar_repaired_after_crash(self, temp_ledger):
        ledger_path, history_path = temp_ledger
        
        # Write initial chain
        last_hash = write_valid_chain(history_path, ledger_path, 5)
        
        # Verify initial state
        is_valid, count, _ = verify_hash_chain(history_path)
        assert is_valid
        assert count == 5
        
        # Simulate crash: write entry 6 but don't update sidecar
        entry_6 = create_valid_entry(5, last_hash)
        with open(history_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry_6) + '\n')
        
        # Sidecar still points to old hash
        sidecar_hash = get_last_hash(ledger_path)
        assert sidecar_hash == last_hash  # Still old
        
        # Reconcile
        was_repaired, current_hash, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        assert was_repaired is True
        assert current_hash == entry_6['entry_hash']
        assert invalid_lines == 0
        
        # Verify chain is still valid
        is_valid, count, _ = verify_hash_chain(history_path)
        assert is_valid
        assert count == 6
    
    def test_no_entries_lost(self, temp_ledger):
        """Verify that crash recovery never loses entries."""
        ledger_path, history_path = temp_ledger
        
        # Write 10 entries
        write_valid_chain(history_path, ledger_path, 10)
        
        # Add 3 more without sidecar update
        prev_hash = get_last_hash(ledger_path)
        for i in range(10, 13):
            entry = create_valid_entry(i, prev_hash)
            with open(history_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + '\n')
            prev_hash = entry['entry_hash']
        
        # Reconcile
        was_repaired, _, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        assert was_repaired is True
        assert invalid_lines == 0
        
        # Count entries - should be 13
        with open(history_path, 'r') as f:
            lines = [l for l in f if l.strip()]
        assert len(lines) == 13


# =============================================================================
# TEST: PARTIAL WRITE (TRUNCATED ENTRY)
# =============================================================================

class TestPartialWrite:
    """
    Simulates partial write where entry is truncated mid-line.
    
    Note: Our current implementation doesn't auto-repair truncated entries,
    but it should detect them during verification.
    """
    
    def test_truncated_entry_detected(self, temp_ledger):
        """Truncated entry should fail verification."""
        ledger_path, history_path = temp_ledger
        
        # Write valid chain
        last_hash = write_valid_chain(history_path, ledger_path, 3)
        
        # Write partial entry (truncated JSON)
        with open(history_path, 'a', encoding='utf-8') as f:
            f.write('{"prediction_id":"pred_003","value":30')  # No closing brace
        
        # Verification should fail
        is_valid, count, error = verify_hash_chain(history_path)
        
        assert is_valid is False
        assert 'JSON' in error or 'line' in error.lower()
    
    def test_reconcile_handles_truncated_gracefully(self, temp_ledger):
        """
        Reconcile should handle truncated last line by computing
        hash from last valid entry, but report the invalid line.
        """
        ledger_path, history_path = temp_ledger
        
        # Write valid chain
        last_hash = write_valid_chain(history_path, ledger_path, 3)
        
        # Write partial entry
        with open(history_path, 'a', encoding='utf-8') as f:
            f.write('{"truncated": true')  # Invalid JSON
        
        # Reconcile - should still work (skips invalid lines but reports them)
        was_repaired, current_hash, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        # Should have hash from last valid entry
        assert current_hash == last_hash
        # Should report the invalid line
        assert invalid_lines == 1


# =============================================================================
# TEST: SIDECAR CORRUPTION
# =============================================================================

class TestSidecarCorruption:
    """Tests for corrupted sidecar file."""
    
    def test_garbage_sidecar_treated_as_genesis(self, temp_ledger):
        """Garbage in sidecar should be treated as genesis."""
        ledger_path, history_path = temp_ledger
        
        # Write garbage to sidecar
        sidecar = ledger_path / HASH_SIDECAR_FILENAME
        sidecar.write_text("not_a_valid_hash_garbage_data")
        
        # get_last_hash should return genesis
        result = get_last_hash(ledger_path)
        assert result == GENESIS_HASH
    
    def test_corrupted_sidecar_repaired(self, temp_ledger):
        """Corrupted sidecar should be repaired from ledger."""
        ledger_path, history_path = temp_ledger
        
        # Write valid chain
        last_hash = write_valid_chain(history_path, ledger_path, 5)
        
        # Corrupt sidecar
        sidecar = ledger_path / HASH_SIDECAR_FILENAME
        sidecar.write_text("corrupted_garbage_not_a_hash")
        
        # Reconcile
        was_repaired, current_hash, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        assert was_repaired is True
        assert current_hash == last_hash
        assert invalid_lines == 0
        
        # Sidecar should now be correct
        assert get_last_hash(ledger_path) == last_hash
    
    def test_wrong_hash_in_sidecar_repaired(self, temp_ledger):
        """Wrong hash in sidecar (but valid format) should be repaired."""
        ledger_path, history_path = temp_ledger
        
        # Write valid chain
        last_hash = write_valid_chain(history_path, ledger_path, 5)
        
        # Write wrong (but valid-looking) hash to sidecar
        wrong_hash = "a" * 64  # Valid format but wrong value
        save_last_hash(ledger_path, wrong_hash)
        
        # Reconcile
        was_repaired, current_hash, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        assert was_repaired is True
        assert current_hash == last_hash
        assert invalid_lines == 0


# =============================================================================
# TEST: MISSING SIDECAR
# =============================================================================

class TestMissingSidecar:
    """Tests for missing sidecar file."""
    
    def test_missing_sidecar_returns_genesis(self, temp_ledger):
        """Missing sidecar should return genesis hash."""
        ledger_path, _ = temp_ledger
        
        # No sidecar exists
        result = get_last_hash(ledger_path)
        assert result == GENESIS_HASH
    
    def test_missing_sidecar_created_on_reconcile(self, temp_ledger):
        """Missing sidecar should be created during reconcile."""
        ledger_path, history_path = temp_ledger
        
        # Write entries directly (no sidecar)
        prev_hash = GENESIS_HASH
        with open(history_path, 'w', encoding='utf-8') as f:
            for i in range(3):
                entry = create_valid_entry(i, prev_hash)
                f.write(json.dumps(entry) + '\n')
                prev_hash = entry['entry_hash']
        
        # Sidecar doesn't exist
        sidecar = ledger_path / HASH_SIDECAR_FILENAME
        assert not sidecar.exists()
        
        # Reconcile
        was_repaired, current_hash, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        # Sidecar should now exist
        assert sidecar.exists()
        assert get_last_hash(ledger_path) == prev_hash
        assert invalid_lines == 0
    
    def test_empty_ledger_empty_sidecar(self, temp_ledger):
        """Empty ledger should have genesis hash."""
        ledger_path, history_path = temp_ledger
        
        # Create empty history file
        history_path.touch()
        
        # Reconcile
        was_repaired, current_hash, invalid_lines = reconcile_ledger(ledger_path, history_path)
        
        assert current_hash == GENESIS_HASH
        assert invalid_lines == 0


# =============================================================================
# TEST: TWO-PHASE APPEND
# =============================================================================

class TestTwoPhaseAppend:
    """Tests for two-phase crash-safe append."""
    
    def test_two_phase_append_creates_valid_entry(self, temp_ledger):
        """Two-phase append should create valid chain entry."""
        ledger_path, history_path = temp_ledger
        
        # Create entry with hash chain
        entry = {
            'prediction_id': 'test_001',
            'value': 42,
        }
        hashed = add_hash_chain(entry, ledger_path)
        
        # Two-phase append
        result_hash = two_phase_append(history_path, ledger_path, hashed)
        
        assert result_hash == hashed['entry_hash']
        
        # Verify chain
        is_valid, count, _ = verify_hash_chain(history_path)
        assert is_valid
        assert count == 1
    
    def test_two_phase_append_multiple(self, temp_ledger):
        """Multiple two-phase appends create valid chain."""
        ledger_path, history_path = temp_ledger
        
        for i in range(5):
            entry = {
                'prediction_id': f'test_{i:03d}',
                'value': i * 10,
            }
            hashed = add_hash_chain(entry, ledger_path)
            two_phase_append(history_path, ledger_path, hashed)
        
        # Verify chain
        is_valid, count, _ = verify_hash_chain(history_path)
        assert is_valid
        assert count == 5
    
    def test_sidecar_updated_only_after_verify(self, temp_ledger):
        """Sidecar should only update after verification succeeds."""
        ledger_path, history_path = temp_ledger
        
        # Write initial entry
        entry1 = {'prediction_id': 'test_001', 'value': 1}
        hashed1 = add_hash_chain(entry1, ledger_path)
        two_phase_append(history_path, ledger_path, hashed1)
        
        first_hash = get_last_hash(ledger_path)
        
        # Simulate append that fails verification by mocking verify_last_entry
        entry2 = {'prediction_id': 'test_002', 'value': 2}
        hashed2 = add_hash_chain(entry2, ledger_path)
        
        with patch('utils.public_forecast_logger.verify_last_entry', return_value=False):
            with pytest.raises(RuntimeError, match="verification failed"):
                two_phase_append(history_path, ledger_path, hashed2)
        
        # Sidecar should NOT have been updated
        assert get_last_hash(ledger_path) == first_hash


# =============================================================================
# TEST: VALIDATE LEDGER INTEGRITY
# =============================================================================

class TestValidateLedgerIntegrity:
    """Tests for comprehensive ledger validation."""
    
    def test_valid_ledger_passes(self, temp_ledger):
        """Valid ledger should pass all checks."""
        ledger_path, history_path = temp_ledger
        
        write_valid_chain(history_path, ledger_path, 10)
        
        is_valid, count, errors = validate_ledger_integrity(
            history_path, repair=False, ledger_path=ledger_path
        )
        
        assert is_valid
        assert count == 10
        assert len(errors) == 0
    
    def test_tampered_entry_detected(self, temp_ledger):
        """Tampered entry should be detected."""
        ledger_path, history_path = temp_ledger
        
        write_valid_chain(history_path, ledger_path, 5)
        
        # Read entries, tamper with one, rewrite
        with open(history_path, 'r') as f:
            lines = f.readlines()
        
        # Tamper with entry 2
        entry = json.loads(lines[2])
        entry['value'] = 999999  # Changed!
        lines[2] = json.dumps(entry) + '\n'
        
        with open(history_path, 'w') as f:
            f.writelines(lines)
        
        # Validate
        is_valid, count, errors = validate_ledger_integrity(
            history_path, repair=False, ledger_path=ledger_path
        )
        
        assert is_valid is False
        assert any('mismatch' in e.lower() or 'hash' in e.lower() for e in errors)
    
    def test_repair_option_fixes_sidecar(self, temp_ledger):
        """repair=True should fix sidecar inconsistency."""
        ledger_path, history_path = temp_ledger
        
        last_hash = write_valid_chain(history_path, ledger_path, 5)
        
        # Corrupt sidecar
        save_last_hash(ledger_path, "wrong" + "a" * 59)
        
        # Validate with repair
        is_valid, count, errors = validate_ledger_integrity(
            history_path, repair=True, ledger_path=ledger_path
        )
        
        # Chain itself should still be valid
        chain_valid, _, _ = verify_hash_chain(history_path)
        assert chain_valid
        
        # Sidecar should be fixed
        assert get_last_hash(ledger_path) == last_hash


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
