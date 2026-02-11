# Experiment Reproducibility & Tamper Evidence

> How briefAI ensures research-grade integrity for forward-test forecasting experiments.

## Overview

briefAI's forecasting system is designed for **scientific reproducibility**. A third-party researcher must be able to:

1. Clone the repository
2. Verify the prediction ledger is intact
3. Reproduce the exact forecasting methodology
4. Trust that no predictions were modified after the fact

This document explains the technical guarantees that make this possible.

---

## Tamper Evidence Guarantee

### Hash Chain Architecture

Every prediction logged to `forecast_history.jsonl` is part of a **cryptographic hash chain**, similar to blockchain technology:

```
Entry 1: { data..., prev_hash: "genesis", entry_hash: "abc123..." }
Entry 2: { data..., prev_hash: "abc123...", entry_hash: "def456..." }
Entry 3: { data..., prev_hash: "def456...", entry_hash: "ghi789..." }
```

Each entry's hash depends on:
- Its own content (deterministically serialized)
- The previous entry's hash

**If any historical entry is modified, the chain breaks.** This is cryptographically detectable.

### Canonical JSON Serialization

To ensure hash stability across different machines and Python versions, we use **deterministic canonical JSON**:

| Rule | Example |
|------|---------|
| Keys sorted alphabetically | `{"a":1,"b":2}` not `{"b":2,"a":1}` |
| Floats normalized (8 decimals) | `1.12345679` not `1.123456789012` |
| No negative zero | `0` not `-0` |
| Datetimes in UTC | `"2024-06-15T12:30:45Z"` |
| No whitespace | `{"a":1}` not `{ "a": 1 }` |
| Runtime fields excluded | `generation_timestamp` not in hash |

This guarantees identical hashes on any machine.

### Hash Computation

```python
# Simplified version
def compute_entry_hash(entry, prev_hash):
    canonical = canonical_dumps(entry, exclude_runtime_fields=True)
    content = prev_hash + canonical
    return sha256(content.encode()).hexdigest()
```

---

## Crash Recovery

### Two-Phase Write Protocol

Writes to the ledger use a crash-safe two-phase commit:

```
Phase 1: Append entry to JSONL, flush(), fsync()
Phase 2: Verify by re-reading last line
Phase 3: Update sidecar hash (atomic rename)
```

If the process crashes between phases:
- **Crash after Phase 1**: Entry is in JSONL, sidecar is stale
- **Crash after Phase 2**: Same as above
- **Crash after Phase 3**: Fully committed

### Automatic Reconciliation

On startup, the logger runs `reconcile_ledger()`:

1. Read entire JSONL
2. Recompute hash chain from genesis
3. Compare with sidecar (`forecast_history_last_hash.txt`)
4. If mismatch: repair sidecar, log WARNING

**Important**: Reconciliation NEVER deletes entries. It only repairs metadata.

---

## Independent Verification

### Verification Tool

Verify any ledger's integrity:

```bash
# Verify specific experiment
python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test

# Verify all experiments
python scripts/verify_ledger_integrity.py --all

# Repair sidecar if inconsistent
python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test --repair

# Output as JSON
python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test --json
```

### Verification Output

```
============================================================
  LEDGER STATUS: VALID
============================================================
  experiment:     v2_1_forward_test
  entries:        124
  genesis_hash:   genesis
  latest_hash:    a1b2c3d4e5f6...
  sidecar_ok:     True

  Integrity Checks:
    broken_links:       0
    hash_mismatches:    0
    duplicate_ids:      0
    chronology_errors:  0
    experiment_errors:  0
    canonical_errors:   0

  verified_at: 2026-02-15T08:30:00Z
============================================================
```

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Ledger valid |
| 1 | Ledger invalid or errors found |
| 2 | Ledger file not found |

### Verification Checks

The tool performs:

