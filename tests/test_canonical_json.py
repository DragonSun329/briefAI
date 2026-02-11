"""
Tests for Canonical JSON Serialization

Tests that canonical_dumps() produces deterministic, cross-platform
stable output for hash chain integrity.

Run with: pytest tests/test_canonical_json.py -v
"""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from utils.canonical_json import (
    canonical_dumps,
    normalize,
    normalize_float,
    normalize_datetime,
    verify_canonical_equivalence,
    CanonicalJSONError,
    FLOAT_PRECISION,
)


# =============================================================================
# TEST: BASIC SERIALIZATION
# =============================================================================

class TestBasicSerialization:
    """Basic canonical JSON serialization tests."""
    
    def test_empty_dict(self):
        assert canonical_dumps({}) == '{}'
    
    def test_empty_list(self):
        assert canonical_dumps([]) == '[]'
    
    def test_null(self):
        assert canonical_dumps(None) == 'null'
    
    def test_boolean_true(self):
        assert canonical_dumps(True) == 'true'
    
    def test_boolean_false(self):
        assert canonical_dumps(False) == 'false'
    
    def test_integer(self):
        assert canonical_dumps(42) == '42'
    
    def test_negative_integer(self):
        assert canonical_dumps(-42) == '-42'
    
    def test_string(self):
        assert canonical_dumps("hello") == '"hello"'
    
    def test_unicode_string(self):
        result = canonical_dumps("你好")
        assert result == '"你好"'  # ensure_ascii=False


# =============================================================================
# TEST: DETERMINISTIC KEY ORDERING
# =============================================================================

class TestKeyOrdering:
    """Tests for deterministic dictionary key ordering."""
    
    def test_keys_sorted_alphabetically(self):
        obj = {'z': 1, 'a': 2, 'm': 3}
        result = canonical_dumps(obj)
        assert result == '{"a":2,"m":3,"z":1}'
    
    def test_nested_keys_sorted(self):
        obj = {'b': {'y': 1, 'x': 2}, 'a': 1}
        result = canonical_dumps(obj)
        assert result == '{"a":1,"b":{"x":2,"y":1}}'
    
    def test_deeply_nested_sorting(self):
        obj = {
            'c': {
                'f': {'z': 1, 'a': 2},
                'e': 3
            },
            'b': 4,
            'a': 5
        }
        result = canonical_dumps(obj)
        parsed = json.loads(result)
        # Verify key order by checking the string
        assert result.index('"a"') < result.index('"b"') < result.index('"c"')
    
    def test_same_hash_different_key_order(self):
        """Different key orders must produce same hash."""
        obj1 = {'b': 1, 'a': 2, 'c': 3}
        obj2 = {'a': 2, 'c': 3, 'b': 1}
        obj3 = {'c': 3, 'b': 1, 'a': 2}
        
        hash1 = hashlib.sha256(canonical_dumps(obj1).encode()).hexdigest()
        hash2 = hashlib.sha256(canonical_dumps(obj2).encode()).hexdigest()
        hash3 = hashlib.sha256(canonical_dumps(obj3).encode()).hexdigest()
        
        assert hash1 == hash2 == hash3


# =============================================================================
# TEST: FLOAT NORMALIZATION
# =============================================================================

class TestFloatNormalization:
    """Tests for deterministic float handling."""
    
    def test_whole_float_becomes_int(self):
        """1.0 should serialize as 1."""
        assert canonical_dumps({'x': 1.0}) == '{"x":1}'
    
    def test_negative_zero_becomes_positive(self):
        """-0.0 should serialize as 0."""
        assert canonical_dumps({'x': -0.0}) == '{"x":0}'
    
    def test_precision_limited(self):
        """Floats rounded to 8 decimal places."""
        result = canonical_dumps({'x': 1.123456789012345})
        parsed = json.loads(result)
        assert parsed['x'] == round(1.123456789012345, FLOAT_PRECISION)
    
    def test_small_precision_differences_same_hash(self):
        """Tiny float differences should hash the same."""
        obj1 = {'x': 1.00000000001}
        obj2 = {'x': 1.00000000002}
        
        hash1 = hashlib.sha256(canonical_dumps(obj1).encode()).hexdigest()
        hash2 = hashlib.sha256(canonical_dumps(obj2).encode()).hexdigest()
        
        assert hash1 == hash2
    
    def test_nan_raises_error(self):
        """NaN is not serializable."""
        with pytest.raises(CanonicalJSONError):
            canonical_dumps({'x': float('nan')})
    
    def test_infinity_raises_error(self):
        """Infinity is not serializable."""
        with pytest.raises(CanonicalJSONError):
            canonical_dumps({'x': float('inf')})
    
    def test_decimal_normalized(self):
        """Decimal values are normalized like floats."""
        result = canonical_dumps({'x': Decimal('1.5')})
        assert result == '{"x":1.5}'


