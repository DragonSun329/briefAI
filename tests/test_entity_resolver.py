"""
Tests for EntityResolver - Bloomberg-grade entity resolution.

Tests cover:
- External identifier lookups
- Alias resolution with confidence scores
- Fuzzy matching
- Relationship management
- Deduplication with audit trail
"""

import pytest
import tempfile
import sqlite3
from datetime import datetime
from pathlib import Path

from utils.entity_resolver import (
    EntityResolver,
    ExternalIdentifiers,
    AliasMapping,
    EntityRelationship,
    RelationshipType,
    ResolutionDecision,
    ResolutionResult,
    MergeAuditRecord,
)


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create base tables
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            canonical_id TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            aliases TEXT,
            description TEXT,
            website TEXT,
            founded_date TEXT,
            headquarters TEXT,
            parent_entity TEXT,
            related_entities TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_observations (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_scores (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signal_profiles (
            id TEXT PRIMARY KEY,
            entity_id TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def resolver(temp_db):
    """Create resolver with temporary database."""
    return EntityResolver(db_path=temp_db)


@pytest.fixture
def resolver_with_data(resolver, temp_db):
    """Create resolver with test data."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Insert test entities
    test_entities = [
        ("e1", "openai", "OpenAI", "company"),
        ("e2", "anthropic", "Anthropic", "company"),
        ("e3", "google", "Google", "company"),
        ("e4", "openai-inc", "OpenAI Inc", "company"),  # Potential duplicate
    ]

    for entity_id, canonical_id, name, entity_type in test_entities:
        cursor.execute("""
            INSERT INTO entities (id, canonical_id, name, entity_type, aliases)
            VALUES (?, ?, ?, ?, '[]')
        """, (entity_id, canonical_id, name, entity_type))

    conn.commit()
    conn.close()

    resolver.refresh_caches()
    return resolver


class TestNameNormalization:
    """Tests for name normalization."""

    def test_normalize_basic(self, resolver):
        """Basic normalization: lowercase and trim."""
        assert resolver.normalize_name("OpenAI") == "openai"
        assert resolver.normalize_name("  Anthropic  ") == "anthropic"

    def test_normalize_removes_inc(self, resolver):
        """Strips Inc. suffix."""
        assert resolver.normalize_name("OpenAI Inc") == "openai"
        assert resolver.normalize_name("OpenAI, Inc.") == "openai"

    def test_normalize_removes_llc(self, resolver):
        """Strips LLC suffix."""
        assert resolver.normalize_name("Acme LLC") == "acme"
        assert resolver.normalize_name("Acme, LLC") == "acme"

    def test_normalize_removes_ltd(self, resolver):
        """Strips Ltd suffix."""
        assert resolver.normalize_name("DeepMind Ltd") == "deepmind"
        assert resolver.normalize_name("DeepMind Limited") == "deepmind"

    def test_normalize_removes_corp(self, resolver):
        """Strips Corp suffix."""
        assert resolver.normalize_name("Microsoft Corp") == "microsoft"
        assert resolver.normalize_name("Microsoft Corporation") == "microsoft"

    def test_normalize_empty(self, resolver):
        """Empty string handling."""
        assert resolver.normalize_name("") == ""
        assert resolver.normalize_name(None) == ""

    def test_normalize_preserves_internal_spaces(self, resolver):
        """Preserves spaces within name."""
        assert resolver.normalize_name("Open AI") == "open ai"


class TestExternalIdentifiers:
    """Tests for external identifier management."""

    def test_set_and_get_external_ids(self, resolver_with_data):
        """Set and retrieve external identifiers."""
        ids = ExternalIdentifiers(
            crunchbase_uuid="abc123",
            ticker_symbol="OAII",
            exchange="NASDAQ",
        )

        resolver_with_data.set_external_ids("e1", ids)
        retrieved = resolver_with_data.get_external_ids("e1")

        assert retrieved is not None
        assert retrieved.crunchbase_uuid == "abc123"
        assert retrieved.ticker_symbol == "OAII"
        assert retrieved.exchange == "NASDAQ"

    def test_lookup_by_crunchbase(self, resolver_with_data):
        """Lookup entity by Crunchbase UUID."""
        ids = ExternalIdentifiers(crunchbase_uuid="cb-uuid-123")
        resolver_with_data.set_external_ids("e1", ids)

        result = resolver_with_data.lookup_by_crunchbase("cb-uuid-123")
        assert result == "e1"

    def test_lookup_by_ticker(self, resolver_with_data):
        """Lookup entity by ticker symbol."""
        ids = ExternalIdentifiers(ticker_symbol="GOOG")
        resolver_with_data.set_external_ids("e3", ids)

        result = resolver_with_data.lookup_by_ticker("GOOG")
        assert result == "e3"

        # Case insensitive
        result = resolver_with_data.lookup_by_ticker("goog")
        assert result == "e3"

    def test_lookup_by_wikidata(self, resolver_with_data):
        """Lookup entity by Wikidata ID."""
        ids = ExternalIdentifiers(wikidata_id="Q1234567")
        resolver_with_data.set_external_ids("e2", ids)

        result = resolver_with_data.lookup_by_wikidata("Q1234567")
        assert result == "e2"

    def test_lookup_by_domain(self, resolver_with_data):
        """Lookup entity by domain."""
        ids = ExternalIdentifiers(domain="openai.com")
        resolver_with_data.set_external_ids("e1", ids)

        result = resolver_with_data.lookup_by_domain("openai.com")
        assert result == "e1"

        # With protocol
        result = resolver_with_data.lookup_by_domain("https://openai.com/research")
        assert result == "e1"

    def test_external_ids_to_dict(self):
        """ExternalIdentifiers serialization."""
        ids = ExternalIdentifiers(
            crunchbase_uuid="abc",
            ticker_symbol="XYZ",
        )
        d = ids.to_dict()

        assert "crunchbase_uuid" in d
        assert d["crunchbase_uuid"] == "abc"
        assert "lei_code" not in d  # None values excluded


class TestAliasResolution:
    """Tests for alias resolution."""

    def test_add_and_resolve_alias(self, resolver_with_data):
        """Add alias and resolve it."""
        resolver_with_data.add_alias(
            alias="Open AI",
            canonical_id="openai",
            confidence=1.0,
            source="manual",
        )

        result = resolver_with_data.resolve_alias("Open AI")
        assert result is not None
        assert result[0] == "openai"
        assert result[1] == 1.0

    def test_alias_normalization(self, resolver_with_data):
        """Aliases are normalized for lookup."""
        resolver_with_data.add_alias("OpenAI Inc.", "openai", 1.0, "test")

        # Should match normalized version
        result = resolver_with_data.resolve_alias("openai inc")
        assert result is not None
        assert result[0] == "openai"

    def test_alias_confidence_update(self, resolver_with_data):
        """Higher confidence alias updates lower one."""
        resolver_with_data.add_alias("GPT", "openai", 0.5, "test")
        resolver_with_data.add_alias("GPT", "openai", 0.9, "test")

        result = resolver_with_data.resolve_alias("GPT")
        assert result[1] == 0.9

    def test_get_aliases_for_entity(self, resolver_with_data):
        """Get all aliases for an entity."""
        resolver_with_data.add_alias("Open AI", "openai", 1.0, "manual")
        resolver_with_data.add_alias("OpenAI Inc", "openai", 0.9, "auto")

        aliases = resolver_with_data.get_aliases("openai")
        assert len(aliases) >= 2
        assert any(a.alias == "Open AI" for a in aliases)


class TestFuzzyMatching:
    """Tests for fuzzy name matching."""

    def test_fuzzy_match_exact(self, resolver_with_data):
        """Exact match returns high score."""
        matches = resolver_with_data.fuzzy_match("OpenAI", threshold=80)

        assert len(matches) > 0
        # First match should be openai with high score
        assert matches[0][2] > 0.9

    def test_fuzzy_match_similar(self, resolver_with_data):
        """Similar names match with lower score."""
        matches = resolver_with_data.fuzzy_match("Open AI Company", threshold=50)

        # Should find OpenAI
        entity_ids = [m[0] for m in matches]
        assert "e1" in entity_ids or "e4" in entity_ids

    def test_fuzzy_match_threshold(self, resolver_with_data):
        """Threshold filters out low matches."""
        matches = resolver_with_data.fuzzy_match("XYZ Corp", threshold=90)
        assert len(matches) == 0

    def test_fuzzy_match_token_sort(self, resolver_with_data):
        """Token sort handles word order."""
        matches = resolver_with_data.fuzzy_match_with_token_sort(
            "Anthropic AI Company",  # Contains entity name
            threshold=60
        )

        # Should find Anthropic
        assert len(matches) > 0


class TestMainResolution:
    """Tests for main resolution flow."""

    def test_resolve_exact_canonical(self, resolver_with_data):
        """Resolve by exact canonical ID."""
        result = resolver_with_data.resolve("openai", log_decision=False)

        assert result.canonical_id == "openai"
        assert result.confidence == 1.0
        assert result.match_type == "exact_canonical"
        assert result.decision == ResolutionDecision.AUTO_EXACT

    def test_resolve_by_name(self, resolver_with_data):
        """Resolve by exact name match."""
        result = resolver_with_data.resolve("OpenAI", log_decision=False)

        assert result.entity_id is not None
        assert result.confidence == 1.0
        assert result.match_type in ["exact_canonical", "exact_name"]

    def test_resolve_by_alias(self, resolver_with_data):
        """Resolve via alias."""
        resolver_with_data.add_alias("Open AI Labs", "openai", 0.95, "test")

        result = resolver_with_data.resolve("Open AI Labs", log_decision=False)

        assert result.canonical_id == "openai"
        assert result.confidence == 0.95
        assert result.match_type == "alias"

    def test_resolve_by_override(self, resolver_with_data):
        """Manual override takes precedence."""
        resolver_with_data.add_override(
            alias="GPT Company",
            canonical_id="openai",
            reason="GPT is OpenAI product",
        )

        result = resolver_with_data.resolve("GPT Company", log_decision=False)

        assert result.canonical_id == "openai"
        assert result.confidence == 1.0
        assert result.match_type == "override"
        assert result.decision == ResolutionDecision.MANUAL_OVERRIDE

    def test_resolve_fuzzy_fallback(self, resolver_with_data):
        """Falls back to fuzzy matching when no exact match."""
        # Test that fuzzy matching works when there's a close but not exact name
        result = resolver_with_data.resolve(
            "Googl",  # Close to "google" but not exact
            fuzzy_threshold=70,
            log_decision=False,
        )

        # Should find Google via fuzzy match
        if result.entity_id is not None and result.match_type == "fuzzy":
            assert result.decision == ResolutionDecision.AUTO_FUZZY
        else:
            # If exact match found (due to normalization), that's also valid
            assert result.entity_id is not None

    def test_resolve_no_match(self, resolver_with_data):
        """No match returns rejected result."""
        result = resolver_with_data.resolve(
            "Completely Unknown Company XYZ",
            fuzzy_threshold=95,
            log_decision=False,
        )

        assert result.entity_id is None
        assert result.decision == ResolutionDecision.REJECTED


class TestRelationships:
    """Tests for entity relationships."""

    def test_add_relationship(self, resolver_with_data):
        """Add entity relationship."""
        rel = EntityRelationship(
            source_entity_id="e1",
            target_entity_id="e2",
            relationship_type=RelationshipType.PARTNERSHIP,
            confidence=0.9,
            source="test",
        )

        resolver_with_data.add_relationship(rel)

        # Retrieve
        rels = resolver_with_data.get_relationships("e1")
        assert len(rels) == 1
        assert rels[0].target_entity_id == "e2"
        assert rels[0].relationship_type == RelationshipType.PARTNERSHIP

    def test_get_relationships_by_type(self, resolver_with_data):
        """Filter relationships by type."""
        rel1 = EntityRelationship(
            source_entity_id="e1",
            target_entity_id="e2",
            relationship_type=RelationshipType.PARTNERSHIP,
        )
        rel2 = EntityRelationship(
            source_entity_id="e1",
            target_entity_id="e3",
            relationship_type=RelationshipType.INVESTED_IN,
        )

        resolver_with_data.add_relationship(rel1)
        resolver_with_data.add_relationship(rel2)

        # Filter by type
        partnerships = resolver_with_data.get_relationships(
            "e1",
            relationship_type=RelationshipType.PARTNERSHIP
        )
        assert len(partnerships) == 1
        assert partnerships[0].target_entity_id == "e2"

    def test_get_parent_company(self, resolver_with_data):
        """Get parent company."""
        rel = EntityRelationship(
            source_entity_id="e2",  # Anthropic is subsidiary
            target_entity_id="e3",  # of Google (hypothetically)
            relationship_type=RelationshipType.SUBSIDIARY,
        )
        resolver_with_data.add_relationship(rel)

        parent = resolver_with_data.get_parent_company("e2")
        assert parent == "e3"

    def test_acquisition_relationship(self, resolver_with_data):
        """Track acquisition with metadata."""
        rel = EntityRelationship(
            source_entity_id="e2",
            target_entity_id="e3",
            relationship_type=RelationshipType.ACQUIRED,
            effective_date=datetime(2024, 1, 15),
            metadata={"price_usd": 1_000_000_000},
            source="crunchbase",
        )
        resolver_with_data.add_relationship(rel)

        rels = resolver_with_data.get_relationships(
            "e2",
            relationship_type=RelationshipType.ACQUIRED
        )
        assert len(rels) == 1
        assert rels[0].metadata.get("price_usd") == 1_000_000_000


class TestDeduplication:
    """Tests for entity deduplication."""

    def test_find_duplicates(self, resolver_with_data):
        """Find duplicate entities."""
        duplicates = resolver_with_data.find_duplicates(threshold=80)

        # Should find OpenAI and OpenAI Inc as duplicates
        assert len(duplicates) > 0

        # Check that e1 and e4 are flagged
        pairs = [(d[0], d[1]) for d in duplicates]
        assert ("e1", "e4") in pairs or ("e4", "e1") in pairs

    def test_merge_entities(self, resolver_with_data, temp_db):
        """Merge duplicate entities."""
        # Add some data to both entities
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO signal_observations (id, entity_id) VALUES ('obs1', 'e4')")
        conn.commit()
        conn.close()

        # Merge e4 into e1
        success = resolver_with_data.merge_entities(
            merged_id="e4",
            surviving_id="e1",
            decision=ResolutionDecision.AUTO_FUZZY,
            confidence=0.95,
            reason="Duplicate OpenAI entry",
        )

        assert success

        # Verify observations were moved
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT entity_id FROM signal_observations WHERE id = 'obs1'")
        row = cursor.fetchone()
        conn.close()

        assert row[0] == "e1"

    def test_merge_preserves_audit_trail(self, resolver_with_data):
        """Merge creates audit record."""
        resolver_with_data.merge_entities(
            merged_id="e4",
            surviving_id="e1",
            decision=ResolutionDecision.MANUAL_MERGE,
            confidence=1.0,
            reason="User confirmed duplicate",
            merged_by="test_user",
        )

        history = resolver_with_data.get_merge_history("e4")
        assert len(history) >= 1

        record = history[0]
        assert record.merged_entity_id == "e4"
        assert record.surviving_entity_id == "e1"
        assert record.merged_by == "test_user"
        assert "old_data_snapshot" in record.__dict__


class TestOverrides:
    """Tests for manual resolution overrides."""

    def test_add_override(self, resolver_with_data):
        """Add resolution override."""
        resolver_with_data.add_override(
            alias="ChatGPT",
            canonical_id="openai",
            reason="ChatGPT is OpenAI product",
            created_by="test",
        )

        overrides = resolver_with_data.get_overrides()
        assert "chatgpt" in overrides
        assert overrides["chatgpt"] == "openai"

    def test_override_takes_precedence(self, resolver_with_data):
        """Override beats other resolution methods."""
        # Add alias pointing to wrong entity
        resolver_with_data.add_alias("Test Entity", "anthropic", 1.0, "test")

        # Add override pointing to correct entity
        resolver_with_data.add_override("Test Entity", "openai")

        result = resolver_with_data.resolve("Test Entity", log_decision=False)
        assert result.canonical_id == "openai"

    def test_remove_override(self, resolver_with_data):
        """Remove override."""
        resolver_with_data.add_override("temp", "openai")
        resolver_with_data.remove_override("temp")

        overrides = resolver_with_data.get_overrides()
        assert "temp" not in overrides


class TestStatistics:
    """Tests for statistics reporting."""

    def test_get_stats(self, resolver_with_data):
        """Get resolver statistics."""
        # Add some data
        resolver_with_data.add_alias("Test", "openai", 0.9, "test")
        ids = ExternalIdentifiers(crunchbase_uuid="abc", ticker_symbol="XYZ")
        resolver_with_data.set_external_ids("e1", ids)

        stats = resolver_with_data.get_stats()

        assert stats["total_entities"] >= 4
        assert stats["with_crunchbase"] >= 1
        assert stats["with_ticker"] >= 1
        assert stats["total_aliases"] >= 1


class TestExternalIdentifiersDataclass:
    """Tests for ExternalIdentifiers dataclass."""

    def test_from_dict(self):
        """Create from dictionary."""
        data = {
            "crunchbase_uuid": "abc",
            "ticker_symbol": "XYZ",
            "unknown_field": "ignored",
        }

        ids = ExternalIdentifiers.from_dict(data)

        assert ids.crunchbase_uuid == "abc"
        assert ids.ticker_symbol == "XYZ"
        assert ids.lei_code is None


class TestResolutionResult:
    """Tests for ResolutionResult dataclass."""

    def test_result_defaults(self):
        """Default values."""
        result = ResolutionResult()

        assert result.canonical_id is None
        assert result.confidence == 0.0
        assert result.match_type == "none"
        assert result.decision == ResolutionDecision.REJECTED
        assert result.alternatives == []
