"""
Business Event Models for briefAI

Defines business events that occur in the AI industry:
FUNDING_ROUND, ACQUISITION, PRODUCT_LAUNCH, PARTNERSHIP,
REGULATORY, LEADERSHIP_CHANGE, IPO, LAYOFF, PIVOT

Events are linked to entities and can be deduplicated across sources.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from enum import Enum
from dataclasses import dataclass, field
import uuid
import hashlib


class BusinessEventType(str, Enum):
    """Types of business events we track."""
    FUNDING_ROUND = "funding_round"           # Series A, B, C, etc.
    ACQUISITION = "acquisition"               # Company acquired/merged
    PRODUCT_LAUNCH = "product_launch"         # New product/model release
    PARTNERSHIP = "partnership"               # Strategic partnership/collaboration
    REGULATORY = "regulatory"                 # Regulatory action, compliance, investigation
    LEADERSHIP_CHANGE = "leadership_change"   # CEO/CTO/executive changes
    IPO = "ipo"                               # IPO/SPAC/direct listing
    LAYOFF = "layoff"                         # Layoffs, workforce reduction
    PIVOT = "pivot"                           # Business model/strategy change
    EXPANSION = "expansion"                   # Geographic/market expansion
    LEGAL = "legal"                           # Lawsuits, IP disputes
    SHUTDOWN = "shutdown"                     # Company shutdown/bankruptcy


class EventConfidence(str, Enum):
    """Confidence levels for event detection."""
    HIGH = "high"           # Multiple authoritative sources confirm
    MEDIUM = "medium"       # Single authoritative source or multiple secondary
    LOW = "low"             # Single secondary source or inference
    UNVERIFIED = "unverified"  # Detected but needs verification


class FundingStage(str, Enum):
    """Funding round stages for FUNDING_ROUND events."""
    PRE_SEED = "pre_seed"
    SEED = "seed"
    SERIES_A = "series_a"
    SERIES_B = "series_b"
    SERIES_C = "series_c"
    SERIES_D = "series_d"
    SERIES_E_PLUS = "series_e_plus"
    BRIDGE = "bridge"
    DEBT = "debt"
    GRANT = "grant"
    UNKNOWN = "unknown"


@dataclass
class EventSource:
    """A source that reported an event."""
    source_id: str                    # e.g., "techcrunch", "reuters"
    source_name: str                  # Display name
    source_url: str                   # Article URL
    source_credibility: float = 0.7  # 0-1 credibility score
    published_at: Optional[datetime] = None
    excerpt: str = ""                 # Relevant text excerpt
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "source_credibility": self.source_credibility,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "excerpt": self.excerpt,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventSource":
        return cls(
            source_id=data.get("source_id", ""),
            source_name=data.get("source_name", ""),
            source_url=data.get("source_url", ""),
            source_credibility=data.get("source_credibility", 0.7),
            published_at=datetime.fromisoformat(data["published_at"]) if data.get("published_at") else None,
            excerpt=data.get("excerpt", ""),
        )


@dataclass
class FundingDetails:
    """Details specific to FUNDING_ROUND events."""
    amount_usd: Optional[float] = None
    stage: FundingStage = FundingStage.UNKNOWN
    lead_investors: List[str] = field(default_factory=list)
    all_investors: List[str] = field(default_factory=list)
    valuation_usd: Optional[float] = None
    is_extension: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "amount_usd": self.amount_usd,
            "stage": self.stage.value,
            "lead_investors": self.lead_investors,
            "all_investors": self.all_investors,
            "valuation_usd": self.valuation_usd,
            "is_extension": self.is_extension,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FundingDetails":
        return cls(
            amount_usd=data.get("amount_usd"),
            stage=FundingStage(data.get("stage", "unknown")),
            lead_investors=data.get("lead_investors", []),
            all_investors=data.get("all_investors", []),
            valuation_usd=data.get("valuation_usd"),
            is_extension=data.get("is_extension", False),
        )


@dataclass
class AcquisitionDetails:
    """Details specific to ACQUISITION events."""
    acquirer_id: str = ""
    acquirer_name: str = ""
    target_id: str = ""
    target_name: str = ""
    deal_value_usd: Optional[float] = None
    deal_type: str = "acquisition"  # acquisition, merger, acqui-hire
    is_rumored: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "acquirer_id": self.acquirer_id,
            "acquirer_name": self.acquirer_name,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "deal_value_usd": self.deal_value_usd,
            "deal_type": self.deal_type,
            "is_rumored": self.is_rumored,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AcquisitionDetails":
        return cls(
            acquirer_id=data.get("acquirer_id", ""),
            acquirer_name=data.get("acquirer_name", ""),
            target_id=data.get("target_id", ""),
            target_name=data.get("target_name", ""),
            deal_value_usd=data.get("deal_value_usd"),
            deal_type=data.get("deal_type", "acquisition"),
            is_rumored=data.get("is_rumored", False),
        )


@dataclass
class ProductLaunchDetails:
    """Details specific to PRODUCT_LAUNCH events."""
    product_name: str = ""
    product_type: str = ""  # model, api, feature, tool
    version: str = ""
    is_beta: bool = False
    is_open_source: bool = False
    capabilities: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_name": self.product_name,
            "product_type": self.product_type,
            "version": self.version,
            "is_beta": self.is_beta,
            "is_open_source": self.is_open_source,
            "capabilities": self.capabilities,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProductLaunchDetails":
        return cls(
            product_name=data.get("product_name", ""),
            product_type=data.get("product_type", ""),
            version=data.get("version", ""),
            is_beta=data.get("is_beta", False),
            is_open_source=data.get("is_open_source", False),
            capabilities=data.get("capabilities", []),
        )


@dataclass
class LeadershipChangeDetails:
    """Details specific to LEADERSHIP_CHANGE events."""
    person_name: str = ""
    old_role: str = ""
    new_role: str = ""  # Empty if departure
    change_type: str = ""  # hired, departed, promoted, demoted
    is_founder: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "person_name": self.person_name,
            "old_role": self.old_role,
            "new_role": self.new_role,
            "change_type": self.change_type,
            "is_founder": self.is_founder,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LeadershipChangeDetails":
        return cls(
            person_name=data.get("person_name", ""),
            old_role=data.get("old_role", ""),
            new_role=data.get("new_role", ""),
            change_type=data.get("change_type", ""),
            is_founder=data.get("is_founder", False),
        )


@dataclass
class PartnershipDetails:
    """Details specific to PARTNERSHIP events."""
    partner_ids: List[str] = field(default_factory=list)
    partner_names: List[str] = field(default_factory=list)
    partnership_type: str = ""  # strategic, technology, distribution, investment
    scope: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "partner_ids": self.partner_ids,
            "partner_names": self.partner_names,
            "partnership_type": self.partnership_type,
            "scope": self.scope,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PartnershipDetails":
        return cls(
            partner_ids=data.get("partner_ids", []),
            partner_names=data.get("partner_names", []),
            partnership_type=data.get("partnership_type", ""),
            scope=data.get("scope", ""),
        )


@dataclass 
class LayoffDetails:
    """Details specific to LAYOFF events."""
    headcount: Optional[int] = None
    percentage: Optional[float] = None  # Percentage of workforce
    departments: List[str] = field(default_factory=list)
    reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "headcount": self.headcount,
            "percentage": self.percentage,
            "departments": self.departments,
            "reason": self.reason,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LayoffDetails":
        return cls(
            headcount=data.get("headcount"),
            percentage=data.get("percentage"),
            departments=data.get("departments", []),
            reason=data.get("reason", ""),
        )


@dataclass
class BusinessEvent:
    """
    A significant business event detected from news.
    
    Events are linked to entities and deduplicated across sources.
    The same event reported by multiple sources strengthens confidence.
    """
    # Identity
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: BusinessEventType = BusinessEventType.PRODUCT_LAUNCH
    
    # Primary entity (the company/entity this event is about)
    entity_id: str = ""
    entity_name: str = ""
    
    # Related entities (partners, acquirers, investors, etc.)
    related_entity_ids: List[str] = field(default_factory=list)
    related_entity_names: List[str] = field(default_factory=list)
    
    # Event details
    event_date: Optional[datetime] = None  # When the event occurred
    headline: str = ""                     # Summary headline
    summary: str = ""                      # 1-2 sentence summary
    
    # Type-specific details (only one will be populated)
    funding_details: Optional[FundingDetails] = None
    acquisition_details: Optional[AcquisitionDetails] = None
    product_details: Optional[ProductLaunchDetails] = None
    leadership_details: Optional[LeadershipChangeDetails] = None
    partnership_details: Optional[PartnershipDetails] = None
    layoff_details: Optional[LayoffDetails] = None
    
    # Generic details (for other event types)
    details: Dict[str, Any] = field(default_factory=dict)
    
    # Sources and confidence
    sources: List[EventSource] = field(default_factory=list)
    confidence: EventConfidence = EventConfidence.MEDIUM
    confidence_score: float = 0.5  # 0-1 numeric confidence
    
    # Deduplication
    content_hash: str = ""  # For dedup matching
    merged_from: List[str] = field(default_factory=list)  # event_ids merged into this
    
    # Event linking
    parent_event_id: Optional[str] = None   # For causal chains
    related_event_ids: List[str] = field(default_factory=list)
    
    # Timestamps
    first_reported: datetime = field(default_factory=datetime.utcnow)
    last_updated: datetime = field(default_factory=datetime.utcnow)
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Compute content hash after initialization."""
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()
    
    def compute_content_hash(self) -> str:
        """
        Compute a content hash for deduplication.
        
        Uses entity + event_type + approximate date + key details
        to identify the same event across sources.
        """
        # Normalize entity name
        entity_norm = self.entity_name.lower().strip()
        
        # Normalize date to week precision (same event in same week = likely same)
        date_str = ""
        if self.event_date:
            # Use year + week number for approximate matching
            date_str = self.event_date.strftime("%Y-W%W")
        
        # Build hash components based on event type
        components = [
            entity_norm,
            self.event_type.value,
            date_str,
        ]
        
        # Add type-specific identifiers
        if self.funding_details:
            # Include stage and approximate amount (rounded to nearest 10M)
            components.append(self.funding_details.stage.value)
            if self.funding_details.amount_usd:
                amount_bucket = int(self.funding_details.amount_usd / 10_000_000)
                components.append(f"amt_{amount_bucket}")
        
        if self.acquisition_details:
            components.append(self.acquisition_details.acquirer_name.lower())
            components.append(self.acquisition_details.target_name.lower())
        
        if self.product_details:
            components.append(self.product_details.product_name.lower())
        
        if self.leadership_details:
            components.append(self.leadership_details.person_name.lower())
            components.append(self.leadership_details.change_type)
        
        # Create hash
        content = "|".join(str(c) for c in components if c)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    @property
    def source_count(self) -> int:
        """Number of sources reporting this event."""
        return len(self.sources)
    
    @property
    def avg_source_credibility(self) -> float:
        """Average credibility of sources."""
        if not self.sources:
            return 0.0
        return sum(s.source_credibility for s in self.sources) / len(self.sources)
    
    def add_source(self, source: EventSource) -> None:
        """Add a source, updating confidence based on source count."""
        # Check for duplicate source URLs
        existing_urls = {s.source_url for s in self.sources}
        if source.source_url in existing_urls:
            return
        
        self.sources.append(source)
        self.last_updated = datetime.utcnow()
        self._update_confidence()
    
    def _update_confidence(self) -> None:
        """Update confidence based on source count and credibility."""
        if not self.sources:
            self.confidence = EventConfidence.UNVERIFIED
            self.confidence_score = 0.0
            return
        
        # Base score from source count
        count_score = min(1.0, len(self.sources) / 3)  # Max at 3 sources
        
        # Weight by credibility
        cred_score = self.avg_source_credibility
        
        # Combine (60% count, 40% credibility)
        self.confidence_score = (0.6 * count_score) + (0.4 * cred_score)
        
        # Map to enum
        if self.confidence_score >= 0.7:
            self.confidence = EventConfidence.HIGH
        elif self.confidence_score >= 0.4:
            self.confidence = EventConfidence.MEDIUM
        elif self.confidence_score > 0:
            self.confidence = EventConfidence.LOW
        else:
            self.confidence = EventConfidence.UNVERIFIED
    
    def merge_with(self, other: "BusinessEvent") -> None:
        """
        Merge another event into this one (for deduplication).
        
        Combines sources and updates confidence.
        """
        if other.event_id == self.event_id:
            return
        
        # Add sources from other
        for source in other.sources:
            self.add_source(source)
        
        # Track merged event IDs
        self.merged_from.append(other.event_id)
        self.merged_from.extend(other.merged_from)
        
        # Use earliest first_reported
        if other.first_reported < self.first_reported:
            self.first_reported = other.first_reported
        
        # Use most complete details
        if not self.summary and other.summary:
            self.summary = other.summary
        
        if not self.headline and other.headline:
            self.headline = other.headline
        
        # Merge type-specific details (prefer existing, fill gaps)
        if other.funding_details and not self.funding_details:
            self.funding_details = other.funding_details
        elif other.funding_details and self.funding_details:
            # Merge investor lists
            for inv in other.funding_details.lead_investors:
                if inv not in self.funding_details.lead_investors:
                    self.funding_details.lead_investors.append(inv)
            for inv in other.funding_details.all_investors:
                if inv not in self.funding_details.all_investors:
                    self.funding_details.all_investors.append(inv)
        
        self.last_updated = datetime.utcnow()
    
    def is_similar_to(self, other: "BusinessEvent", threshold: float = 0.7) -> bool:
        """
        Check if this event is similar to another (for dedup).
        
        Uses content hash match or fuzzy matching on key fields.
        """
        # Exact hash match
        if self.content_hash == other.content_hash:
            return True
        
        # Must be same event type
        if self.event_type != other.event_type:
            return False
        
        # Entity must match (fuzzy)
        from difflib import SequenceMatcher
        
        # Normalize entity names for comparison
        name1 = self.entity_name.lower().replace("inc", "").replace(".", "").strip()
        name2 = other.entity_name.lower().replace("inc", "").replace(".", "").strip()
        
        entity_sim = SequenceMatcher(None, name1, name2).ratio()
        
        # Also check if one contains the other
        if name1 in name2 or name2 in name1:
            entity_sim = max(entity_sim, 0.85)
        
        if entity_sim < threshold:
            return False
        
        # Date must be within 2 weeks
        if self.event_date and other.event_date:
            date_diff = abs((self.event_date - other.event_date).days)
            if date_diff > 14:
                return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "related_entity_ids": self.related_entity_ids,
            "related_entity_names": self.related_entity_names,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "headline": self.headline,
            "summary": self.summary,
            "funding_details": self.funding_details.to_dict() if self.funding_details else None,
            "acquisition_details": self.acquisition_details.to_dict() if self.acquisition_details else None,
            "product_details": self.product_details.to_dict() if self.product_details else None,
            "leadership_details": self.leadership_details.to_dict() if self.leadership_details else None,
            "partnership_details": self.partnership_details.to_dict() if self.partnership_details else None,
            "layoff_details": self.layoff_details.to_dict() if self.layoff_details else None,
            "details": self.details,
            "sources": [s.to_dict() for s in self.sources],
            "confidence": self.confidence.value,
            "confidence_score": self.confidence_score,
            "content_hash": self.content_hash,
            "merged_from": self.merged_from,
            "parent_event_id": self.parent_event_id,
            "related_event_ids": self.related_event_ids,
            "first_reported": self.first_reported.isoformat(),
            "last_updated": self.last_updated.isoformat(),
            "created_at": self.created_at.isoformat(),
            "source_count": self.source_count,
            "avg_source_credibility": self.avg_source_credibility,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BusinessEvent":
        """Create from dictionary."""
        event = cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            event_type=BusinessEventType(data.get("event_type", "product_launch")),
            entity_id=data.get("entity_id", ""),
            entity_name=data.get("entity_name", ""),
            related_entity_ids=data.get("related_entity_ids", []),
            related_entity_names=data.get("related_entity_names", []),
            headline=data.get("headline", ""),
            summary=data.get("summary", ""),
            details=data.get("details", {}),
            confidence=EventConfidence(data.get("confidence", "medium")),
            confidence_score=data.get("confidence_score", 0.5),
            content_hash=data.get("content_hash", ""),
            merged_from=data.get("merged_from", []),
            parent_event_id=data.get("parent_event_id"),
            related_event_ids=data.get("related_event_ids", []),
        )
        
        # Parse dates
        if data.get("event_date"):
            event.event_date = datetime.fromisoformat(data["event_date"])
        if data.get("first_reported"):
            event.first_reported = datetime.fromisoformat(data["first_reported"])
        if data.get("last_updated"):
            event.last_updated = datetime.fromisoformat(data["last_updated"])
        if data.get("created_at"):
            event.created_at = datetime.fromisoformat(data["created_at"])
        
        # Parse sources
        event.sources = [EventSource.from_dict(s) for s in data.get("sources", [])]
        
        # Parse type-specific details
        if data.get("funding_details"):
            event.funding_details = FundingDetails.from_dict(data["funding_details"])
        if data.get("acquisition_details"):
            event.acquisition_details = AcquisitionDetails.from_dict(data["acquisition_details"])
        if data.get("product_details"):
            event.product_details = ProductLaunchDetails.from_dict(data["product_details"])
        if data.get("leadership_details"):
            event.leadership_details = LeadershipChangeDetails.from_dict(data["leadership_details"])
        if data.get("partnership_details"):
            event.partnership_details = PartnershipDetails.from_dict(data["partnership_details"])
        if data.get("layoff_details"):
            event.layoff_details = LayoffDetails.from_dict(data["layoff_details"])
        
        return event


