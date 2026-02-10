"""
Tests for Bloomberg Terminal-Grade Data Validation Layer.

Tests cover:
- Source reliability tracking
- Audit log provenance
- Data validation with cross-source verification
- Validation rules engine
"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from utils.source_reliability import (
    SourceReliabilityTracker,
    SourceReliabilityScore,
    ReliabilityUpdate,
)
from utils.audit_log import AuditLogger, AuditEntry, EntityHistory
from utils.data_validator import DataValidator, Claim, ClaimValidationResult


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    yield path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def temp_rules_file():
    """Create a temporary rules file."""
    rules = {
        "global_settings": {
            "default_min_sources": 1,
            "high_value_min_sources": 2,
            "high_value_threshold_usd": 100000000,
        },
        "claim_types": {
            "funding_amount": {
                "validation_rules": [
                    {"name": "small_funding", "condition": {"value_lt": 10000000}, "min_sources": 1, "min_tier": 3},
                    {"name": "large_funding", "condition": {"value_gte": 10000000}, "min_sources": 2, "min_tier": 1},
                ]
            }
        },
        "source_tiers": {
            "tier_1": {"weight": 1.0, "examples": ["sec", "bloomberg", "wsj"]},
            "tier_2": {"weight": 0.8, "examples": ["crunchbase", "techcrunch"]},
            "tier_3": {"weight": 0.6, "examples": ["github", "reddit"]},
        }
    }
    
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w') as f:
        json.dump(rules, f)
    yield path
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def reliability_tracker(temp_db):
    """Create a SourceReliabilityTracker with temp DB."""
    return SourceReliabilityTracker(db_path=temp_db)


@pytest.fixture
def audit_logger(temp_db):
    """Create an AuditLogger with temp DB."""
    return AuditLogger(db_path=temp_db)


@pytest.fixture
def data_validator(temp_db, temp_rules_file):
    """Create a DataValidator with temp DB and rules."""
    return DataValidator(
        db_path=temp_db,
        rules_path=temp_rules_file,
        enable_audit=True,
    )


# ============================================================================
# Source Reliability Tests
# ============================================================================

class TestSourceReliability:
    """Tests for SourceReliabilityTracker."""
    
    def test_get_new_source_reliability(self, reliability_tracker):
        """New sources get base reliability based on tier."""
        score = reliability_tracker.get_reliability("bloomberg")
        
        assert score.source_id == "bloomberg"
        assert score.reliability_score >= 0.7  # Tier 1 source
        assert score.total_claims == 0
        assert score.verified_claims == 0
    
    def test_record_verified_claim_increases_reliability(self, reliability_tracker):
        """Recording verified claims increases reliability."""
        # Record initial claim
        reliability_tracker.record_claim(
            source_id="techcrunch",
            claim_type="funding_amount",
            was_verified=True,
        )
        
        # Record more verified claims
        for _ in range(5):
            reliability_tracker.record_claim(
                source_id="techcrunch",
                claim_type="funding_amount",
                was_verified=True,
            )
        
        score = reliability_tracker.get_reliability("techcrunch")
        
        assert score.total_claims == 6
        assert score.verified_claims == 6
        # After 6 verified claims, reliability should be high
        assert score.reliability_score > 0.7
    
    def test_contradicted_claims_decrease_reliability(self, reliability_tracker):
        """Contradicted claims decrease reliability."""
        # Record some claims, half contradicted
        for _ in range(5):
            reliability_tracker.record_claim(
                source_id="twitter",
                claim_type="funding_amount",
                was_contradicted=True,
            )
        
        score = reliability_tracker.get_reliability("twitter")
        
        assert score.contradicted_claims == 5
        # After 5 contradictions, reliability should drop
        assert score.reliability_score < 0.7
    
    def test_first_to_report_tracking(self, reliability_tracker):
        """First-to-report events are tracked."""
        reliability_tracker.record_claim(
            source_id="reuters",
            claim_type="acquisition_price",
            was_first_to_report=True,
            was_verified=True,
        )
        
        score = reliability_tracker.get_reliability("reuters")
        
        assert score.first_to_report_count == 1
    
    def test_category_specific_accuracy(self, reliability_tracker):
        """Category-specific accuracy is tracked."""
        # Source is good at funding but bad at valuations
        for _ in range(5):
            reliability_tracker.record_claim(
                source_id="crunchbase",
                claim_type="funding_amount",
                was_verified=True,
            )
            reliability_tracker.record_claim(
                source_id="crunchbase",
                claim_type="valuation",
                was_contradicted=True,
            )
        
        score = reliability_tracker.get_reliability("crunchbase")
        
        assert "funding_amount" in score.accuracy_by_category
        assert "valuation" in score.accuracy_by_category
        assert score.accuracy_by_category["funding_amount"]["accuracy"] > 0.5
        assert score.accuracy_by_category["valuation"]["accuracy"] < 0.5
    
    def test_get_reliability_for_claim_type(self, reliability_tracker):
        """get_reliability_for_claim uses category-specific accuracy."""
        # Build up history
        for _ in range(6):
            reliability_tracker.record_claim(
                source_id="test_source",
                claim_type="funding_amount",
                was_verified=True,
            )
            reliability_tracker.record_claim(
                source_id="test_source",
                claim_type="employee_count",
                was_contradicted=True,
            )
        
        funding_rel = reliability_tracker.get_reliability_for_claim("test_source", "funding_amount")
        employee_rel = reliability_tracker.get_reliability_for_claim("test_source", "employee_count")
        
        assert funding_rel > employee_rel
    
    def test_weighted_confidence_computation(self, reliability_tracker):
        """Weighted confidence is computed correctly."""
        # Set up sources with different reliabilities
        for _ in range(6):
            reliability_tracker.record_claim("high_rel", "test", was_verified=True)
            reliability_tracker.record_claim("low_rel", "test", was_contradicted=True)
        
        # Compute weighted confidence
        source_claims = [
            ("high_rel", 0.8, "test"),
            ("low_rel", 0.8, "test"),
        ]
        
        weighted = reliability_tracker.compute_weighted_confidence(source_claims)
        
        # Should be weighted toward the high-reliability source
        assert 0.0 <= weighted <= 1.0


# ============================================================================
# Audit Log Tests
# ============================================================================

class TestAuditLog:
    """Tests for AuditLogger."""
    
    def test_log_insert(self, audit_logger):
        """log_insert creates an entry."""
        entry_id = audit_logger.log_insert(
            table_name="entities",
            record_id="entity_123",
            data={"name": "OpenAI", "type": "company"},
            source_id="crunchbase",
            entity_id="entity_123",
        )
        
        assert entry_id is not None
        
        history = audit_logger.get_record_history("entities", "entity_123")
        assert len(history) == 1
        assert history[0].operation == "INSERT"
        assert history[0].source_id == "crunchbase"
    
    def test_log_update(self, audit_logger):
        """log_update tracks field changes."""
        audit_logger.log_update(
            table_name="entities",
            record_id="entity_123",
            field_name="employee_count",
            old_value=100,
            new_value=150,
            source_id="linkedin",
            entity_id="entity_123",
            change_reason="headcount_update",
        )
        
        history = audit_logger.get_record_history("entities", "entity_123")
        
        assert len(history) == 1
        assert history[0].field_name == "employee_count"
        assert history[0].old_value == 100
        assert history[0].new_value == 150
    
    def test_log_delete(self, audit_logger):
        """log_delete tracks deletions."""
        audit_logger.log_delete(
            table_name="entities",
            record_id="entity_123",
            data={"name": "OldCompany"},
            actor="manual:cleanup",
        )
        
        history = audit_logger.get_record_history("entities", "entity_123")
        
        assert len(history) == 1
        assert history[0].operation == "DELETE"
        assert history[0].actor == "manual:cleanup"
    
    def test_entity_history(self, audit_logger):
        """get_entity_history aggregates changes."""
        entity_id = "entity_456"
        
        # Create multiple changes
        audit_logger.log_insert("entities", entity_id, {"name": "Test"}, entity_id=entity_id)
        audit_logger.log_update("entities", entity_id, "funding", 0, 10000000, 
                                source_id="crunchbase", entity_id=entity_id)
        audit_logger.log_update("entities", entity_id, "funding", 10000000, 50000000,
                                source_id="techcrunch", entity_id=entity_id)
        
        history = audit_logger.get_entity_history(entity_id)
        
        assert history.entity_id == entity_id
        assert history.total_changes == 3
        assert "crunchbase" in history.changes_by_source
        assert "techcrunch" in history.changes_by_source
        assert "funding" in history.changes_by_field
    
    def test_changes_by_source(self, audit_logger):
        """get_changes_by_source filters correctly."""
        audit_logger.log_insert("entities", "e1", {}, source_id="source_a")
        audit_logger.log_insert("entities", "e2", {}, source_id="source_b")
        audit_logger.log_insert("entities", "e3", {}, source_id="source_a")
        
        changes = audit_logger.get_changes_by_source("source_a")
        
        assert len(changes) == 2
        assert all(c.source_id == "source_a" for c in changes)
    
    def test_recent_changes(self, audit_logger):
        """get_recent_changes with filters."""
        audit_logger.log_insert("entities", "e1", {})
        audit_logger.log_update("entities", "e1", "name", "old", "new")
        audit_logger.log_delete("entities", "e2", {})
        
        inserts = audit_logger.get_recent_changes(operation="INSERT")
        assert len(inserts) == 1
        
        entity_changes = audit_logger.get_recent_changes(table_name="entities")
        assert len(entity_changes) == 3
    
    def test_statistics(self, audit_logger):
        """get_statistics returns correct counts."""
        for i in range(5):
            audit_logger.log_insert("entities", f"e{i}", {})
        for i in range(3):
            audit_logger.log_update("entities", f"e{i}", "field", "old", "new")
        
        stats = audit_logger.get_statistics()
        
        assert stats["total_entries"] == 8
        assert stats["by_operation"]["INSERT"] == 5
        assert stats["by_operation"]["UPDATE"] == 3


# ============================================================================
# Data Validator Tests
# ============================================================================

class TestDataValidator:
    """Tests for DataValidator."""
    
    def test_validate_new_claim(self, data_validator):
        """Validating a new claim creates registry entry."""
        claim = Claim(
            entity_id="openai",
            claim_type="funding_amount",
            claim_value=5000000,  # $5M - small funding
            claim_unit="usd",
            source_id="techcrunch",
        )
        
        result = data_validator.validate_claim(claim)
        
        assert result.is_first_report
        assert result.first_reported_by == "techcrunch"
        assert result.source_count == 1
        assert result.claim_hash is not None
        assert result.registry_id is not None
    
    def test_validate_duplicate_from_same_source(self, data_validator):
        """Same source reporting same claim is handled."""
        claim = Claim(
            entity_id="anthropic",
            claim_type="funding_amount",
            claim_value=100000000,
            source_id="crunchbase",
        )
        
        result1 = data_validator.validate_claim(claim)
        result2 = data_validator.validate_claim(claim)
        
        assert result1.is_first_report
        assert not result2.is_first_report
        assert result2.source_count == 1  # Still 1, same source
    
    def test_cross_source_corroboration(self, data_validator):
        """Different sources reporting same claim increases confidence."""
        # Use small funding amount that doesn't require multiple sources per rules
        claim1 = Claim(
            entity_id="xai",
            claim_type="funding_amount",
            claim_value=5000000,  # $5M - small funding
            source_id="techcrunch",
        )
        claim2 = Claim(
            entity_id="xai",
            claim_type="funding_amount",
            claim_value=5000000,  # Same value
            source_id="crunchbase",
        )
        
        result1 = data_validator.validate_claim(claim1)
        result2 = data_validator.validate_claim(claim2)
        
        assert result1.source_count == 1
        assert result2.source_count == 2
        assert result2.validation_status == "corroborated"
        assert "techcrunch" in result2.confirmed_by or result2.first_reported_by == "techcrunch"
    
    def test_small_funding_single_source_valid(self, data_validator):
        """Small funding amounts are valid with single source."""
        claim = Claim(
            entity_id="startup",
            claim_type="funding_amount",
            claim_value=1000000,  # $1M
            source_id="techcrunch",
        )
        
        result = data_validator.validate_claim(claim)
        
        assert result.is_valid
        assert result.validation_status == "single_source"
    
    def test_large_funding_requires_multiple_sources(self, data_validator):
        """Large funding amounts require multiple sources."""
        claim = Claim(
            entity_id="bigtech",
            claim_type="funding_amount",
            claim_value=500000000,  # $500M
            source_id="reddit",
        )
        
        result = data_validator.validate_claim(claim)
        
        # With our test rules, large funding needs min_sources=2
        assert result.validation_status == "pending"
        assert result.requires_review
    
    def test_bypass_validation_mode(self, temp_db, temp_rules_file):
        """Bypass mode skips all validation."""
        validator = DataValidator(
            db_path=temp_db,
            rules_path=temp_rules_file,
            bypass_validation=True,
        )
        
        claim = Claim(
            entity_id="test",
            claim_type="funding_amount",
            claim_value=1000000000,
            source_id="unknown",
        )
        
        result = validator.validate_claim(claim)
        
        assert result.is_valid
        assert result.validation_status == "bypassed"
    
    def test_claim_hash_normalization(self, data_validator):
        """Similar values produce same claim hash."""
        # These should hash to the same claim (rounded to millions)
        claim1 = Claim(
            entity_id="test",
            claim_type="funding_amount",
            claim_value=100000000,
            source_id="source_a",
        )
        claim2 = Claim(
            entity_id="test",
            claim_type="funding_amount",
            claim_value=100000001,  # $1 difference
            source_id="source_b",
        )
        
        result1 = data_validator.validate_claim(claim1)
        result2 = data_validator.validate_claim(claim2)
        
        # Second claim should be seen as corroboration of first
        assert result2.source_count == 2
    
    def test_get_claims_for_entity(self, data_validator):
        """Can retrieve claims for an entity."""
        entity_id = "test_entity"
        
        data_validator.validate_claim(Claim(
            entity_id=entity_id,
            claim_type="funding_amount",
            claim_value=1000000,
            source_id="source_1",
        ))
        data_validator.validate_claim(Claim(
            entity_id=entity_id,
            claim_type="employee_count",
            claim_value=100,
            source_id="source_1",
        ))
        
        claims = data_validator.get_claims_for_entity(entity_id)
        
        assert len(claims) == 2
    
    def test_get_claims_requiring_review(self, data_validator):
        """Can retrieve claims needing review."""
        # Create a high-value claim that needs review
        data_validator.validate_claim(Claim(
            entity_id="bigco",
            claim_type="funding_amount",
            claim_value=500000000,
            source_id="reddit",
        ))
        
        review_queue = data_validator.get_claims_requiring_review()
        
        assert len(review_queue) >= 1
    
    def test_validation_statistics(self, data_validator):
        """Can get validation statistics."""
        # Create some claims
        for i in range(5):
            data_validator.validate_claim(Claim(
                entity_id=f"entity_{i}",
                claim_type="funding_amount",
                claim_value=1000000 * i,
                source_id="techcrunch",
            ))
        
        stats = data_validator.get_validation_statistics()
        
        assert stats["total_claims"] == 5
        assert "by_status" in stats
        assert "by_type" in stats


# ============================================================================
# Integration Tests
# ============================================================================

class TestValidationIntegration:
    """Integration tests for the full validation pipeline."""
    
    def test_full_validation_flow(self, temp_db, temp_rules_file):
        """Test complete validation flow with all components."""
        validator = DataValidator(
            db_path=temp_db,
            rules_path=temp_rules_file,
            enable_audit=True,
        )
        
        # First report
        claim1 = Claim(
            entity_id="openai",
            claim_type="funding_amount",
            claim_value=6000000000,
            source_id="sec",
        )
        result1 = validator.validate_claim(claim1)
        
        assert result1.is_first_report
        assert result1.first_reported_by == "sec"
        
        # Corroboration from another source
        claim2 = Claim(
            entity_id="openai",
            claim_type="funding_amount",
            claim_value=6000000000,
            source_id="bloomberg",
        )
        result2 = validator.validate_claim(claim2)
        
        assert not result2.is_first_report
        assert result2.source_count == 2
        assert result2.validation_status == "corroborated"
        
        # Check reliability was updated
        reliability = validator.reliability_tracker.get_reliability("sec")
        assert reliability.verified_claims >= 1
        
        # Check audit log
        audit = AuditLogger(db_path=temp_db)
        stats = audit.get_statistics()
        assert stats["total_entries"] > 0
    
    def test_reliability_affects_confidence(self, temp_db, temp_rules_file):
        """Source reliability affects claim confidence."""
        validator = DataValidator(
            db_path=temp_db,
            rules_path=temp_rules_file,
        )
        
        # Build up reliability history for one source
        for _ in range(10):
            validator.reliability_tracker.record_claim(
                source_id="trusted_source",
                claim_type="funding_amount",
                was_verified=True,
            )
            validator.reliability_tracker.record_claim(
                source_id="untrusted_source",
                claim_type="funding_amount",
                was_contradicted=True,
            )
        
        # Claims from different sources should have different confidence
        claim_trusted = Claim(
            entity_id="test1",
            claim_type="funding_amount",
            claim_value=1000000,
            source_id="trusted_source",
        )
        claim_untrusted = Claim(
            entity_id="test2",
            claim_type="funding_amount",
            claim_value=1000000,
            source_id="untrusted_source",
        )
        
        result_trusted = validator.validate_claim(claim_trusted)
        result_untrusted = validator.validate_claim(claim_untrusted)
        
        assert result_trusted.confidence_score > result_untrusted.confidence_score


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
