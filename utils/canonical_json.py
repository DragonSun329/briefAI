"""
Canonical JSON Serialization v1.0

Provides deterministic, cross-platform JSON serialization for audit-grade
hash chain integrity. The output of canonical_dumps() is guaranteed identical
across:
- Python versions (3.8+)
- Operating systems
- Machines
- Timezones

This is CRITICAL for ledger tamper-evidence. If two systems compute different
hashes for the same logical data, the chain verification fails.

Rules:
1. Dictionary keys sorted recursively (lexicographic)
2. Lists preserve original order
3. Floats normalized: 8 decimal places, no -0.0
4. Datetimes: ISO8601 UTC, no microseconds (YYYY-MM-DDTHH:MM:SSZ)
5. Compact separators: no whitespace
6. Booleans: true/false (JSON standard)
7. Null: null (JSON standard)
8. Strings: UTF-8, escaped per JSON spec
9. Unknown types: raise CanonicalJSONError
"""

import json
import math
from datetime import datetime, timezone, date
from typing import Any, List, Dict, Union
from decimal import Decimal


# =============================================================================
# EXCEPTIONS
# =============================================================================

class CanonicalJSONError(TypeError):
    """Raised when an object cannot be canonically serialized."""
    
    def __init__(self, obj: Any, path: str = ""):
        self.obj = obj
        self.path = path
        type_name = type(obj).__name__
        msg = f"Cannot canonically serialize type '{type_name}'"
        if path:
            msg += f" at path '{path}'"
        super().__init__(msg)


# =============================================================================
# CONSTANTS
# =============================================================================

# Float precision for normalization (8 decimal places)
FLOAT_PRECISION = 8

# Fields to EXCLUDE from hashing (runtime-only, non-deterministic)
RUNTIME_ONLY_FIELDS = frozenset({
    'generation_timestamp',
    'created_at',
    'updated_at',
    'local_path',
    'filesystem_path',
    'hostname',
    'pid',
    'memory_usage',
    '_runtime_id',
})


# =============================================================================
# NORMALIZERS
# =============================================================================

def normalize_float(value: float) -> Union[float, int]:
    """
    Normalize a float for deterministic serialization.
    
    Rules:
    - Round to FLOAT_PRECISION decimal places
    - Convert -0.0 to 0.0
    - NaN and Inf raise error (not JSON-serializable anyway)
    - Convert to int if no fractional part
    """
    if math.isnan(value):
        raise CanonicalJSONError(value, "NaN is not JSON-serializable")
    if math.isinf(value):
        raise CanonicalJSONError(value, "Infinity is not JSON-serializable")
    
    # Round to fixed precision
    rounded = round(value, FLOAT_PRECISION)
    
    # Handle negative zero
    if rounded == 0.0:
        rounded = 0.0  # Ensures -0.0 becomes 0.0
    
    # Convert to int if whole number (avoids 1.0 vs 1 differences)
    if rounded == int(rounded) and abs(rounded) < 2**53:
        return int(rounded)
    
    return rounded


def normalize_datetime(dt: datetime) -> str:
    """
    Normalize a datetime to canonical ISO8601 UTC string.
    
    Output format: YYYY-MM-DDTHH:MM:SSZ
    
    - Always UTC
    - No microseconds
    - No timezone offset (always Z suffix)
    """
    # Convert to UTC if timezone-aware
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc)
    else:
        # Assume naive datetime is UTC (common in this codebase)
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Format without microseconds
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def normalize_date(d: date) -> str:
    """Normalize a date to YYYY-MM-DD string."""
    return d.strftime('%Y-%m-%d')


def normalize(obj: Any, path: str = "", exclude_runtime: bool = False) -> Any:
    """
    Recursively normalize an object for canonical serialization.
    
    Args:
        obj: Object to normalize
        path: Current path (for error messages)
        exclude_runtime: If True, exclude RUNTIME_ONLY_FIELDS from dicts
    
    Returns:
        Normalized object suitable for json.dumps
    
    Raises:
        CanonicalJSONError: If object type is not serializable
    """
    # None
    if obj is None:
        return None
    
    # Booleans (must check before int, since bool is subclass of int)
    if isinstance(obj, bool):
        return obj
    
    # Integers
    if isinstance(obj, int):
        return obj
    
    # Floats
    if isinstance(obj, float):
        return normalize_float(obj)
    
    # Decimal -> float -> normalized
    if isinstance(obj, Decimal):
        return normalize_float(float(obj))
    
    # Strings
    if isinstance(obj, str):
        return obj
    
    # Bytes -> base64 or reject
    if isinstance(obj, bytes):
        raise CanonicalJSONError(obj, path + " (use base64 encoding)")
    
    # Datetime
    if isinstance(obj, datetime):
        return normalize_datetime(obj)
    
    # Date (not datetime)
    if isinstance(obj, date):
        return normalize_date(obj)
    
    # Lists and tuples (preserve order)
    if isinstance(obj, (list, tuple)):
        return [
            normalize(item, f"{path}[{i}]", exclude_runtime)
            for i, item in enumerate(obj)
        ]
    
    # Dictionaries (sort keys)
    if isinstance(obj, dict):
        result = {}
        for key in sorted(obj.keys()):
            # Skip runtime-only fields if requested
            if exclude_runtime and key in RUNTIME_ONLY_FIELDS:
                continue
            
            if not isinstance(key, str):
                raise CanonicalJSONError(
                    key, f"{path}.{key} (dict keys must be strings)"
                )
            
            value = obj[key]
            result[key] = normalize(value, f"{path}.{key}", exclude_runtime)
        
        return result
    
    # Sets -> sorted lists
    if isinstance(obj, (set, frozenset)):
        try:
            return sorted(
                normalize(item, f"{path}[set]", exclude_runtime) 
                for item in obj
            )
        except TypeError:
            # Items not comparable, use string representation
            return sorted(
                str(normalize(item, f"{path}[set]", exclude_runtime))
                for item in obj
            )
    
    # Unknown type
    raise CanonicalJSONError(obj, path)


