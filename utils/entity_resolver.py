"""
Entity Resolver - Bloomberg-grade entity resolution for briefAI.

Provides robust entity resolution with:
- External ID mapping (Crunchbase UUID, ticker, LEI, Wikidata)
- Fuzzy alias resolution with confidence scores
- Parent/subsidiary relationship tracking
- Cross-scraper entity linking
- Deduplication with merge audit trail

This module extends the existing EntityMatcher with finance-grade identity resolution.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class RelationshipType(str, Enum):
    """Types of entity relationships."""
    PARENT = "parent"              # Parent company owns subsidiary
    SUBSIDIARY = "subsidiary"      # Subsidiary owned by parent
    ACQUIRED = "acquired"          # Company was acquired
    ACQUIRER = "acquirer"          # Company acquired another
    PRODUCT_OF = "product_of"      # Product belongs to company
    INVESTED_IN = "invested_in"    # Investor in company
    PARTNERSHIP = "partnership"    # Strategic partnership
    SPIN_OFF = "spin_off"          # Spun off from parent


class ResolutionDecision(str, Enum):
    """Types of resolution decisions for audit trail."""
    AUTO_EXACT = "auto_exact"           # Exact match
    AUTO_FUZZY = "auto_fuzzy"           # Fuzzy match above threshold
    AUTO_EXTERNAL_ID = "auto_external_id"  # Matched via external ID
    MANUAL_MERGE = "manual_merge"       # Manual merge decision
    MANUAL_OVERRIDE = "manual_override"  # Manual override of auto decision
    REJECTED = "rejected"               # Explicitly rejected match


@dataclass
class ExternalIdentifiers:
    """External identifiers for an entity."""
    crunchbase_uuid: Optional[str] = None
    crunchbase_permalink: Optional[str] = None
    ticker_symbol: Optional[str] = None
    exchange: Optional[str] = None  # NYSE, NASDAQ, etc.
    lei_code: Optional[str] = None  # Legal Entity Identifier
    wikidata_id: Optional[str] = None  # e.g., Q123456
    linkedin_id: Optional[str] = None
    domain: Optional[str] = None  # Primary website domain

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExternalIdentifiers":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AliasMapping:
    """An alias mapping with confidence score."""
    alias: str
    canonical_id: str
    confidence: float  # 0.0 - 1.0
    source: str  # Where this alias came from
    created_at: datetime = field(default_factory=datetime.utcnow)
    verified: bool = False  # Manually verified?

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alias": self.alias,
            "canonical_id": self.canonical_id,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "verified": self.verified,
        }


@dataclass
class EntityRelationship:
    """A relationship between two entities."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_entity_id: str = ""  # The entity this relationship is FROM
    target_entity_id: str = ""  # The entity this relationship is TO
    relationship_type: RelationshipType = RelationshipType.PARENT
    effective_date: Optional[datetime] = None  # When relationship started
    end_date: Optional[datetime] = None  # When relationship ended (for acquisitions)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Additional info (price, etc.)
    confidence: float = 1.0
    source: str = "manual"  # Where this relationship came from
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_entity_id": self.source_entity_id,
            "target_entity_id": self.target_entity_id,
            "relationship_type": self.relationship_type.value,
            "effective_date": self.effective_date.isoformat() if self.effective_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MergeAuditRecord:
    """Audit trail for entity merges."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    merged_entity_id: str = ""  # Entity that was merged away
    surviving_entity_id: str = ""  # Entity that survived
    decision: ResolutionDecision = ResolutionDecision.AUTO_FUZZY
    confidence: float = 0.0
    reason: str = ""
    merged_at: datetime = field(default_factory=datetime.utcnow)
    merged_by: str = "system"  # User or system
    old_data_snapshot: Dict[str, Any] = field(default_factory=dict)  # Preserve old data

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "merged_entity_id": self.merged_entity_id,
            "surviving_entity_id": self.surviving_entity_id,
            "decision": self.decision.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "merged_at": self.merged_at.isoformat(),
            "merged_by": self.merged_by,
            "old_data_snapshot": self.old_data_snapshot,
        }


@dataclass
class ResolutionResult:
    """Result of entity resolution."""
    canonical_id: Optional[str] = None
    entity_id: Optional[str] = None  # Database ID
    name: Optional[str] = None
    confidence: float = 0.0
    match_type: str = "none"  # exact, fuzzy, external_id, alias
    external_ids: Optional[ExternalIdentifiers] = None
    alternatives: List[Tuple[str, float]] = field(default_factory=list)  # Other candidates
    decision: ResolutionDecision = ResolutionDecision.REJECTED


class EntityResolver:
    """
    Bloomberg-grade entity resolver.

    Provides robust entity resolution with external ID mapping,
    fuzzy matching, relationship tracking, and deduplication.
    """

    # Suffixes to strip for normalization
    SUFFIXES = [
        r"\s*,?\s*inc\.?$",
        r"\s*,?\s*llc\.?$",
        r"\s*,?\s*ltd\.?$",
        r"\s*,?\s*corp\.?$",
        r"\s*,?\s*pbc\.?$",
        r"\s*,?\s*co\.?$",
        r"\s*,?\s*limited$",
        r"\s*,?\s*incorporated$",
        r"\s*,?\s*corporation$",
        r"\s*,?\s*gmbh$",
        r"\s*,?\s*ag$",
        r"\s*,?\s*s\.?a\.?$",
        r"\s*,?\s*plc$",
    ]

    def __init__(self, db_path: Optional[str] = None):
        """Initialize entity resolver."""
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "signals.db")

        self.db_path = db_path
        self._ensure_tables()
        self._load_caches()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create additional tables for entity resolution."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # External identifiers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_external_ids (
                entity_id TEXT PRIMARY KEY,
                crunchbase_uuid TEXT,
                crunchbase_permalink TEXT,
                ticker_symbol TEXT,
                exchange TEXT,
                lei_code TEXT,
                wikidata_id TEXT,
                linkedin_id TEXT,
                domain TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ext_crunchbase ON entity_external_ids(crunchbase_uuid)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ext_ticker ON entity_external_ids(ticker_symbol)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ext_lei ON entity_external_ids(lei_code)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ext_wikidata ON entity_external_ids(wikidata_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_ext_domain ON entity_external_ids(domain)")

        # Alias mappings table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL,
                normalized_alias TEXT NOT NULL,
                canonical_id TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'manual',
                verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(normalized_alias, canonical_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_normalized ON entity_aliases(normalized_alias)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_alias_canonical ON entity_aliases(canonical_id)")

        # Entity relationships table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_relationships (
                id TEXT PRIMARY KEY,
                source_entity_id TEXT NOT NULL,
                target_entity_id TEXT NOT NULL,
                relationship_type TEXT NOT NULL,
                effective_date TIMESTAMP,
                end_date TIMESTAMP,
                metadata TEXT,
                confidence REAL DEFAULT 1.0,
                source TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_entity_id) REFERENCES entities(id),
                FOREIGN KEY (target_entity_id) REFERENCES entities(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_source ON entity_relationships(source_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_target ON entity_relationships(target_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rel_type ON entity_relationships(relationship_type)")

        # Merge audit trail
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_merge_audit (
                id TEXT PRIMARY KEY,
                merged_entity_id TEXT NOT NULL,
                surviving_entity_id TEXT NOT NULL,
                decision TEXT NOT NULL,
                confidence REAL,
                reason TEXT,
                merged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                merged_by TEXT DEFAULT 'system',
                old_data_snapshot TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_merge_merged ON entity_merge_audit(merged_entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_merge_surviving ON entity_merge_audit(surviving_entity_id)")

        # Manual overrides table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_resolution_overrides (
                alias TEXT PRIMARY KEY,
                canonical_id TEXT NOT NULL,
                reason TEXT,
                created_by TEXT DEFAULT 'system',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Resolution decisions log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entity_resolution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_name TEXT NOT NULL,
                resolved_to TEXT,
                decision TEXT NOT NULL,
                confidence REAL,
                source TEXT,
                context TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reslog_input ON entity_resolution_log(input_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_reslog_resolved ON entity_resolution_log(resolved_to)")

        conn.commit()
        conn.close()

    def _load_caches(self):
        """Load frequently-accessed data into memory."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Load alias -> canonical_id mapping
        self._alias_cache: Dict[str, Tuple[str, float]] = {}
        cursor.execute("SELECT normalized_alias, canonical_id, confidence FROM entity_aliases")
        for row in cursor.fetchall():
            self._alias_cache[row["normalized_alias"]] = (row["canonical_id"], row["confidence"])

        # Load overrides
        self._overrides: Dict[str, str] = {}
        cursor.execute("SELECT alias, canonical_id FROM entity_resolution_overrides")
        for row in cursor.fetchall():
            self._overrides[self.normalize_name(row["alias"])] = row["canonical_id"]

        # Load external ID lookups
        self._crunchbase_to_entity: Dict[str, str] = {}
        self._ticker_to_entity: Dict[str, str] = {}
        self._wikidata_to_entity: Dict[str, str] = {}
        self._domain_to_entity: Dict[str, str] = {}

        cursor.execute("SELECT entity_id, crunchbase_uuid, ticker_symbol, wikidata_id, domain FROM entity_external_ids")
        for row in cursor.fetchall():
            if row["crunchbase_uuid"]:
                self._crunchbase_to_entity[row["crunchbase_uuid"]] = row["entity_id"]
            if row["ticker_symbol"]:
                self._ticker_to_entity[row["ticker_symbol"].upper()] = row["entity_id"]
            if row["wikidata_id"]:
                self._wikidata_to_entity[row["wikidata_id"]] = row["entity_id"]
            if row["domain"]:
                self._domain_to_entity[row["domain"].lower()] = row["entity_id"]

        # Load entity names for fuzzy matching
        self._entity_names: Dict[str, str] = {}  # normalized_name -> entity_id
        self._canonical_ids: Dict[str, str] = {}  # canonical_id -> entity_id
        cursor.execute("SELECT id, canonical_id, name FROM entities")
        for row in cursor.fetchall():
            self._entity_names[self.normalize_name(row["name"])] = row["id"]
            self._canonical_ids[row["canonical_id"]] = row["id"]

        conn.close()

    def normalize_name(self, name: str) -> str:
        """Normalize company name for matching."""
        if not name:
            return ""

        name = name.lower().strip()

        # Remove common suffixes
        for suffix in self.SUFFIXES:
            name = re.sub(suffix, "", name, flags=re.IGNORECASE)

        # Remove extra whitespace
        name = re.sub(r"\s+", " ", name).strip()

        return name

    def refresh_caches(self):
        """Refresh in-memory caches from database."""
        self._load_caches()

    # =========================================================================
    # External ID Lookups
    # =========================================================================

    def lookup_by_crunchbase(self, cb_uuid: str) -> Optional[str]:
        """Look up entity by Crunchbase UUID."""
        return self._crunchbase_to_entity.get(cb_uuid)

    def lookup_by_ticker(self, ticker: str) -> Optional[str]:
        """Look up entity by stock ticker."""
        return self._ticker_to_entity.get(ticker.upper())

    def lookup_by_wikidata(self, wikidata_id: str) -> Optional[str]:
        """Look up entity by Wikidata ID."""
        return self._wikidata_to_entity.get(wikidata_id)

    def lookup_by_domain(self, domain: str) -> Optional[str]:
        """Look up entity by website domain."""
        domain = domain.lower().replace("https://", "").replace("http://", "").split("/")[0]
        return self._domain_to_entity.get(domain)

    def get_external_ids(self, entity_id: str) -> Optional[ExternalIdentifiers]:
        """Get external identifiers for an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM entity_external_ids WHERE entity_id = ?", (entity_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return ExternalIdentifiers(
                crunchbase_uuid=row["crunchbase_uuid"],
                crunchbase_permalink=row["crunchbase_permalink"],
                ticker_symbol=row["ticker_symbol"],
                exchange=row["exchange"],
                lei_code=row["lei_code"],
                wikidata_id=row["wikidata_id"],
                linkedin_id=row["linkedin_id"],
                domain=row["domain"],
            )
        return None

    def set_external_ids(self, entity_id: str, ids: ExternalIdentifiers):
        """Set external identifiers for an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entity_external_ids (
                entity_id, crunchbase_uuid, crunchbase_permalink, ticker_symbol,
                exchange, lei_code, wikidata_id, linkedin_id, domain, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(entity_id) DO UPDATE SET
                crunchbase_uuid = COALESCE(excluded.crunchbase_uuid, crunchbase_uuid),
                crunchbase_permalink = COALESCE(excluded.crunchbase_permalink, crunchbase_permalink),
                ticker_symbol = COALESCE(excluded.ticker_symbol, ticker_symbol),
                exchange = COALESCE(excluded.exchange, exchange),
                lei_code = COALESCE(excluded.lei_code, lei_code),
                wikidata_id = COALESCE(excluded.wikidata_id, wikidata_id),
                linkedin_id = COALESCE(excluded.linkedin_id, linkedin_id),
                domain = COALESCE(excluded.domain, domain),
                updated_at = excluded.updated_at
        """, (
            entity_id,
            ids.crunchbase_uuid,
            ids.crunchbase_permalink,
            ids.ticker_symbol,
            ids.exchange,
            ids.lei_code,
            ids.wikidata_id,
            ids.linkedin_id,
            ids.domain,
            datetime.utcnow().isoformat(),
        ))

        conn.commit()
        conn.close()

        # Update caches
        if ids.crunchbase_uuid:
            self._crunchbase_to_entity[ids.crunchbase_uuid] = entity_id
        if ids.ticker_symbol:
            self._ticker_to_entity[ids.ticker_symbol.upper()] = entity_id
        if ids.wikidata_id:
            self._wikidata_to_entity[ids.wikidata_id] = entity_id
        if ids.domain:
            self._domain_to_entity[ids.domain.lower()] = entity_id

    # =========================================================================
    # Alias Resolution
    # =========================================================================

    def add_alias(
        self,
        alias: str,
        canonical_id: str,
        confidence: float = 1.0,
        source: str = "manual",
        verified: bool = False,
    ):
        """Add an alias mapping."""
        normalized = self.normalize_name(alias)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entity_aliases (alias, normalized_alias, canonical_id, confidence, source, verified)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_alias, canonical_id) DO UPDATE SET
                confidence = MAX(excluded.confidence, confidence),
                verified = MAX(excluded.verified, verified)
        """, (alias, normalized, canonical_id, confidence, source, int(verified)))

        conn.commit()
        conn.close()

        # Update cache
        if normalized not in self._alias_cache or confidence > self._alias_cache[normalized][1]:
            self._alias_cache[normalized] = (canonical_id, confidence)

    def get_aliases(self, canonical_id: str) -> List[AliasMapping]:
        """Get all aliases for a canonical ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT alias, normalized_alias, canonical_id, confidence, source, verified, created_at
            FROM entity_aliases WHERE canonical_id = ?
        """, (canonical_id,))

        aliases = []
        for row in cursor.fetchall():
            aliases.append(AliasMapping(
                alias=row["alias"],
                canonical_id=row["canonical_id"],
                confidence=row["confidence"],
                source=row["source"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
                verified=bool(row["verified"]),
            ))

        conn.close()
        return aliases

    def resolve_alias(self, name: str) -> Optional[Tuple[str, float]]:
        """Resolve an alias to canonical ID with confidence."""
        normalized = self.normalize_name(name)

        # Check overrides first
        if normalized in self._overrides:
            return (self._overrides[normalized], 1.0)

        # Check alias cache
        if normalized in self._alias_cache:
            return self._alias_cache[normalized]

        return None

    # =========================================================================
    # Fuzzy Matching
    # =========================================================================

    def fuzzy_match(
        self,
        name: str,
        threshold: int = 85,
        limit: int = 5,
    ) -> List[Tuple[str, str, float]]:
        """
        Find fuzzy matches for a name.

        Returns list of (entity_id, name, score) tuples.
        """
        normalized = self.normalize_name(name)

        if not self._entity_names:
            return []

        # Use rapidfuzz for fast fuzzy matching
        matches = process.extract(
            normalized,
            list(self._entity_names.keys()),
            scorer=fuzz.ratio,
            limit=limit,
            score_cutoff=threshold,
        )

        results = []
        for match_name, score, _ in matches:
            entity_id = self._entity_names[match_name]
            results.append((entity_id, match_name, score / 100.0))

        return results

    def fuzzy_match_with_token_sort(
        self,
        name: str,
        threshold: int = 80,
        limit: int = 5,
    ) -> List[Tuple[str, str, float]]:
        """
        Fuzzy match using token sort ratio (handles word order differences).

        Better for "AI OpenAI" vs "OpenAI AI".
        """
        normalized = self.normalize_name(name)

        if not self._entity_names:
            return []

        matches = process.extract(
            normalized,
            list(self._entity_names.keys()),
            scorer=fuzz.token_sort_ratio,
            limit=limit,
            score_cutoff=threshold,
        )

        results = []
        for match_name, score, _ in matches:
            entity_id = self._entity_names[match_name]
            results.append((entity_id, match_name, score / 100.0))

        return results

    # =========================================================================
    # Main Resolution
    # =========================================================================

    def resolve(
        self,
        name: str,
        source: str = "",
        context: str = "",
        fuzzy_threshold: int = 85,
        log_decision: bool = True,
    ) -> ResolutionResult:
        """
        Resolve a name to a canonical entity.

        Resolution order:
        1. Manual override lookup
        2. Exact canonical_id match
        3. Exact name match
        4. Alias lookup
        5. External ID match (domain, ticker)
        6. Fuzzy match

        Args:
            name: Entity name to resolve
            source: Source of the mention (github, crunchbase, news, etc.)
            context: Additional context for disambiguation
            fuzzy_threshold: Minimum fuzzy match score (0-100)
            log_decision: Whether to log the resolution decision

        Returns:
            ResolutionResult with entity details and confidence
        """
        if not name or not name.strip():
            return ResolutionResult()

        normalized = self.normalize_name(name)
        result = ResolutionResult()

        # 1. Check manual overrides
        if normalized in self._overrides:
            canonical_id = self._overrides[normalized]
            if canonical_id in self._canonical_ids:
                result.canonical_id = canonical_id
                result.entity_id = self._canonical_ids[canonical_id]
                result.confidence = 1.0
                result.match_type = "override"
                result.decision = ResolutionDecision.MANUAL_OVERRIDE
                return self._finalize_result(result, name, source, context, log_decision)

        # 2. Exact canonical_id match
        if normalized in self._canonical_ids:
            result.canonical_id = normalized
            result.entity_id = self._canonical_ids[normalized]
            result.confidence = 1.0
            result.match_type = "exact_canonical"
            result.decision = ResolutionDecision.AUTO_EXACT
            return self._finalize_result(result, name, source, context, log_decision)

        # 3. Exact name match
        if normalized in self._entity_names:
            result.entity_id = self._entity_names[normalized]
            result.confidence = 1.0
            result.match_type = "exact_name"
            result.decision = ResolutionDecision.AUTO_EXACT
            return self._finalize_result(result, name, source, context, log_decision)

        # 4. Alias lookup
        alias_result = self.resolve_alias(name)
        if alias_result:
            canonical_id, confidence = alias_result
            if canonical_id in self._canonical_ids:
                result.canonical_id = canonical_id
                result.entity_id = self._canonical_ids[canonical_id]
                result.confidence = confidence
                result.match_type = "alias"
                result.decision = ResolutionDecision.AUTO_EXACT if confidence >= 1.0 else ResolutionDecision.AUTO_FUZZY
                return self._finalize_result(result, name, source, context, log_decision)

        # 5. External ID lookup (try domain extraction from name)
        domain_match = re.search(r"(\w+\.(com|ai|io|co|org|net))", name.lower())
        if domain_match:
            domain = domain_match.group(1)
            entity_id = self.lookup_by_domain(domain)
            if entity_id:
                result.entity_id = entity_id
                result.confidence = 0.9
                result.match_type = "domain"
                result.decision = ResolutionDecision.AUTO_EXTERNAL_ID
                return self._finalize_result(result, name, source, context, log_decision)

        # 6. Fuzzy match
        fuzzy_matches = self.fuzzy_match(name, threshold=fuzzy_threshold)
        if fuzzy_matches:
            best_match = fuzzy_matches[0]
            result.entity_id = best_match[0]
            result.confidence = best_match[2]
            result.match_type = "fuzzy"
            result.alternatives = [(m[0], m[2]) for m in fuzzy_matches[1:]]
            result.decision = ResolutionDecision.AUTO_FUZZY
            return self._finalize_result(result, name, source, context, log_decision)

        # No match found
        result.decision = ResolutionDecision.REJECTED
        if log_decision:
            self._log_decision(name, None, result.decision, 0.0, source, context)

        return result

    def _finalize_result(
        self,
        result: ResolutionResult,
        input_name: str,
        source: str,
        context: str,
        log_decision: bool,
    ) -> ResolutionResult:
        """Finalize resolution result with entity details."""
        if result.entity_id:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT canonical_id, name FROM entities WHERE id = ?", (result.entity_id,))
            row = cursor.fetchone()
            if row:
                result.canonical_id = result.canonical_id or row["canonical_id"]
                result.name = row["name"]

            conn.close()

            # Get external IDs
            result.external_ids = self.get_external_ids(result.entity_id)

        if log_decision:
            self._log_decision(input_name, result.canonical_id, result.decision, result.confidence, source, context)

        return result

    def _log_decision(
        self,
        input_name: str,
        resolved_to: Optional[str],
        decision: ResolutionDecision,
        confidence: float,
        source: str,
        context: str,
    ):
        """Log a resolution decision."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entity_resolution_log (input_name, resolved_to, decision, confidence, source, context)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (input_name, resolved_to, decision.value, confidence, source, context[:500] if context else None))

        conn.commit()
        conn.close()

    # =========================================================================
    # Relationship Management
    # =========================================================================

    def add_relationship(self, relationship: EntityRelationship):
        """Add an entity relationship."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entity_relationships (
                id, source_entity_id, target_entity_id, relationship_type,
                effective_date, end_date, metadata, confidence, source, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                relationship_type = excluded.relationship_type,
                effective_date = excluded.effective_date,
                end_date = excluded.end_date,
                metadata = excluded.metadata,
                confidence = excluded.confidence
        """, (
            relationship.id,
            relationship.source_entity_id,
            relationship.target_entity_id,
            relationship.relationship_type.value,
            relationship.effective_date.isoformat() if relationship.effective_date else None,
            relationship.end_date.isoformat() if relationship.end_date else None,
            json.dumps(relationship.metadata),
            relationship.confidence,
            relationship.source,
            relationship.created_at.isoformat(),
        ))

        conn.commit()
        conn.close()

    def get_relationships(
        self,
        entity_id: str,
        relationship_type: Optional[RelationshipType] = None,
        direction: str = "both",  # "outgoing", "incoming", "both"
    ) -> List[EntityRelationship]:
        """Get relationships for an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM entity_relationships WHERE 1=1"
        params: List[Any] = []

        if direction in ("outgoing", "both"):
            query += " AND (source_entity_id = ?"
            params.append(entity_id)
            if direction == "both":
                query += " OR target_entity_id = ?)"
                params.append(entity_id)
            else:
                query += ")"
        elif direction == "incoming":
            query += " AND target_entity_id = ?"
            params.append(entity_id)

        if relationship_type:
            query += " AND relationship_type = ?"
            params.append(relationship_type.value)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        relationships = []
        for row in rows:
            relationships.append(EntityRelationship(
                id=row["id"],
                source_entity_id=row["source_entity_id"],
                target_entity_id=row["target_entity_id"],
                relationship_type=RelationshipType(row["relationship_type"]),
                effective_date=datetime.fromisoformat(row["effective_date"]) if row["effective_date"] else None,
                end_date=datetime.fromisoformat(row["end_date"]) if row["end_date"] else None,
                metadata=json.loads(row["metadata"]) if row["metadata"] else {},
                confidence=row["confidence"],
                source=row["source"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            ))

        return relationships

    def get_parent_company(self, entity_id: str) -> Optional[str]:
        """Get the parent company of an entity."""
        relationships = self.get_relationships(
            entity_id,
            relationship_type=RelationshipType.SUBSIDIARY,
            direction="outgoing",
        )
        if relationships:
            return relationships[0].target_entity_id
        return None

    def get_subsidiaries(self, entity_id: str) -> List[str]:
        """Get all subsidiaries of a company."""
        relationships = self.get_relationships(
            entity_id,
            relationship_type=RelationshipType.PARENT,
            direction="outgoing",
        )
        return [r.target_entity_id for r in relationships]

    def get_products(self, entity_id: str) -> List[str]:
        """Get all products of a company."""
        relationships = self.get_relationships(
            entity_id,
            relationship_type=RelationshipType.PRODUCT_OF,
            direction="incoming",
        )
        return [r.source_entity_id for r in relationships]

    # =========================================================================
    # Deduplication
    # =========================================================================

    def find_duplicates(
        self,
        threshold: int = 90,
        limit: int = 100,
    ) -> List[Tuple[str, str, float]]:
        """
        Find potential duplicate entities.

        Returns list of (entity1_id, entity2_id, similarity) tuples.
        """
        duplicates = []

        # Get all entity names
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, canonical_id, name FROM entities")
        entities = [(row["id"], row["canonical_id"], row["name"]) for row in cursor.fetchall()]
        conn.close()

        # Compare each pair (O(n²) but necessary for deduplication)
        seen_pairs: Set[Tuple[str, str]] = set()

        for i, (id1, canonical1, name1) in enumerate(entities):
            for id2, canonical2, name2 in entities[i + 1:]:
                if (id1, id2) in seen_pairs or (id2, id1) in seen_pairs:
                    continue

                # Skip if same entity
                if id1 == id2:
                    continue

                # Compare normalized names
                norm1 = self.normalize_name(name1)
                norm2 = self.normalize_name(name2)

                score = fuzz.ratio(norm1, norm2)
                if score >= threshold:
                    duplicates.append((id1, id2, score / 100.0))
                    seen_pairs.add((id1, id2))

                    if len(duplicates) >= limit:
                        return duplicates

        return duplicates

    def merge_entities(
        self,
        merged_id: str,
        surviving_id: str,
        decision: ResolutionDecision = ResolutionDecision.AUTO_FUZZY,
        confidence: float = 0.0,
        reason: str = "",
        merged_by: str = "system",
    ) -> bool:
        """
        Merge one entity into another, preserving history.

        The merged entity is marked as merged (not deleted) and all references
        are updated to point to the surviving entity.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Get old data for audit
            cursor.execute("SELECT * FROM entities WHERE id = ?", (merged_id,))
            old_row = cursor.fetchone()
            if not old_row:
                logger.warning(f"Entity {merged_id} not found for merge")
                return False

            old_data = dict(old_row)

            # Create audit record
            audit = MergeAuditRecord(
                merged_entity_id=merged_id,
                surviving_entity_id=surviving_id,
                decision=decision,
                confidence=confidence,
                reason=reason,
                merged_by=merged_by,
                old_data_snapshot=old_data,
            )

            cursor.execute("""
                INSERT INTO entity_merge_audit (
                    id, merged_entity_id, surviving_entity_id, decision,
                    confidence, reason, merged_at, merged_by, old_data_snapshot
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                audit.id,
                audit.merged_entity_id,
                audit.surviving_entity_id,
                audit.decision.value,
                audit.confidence,
                audit.reason,
                audit.merged_at.isoformat(),
                audit.merged_by,
                json.dumps(audit.old_data_snapshot),
            ))

            # Update all references from merged to surviving
            # Signal observations
            cursor.execute(
                "UPDATE signal_observations SET entity_id = ? WHERE entity_id = ?",
                (surviving_id, merged_id)
            )

            # Signal scores
            cursor.execute(
                "UPDATE signal_scores SET entity_id = ? WHERE entity_id = ?",
                (surviving_id, merged_id)
            )

            # Signal profiles
            cursor.execute(
                "UPDATE signal_profiles SET entity_id = ? WHERE entity_id = ?",
                (surviving_id, merged_id)
            )

            # Relationships (update both source and target)
            cursor.execute(
                "UPDATE entity_relationships SET source_entity_id = ? WHERE source_entity_id = ?",
                (surviving_id, merged_id)
            )
            cursor.execute(
                "UPDATE entity_relationships SET target_entity_id = ? WHERE target_entity_id = ?",
                (surviving_id, merged_id)
            )

            # External IDs - merge if surviving doesn't have them
            cursor.execute("SELECT * FROM entity_external_ids WHERE entity_id = ?", (merged_id,))
            merged_ext = cursor.fetchone()
            if merged_ext:
                cursor.execute("SELECT * FROM entity_external_ids WHERE entity_id = ?", (surviving_id,))
                surviving_ext = cursor.fetchone()

                if surviving_ext:
                    # Merge missing values
                    cursor.execute("""
                        UPDATE entity_external_ids SET
                            crunchbase_uuid = COALESCE(crunchbase_uuid, ?),
                            crunchbase_permalink = COALESCE(crunchbase_permalink, ?),
                            ticker_symbol = COALESCE(ticker_symbol, ?),
                            exchange = COALESCE(exchange, ?),
                            lei_code = COALESCE(lei_code, ?),
                            wikidata_id = COALESCE(wikidata_id, ?),
                            linkedin_id = COALESCE(linkedin_id, ?),
                            domain = COALESCE(domain, ?)
                        WHERE entity_id = ?
                    """, (
                        merged_ext["crunchbase_uuid"],
                        merged_ext["crunchbase_permalink"],
                        merged_ext["ticker_symbol"],
                        merged_ext["exchange"],
                        merged_ext["lei_code"],
                        merged_ext["wikidata_id"],
                        merged_ext["linkedin_id"],
                        merged_ext["domain"],
                        surviving_id,
                    ))
                else:
                    # Move external IDs to surviving
                    cursor.execute(
                        "UPDATE entity_external_ids SET entity_id = ? WHERE entity_id = ?",
                        (surviving_id, merged_id)
                    )

            # Add old aliases to surviving entity
            old_aliases = json.loads(old_data.get("aliases", "[]"))
            old_name = old_data.get("name")
            if old_name:
                old_aliases.append(old_name)

            for alias in old_aliases:
                cursor.execute("""
                    INSERT OR IGNORE INTO entity_aliases (alias, normalized_alias, canonical_id, confidence, source, verified)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (alias, self.normalize_name(alias), old_data.get("canonical_id"), 1.0, "merge", 1))

            # Delete the merged entity (or mark as merged)
            cursor.execute("DELETE FROM entities WHERE id = ?", (merged_id,))

            conn.commit()
            logger.info(f"Merged entity {merged_id} into {surviving_id}")

            # Refresh caches
            self.refresh_caches()

            return True

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to merge entities: {e}")
            return False

        finally:
            conn.close()

    def get_merge_history(self, entity_id: str) -> List[MergeAuditRecord]:
        """Get merge audit history for an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM entity_merge_audit
            WHERE merged_entity_id = ? OR surviving_entity_id = ?
            ORDER BY merged_at DESC
        """, (entity_id, entity_id))

        records = []
        for row in cursor.fetchall():
            records.append(MergeAuditRecord(
                id=row["id"],
                merged_entity_id=row["merged_entity_id"],
                surviving_entity_id=row["surviving_entity_id"],
                decision=ResolutionDecision(row["decision"]),
                confidence=row["confidence"],
                reason=row["reason"],
                merged_at=datetime.fromisoformat(row["merged_at"]) if row["merged_at"] else datetime.utcnow(),
                merged_by=row["merged_by"],
                old_data_snapshot=json.loads(row["old_data_snapshot"]) if row["old_data_snapshot"] else {},
            ))

        conn.close()
        return records

    # =========================================================================
    # Overrides
    # =========================================================================

    def add_override(self, alias: str, canonical_id: str, reason: str = "", created_by: str = "system"):
        """Add a manual resolution override."""
        normalized = self.normalize_name(alias)

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entity_resolution_overrides (alias, canonical_id, reason, created_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(alias) DO UPDATE SET
                canonical_id = excluded.canonical_id,
                reason = excluded.reason,
                created_by = excluded.created_by,
                created_at = CURRENT_TIMESTAMP
        """, (normalized, canonical_id, reason, created_by))

        conn.commit()
        conn.close()

        # Update cache
        self._overrides[normalized] = canonical_id

    def remove_override(self, alias: str):
        """Remove a resolution override."""
        normalized = self.normalize_name(alias)

        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM entity_resolution_overrides WHERE alias = ?", (normalized,))
        conn.commit()
        conn.close()

        # Update cache
        if normalized in self._overrides:
            del self._overrides[normalized]

    def get_overrides(self) -> Dict[str, str]:
        """Get all resolution overrides."""
        return self._overrides.copy()

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get entity resolution statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        stats = {}

        # Entity counts
        cursor.execute("SELECT COUNT(*) FROM entities")
        stats["total_entities"] = cursor.fetchone()[0]

        # External IDs coverage
        cursor.execute("SELECT COUNT(*) FROM entity_external_ids WHERE crunchbase_uuid IS NOT NULL")
        stats["with_crunchbase"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM entity_external_ids WHERE ticker_symbol IS NOT NULL")
        stats["with_ticker"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM entity_external_ids WHERE wikidata_id IS NOT NULL")
        stats["with_wikidata"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM entity_external_ids WHERE lei_code IS NOT NULL")
        stats["with_lei"] = cursor.fetchone()[0]

        # Aliases
        cursor.execute("SELECT COUNT(*) FROM entity_aliases")
        stats["total_aliases"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM entity_aliases WHERE verified = 1")
        stats["verified_aliases"] = cursor.fetchone()[0]

        # Relationships
        cursor.execute("SELECT COUNT(*) FROM entity_relationships")
        stats["total_relationships"] = cursor.fetchone()[0]

        cursor.execute("SELECT relationship_type, COUNT(*) FROM entity_relationships GROUP BY relationship_type")
        stats["relationships_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Merges
        cursor.execute("SELECT COUNT(*) FROM entity_merge_audit")
        stats["total_merges"] = cursor.fetchone()[0]

        # Resolution log stats
        cursor.execute("""
            SELECT decision, COUNT(*) FROM entity_resolution_log
            GROUP BY decision
        """)
        stats["resolutions_by_decision"] = {row[0]: row[1] for row in cursor.fetchall()}

        # Overrides
        stats["total_overrides"] = len(self._overrides)

        conn.close()
        return stats


# Convenience functions
def resolve_entity(name: str, source: str = "", context: str = "") -> ResolutionResult:
    """Quick entity resolution using default resolver."""
    resolver = EntityResolver()
    return resolver.resolve(name, source, context)


def get_entity_external_ids(entity_id: str) -> Optional[ExternalIdentifiers]:
    """Get external IDs for an entity."""
    resolver = EntityResolver()
    return resolver.get_external_ids(entity_id)