@dataclass
class EventTimeline:
    """
    A timeline of events for an entity.
    
    Provides chronological view of events with causal chain detection.
    """
    entity_id: str
    entity_name: str
    events: List[BusinessEvent] = field(default_factory=list)
    
    def add_event(self, event: BusinessEvent) -> None:
        """Add event and maintain chronological order."""
        self.events.append(event)
        self.events.sort(key=lambda e: e.event_date or e.first_reported)
    
    def get_events_by_type(self, event_type: BusinessEventType) -> List[BusinessEvent]:
        """Filter events by type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_events_in_range(
        self, 
        start: datetime, 
        end: datetime
    ) -> List[BusinessEvent]:
        """Get events within a date range."""
        return [
            e for e in self.events
            if e.event_date and start <= e.event_date <= end
        ]
    
    def detect_causal_chains(self) -> List[List[BusinessEvent]]:
        """
        Detect causal chains in the timeline.
        
        Common patterns:
        - FUNDING_ROUND → EXPANSION/HIRING
        - ACQUISITION → LEADERSHIP_CHANGE
        - LAYOFF → PIVOT
        - IPO → LEADERSHIP_CHANGE
        """
        chains = []
        
        # Define causal patterns (cause → effect, max days between)
        patterns = [
            (BusinessEventType.FUNDING_ROUND, BusinessEventType.EXPANSION, 90),
            (BusinessEventType.FUNDING_ROUND, BusinessEventType.PRODUCT_LAUNCH, 180),
            (BusinessEventType.ACQUISITION, BusinessEventType.LEADERSHIP_CHANGE, 60),
            (BusinessEventType.IPO, BusinessEventType.LEADERSHIP_CHANGE, 90),
            (BusinessEventType.LAYOFF, BusinessEventType.PIVOT, 120),
            (BusinessEventType.PARTNERSHIP, BusinessEventType.PRODUCT_LAUNCH, 180),
        ]
        
        for cause_type, effect_type, max_days in patterns:
            causes = self.get_events_by_type(cause_type)
            effects = self.get_events_by_type(effect_type)
            
            for cause in causes:
                if not cause.event_date:
                    continue
                    
                for effect in effects:
                    if not effect.event_date:
                        continue
                    
                    # Effect must come after cause
                    days_diff = (effect.event_date - cause.event_date).days
                    if 0 < days_diff <= max_days:
                        chains.append([cause, effect])
                        
                        # Link the events
                        if cause.event_id not in effect.related_event_ids:
                            effect.related_event_ids.append(cause.event_id)
                            effect.parent_event_id = cause.event_id
        
        return chains
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_id": self.entity_id,
            "entity_name": self.entity_name,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
            "causal_chains": [
                [e.event_id for e in chain]
                for chain in self.detect_causal_chains()
            ],
        }