# =============================================================================
# TEST: DATETIME NORMALIZATION
# =============================================================================

class TestDatetimeNormalization:
    """Tests for deterministic datetime handling."""
    
    def test_naive_datetime_utc(self):
        """Naive datetime treated as UTC."""
        dt = datetime(2024, 6, 15, 12, 30, 45)
        result = canonical_dumps({'t': dt})
        assert result == '{"t":"2024-06-15T12:30:45Z"}'
    
    def test_aware_datetime_converted_to_utc(self):
        """Timezone-aware datetime converted to UTC."""
        # Create datetime in US Eastern (UTC-5)
        eastern = timezone(timedelta(hours=-5))
        dt = datetime(2024, 6, 15, 7, 30, 45, tzinfo=eastern)
        result = canonical_dumps({'t': dt})
        assert result == '{"t":"2024-06-15T12:30:45Z"}'
    
    def test_microseconds_stripped(self):
        """Microseconds are not included."""
        dt = datetime(2024, 6, 15, 12, 30, 45, 123456)
        result = canonical_dumps({'t': dt})
        assert '123456' not in result
        assert result == '{"t":"2024-06-15T12:30:45Z"}'
    
    def test_different_timezones_same_hash(self):
        """Same instant in different timezones produces same hash."""
        utc = timezone.utc
        eastern = timezone(timedelta(hours=-5))
        
        dt1 = datetime(2024, 6, 15, 12, 30, 45, tzinfo=utc)
        dt2 = datetime(2024, 6, 15, 7, 30, 45, tzinfo=eastern)
        
        obj1 = {'timestamp': dt1}
        obj2 = {'timestamp': dt2}
        
        hash1 = hashlib.sha256(canonical_dumps(obj1).encode()).hexdigest()
        hash2 = hashlib.sha256(canonical_dumps(obj2).encode()).hexdigest()
        
        assert hash1 == hash2


# =============================================================================
# TEST: LISTS
# =============================================================================

class TestLists:
    """Tests for list handling."""
    
    def test_list_order_preserved(self):
        """Lists maintain original order."""
        obj = {'items': [3, 1, 2]}
        result = canonical_dumps(obj)
        assert result == '{"items":[3,1,2]}'
    
    def test_nested_list_elements_normalized(self):
        """List elements are recursively normalized."""
        obj = {'items': [{'b': 1, 'a': 2}]}
        result = canonical_dumps(obj)
        assert result == '{"items":[{"a":2,"b":1}]}'
    
    def test_tuple_serialized_as_list(self):
        """Tuples serialize the same as lists."""
        list_obj = {'items': [1, 2, 3]}
        tuple_obj = {'items': (1, 2, 3)}
        
        assert canonical_dumps(list_obj) == canonical_dumps(tuple_obj)


# =============================================================================
# TEST: CROSS-RUN CONSISTENCY
# =============================================================================

class TestCrossRunConsistency:
    """Tests for consistent results across multiple runs."""
    
    def test_same_hash_across_5_runs(self):
        """Same object produces identical hash across 5 runs."""
        obj = {
            'id': 'test_123',
            'value': 42.5,
            'nested': {'z': 1, 'a': 2},
            'items': [1, 2, 3],
            'flag': True,
        }
        
        hashes = set()
        for _ in range(5):
            canonical = canonical_dumps(obj)
            hash_val = hashlib.sha256(canonical.encode()).hexdigest()
            hashes.add(hash_val)
        
        assert len(hashes) == 1, "Hash should be identical across runs"
    
    def test_complex_object_deterministic(self):
        """Complex nested object is deterministic."""
        obj = {
            'experiment_id': 'v2_1_forward_test',
            'predictions': [
                {
                    'id': 'pred_001',
                    'confidence': 0.75,
                    'entity': 'nvidia',
                    'metrics': {'price': 123.45, 'volume': 1000000.0}
                },
                {
                    'id': 'pred_002',
                    'confidence': 0.60,
                    'entity': 'amd',
                    'metrics': {'price': 98.76, 'volume': 500000.0}
                }
            ],
            'metadata': {
                'version': '2.1',
                'engine_tag': 'ENGINE_v2.1_DAY0',
            }
        }
        
        canonical1 = canonical_dumps(obj)
        canonical2 = canonical_dumps(obj)
        
        assert canonical1 == canonical2


