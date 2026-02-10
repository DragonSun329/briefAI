"""
Data Validator for Bloomberg Terminal-Grade Claim Verification.

Integrates:
- Cross-source verification with agreement scoring
- Citation tracing (who reported first, who confirmed)
- Source reliability weighting
- Configurable validation rules engine
- Audit trail logging

This is the main entry point for validating claims before storage.
"""

import hashlib
import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from utils.source_reliability import SourceReliabilityTracker, SourceReliabilityScore
from utils.audit_log import AuditLogger

logger = logging.getLogger(__name__)


@dataclass
class Claim:
    """A claim about an entity from a source."""
    entity_id: str
    claim_type: str           # funding_amount, valuation, employee_count, etc.
    claim_value: Any          # The actual value
    claim_unit: Optional[str] = None  # usd, count, percent
    source_id: str = "unknown"
    source_confidence: float = 1.0
    observed_at: datetime = field(default_factory=datetime.utcnow)
    claim_date: Optional[str] = None  # Date the claim refers to (e.g., "2024-Q4")
    raw_data: Dict[str, Any] = field(default_factory=dict)
    observation_id: Optional[str] = None  # Link to signal_observations


@dataclass
class ClaimValidationResult:
    """Result of validating a claim."""
    claim: Claim
    is_valid: bool
    validation_status: str      # pending, validated, conflict, rejected, review_required
    confidence_score: float     # 0-1
    
    # Citation tracing
    is_first_report: bool
    first_reported_by: Optional[str]
    first_reported_at: Optional[datetime]
    confirmed_by: List[str] = field(default_factory=list)
    
    # Cross-source verification
    source_count: int = 1
    agreement_score: float = 1.0
    conflicting_values: List[Dict[str, Any]] = field(default_factory=list)
    
    # Rule evaluation
    rules_evaluated: List[str] = field(default_factory=list)
    rules_passed: List[str] = field(default_factory=list)
    rules_failed: List[str] = field(default_factory=list)
    
    # Actions
    requires_review: bool = False
    review_reason: Optional[str] = None
    
    # Claim registry ID
    claim_hash: Optional[str] = None
    registry_id: Optional[str] = None


