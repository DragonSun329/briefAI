"""
Source Reliability Scoring for Bloomberg Terminal-Grade Validation.

Tracks historical accuracy per source:
- Dynamic reliability scores based on verification history
- Reliability decay for sources that haven't been verified recently
- Category-specific accuracy (e.g., source may be good at funding but bad at valuations)
- First-to-report tracking for breaking news credibility
"""

import json
import logging
import math
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SourceReliabilityScore:
    """Reliability assessment for a single source."""
    source_id: str
    reliability_score: float          # Current dynamic reliability (0-1)
    base_reliability: float           # Configured base reliability
    total_claims: int
    verified_claims: int
    contradicted_claims: int
    accuracy_by_category: Dict[str, float]
    avg_reporting_delay_hours: Optional[float]
    first_to_report_count: int
    last_verified_at: Optional[datetime]
    reliability_history: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ReliabilityUpdate:
    """Result of a reliability calculation update."""
    source_id: str
    old_score: float
    new_score: float
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class SourceReliabilityTracker:
    """
    Tracks and computes dynamic source reliability scores.
    
    Features:
    - Historical accuracy tracking
    - Reliability decay over time (unused sources become less trusted)
    - Category-specific accuracy
    - First-to-report bonuses
    """
    
    # Default base reliability by source tier (from source_credibility.json)
    DEFAULT_BASE_RELIABILITY = {
        "tier_1": 0.95,  # SEC, Bloomberg, WSJ
        "tier_2": 0.85,  # Crunchbase, Forbes
        "tier_3": 0.70,  # TechCrunch, VentureBeat
        "tier_4": 0.50,  # Twitter, Reddit
    }
    
    # Decay parameters
    DECAY_HALF_LIFE_DAYS = 90  # Reliability halves toward base every 90 days without verification
    MIN_CLAIMS_FOR_DYNAMIC = 5  # Need at least 5 claims before dynamic scoring kicks in
    
    # Category-specific weights
    HIGH_VALUE_CATEGORIES = ["funding_amount", "valuation", "acquisition_price", "employee_count"]
    
    def __init__(self, db_path: Optional[str] = None, config_path: Optional[str] = None):
        """Initialize reliability tracker."""
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "signals.db")
        self.db_path = db_path
        
        # Load source credibility config
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "source_credibility.json"
        self._load_config(config_path)
        
        # Ensure tables exist
        self._ensure_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _load_config(self, config_path: Path):
        """Load source credibility configuration."""
        self.source_tiers: Dict[str, str] = {}  # source_id → tier
        self.tier_weights: Dict[str, float] = {}
        
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
            
            # Build source → tier mapping
            for tier_name, tier_info in config.get("tiers", {}).items():
                weight = tier_info.get("weight", 0.5)
                self.tier_weights[tier_name] = weight
                
                for source_type, sources in tier_info.get("sources", {}).items():
                    for source in sources:
                        self.source_tiers[source.lower()] = tier_name
            
            # Load signal source mappings
            for signal, mapping in config.get("signal_source_mappings", {}).items():
                default_tier = mapping.get("default_tier", "tier_3")
                for source, tier in mapping.get("sources", {}).items():
                    self.source_tiers[source.lower()] = tier
                    
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load source_credibility.json: {e}")
            self.tier_weights = {
                "tier_1": 1.0,
                "tier_2": 0.8,
                "tier_3": 0.6,
                "tier_4": 0.4,
            }
    
    def _ensure_tables(self):
        """Ensure reliability tables exist."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS source_reliability (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL UNIQUE,
                reliability_score REAL DEFAULT 0.7,
                base_reliability REAL DEFAULT 0.7,
                total_claims INTEGER DEFAULT 0,
                verified_claims INTEGER DEFAULT 0,
                contradicted_claims INTEGER DEFAULT 0,
                accuracy_by_category TEXT,
                avg_reporting_delay_hours REAL,
                first_to_report_count INTEGER DEFAULT 0,
                last_verified_at TIMESTAMP,
                reliability_decay_applied_at TIMESTAMP,
                reliability_history TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_source_reliability_score ON source_reliability(reliability_score)")
        
        conn.commit()
        conn.close()
    
    def get_reliability(self, source_id: str) -> SourceReliabilityScore:
        """
        Get current reliability score for a source.
        
        Creates a new record with base reliability if source not tracked.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM source_reliability WHERE source_id = ?", (source_id,))
        row = cursor.fetchone()
        
        if row:
            conn.close()
            return self._row_to_score(row)
        
        # Create new record with base reliability
        base_rel = self._get_base_reliability(source_id)
        record_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO source_reliability (
                id, source_id, reliability_score, base_reliability,
                total_claims, verified_claims, contradicted_claims,
                accuracy_by_category, first_to_report_count,
                reliability_history, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, 0, '{}', 0, '[]', ?, ?)
        """, (
            record_id, source_id, base_rel, base_rel,
            datetime.utcnow().isoformat(),
            datetime.utcnow().isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return SourceReliabilityScore(
            source_id=source_id,
            reliability_score=base_rel,
            base_reliability=base_rel,
            total_claims=0,
            verified_claims=0,
            contradicted_claims=0,
            accuracy_by_category={},
            avg_reporting_delay_hours=None,
            first_to_report_count=0,
            last_verified_at=None,
            reliability_history=[]
        )
    
    def _get_base_reliability(self, source_id: str) -> float:
        """Get base reliability for a source based on tier."""
        source_lower = source_id.lower()
        
        # Check direct mapping
        tier = self.source_tiers.get(source_lower)
        if tier:
            return self.DEFAULT_BASE_RELIABILITY.get(tier, 0.7)
        
        # Check if source name contains known keywords
        tier_keywords = {
            "tier_1": ["sec", "bloomberg", "wsj", "reuters", "ft"],
            "tier_2": ["crunchbase", "forbes", "cnbc"],
            "tier_3": ["techcrunch", "venturebeat", "github"],
            "tier_4": ["twitter", "reddit", "discord"],
        }
        
        for tier, keywords in tier_keywords.items():
            if any(kw in source_lower for kw in keywords):
                return self.DEFAULT_BASE_RELIABILITY.get(tier, 0.7)
        
        # Default to tier 3
        return 0.7
    
    def _row_to_score(self, row: sqlite3.Row) -> SourceReliabilityScore:
        """Convert database row to SourceReliabilityScore."""
        return SourceReliabilityScore(
            source_id=row["source_id"],
            reliability_score=row["reliability_score"],
            base_reliability=row["base_reliability"],
            total_claims=row["total_claims"],
            verified_claims=row["verified_claims"],
            contradicted_claims=row["contradicted_claims"],
            accuracy_by_category=json.loads(row["accuracy_by_category"]) if row["accuracy_by_category"] else {},
            avg_reporting_delay_hours=row["avg_reporting_delay_hours"],
            first_to_report_count=row["first_to_report_count"],
            last_verified_at=datetime.fromisoformat(row["last_verified_at"]) if row["last_verified_at"] else None,
            reliability_history=json.loads(row["reliability_history"]) if row["reliability_history"] else []
        )
    
    def record_claim(
        self,
        source_id: str,
        claim_type: str,
        was_verified: bool = False,
        was_contradicted: bool = False,
        was_first_to_report: bool = False,
        reporting_delay_hours: Optional[float] = None,
    ) -> ReliabilityUpdate:
        """
        Record a claim from a source and update reliability.
        
        Args:
            source_id: Source that made the claim
            claim_type: Type of claim (funding_amount, valuation, etc.)
            was_verified: Whether claim was corroborated by other sources
            was_contradicted: Whether claim was contradicted
            was_first_to_report: Whether this source was first to report
            reporting_delay_hours: How many hours after the event was this reported?
        
        Returns:
            ReliabilityUpdate with old and new scores
        """
        current = self.get_reliability(source_id)
        old_score = current.reliability_score
        
        # Update counters
        new_total = current.total_claims + 1
        new_verified = current.verified_claims + (1 if was_verified else 0)
        new_contradicted = current.contradicted_claims + (1 if was_contradicted else 0)
        new_first_count = current.first_to_report_count + (1 if was_first_to_report else 0)
        
        # Update category accuracy
        accuracy_by_cat = current.accuracy_by_category.copy()
        if claim_type:
            cat_key = claim_type.lower()
            if cat_key not in accuracy_by_cat:
                accuracy_by_cat[cat_key] = {"total": 0, "verified": 0, "accuracy": 0.5}
            
            accuracy_by_cat[cat_key]["total"] += 1
            if was_verified:
                accuracy_by_cat[cat_key]["verified"] += 1
            
            # Compute category accuracy
            if accuracy_by_cat[cat_key]["total"] > 0:
                accuracy_by_cat[cat_key]["accuracy"] = (
                    accuracy_by_cat[cat_key]["verified"] / accuracy_by_cat[cat_key]["total"]
                )
        
        # Update average reporting delay
        if reporting_delay_hours is not None:
            if current.avg_reporting_delay_hours is None:
                new_avg_delay = reporting_delay_hours
            else:
                # Exponential moving average
                alpha = 0.3
                new_avg_delay = (
                    alpha * reporting_delay_hours + 
                    (1 - alpha) * current.avg_reporting_delay_hours
                )
        else:
            new_avg_delay = current.avg_reporting_delay_hours
        
        # Calculate new reliability score
        new_score = self._calculate_reliability(
            base_reliability=current.base_reliability,
            total_claims=new_total,
            verified_claims=new_verified,
            contradicted_claims=new_contradicted,
            first_to_report_count=new_first_count,
            accuracy_by_category=accuracy_by_cat,
            last_verified_at=datetime.utcnow() if was_verified else current.last_verified_at,
        )
        
        # Update database
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Add to history (keep last 100)
        history = current.reliability_history[-99:] + [{
            "date": datetime.utcnow().isoformat(),
            "score": new_score,
            "event": "claim_recorded",
            "verified": was_verified,
            "contradicted": was_contradicted,
        }]
        
        cursor.execute("""
            UPDATE source_reliability SET
                reliability_score = ?,
                total_claims = ?,
                verified_claims = ?,
                contradicted_claims = ?,
                first_to_report_count = ?,
                accuracy_by_category = ?,
                avg_reporting_delay_hours = ?,
                last_verified_at = ?,
                reliability_history = ?,
                updated_at = ?
            WHERE source_id = ?
        """, (
            new_score,
            new_total,
            new_verified,
            new_contradicted,
            new_first_count,
            json.dumps(accuracy_by_cat),
            new_avg_delay,
            datetime.utcnow().isoformat() if was_verified else (
                current.last_verified_at.isoformat() if current.last_verified_at else None
            ),
            json.dumps(history),
            datetime.utcnow().isoformat(),
            source_id
        ))
        
        conn.commit()
        conn.close()
        
        return ReliabilityUpdate(
            source_id=source_id,
            old_score=old_score,
            new_score=new_score,
            reason="claim_recorded",
            details={
                "was_verified": was_verified,
                "was_contradicted": was_contradicted,
                "was_first_to_report": was_first_to_report,
                "claim_type": claim_type,
            }
        )
    
    def _calculate_reliability(
        self,
        base_reliability: float,
        total_claims: int,
        verified_claims: int,
        contradicted_claims: int,
        first_to_report_count: int,
        accuracy_by_category: Dict[str, Any],
        last_verified_at: Optional[datetime],
    ) -> float:
        """
        Calculate dynamic reliability score.
        
        Formula:
        - Start with base reliability
        - Adjust based on verification rate (if enough claims)
        - Apply penalty for contradictions
        - Bonus for first-to-report accuracy
        - Apply decay if not recently verified
        """
        if total_claims < self.MIN_CLAIMS_FOR_DYNAMIC:
            # Not enough data for dynamic scoring
            return base_reliability
        
        # Base verification rate
        verification_rate = verified_claims / total_claims if total_claims > 0 else 0
        contradiction_rate = contradicted_claims / total_claims if total_claims > 0 else 0
        
        # Dynamic score starts at base
        score = base_reliability
        
        # Adjust based on verification rate
        # If verification rate > base_reliability, boost score
        # If verification rate < base_reliability, reduce score
        verification_adjustment = (verification_rate - 0.5) * 0.4
        score += verification_adjustment
        
        # Penalty for contradictions (stronger penalty)
        contradiction_penalty = contradiction_rate * 0.6
        score -= contradiction_penalty
        
        # First-to-report bonus (scaled by accuracy)
        if total_claims > 0 and first_to_report_count > 0:
            first_rate = first_to_report_count / total_claims
            # Only bonus if verified claims are also high
            if verification_rate > 0.5:
                score += first_rate * 0.1
        
        # High-value category bonus/penalty
        for cat_key in self.HIGH_VALUE_CATEGORIES:
            if cat_key in accuracy_by_category:
                cat_data = accuracy_by_category[cat_key]
                if cat_data.get("total", 0) >= 3:
                    cat_accuracy = cat_data.get("accuracy", 0.5)
                    # Strong adjustment for high-value categories
                    score += (cat_accuracy - 0.5) * 0.15
        
        # Apply decay if not recently verified
        if last_verified_at:
            days_since_verification = (datetime.utcnow() - last_verified_at).days
            if days_since_verification > 30:
                # Decay toward base reliability
                decay_factor = math.exp(-days_since_verification / self.DECAY_HALF_LIFE_DAYS)
                score = score * decay_factor + base_reliability * (1 - decay_factor)
        
        # Clamp to [0.1, 1.0]
        return max(0.1, min(1.0, score))
    
    def apply_decay_to_all(self) -> List[ReliabilityUpdate]:
        """
        Apply time-based decay to all sources.
        
        Call periodically (e.g., daily) to ensure stale sources don't maintain
        artificially high reliability.
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM source_reliability
            WHERE last_verified_at IS NOT NULL
              AND (reliability_decay_applied_at IS NULL 
                   OR reliability_decay_applied_at < datetime('now', '-1 day'))
        """)
        
        rows = cursor.fetchall()
        updates = []
        
        for row in rows:
            score = self._row_to_score(row)
            old_score = score.reliability_score
            
            # Recalculate with current time
            new_score = self._calculate_reliability(
                base_reliability=score.base_reliability,
                total_claims=score.total_claims,
                verified_claims=score.verified_claims,
                contradicted_claims=score.contradicted_claims,
                first_to_report_count=score.first_to_report_count,
                accuracy_by_category=score.accuracy_by_category,
                last_verified_at=score.last_verified_at,
            )
            
            if abs(new_score - old_score) > 0.001:
                cursor.execute("""
                    UPDATE source_reliability SET
                        reliability_score = ?,
                        reliability_decay_applied_at = ?,
                        updated_at = ?
                    WHERE source_id = ?
                """, (
                    new_score,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                    score.source_id
                ))
                
                updates.append(ReliabilityUpdate(
                    source_id=score.source_id,
                    old_score=old_score,
                    new_score=new_score,
                    reason="decay_applied",
                    details={"days_since_verification": (
                        (datetime.utcnow() - score.last_verified_at).days
                        if score.last_verified_at else None
                    )}
                ))
        
        conn.commit()
        conn.close()
        
        return updates
    
    def get_reliability_for_claim(
        self,
        source_id: str,
        claim_type: Optional[str] = None
    ) -> float:
        """
        Get effective reliability for a specific claim type.
        
        Uses category-specific accuracy if available, otherwise overall reliability.
        """
        score = self.get_reliability(source_id)
        
        if claim_type and claim_type.lower() in score.accuracy_by_category:
            cat_data = score.accuracy_by_category[claim_type.lower()]
            if cat_data.get("total", 0) >= self.MIN_CLAIMS_FOR_DYNAMIC:
                # Blend category accuracy with overall reliability
                cat_accuracy = cat_data.get("accuracy", score.reliability_score)
                return 0.7 * cat_accuracy + 0.3 * score.reliability_score
        
        return score.reliability_score
    
    def get_all_reliabilities(self, min_claims: int = 0) -> List[SourceReliabilityScore]:
        """Get reliability scores for all tracked sources."""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM source_reliability WHERE total_claims >= ? ORDER BY reliability_score DESC",
            (min_claims,)
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_score(row) for row in rows]
    
    def get_most_reliable_sources(
        self,
        claim_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Tuple[str, float]]:
        """Get the most reliable sources, optionally for a specific claim type."""
        all_scores = self.get_all_reliabilities(min_claims=self.MIN_CLAIMS_FOR_DYNAMIC)
        
        if claim_type:
            # Score by category-specific accuracy
            scored = []
            for s in all_scores:
                eff_reliability = self.get_reliability_for_claim(s.source_id, claim_type)
                scored.append((s.source_id, eff_reliability))
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:limit]
        else:
            return [(s.source_id, s.reliability_score) for s in all_scores[:limit]]
    
    def compute_weighted_confidence(
        self,
        source_claims: List[Tuple[str, float, Optional[str]]]
    ) -> float:
        """
        Compute weighted confidence from multiple sources.
        
        Args:
            source_claims: List of (source_id, claim_confidence, claim_type)
        
        Returns:
            Weighted average confidence (0-1)
        """
        if not source_claims:
            return 0.0
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for source_id, claim_confidence, claim_type in source_claims:
            reliability = self.get_reliability_for_claim(source_id, claim_type)
            weight = reliability
            
            weighted_sum += claim_confidence * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0.0
        
        return weighted_sum / total_weight