# =============================================================================
# PUBLIC API
# =============================================================================

def canonical_dumps(
    obj: Any,
    exclude_runtime_fields: bool = False,
) -> str:
    """
    Serialize object to deterministic canonical JSON string.
    
    This function guarantees identical output across:
    - Python versions
    - Operating systems
    - Machines
    - Timezones
    
    Args:
        obj: Object to serialize
        exclude_runtime_fields: If True, exclude runtime-only fields like
                               'generation_timestamp' from output
    
    Returns:
        Canonical JSON string (compact, sorted keys, normalized values)
    
    Raises:
        CanonicalJSONError: If object contains unserializable types
    
    Example:
        >>> canonical_dumps({'b': 1, 'a': 2})
        '{"a":2,"b":1}'
        
        >>> canonical_dumps({'x': 1.0000000001})
        '{"x":1}'
        
        >>> canonical_dumps({'dt': datetime(2024, 1, 15, 12, 30, 45)})
        '{"dt":"2024-01-15T12:30:45Z"}'
    """
    normalized = normalize(obj, "", exclude_runtime=exclude_runtime_fields)
    return json.dumps(
        normalized,
        separators=(',', ':'),
        ensure_ascii=False,
        sort_keys=True,  # Redundant but explicit safety
    )


def canonical_hash_content(
    obj: Any,
    prev_hash: str,
) -> str:
    """
    Create the content string to be hashed for ledger entries.
    
    This EXCLUDES runtime-only fields to ensure hash stability
    across different execution environments.
    
    Args:
        obj: Object to include in hash
        prev_hash: Previous entry's hash (or "genesis")
    
    Returns:
        String to be fed to SHA-256: prev_hash + canonical_json
    """
    canonical = canonical_dumps(obj, exclude_runtime_fields=True)
    return prev_hash + canonical


def verify_canonical_equivalence(obj1: Any, obj2: Any) -> bool:
    """
    Check if two objects are canonically equivalent.
    
    Useful for testing that different representations
    produce the same canonical form.
    """
    try:
        return canonical_dumps(obj1) == canonical_dumps(obj2)
    except CanonicalJSONError:
        return False


# =============================================================================
# CLI FOR TESTING
# =============================================================================

def main():
    """CLI for testing canonical serialization."""
    import sys
    import hashlib
    
    if len(sys.argv) < 2:
        print("Usage: python canonical_json.py <json_string>")
        print("       python canonical_json.py --test")
        sys.exit(1)
    
    if sys.argv[1] == '--test':
        # Run basic self-tests
        tests = [
            # Key ordering
            ({'b': 1, 'a': 2}, '{"a":2,"b":1}'),
            # Float normalization
            ({'x': 1.0}, '{"x":1}'),
            ({'x': 1.123456789012}, '{"x":1.12345679}'),
            ({'x': -0.0}, '{"x":0}'),
            # Nested
            ({'a': {'c': 1, 'b': 2}}, '{"a":{"b":2,"c":1}}'),
            # Lists preserve order
            ({'a': [3, 1, 2]}, '{"a":[3,1,2]}'),
            # Booleans and null
            ({'t': True, 'f': False, 'n': None}, '{"f":false,"n":null,"t":true}'),
        ]
        
        passed = 0
        failed = 0
        
        for obj, expected in tests:
            result = canonical_dumps(obj)
            if result == expected:
                passed += 1
                print(f"[PASS] {obj}")
            else:
                failed += 1
                print(f"[FAIL] {obj}")
                print(f"  Expected: {expected}")
                print(f"  Got:      {result}")
        
        print(f"\n{passed} passed, {failed} failed")
        sys.exit(0 if failed == 0 else 1)
    
    # Parse input JSON and canonicalize
    try:
        obj = json.loads(sys.argv[1])
        canonical = canonical_dumps(obj)
        hash_val = hashlib.sha256(canonical.encode()).hexdigest()
        
        print(f"Input:     {sys.argv[1]}")
        print(f"Canonical: {canonical}")
        print(f"SHA-256:   {hash_val}")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON: {e}")
        sys.exit(1)
    except CanonicalJSONError as e:
        print(f"Serialization error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