@dataclass
class ValidationRuleResult:
    """Result of evaluating a single validation rule."""
    rule_name: str
    passed: bool
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class DataValidator:
    """
    Main validation layer for claim verification.
    
    Usage:
        validator = DataValidator()
        result = validator.validate_claim(claim)
        
        if result.is_valid:
            # Proceed with storage
        else:
            # Handle validation failure
    """
    
    def __init__(
        self,
        db_path: Optional[str] = None,
        rules_path: Optional[str] = None,
        enable_audit: bool = True,
        bypass_validation: bool = False,
    ):
        """
        Initialize data validator.
        
        Args:
            db_path: Path to signals database
            rules_path: Path to validation_rules.json
            enable_audit: Whether to log all validation decisions
            bypass_validation: Skip validation (for speed in bulk imports)
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "signals.db")
        self.db_path = db_path
        
        self.bypass_validation = bypass_validation
        self.enable_audit = enable_audit
        
        # Load validation rules
        if rules_path is None:
            rules_path = Path(__file__).parent.parent / "config" / "validation_rules.json"
        self._load_rules(rules_path)
        
        # Initialize components
        self.reliability_tracker = SourceReliabilityTracker(db_path)
        self.audit_logger = AuditLogger(db_path) if enable_audit else None
        
        # Ensure tables exist
        self._ensure_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _load_rules(self, rules_path: Path):
        """Load validation rules configuration."""
        try:
            with open(rules_path, encoding="utf-8") as f:
                self.rules_config = json.load(f)
            
            self.global_settings = self.rules_config.get("global_settings", {})
            self.claim_type_rules = self.rules_config.get("claim_types", {})
            self.source_tiers = self.rules_config.get("source_tiers", {})
            self.conflict_strategies = self.rules_config.get("conflict_resolution_strategies", {})
            
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load validation_rules.json: {e}")
            self.rules_config = {}
            self.global_settings = {
                "default_min_sources": 1,
                "high_value_min_sources": 2,
                "high_value_threshold_usd": 100000000,
            }
            self.claim_type_rules = {}
            self.source_tiers = {}
            self.conflict_strategies = {}
    
    def _ensure_tables(self):
        """Ensure validation tables exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Claim registry table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS claim_registry (
                id TEXT PRIMARY KEY,
                claim_hash TEXT NOT NULL UNIQUE,
                claim_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                claim_value TEXT NOT NULL,
                claim_value_numeric REAL,
                claim_unit TEXT,
                claim_date TEXT,
                first_source_id TEXT NOT NULL,
                first_observed_at TIMESTAMP NOT NULL,
                confirming_sources TEXT,
                conflicting_sources TEXT,
                source_count INTEGER DEFAULT 1,
                agreement_score REAL,
                validation_status TEXT DEFAULT 'single_source',
                requires_review INTEGER DEFAULT 0,
                confidence_score REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_entity ON claim_registry(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_type ON claim_registry(claim_type)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_status ON claim_registry(validation_status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_claim_registry_hash ON claim_registry(claim_hash)")
        
        conn.commit()
        conn.close()
    
    def validate_claim(self, claim: Claim) -> ClaimValidationResult:
        """
        Validate a claim through the full validation pipeline.
        
        Steps:
        1. Generate claim hash for deduplication
        2. Check for existing claims (cross-source verification)
        3. Evaluate validation rules
        4. Compute confidence score
        5. Update claim registry
        6. Log audit trail
        
        Args:
            claim: The claim to validate
        
        Returns:
            ClaimValidationResult with validation status and details
        """
        if self.bypass_validation:
            return ClaimValidationResult(
                claim=claim,
                is_valid=True,
                validation_status="bypassed",
                confidence_score=claim.source_confidence,
                is_first_report=True,
                first_reported_by=claim.source_id,
                first_reported_at=claim.observed_at,
                source_count=1,
            )
        
        # Step 1: Generate claim hash
        claim_hash = self._generate_claim_hash(claim)
        
        # Step 2: Check existing claims
        existing = self._get_existing_claim(claim_hash)
        
        if existing:
            # Cross-source verification
            return self._validate_with_existing(claim, existing, claim_hash)
        else:
            # First report of this claim
            return self._validate_new_claim(claim, claim_hash)
    
    def _generate_claim_hash(self, claim: Claim) -> str:
        """
        Generate a hash for claim deduplication.
        
        Normalizes the claim to handle minor variations.
        """
        # Normalize value based on type
        normalized_value = self._normalize_claim_value(
            claim.claim_value, 
            claim.claim_type,
            claim.claim_unit
        )
        
        # Create hash input
        hash_input = f"{claim.entity_id}|{claim.claim_type}|{normalized_value}|{claim.claim_date or ''}"
        
        return hashlib.sha256(hash_input.encode()).hexdigest()[:32]
    
    def _normalize_claim_value(
        self,
        value: Any,
        claim_type: str,
        unit: Optional[str]
    ) -> str:
        """Normalize claim value for comparison."""
        if value is None:
            return "null"
        
        # Numeric values: round to handle minor differences
        if isinstance(value, (int, float)):
            # Round to significant figures based on claim type
            if claim_type in ("funding_amount", "valuation", "revenue", "acquisition_price"):
                # Round to millions for large amounts
                if value >= 1_000_000:
                    return str(round(value / 1_000_000) * 1_000_000)
            elif claim_type == "employee_count":
                # Round to nearest 10 for employee counts
                if value >= 100:
                    return str(round(value / 10) * 10)
            return str(round(value, 2))
        
        # String values: lowercase and strip
        if isinstance(value, str):
            return value.lower().strip()
        
        # Boolean
        if isinstance(value, bool):
            return str(value).lower()
        
        return json.dumps(value, sort_keys=True)
    
    def _get_existing_claim(self, claim_hash: str) -> Optional[Dict[str, Any]]:
        """Get existing claim from registry by hash."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM claim_registry WHERE claim_hash = ?",
            (claim_hash,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def _validate_new_claim(
        self,
        claim: Claim,
        claim_hash: str
    ) -> ClaimValidationResult:
        """Validate a claim that hasn't been seen before."""
        
        # Get source reliability
        source_reliability = self.reliability_tracker.get_reliability_for_claim(
            claim.source_id,
            claim.claim_type
        )
        
        # Evaluate validation rules
        rule_results = self._evaluate_rules(claim, source_count=1)
        
        # Determine validation status
        rules_passed = [r for r in rule_results if r.passed]
        rules_failed = [r for r in rule_results if not r.passed]
        
        # Check if claim needs multiple sources
        type_rules = self.claim_type_rules.get(claim.claim_type, {})
        applicable_rule = self._get_applicable_rule(claim, type_rules.get("validation_rules", []))
        
        min_sources = 1
        if applicable_rule:
            min_sources = applicable_rule.get("min_sources", 1)
        
        # Determine status
        if min_sources > 1:
            validation_status = "pending"
            requires_review = True
            review_reason = f"High-value claim requires {min_sources} sources"
        elif rules_failed:
            validation_status = "review_required"
            requires_review = True
            review_reason = f"Failed rules: {[r.rule_name for r in rules_failed]}"
        else:
            validation_status = "single_source"
            requires_review = False
            review_reason = None
        
        # Compute confidence
        confidence = source_reliability * claim.source_confidence
        
        # Create registry entry
        registry_id = self._create_registry_entry(
            claim_hash=claim_hash,
            claim=claim,
            validation_status=validation_status,
            confidence_score=confidence,
            requires_review=requires_review,
        )
        
        # Log audit
        if self.audit_logger:
            self.audit_logger.log_insert(
                table_name="claim_registry",
                record_id=registry_id,
                data={
                    "claim_hash": claim_hash,
                    "claim_type": claim.claim_type,
                    "entity_id": claim.entity_id,
                    "value": str(claim.claim_value),
                    "source": claim.source_id,
                },
                source_id=claim.source_id,
                entity_id=claim.entity_id,
                change_reason="new_claim_registered",
            )
        
        # Update source reliability (first report)
        self.reliability_tracker.record_claim(
            source_id=claim.source_id,
            claim_type=claim.claim_type,
            was_first_to_report=True,
        )
        
        return ClaimValidationResult(
            claim=claim,
            is_valid=validation_status in ("single_source", "validated"),
            validation_status=validation_status,
            confidence_score=confidence,
            is_first_report=True,
            first_reported_by=claim.source_id,
            first_reported_at=claim.observed_at,
            source_count=1,
            agreement_score=1.0,
            rules_evaluated=[r.rule_name for r in rule_results],
            rules_passed=[r.rule_name for r in rules_passed],
            rules_failed=[r.rule_name for r in rules_failed],
            requires_review=requires_review,
            review_reason=review_reason,
            claim_hash=claim_hash,
            registry_id=registry_id,
        )
    
    def _validate_with_existing(
        self,
        claim: Claim,
        existing: Dict[str, Any],
        claim_hash: str
    ) -> ClaimValidationResult:
        """Validate a claim against an existing claim in the registry."""
        
        # Parse existing data
        confirming_sources = json.loads(existing["confirming_sources"] or "[]")
        conflicting_sources = json.loads(existing["conflicting_sources"] or "[]")
        
        # Check if this source already reported
        all_sources = [existing["first_source_id"]] + [s["source_id"] for s in confirming_sources]
        if claim.source_id in all_sources:
            # Duplicate from same source
            return ClaimValidationResult(
                claim=claim,
                is_valid=True,
                validation_status=existing["validation_status"],
                confidence_score=existing["confidence_score"] or 0.5,
                is_first_report=False,
                first_reported_by=existing["first_source_id"],
                first_reported_at=datetime.fromisoformat(existing["first_observed_at"]),
                confirmed_by=[s["source_id"] for s in confirming_sources],
                source_count=existing["source_count"],
                agreement_score=existing["agreement_score"] or 1.0,
                claim_hash=claim_hash,
                registry_id=existing["id"],
            )
        
        # New source confirming the claim
        source_reliability = self.reliability_tracker.get_reliability_for_claim(
            claim.source_id,
            claim.claim_type
        )
        
        # Add to confirming sources
        confirming_sources.append({
            "source_id": claim.source_id,
            "observed_at": claim.observed_at.isoformat(),
            "confidence": claim.source_confidence * source_reliability,
        })
        
        new_source_count = existing["source_count"] + 1
        
        # Recompute agreement score
        agreement_score = self._compute_agreement_score(
            claim, existing, confirming_sources, conflicting_sources
        )
        
        # Recompute confidence with multiple sources
        confidence = self._compute_multi_source_confidence(
            existing, confirming_sources, claim
        )
        
        # Re-evaluate rules with new source count
        rule_results = self._evaluate_rules(claim, source_count=new_source_count)
        rules_passed = [r for r in rule_results if r.passed]
        rules_failed = [r for r in rule_results if not r.passed]
        
        # Determine new status
        if rules_failed:
            validation_status = "review_required"
            requires_review = True
            review_reason = f"Failed rules: {[r.rule_name for r in rules_failed]}"
        elif agreement_score < 0.8:
            validation_status = "conflict"
            requires_review = True
            review_reason = f"Source disagreement: agreement={agreement_score:.2f}"
        elif new_source_count >= 2:
            validation_status = "corroborated"
            requires_review = False
            review_reason = None
        else:
            validation_status = "validated"
            requires_review = False
            review_reason = None
        
        # Update registry
        self._update_registry_entry(
            registry_id=existing["id"],
            confirming_sources=confirming_sources,
            conflicting_sources=conflicting_sources,
            source_count=new_source_count,
            agreement_score=agreement_score,
            validation_status=validation_status,
            confidence_score=confidence,
            requires_review=requires_review,
        )
        
        # Log audit
        if self.audit_logger:
            self.audit_logger.log_update(
                table_name="claim_registry",
                record_id=existing["id"],
                field_name="source_count",
                old_value=existing["source_count"],
                new_value=new_source_count,
                source_id=claim.source_id,
                entity_id=claim.entity_id,
                change_reason="claim_corroborated",
            )
        
        # Update source reliability (verified claim)
        self.reliability_tracker.record_claim(
            source_id=claim.source_id,
            claim_type=claim.claim_type,
            was_verified=True,
            was_first_to_report=False,
        )
        
        # Also update first reporter's reliability
        self.reliability_tracker.record_claim(
            source_id=existing["first_source_id"],
            claim_type=claim.claim_type,
            was_verified=True,
        )
        
        return ClaimValidationResult(
            claim=claim,
            is_valid=validation_status in ("corroborated", "validated"),
            validation_status=validation_status,
            confidence_score=confidence,
            is_first_report=False,
            first_reported_by=existing["first_source_id"],
            first_reported_at=datetime.fromisoformat(existing["first_observed_at"]),
            confirmed_by=[s["source_id"] for s in confirming_sources],
            source_count=new_source_count,
            agreement_score=agreement_score,
            conflicting_values=[{"source_id": s["source_id"], "value": s.get("value")} for s in conflicting_sources],
            rules_evaluated=[r.rule_name for r in rule_results],
            rules_passed=[r.rule_name for r in rules_passed],
            rules_failed=[r.rule_name for r in rules_failed],
            requires_review=requires_review,
            review_reason=review_reason,
            claim_hash=claim_hash,
            registry_id=existing["id"],
        )
    
    def _evaluate_rules(
        self,
        claim: Claim,
        source_count: int
    ) -> List[ValidationRuleResult]:
        """Evaluate validation rules for a claim."""
        results = []
        
        type_rules = self.claim_type_rules.get(claim.claim_type, {})
        validation_rules = type_rules.get("validation_rules", [])
        
        if not validation_rules:
            # No specific rules, use global defaults
            min_sources = self.global_settings.get("default_min_sources", 1)
            results.append(ValidationRuleResult(
                rule_name="global_min_sources",
                passed=source_count >= min_sources,
                reason=f"Requires {min_sources} sources, has {source_count}",
            ))
            return results
        
        # Find applicable rule
        applicable = self._get_applicable_rule(claim, validation_rules)
        
        if applicable:
            rule_name = applicable.get("name", "unnamed_rule")
            min_sources = applicable.get("min_sources", 1)
            min_tier = applicable.get("min_tier", 4)
            require_official = applicable.get("require_official_source", False)
            
            # Check min sources
            results.append(ValidationRuleResult(
                rule_name=f"{rule_name}_min_sources",
                passed=source_count >= min_sources,
                reason=f"Requires {min_sources} sources, has {source_count}",
                details={"required": min_sources, "actual": source_count},
            ))
            
            # Check source tier
            source_tier = self._get_source_tier(claim.source_id)
            tier_num = int(source_tier.replace("tier_", "")) if source_tier else 4
            results.append(ValidationRuleResult(
                rule_name=f"{rule_name}_min_tier",
                passed=tier_num <= min_tier,
                reason=f"Requires tier {min_tier} or better, source is tier {tier_num}",
                details={"required_tier": min_tier, "actual_tier": tier_num},
            ))
            
            # Check official source requirement
            if require_official:
                is_official = self._is_official_source(claim.source_id)
                results.append(ValidationRuleResult(
                    rule_name=f"{rule_name}_official_source",
                    passed=is_official,
                    reason="Requires official source" if not is_official else "Official source present",
                    details={"source_id": claim.source_id, "is_official": is_official},
                ))
        
        return results
    
    def _get_applicable_rule(
        self,
        claim: Claim,
        rules: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find the applicable validation rule based on claim value."""
        numeric_value = None
        if isinstance(claim.claim_value, (int, float)):
            numeric_value = claim.claim_value
        
        for rule in rules:
            condition = rule.get("condition", {})
            
            if not condition:
                # Default rule (no condition)
                return rule
            
            matches = True
            
            # Check value conditions
            if "value_lt" in condition and numeric_value is not None:
                if not numeric_value < condition["value_lt"]:
                    matches = False
            
            if "value_gte" in condition and numeric_value is not None:
                if not numeric_value >= condition["value_gte"]:
                    matches = False
            
            if "value_lte" in condition and numeric_value is not None:
                if not numeric_value <= condition["value_lte"]:
                    matches = False
            
            if matches:
                return rule
        
        # Return first rule as default
        return rules[0] if rules else None
    
    def _get_source_tier(self, source_id: str) -> Optional[str]:
        """Get tier for a source."""
        source_lower = source_id.lower()
        
        for tier_name, tier_info in self.source_tiers.items():
            examples = tier_info.get("examples", [])
            if any(ex in source_lower for ex in examples):
                return tier_name
        
        return "tier_3"  # Default
    
    def _is_official_source(self, source_id: str) -> bool:
        """Check if source is an official/tier-1 source."""
        official_keywords = ["sec", "company_ir", "press_release", "earnings", "10k", "10q", "8k"]
        source_lower = source_id.lower()
        return any(kw in source_lower for kw in official_keywords)
    
    def _compute_agreement_score(
        self,
        claim: Claim,
        existing: Dict[str, Any],
        confirming_sources: List[Dict],
        conflicting_sources: List[Dict],
    ) -> float:
        """Compute agreement score across sources."""
        total_sources = 1 + len(confirming_sources) + len(conflicting_sources)
        agreeing_sources = 1 + len(confirming_sources)
        
        if total_sources == 0:
            return 1.0
        
        return agreeing_sources / total_sources
    
    def _compute_multi_source_confidence(
        self,
        existing: Dict[str, Any],
        confirming_sources: List[Dict],
        new_claim: Claim,
    ) -> float:
        """Compute weighted confidence from multiple sources."""
        # Get all source reliabilities
        source_claims = []
        
        # First reporter
        first_reliability = self.reliability_tracker.get_reliability_for_claim(
            existing["first_source_id"],
            new_claim.claim_type
        )
        source_claims.append((existing["first_source_id"], first_reliability, new_claim.claim_type))
        
        # Confirming sources
        for s in confirming_sources:
            rel = self.reliability_tracker.get_reliability_for_claim(
                s["source_id"],
                new_claim.claim_type
            )
            source_claims.append((s["source_id"], s.get("confidence", rel), new_claim.claim_type))
        
        return self.reliability_tracker.compute_weighted_confidence(source_claims)
    
    def _create_registry_entry(
        self,
        claim_hash: str,
        claim: Claim,
        validation_status: str,
        confidence_score: float,
        requires_review: bool,
    ) -> str:
        """Create a new claim registry entry."""
        registry_id = str(uuid.uuid4())
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Extract numeric value if possible
        numeric_value = None
        if isinstance(claim.claim_value, (int, float)):
            numeric_value = claim.claim_value
        
        cursor.execute("""
            INSERT INTO claim_registry (
                id, claim_hash, claim_type, entity_id, claim_value,
                claim_value_numeric, claim_unit, claim_date,
                first_source_id, first_observed_at, confirming_sources,
                conflicting_sources, source_count, agreement_score,
                validation_status, requires_review, confidence_score,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            registry_id, claim_hash, claim.claim_type, claim.entity_id,
            json.dumps(claim.claim_value), numeric_value, claim.claim_unit,
            claim.claim_date, claim.source_id, claim.observed_at.isoformat(),
            "[]", "[]", 1, 1.0, validation_status, 1 if requires_review else 0,
            confidence_score, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return registry_id
    
    def _update_registry_entry(
        self,
        registry_id: str,
        confirming_sources: List[Dict],
        conflicting_sources: List[Dict],
        source_count: int,
        agreement_score: float,
        validation_status: str,
        confidence_score: float,
        requires_review: bool,
    ):
        """Update an existing claim registry entry."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE claim_registry SET
                confirming_sources = ?,
                conflicting_sources = ?,
                source_count = ?,
                agreement_score = ?,
                validation_status = ?,
                requires_review = ?,
                confidence_score = ?,
                updated_at = ?
            WHERE id = ?
        """, (
            json.dumps(confirming_sources),
            json.dumps(conflicting_sources),
            source_count,
            agreement_score,
            validation_status,
            1 if requires_review else 0,
            confidence_score,
            datetime.utcnow().isoformat(),
            registry_id
        ))
        
        conn.commit()
        conn.close()
    
    # =========================================================================
    # Query Methods
    # =========================================================================
    
    def get_claims_for_entity(
        self,
        entity_id: str,
        claim_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all claims for an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        if claim_type:
            cursor.execute(
                "SELECT * FROM claim_registry WHERE entity_id = ? AND claim_type = ?",
                (entity_id, claim_type)
            )
        else:
            cursor.execute(
                "SELECT * FROM claim_registry WHERE entity_id = ?",
                (entity_id,)
            )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_claims_requiring_review(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get claims that require manual review."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM claim_registry
            WHERE requires_review = 1
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_conflicting_claims(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get claims with source conflicts."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM claim_registry
            WHERE validation_status = 'conflict'
            ORDER BY updated_at DESC
            LIMIT ?
        """, (limit,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def get_validation_statistics(self) -> Dict[str, Any]:
        """Get validation layer statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Total claims
        cursor.execute("SELECT COUNT(*) FROM claim_registry")
        total = cursor.fetchone()[0]
        
        # By status
        cursor.execute("""
            SELECT validation_status, COUNT(*) FROM claim_registry
            GROUP BY validation_status
        """)
        by_status = {row[0]: row[1] for row in cursor.fetchall()}
        
        # By type
        cursor.execute("""
            SELECT claim_type, COUNT(*) FROM claim_registry
            GROUP BY claim_type
        """)
        by_type = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Avg confidence by status
        cursor.execute("""
            SELECT validation_status, AVG(confidence_score) FROM claim_registry
            GROUP BY validation_status
        """)
        avg_confidence = {row[0]: row[1] for row in cursor.fetchall()}
        
        # Multi-source claims
        cursor.execute("SELECT COUNT(*) FROM claim_registry WHERE source_count >= 2")
        multi_source = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_claims": total,
            "by_status": by_status,
            "by_type": by_type,
            "avg_confidence_by_status": avg_confidence,
            "multi_source_claims": multi_source,
            "single_source_claims": total - multi_source,
            "review_queue_size": by_status.get("review_required", 0) + by_status.get("pending", 0),
        }