1. **JSON Validity**: Each line is valid JSON
2. **Canonical JSON**: Entries can be canonically serialized
3. **Hash Chain**: `prev_hash` links form unbroken chain
4. **Hash Integrity**: Stored `entry_hash` matches computed
5. **Sidecar Consistency**: Sidecar matches actual last hash
6. **Duplicate IDs**: No repeated `prediction_id`
7. **Chronology**: Entries in chronological order
8. **Experiment ID**: All entries belong to correct experiment

---

## Reproducibility Checklist

### For Researchers

To verify a briefAI experiment:

```bash
# 1. Clone repository
git clone https://github.com/[repo]/briefAI.git
cd briefAI

# 2. Checkout exact engine version
git checkout ENGINE_v2.1_DAY0

# 3. Install dependencies
pip install -r requirements.txt

# 4. Verify ledger integrity
python scripts/verify_ledger_integrity.py --experiment v2_1_forward_test

# 5. Compare hashes
# The genesis_hash and latest_hash should match public records
```

### Hash Portability

The same ledger file will produce identical verification results on:
- Windows, macOS, Linux
- Python 3.8, 3.9, 3.10, 3.11, 3.12
- x86_64, ARM64
- Any timezone

This is guaranteed by canonical JSON serialization.

---

## File Locations

| File | Purpose |
|------|---------|
| `data/public/experiments/{exp}/forecast_history.jsonl` | Append-only prediction ledger |
| `data/public/experiments/{exp}/forecast_history_last_hash.txt` | Latest hash (sidecar) |
| `data/public/experiments/{exp}/daily_snapshot_YYYY-MM-DD.json` | Daily frozen predictions |
| `data/public/experiments/{exp}/run_metadata_YYYY-MM-DD.json` | Run environment + config hash |
| `data/public/experiments/{exp}/METHODOLOGY.md` | Auto-generated methodology |

---

## Security Considerations

### What This Protects Against

- ✅ Post-hoc modification of predictions
- ✅ Silent data corruption
- ✅ Accidental overwrites
- ✅ Cross-experiment contamination
- ✅ Process crashes during writes

### What This Does NOT Protect Against

- ❌ Attacker with write access to entire ledger (can rewrite from genesis)
- ❌ Pre-generation bias (making predictions after seeing outcomes)
- ❌ Selective publication (only publishing good predictions)

For stronger guarantees, consider:
- Publishing daily ledger hashes to a public blockchain
- Using timestamping authorities (RFC 3161)
- Publishing predictions to immutable storage (IPFS, Arweave)

---

## Technical Reference

### Canonical JSON Module

```python
from utils.canonical_json import canonical_dumps, verify_canonical_equivalence

# Deterministic serialization
json_str = canonical_dumps(obj, exclude_runtime_fields=True)

# Check equivalence
are_equal = verify_canonical_equivalence(obj1, obj2)
```

### Hash Chain Functions

```python
from utils.public_forecast_logger import (
    compute_entry_hash,
    verify_hash_chain,
    reconcile_ledger,
    validate_ledger_integrity,
)

# Compute hash for new entry
entry_hash = compute_entry_hash(entry, prev_hash)

# Quick chain verification
is_valid, count, error = verify_hash_chain(history_path)

# Comprehensive validation
is_valid, count, errors = validate_ledger_integrity(
    history_path, repair=True, ledger_path=ledger_path
)

# Crash recovery
was_repaired, current_hash = reconcile_ledger(ledger_path, history_path)
```

---

## Migration Notes

### Pre-Hash-Chain Entries

Entries created before v1.2 do not have `prev_hash` and `entry_hash` fields.
The verifier will report these as "missing" but they are valid legacy entries.

Options for existing experiments:
1. **Continue as-is**: New entries get hash chain, old entries remain legacy
2. **Migrate**: Add hash chain fields to existing entries (one-time operation)
3. **New experiment**: Start fresh experiment with hash chain from day 1

For maximum auditability, option 3 (new experiment) is recommended when
starting a production forward-test.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-02-10 | Initial hash chain implementation |
| 1.1 | 2026-02-14 | Engine freeze + env fingerprint |
| 1.2 | 2026-02-15 | Canonical JSON + crash recovery + truncated line detection |

---

*This document is part of the briefAI experiment reproducibility framework.*