# =============================================================================
# TEST: RUNTIME FIELD EXCLUSION
# =============================================================================

class TestRuntimeFieldExclusion:
    """Tests for runtime-only field exclusion."""
    
    def test_generation_timestamp_excluded(self):
        """generation_timestamp excluded when flag set."""
        obj = {
            'id': 'test',
            'generation_timestamp': '2024-06-15T12:00:00Z',
            'value': 42,
        }
        
        result = canonical_dumps(obj, exclude_runtime_fields=True)
        assert 'generation_timestamp' not in result
        assert 'value' in result
    
    def test_same_hash_different_timestamps(self):
        """Different timestamps produce same hash when excluded."""
        obj1 = {
            'id': 'test',
            'generation_timestamp': '2024-06-15T12:00:00Z',
            'value': 42,
        }
        obj2 = {
            'id': 'test',
            'generation_timestamp': '2024-06-15T13:00:00Z',
            'value': 42,
        }
        
        c1 = canonical_dumps(obj1, exclude_runtime_fields=True)
        c2 = canonical_dumps(obj2, exclude_runtime_fields=True)
        
        h1 = hashlib.sha256(c1.encode()).hexdigest()
        h2 = hashlib.sha256(c2.encode()).hexdigest()
        
        assert h1 == h2


# =============================================================================
# TEST: ERROR HANDLING
# =============================================================================

class TestErrorHandling:
    """Tests for error handling."""
    
    def test_bytes_raises_error(self):
        """Bytes are not directly serializable."""
        with pytest.raises(CanonicalJSONError):
            canonical_dumps({'data': b'binary'})
    
    def test_non_string_dict_key_raises_error(self):
        """Non-string dict keys raise error."""
        with pytest.raises(CanonicalJSONError):
            canonical_dumps({1: 'value'})
    
    def test_custom_object_raises_error(self):
        """Custom objects without serialization raise error."""
        class Custom:
            pass
        
        with pytest.raises(CanonicalJSONError):
            canonical_dumps({'obj': Custom()})


# =============================================================================
# TEST: EQUIVALENCE CHECKER
# =============================================================================

class TestEquivalence:
    """Tests for canonical equivalence checking."""
    
    def test_equivalent_objects(self):
        obj1 = {'b': 1, 'a': 2}
        obj2 = {'a': 2, 'b': 1}
        assert verify_canonical_equivalence(obj1, obj2)
    
    def test_non_equivalent_objects(self):
        obj1 = {'a': 1}
        obj2 = {'a': 2}
        assert not verify_canonical_equivalence(obj1, obj2)
    
    def test_float_precision_equivalence(self):
        obj1 = {'x': 1.0000000001}
        obj2 = {'x': 1.0000000002}
        assert verify_canonical_equivalence(obj1, obj2)


# =============================================================================
# SIMULATED CROSS-MACHINE TEST
# =============================================================================

class TestSimulatedCrossMachine:
    """
    Simulate cross-machine serialization by creating objects
    in different ways that might differ between environments.
    """
    
    def test_dict_created_different_ways(self):
        """Dicts created differently serialize identically."""
        # Method 1: literal
        obj1 = {'z': 1, 'a': 2, 'm': 3}
        
        # Method 2: dict()
        obj2 = dict(z=1, a=2, m=3)
        
        # Method 3: dict comprehension
        obj3 = {k: v for k, v in [('z', 1), ('a', 2), ('m', 3)]}
        
        c1 = canonical_dumps(obj1)
        c2 = canonical_dumps(obj2)
        c3 = canonical_dumps(obj3)
        
        assert c1 == c2 == c3
    
    def test_float_from_string_vs_literal(self):
        """Floats from different sources serialize identically."""
        obj1 = {'x': 1.5}
        obj2 = {'x': float('1.5')}
        obj3 = {'x': float(Decimal('1.5'))}
        
        c1 = canonical_dumps(obj1)
        c2 = canonical_dumps(obj2)
        c3 = canonical_dumps(obj3)
        
        assert c1 == c2 == c3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
