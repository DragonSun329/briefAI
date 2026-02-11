#!/usr/bin/env python
"""
Verify Ledger Integrity v1.0

Audit-grade verification tool for briefAI forecast ledgers.
Performs comprehensive integrity checks:

1. Canonical JSON validity
2. Full hash chain continuity  
3. Sidecar consistency
4. Duplicate prediction ID detection
5. Chronological ordering
6. Experiment ID consistency

Usage:
    python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test
    python scripts/verify_ledger_integrity.py --all
    python scripts/verify_ledger_integrity.py --repair

Exit codes:
    0 - Ledger valid
    1 - Ledger invalid or errors found
    2 - Ledger file not found
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple
from dataclasses import dataclass, field

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.public_forecast_logger import (
    GENESIS_HASH,
    compute_entry_hash,
    get_last_hash,
    save_last_hash,
    verify_hash_chain,
)
from utils.canonical_json import canonical_dumps, CanonicalJSONError
from utils.experiment_manager import (
    get_experiment,
    get_active_experiment,
    list_experiments,
    get_ledger_path,
    get_forecast_history_path,
)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class LedgerVerificationResult:
    """Complete verification result for a ledger."""
    experiment_id: str
    status: str = "PENDING"  # VALID, INVALID, NOT_FOUND, ERROR, CORRUPTED
    entry_count: int = 0
    genesis_hash: str = GENESIS_HASH
    latest_hash: str = GENESIS_HASH
    broken_links: int = 0
    hash_mismatches: int = 0
    duplicate_ids: int = 0
    chronology_errors: int = 0
    experiment_id_mismatches: int = 0
    canonical_json_errors: int = 0
    truncated_lines: int = 0  # Lines with invalid JSON (potential crash)
    sidecar_consistent: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    verified_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + 'Z')
    
    @property
    def is_valid(self) -> bool:
        return self.status == "VALID"
    
    def print_report(self, verbose: bool = False) -> None:
        """Print human-readable verification report."""
        width = 60
        
        print("\n" + "=" * width)
        if self.is_valid:
            print(f"  LEDGER STATUS: VALID")
        else:
            print(f"  LEDGER STATUS: {self.status}")
        print("=" * width)
        
        print(f"  experiment:     {self.experiment_id}")
        print(f"  entries:        {self.entry_count}")
        print(f"  genesis_hash:   {self.genesis_hash}")
        print(f"  latest_hash:    {self.latest_hash[:32]}...")
        print(f"  sidecar_ok:     {self.sidecar_consistent}")
        print()
        
        print("  Integrity Checks:")
        print(f"    broken_links:       {self.broken_links}")
        print(f"    hash_mismatches:    {self.hash_mismatches}")
        print(f"    duplicate_ids:      {self.duplicate_ids}")
        print(f"    chronology_errors:  {self.chronology_errors}")
        print(f"    experiment_errors:  {self.experiment_id_mismatches}")
        print(f"    canonical_errors:   {self.canonical_json_errors}")
        if self.truncated_lines > 0:
            print(f"    TRUNCATED_LINES:    {self.truncated_lines} *** REQUIRES MANUAL FIX ***")
        
        if self.warnings:
            print()
            print("  Warnings:")
            for w in self.warnings[:10]:
                print(f"    [!] {w}")
            if len(self.warnings) > 10:
                print(f"    ... and {len(self.warnings) - 10} more")
        
        if self.errors:
            print()
            print("  Errors:")
            for e in self.errors[:10]:
                print(f"    [X] {e}")
            if len(self.errors) > 10:
                print(f"    ... and {len(self.errors) - 10} more")
        
        if verbose and self.is_valid:
            print()
            print("  Hash chain verified cryptographically.")
            print("  Third-party verification will produce identical results.")
        
        print()
        print(f"  verified_at: {self.verified_at}")
        print("=" * width + "\n")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'experiment_id': self.experiment_id,
            'status': self.status,
            'entry_count': self.entry_count,
            'genesis_hash': self.genesis_hash,
            'latest_hash': self.latest_hash,
            'broken_links': self.broken_links,
            'hash_mismatches': self.hash_mismatches,
            'duplicate_ids': self.duplicate_ids,
            'chronology_errors': self.chronology_errors,
            'experiment_id_mismatches': self.experiment_id_mismatches,
            'canonical_json_errors': self.canonical_json_errors,
            'truncated_lines': self.truncated_lines,
            'sidecar_consistent': self.sidecar_consistent,
            'errors': self.errors,
            'warnings': self.warnings,
            'verified_at': self.verified_at,
        }


# =============================================================================
# VERIFICATION FUNCTIONS
# =============================================================================

def verify_ledger_comprehensive(
    experiment_id: str,
    repair_sidecar: bool = False,
) -> LedgerVerificationResult:
    """
    Perform comprehensive ledger verification.
    
    Checks:
    1. File existence
    2. JSON validity on each line
    3. Canonical JSON serialization
    4. Hash chain continuity
    5. Sidecar consistency
    6. Duplicate prediction IDs
    7. Chronological ordering
    8. Experiment ID consistency
    
    Args:
        experiment_id: Experiment to verify
        repair_sidecar: If True, repair sidecar if inconsistent
    
    Returns:
        LedgerVerificationResult
    """
    result = LedgerVerificationResult(experiment_id=experiment_id)
    
    # Get paths
    try:
        ledger_path = get_ledger_path(experiment_id)
        history_path = get_forecast_history_path(experiment_id)
    except Exception as e:
        result.status = "ERROR"
        result.errors.append(f"Could not resolve paths: {e}")
        return result
    
    # Check file exists
    if not history_path.exists():
        result.status = "NOT_FOUND"
        result.errors.append(f"Ledger file not found: {history_path}")
        return result
    
    # Read and verify all entries
    seen_ids: Set[str] = set()
    prev_hash = GENESIS_HASH
    prev_timestamp: Optional[str] = None
    
    try:
        with open(history_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                result.entry_count += 1
                
                # Parse JSON
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError as e:
                    result.truncated_lines += 1
                    result.errors.append(
                        f"Line {line_num}: Invalid JSON (possible crash mid-write) - {e}. "
                        f"This line cannot be auto-repaired."
                    )
                    continue
                
                # Check canonical JSON serialization
                try:
                    canonical_dumps(entry, exclude_runtime_fields=True)
                except CanonicalJSONError as e:
                    result.canonical_json_errors += 1
                    result.warnings.append(f"Line {line_num}: Canonical JSON warning - {e}")
                
                # Check prev_hash link
                stored_prev = entry.get('prev_hash')
                if stored_prev is None:
                    result.broken_links += 1
                    result.errors.append(f"Line {line_num}: Missing prev_hash")
                elif stored_prev != prev_hash:
                    result.broken_links += 1
                    result.errors.append(
                        f"Line {line_num}: Chain broken - "
                        f"expected {prev_hash[:16]}..., got {stored_prev[:16]}..."
                    )
                
                # Verify hash
                stored_hash = entry.get('entry_hash')
                if stored_hash is None:
                    result.hash_mismatches += 1
                    result.errors.append(f"Line {line_num}: Missing entry_hash")
                else:
                    computed = compute_entry_hash(entry, prev_hash)
                    if computed != stored_hash:
                        result.hash_mismatches += 1
                        result.errors.append(
                            f"Line {line_num}: Hash mismatch - "
                            f"computed {computed[:16]}..., stored {stored_hash[:16]}..."
                        )
                    prev_hash = stored_hash
                
                # Check duplicate prediction IDs
                pred_id = entry.get('prediction_id')
                if pred_id:
                    if pred_id in seen_ids:
                        result.duplicate_ids += 1
                        result.warnings.append(
                            f"Line {line_num}: Duplicate prediction_id '{pred_id}'"
                        )
                    seen_ids.add(pred_id)
                
                # Check chronological order
                timestamp = entry.get('generation_timestamp') or entry.get('created_at')
                if timestamp and prev_timestamp:
                    if timestamp < prev_timestamp:
                        result.chronology_errors += 1
                        result.warnings.append(
                            f"Line {line_num}: Out of chronological order"
                        )
                if timestamp:
                    prev_timestamp = timestamp
                
                # Check experiment ID consistency
                entry_exp_id = entry.get('experiment_id')
                if entry_exp_id and entry_exp_id != experiment_id:
                    result.experiment_id_mismatches += 1
                    result.errors.append(
                        f"Line {line_num}: Wrong experiment_id '{entry_exp_id}' "
                        f"(expected '{experiment_id}')"
                    )
        
        result.latest_hash = prev_hash
        
    except Exception as e:
        result.status = "ERROR"
        result.errors.append(f"Read error: {e}")
        return result
    
    # Check sidecar consistency
    sidecar_hash = get_last_hash(ledger_path)
    if sidecar_hash != prev_hash:
        result.sidecar_consistent = False
        result.warnings.append(
            f"Sidecar inconsistent: {sidecar_hash[:16]}... vs {prev_hash[:16]}..."
        )
        
        if repair_sidecar:
            save_last_hash(ledger_path, prev_hash)
            result.warnings.append("Sidecar repaired")
            result.sidecar_consistent = True
    
    # Determine status
    has_corruption = result.truncated_lines > 0
    has_chain_errors = (
        result.broken_links > 0 or
        result.hash_mismatches > 0 or
        result.experiment_id_mismatches > 0
    )
    has_errors = has_chain_errors or has_corruption or len(result.errors) > 0
    
    if has_corruption:
        result.status = "CORRUPTED"  # Distinct status for truncated lines
    elif has_errors:
        result.status = "INVALID"
    else:
        result.status = "VALID"
    
    return result


def verify_all_experiments(repair: bool = False) -> List[LedgerVerificationResult]:
    """Verify all configured experiments."""
    results = []
    
    for experiment in list_experiments():
        result = verify_ledger_comprehensive(
            experiment.experiment_id,
            repair_sidecar=repair,
        )
        results.append(result)
    
    return results


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Verify ledger integrity for briefAI experiments',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify specific experiment
  python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test
  
  # Verify all experiments
  python scripts/verify_ledger_integrity.py --all
  
  # Verify and repair sidecar if inconsistent
  python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test --repair
  
  # Output as JSON
  python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test --json

Exit Codes:
  0 - All verified ledgers are valid
  1 - At least one ledger is invalid
  2 - Ledger file not found
        """
    )
    
    parser.add_argument(
        '--experiment', '-e',
        help='Experiment ID to verify (uses active if not specified)'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Verify all configured experiments'
    )
    parser.add_argument(
        '--repair', '-r',
        action='store_true',
        help='Repair sidecar file if inconsistent'
    )
    parser.add_argument(
        '--json', '-j',
        action='store_true',
        help='Output as JSON'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Determine what to verify
    if args.all:
        results = verify_all_experiments(repair=args.repair)
    else:
        experiment_id = args.experiment
        if not experiment_id:
            experiment = get_active_experiment()
            if experiment:
                experiment_id = experiment.experiment_id
            else:
                print("Error: No experiment specified and no active experiment")
                sys.exit(1)
        
        result = verify_ledger_comprehensive(
            experiment_id,
            repair_sidecar=args.repair,
        )
        results = [result]
    
    # Output results
    if args.json:
        output = [r.to_dict() for r in results]
        print(json.dumps(output if len(output) > 1 else output[0], indent=2))
    else:
        for result in results:
            result.print_report(verbose=args.verbose)
    
    # Determine exit code
    all_valid = all(r.is_valid for r in results)
    any_not_found = any(r.status == "NOT_FOUND" for r in results)
    
    if any_not_found:
        sys.exit(2)
    elif not all_valid:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
