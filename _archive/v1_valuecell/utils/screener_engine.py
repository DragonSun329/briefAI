"""
Custom Screener Engine

Powerful filtering system for entities based on multi-dimensional criteria.
Supports score filters, momentum, categories, signals, dates, and comparisons.

Key Features:
- Flexible criterion-based filtering
- Field comparisons (media_score > technical_score)
- Persistence of custom screeners
- Real-time preview with match counts
"""

from __future__ import annotations

import json
import operator
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from loguru import logger

from pydantic import BaseModel, Field

from .signal_store import SignalStore
from .signal_models import SignalProfile, SignalCategory, EntityType


# =============================================================================
# Data Models
# =============================================================================

class FilterOperator(str, Enum):
    """Supported filter operators."""
    EQ = "="
    NEQ = "!="
    GT = ">"
    GTE = ">="
    LT = "<"
    LTE = "<="
    IN = "in"
    NOT_IN = "not_in"
    CONTAINS = "contains"
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    BETWEEN = "between"
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"
    FIELD_GT = "field_gt"   # Compare two fields
    FIELD_LT = "field_lt"
    FIELD_GTE = "field_gte"
    FIELD_LTE = "field_lte"
    

class CriterionType(str, Enum):
    """Types of filtering criteria."""
    SCORE = "score"              # media_score > 7
    MOMENTUM = "momentum"        # momentum_7d > 10%
    CATEGORY = "category"        # sector = "ai-foundation"
    SIGNAL = "signal"            # has_funding_signal = true
    DATE = "date"                # last_signal_date > 7 days ago
    COMPARISON = "comparison"    # media_score > technical_score
    COMPOSITE = "composite"      # composite_score > 50


class Criterion(BaseModel):
    """A single filter criterion."""
    field: str                                    # Field to filter on
    operator: FilterOperator                      # Comparison operator
    value: Any                                    # Value to compare against
    criterion_type: CriterionType = CriterionType.SCORE
    compare_field: Optional[str] = None          # For field comparisons
    
    # Optional metadata
    label: Optional[str] = None                  # Human-readable label
    description: Optional[str] = None            # Explanation
    
    class Config:
        use_enum_values = True


class LogicalOperator(str, Enum):
    """Logical operators for combining criteria."""
    AND = "AND"
    OR = "OR"


class CriteriaGroup(BaseModel):
    """Group of criteria combined with a logical operator."""
    criteria: List[Union[Criterion, "CriteriaGroup"]] = Field(default_factory=list)
    operator: LogicalOperator = LogicalOperator.AND
    
    class Config:
        use_enum_values = True


class Screener(BaseModel):
    """A saved screener configuration."""
    name: str
    description: Optional[str] = None
    criteria: List[Criterion] = Field(default_factory=list)
    criteria_group: Optional[CriteriaGroup] = None  # For complex logic
    
    # Screener settings
    sort_by: Optional[str] = "composite_score"
    sort_order: str = "desc"
    limit: int = 100
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    is_preset: bool = False
    category: Optional[str] = None  # For organizing screeners
    tags: List[str] = Field(default_factory=list)
    
    # Performance tracking
    last_run_at: Optional[datetime] = None
    last_match_count: Optional[int] = None


class ScreenerResult(BaseModel):
    """Result of running a screener."""
    screener_name: str
    total_entities: int
    matching_entities: int
    results: List[Dict[str, Any]]
    execution_time_ms: float
    criteria_summary: str
    run_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# Field Definitions
# =============================================================================

# Map of available fields and their types
SCREENABLE_FIELDS = {
    # Score fields (0-100 scale)
    "technical_score": {"type": "float", "range": (0, 100), "category": "scores", "description": "Technical/research signal strength"},
    "company_score": {"type": "float", "range": (0, 100), "category": "scores", "description": "Company fundamentals strength"},
    "financial_score": {"type": "float", "range": (0, 100), "category": "scores", "description": "Financial/funding signal strength"},
    "product_score": {"type": "float", "range": (0, 100), "category": "scores", "description": "Product traction signal strength"},
    "media_score": {"type": "float", "range": (0, 100), "category": "scores", "description": "Media coverage signal strength"},
    "composite_score": {"type": "float", "range": (0, 100), "category": "scores", "description": "Weighted composite of all signals"},
    
    # Momentum fields (percentage change)
    "momentum_7d": {"type": "float", "range": (-100, 500), "category": "momentum", "description": "7-day score momentum %"},
    "momentum_30d": {"type": "float", "range": (-100, 500), "category": "momentum", "description": "30-day score momentum %"},
    "buzz_momentum": {"type": "float", "range": (-100, 500), "category": "momentum", "description": "Mention velocity change"},
    "funding_momentum": {"type": "float", "range": (-100, 1000), "category": "momentum", "description": "Funding acceleration"},
    
    # Divergence fields
    "has_divergence": {"type": "bool", "category": "signals", "description": "Has active divergence"},
    "divergence_strength": {"type": "float", "range": (0, 1), "category": "signals", "description": "Divergence magnitude"},
    "divergence_type": {"type": "str", "category": "signals", "description": "Type of divergence detected"},
    
    # Category fields
    "entity_type": {"type": "str", "values": ["company", "technology", "concept", "person"], "category": "category", "description": "Entity classification"},
    "sector": {"type": "str", "category": "category", "description": "Business sector"},
    "region": {"type": "str", "category": "category", "description": "Geographic region"},
    
    # Signal flags
    "has_funding_signal": {"type": "bool", "category": "signals", "description": "Recent funding activity"},
    "has_product_launch": {"type": "bool", "category": "signals", "description": "Recent product launch"},
    "has_partnership": {"type": "bool", "category": "signals", "description": "Recent partnership announcement"},
    "has_regulatory": {"type": "bool", "category": "signals", "description": "Regulatory news"},
    "has_leadership_change": {"type": "bool", "category": "signals", "description": "Leadership/org changes"},
    
    # Date fields
    "last_signal_date": {"type": "date", "category": "dates", "description": "Most recent signal timestamp"},
    "last_funding_date": {"type": "date", "category": "dates", "description": "Most recent funding"},
    "created_at": {"type": "date", "category": "dates", "description": "When entity was first tracked"},
    
    # Computed fields
    "signal_count_7d": {"type": "int", "category": "activity", "description": "Number of signals in past 7 days"},
    "signal_count_30d": {"type": "int", "category": "activity", "description": "Number of signals in past 30 days"},
    "mention_count": {"type": "int", "category": "activity", "description": "Total mentions"},
    "volatility": {"type": "float", "range": (0, 100), "category": "risk", "description": "Score volatility"},
}


# =============================================================================
# Screener Engine
# =============================================================================

class ScreenerEngine:
    """
    Core engine for screening entities based on custom criteria.
    
    Usage:
        engine = ScreenerEngine()
        
        # Simple screening
        criteria = [
            Criterion(field="media_score", operator=FilterOperator.GT, value=7),
            Criterion(field="momentum_7d", operator=FilterOperator.GT, value=10),
        ]
        results = engine.screen(criteria)
        
        # Field comparison
        criteria = [
            Criterion(
                field="media_score",
                operator=FilterOperator.FIELD_GT,
                compare_field="technical_score",
                criterion_type=CriterionType.COMPARISON
            )
        ]
        
        # Save/load screeners
        engine.save_screener("my-screener", criteria)
        loaded = engine.load_screener("my-screener")
    """
    
    def __init__(self, store: Optional[SignalStore] = None, screeners_path: Optional[Path] = None):
        self.store = store or SignalStore()
        self.screeners_path = screeners_path or Path(__file__).parent.parent / "data" / "screeners"
        self.screeners_path.mkdir(parents=True, exist_ok=True)
        
        # Presets path
        self.presets_path = Path(__file__).parent.parent / "config" / "preset_screeners.json"
        
        # Operator mapping
        self._operators: Dict[FilterOperator, Callable] = {
            FilterOperator.EQ: operator.eq,
            FilterOperator.NEQ: operator.ne,
            FilterOperator.GT: operator.gt,
            FilterOperator.GTE: operator.ge,
            FilterOperator.LT: operator.lt,
            FilterOperator.LTE: operator.le,
        }
        
        logger.info(f"ScreenerEngine initialized with screeners path: {self.screeners_path}")
    
    # -------------------------------------------------------------------------
    # Core Screening
    # -------------------------------------------------------------------------
    
    def screen(
        self,
        criteria: List[Criterion],
        entities: Optional[List[Dict[str, Any]]] = None,
        limit: int = 100,
        sort_by: str = "composite_score",
        sort_order: str = "desc"
    ) -> ScreenerResult:
        """
        Screen entities based on criteria.
        
        Args:
            criteria: List of filter criteria
            entities: Optional pre-loaded entities (fetches from store if None)
            limit: Maximum results to return
            sort_by: Field to sort by
            sort_order: "asc" or "desc"
            
        Returns:
            ScreenerResult with matching entities
        """
        import time
        start_time = time.time()
        
        # Load entities if not provided
        if entities is None:
            entities = self._load_all_entities()
        
        total_entities = len(entities)
        
        # Apply filters
        matching = []
        for entity in entities:
            if self._matches_all_criteria(entity, criteria):
                matching.append(entity)
        
        # Sort results
        reverse = sort_order.lower() == "desc"
        matching.sort(
            key=lambda e: self._get_sort_value(e, sort_by),
            reverse=reverse
        )
        
        # Apply limit
        results = matching[:limit]
        
        execution_time = (time.time() - start_time) * 1000
        
        return ScreenerResult(
            screener_name="custom",
            total_entities=total_entities,
            matching_entities=len(matching),
            results=results,
            execution_time_ms=round(execution_time, 2),
            criteria_summary=self._summarize_criteria(criteria),
            run_at=datetime.utcnow()
        )
    
    def screen_with_group(
        self,
        criteria_group: CriteriaGroup,
        entities: Optional[List[Dict[str, Any]]] = None,
        limit: int = 100,
        sort_by: str = "composite_score",
        sort_order: str = "desc"
    ) -> ScreenerResult:
        """Screen with complex grouped criteria (AND/OR logic)."""
        import time
        start_time = time.time()
        
        if entities is None:
            entities = self._load_all_entities()
        
        total_entities = len(entities)
        
        matching = [e for e in entities if self._matches_criteria_group(e, criteria_group)]
        
        reverse = sort_order.lower() == "desc"
        matching.sort(
            key=lambda e: self._get_sort_value(e, sort_by),
            reverse=reverse
        )
        
        results = matching[:limit]
        execution_time = (time.time() - start_time) * 1000
        
        return ScreenerResult(
            screener_name="custom_grouped",
            total_entities=total_entities,
            matching_entities=len(matching),
            results=results,
            execution_time_ms=round(execution_time, 2),
            criteria_summary=self._summarize_group(criteria_group),
            run_at=datetime.utcnow()
        )
    
    def run_screener(self, name: str) -> ScreenerResult:
        """Run a saved screener by name."""
        screener = self.load_screener(name)
        if screener is None:
            raise ValueError(f"Screener not found: {name}")
        
        if screener.criteria_group:
            result = self.screen_with_group(
                screener.criteria_group,
                limit=screener.limit,
                sort_by=screener.sort_by or "composite_score",
                sort_order=screener.sort_order
            )
        else:
            result = self.screen(
                screener.criteria,
                limit=screener.limit,
                sort_by=screener.sort_by or "composite_score",
                sort_order=screener.sort_order
            )
        
        result.screener_name = name
        
        # Update screener stats
        screener.last_run_at = datetime.utcnow()
        screener.last_match_count = result.matching_entities
        self.save_screener(name, screener.criteria, screener)
        
        return result
    
    # -------------------------------------------------------------------------
    # Criterion Matching
    # -------------------------------------------------------------------------
    
    def _matches_all_criteria(self, entity: Dict[str, Any], criteria: List[Criterion]) -> bool:
        """Check if entity matches all criteria (AND logic)."""
        return all(self._matches_criterion(entity, c) for c in criteria)
    
    def _matches_criteria_group(self, entity: Dict[str, Any], group: CriteriaGroup) -> bool:
        """Recursively evaluate a criteria group."""
        results = []
        
        for item in group.criteria:
            if isinstance(item, CriteriaGroup):
                results.append(self._matches_criteria_group(entity, item))
            else:
                results.append(self._matches_criterion(entity, item))
        
        if group.operator == LogicalOperator.AND:
            return all(results)
        else:  # OR
            return any(results)
    
    def _matches_criterion(self, entity: Dict[str, Any], criterion: Criterion) -> bool:
        """Evaluate a single criterion against an entity."""
        try:
            field_value = self._get_field_value(entity, criterion.field)
            
            # Handle field comparison operators
            if criterion.operator in [FilterOperator.FIELD_GT, FilterOperator.FIELD_LT,
                                       FilterOperator.FIELD_GTE, FilterOperator.FIELD_LTE]:
                return self._compare_fields(entity, criterion)
            
            # Handle NULL checks
            if criterion.operator == FilterOperator.IS_NULL:
                return field_value is None
            if criterion.operator == FilterOperator.IS_NOT_NULL:
                return field_value is not None
            
            # Skip if field is None (unless checking for null)
            if field_value is None:
                return False
            
            # Handle IN/NOT_IN operators
            if criterion.operator == FilterOperator.IN:
                values = criterion.value if isinstance(criterion.value, list) else [criterion.value]
                return field_value in values
            
            if criterion.operator == FilterOperator.NOT_IN:
                values = criterion.value if isinstance(criterion.value, list) else [criterion.value]
                return field_value not in values
            
            # Handle CONTAINS
            if criterion.operator == FilterOperator.CONTAINS:
                return str(criterion.value).lower() in str(field_value).lower()
            
            # Handle STARTS_WITH
            if criterion.operator == FilterOperator.STARTS_WITH:
                return str(field_value).lower().startswith(str(criterion.value).lower())
            
            # Handle ENDS_WITH
            if criterion.operator == FilterOperator.ENDS_WITH:
                return str(field_value).lower().endswith(str(criterion.value).lower())
            
            # Handle BETWEEN
            if criterion.operator == FilterOperator.BETWEEN:
                if isinstance(criterion.value, (list, tuple)) and len(criterion.value) == 2:
                    return criterion.value[0] <= field_value <= criterion.value[1]
                return False
            
            # Handle date comparisons
            if criterion.criterion_type == CriterionType.DATE:
                return self._compare_dates(field_value, criterion)
            
            # Standard comparison operators
            op_func = self._operators.get(criterion.operator)
            if op_func:
                compare_value = self._coerce_value(field_value, criterion.value)
                return op_func(field_value, compare_value)
            
            return False
            
        except Exception as e:
            logger.warning(f"Error evaluating criterion {criterion}: {e}")
            return False
    
    def _compare_fields(self, entity: Dict[str, Any], criterion: Criterion) -> bool:
        """Compare two fields within the same entity."""
        field_a = self._get_field_value(entity, criterion.field)
        field_b = self._get_field_value(entity, criterion.compare_field)
        
        if field_a is None or field_b is None:
            return False
        
        op_map = {
            FilterOperator.FIELD_GT: operator.gt,
            FilterOperator.FIELD_LT: operator.lt,
            FilterOperator.FIELD_GTE: operator.ge,
            FilterOperator.FIELD_LTE: operator.le,
        }
        
        op_func = op_map.get(criterion.operator)
        return op_func(field_a, field_b) if op_func else False
    
    def _compare_dates(self, field_value: Any, criterion: Criterion) -> bool:
        """Handle date-specific comparisons like 'within X days'."""
        if isinstance(field_value, str):
            try:
                field_value = datetime.fromisoformat(field_value.replace('Z', '+00:00'))
            except:
                return False
        
        if not isinstance(field_value, datetime):
            return False
        
        # Handle relative date values like "7 days ago"
        compare_value = criterion.value
        if isinstance(compare_value, str):
            match = re.match(r"(\d+)\s*(days?|hours?|weeks?)\s*ago", compare_value.lower())
            if match:
                amount = int(match.group(1))
                unit = match.group(2)
                if "day" in unit:
                    compare_value = datetime.utcnow() - timedelta(days=amount)
                elif "hour" in unit:
                    compare_value = datetime.utcnow() - timedelta(hours=amount)
                elif "week" in unit:
                    compare_value = datetime.utcnow() - timedelta(weeks=amount)
        
        if isinstance(compare_value, str):
            try:
                compare_value = datetime.fromisoformat(compare_value.replace('Z', '+00:00'))
            except:
                return False
        
        op_func = self._operators.get(criterion.operator)
        return op_func(field_value, compare_value) if op_func else False
    
    def _get_field_value(self, entity: Dict[str, Any], field: str) -> Any:
        """Get a field value from entity, supporting nested paths."""
        if "." in field:
            parts = field.split(".")
            value = entity
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return None
            return value
        return entity.get(field)
    
    def _get_sort_value(self, entity: Dict[str, Any], field: str) -> Any:
        """Get sortable value, handling None."""
        value = self._get_field_value(entity, field)
        if value is None:
            return float('-inf')
        return value
    
    def _coerce_value(self, field_value: Any, compare_value: Any) -> Any:
        """Coerce compare_value to match field_value type."""
        if isinstance(field_value, bool):
            if isinstance(compare_value, str):
                return compare_value.lower() in ('true', '1', 'yes')
            return bool(compare_value)
        if isinstance(field_value, (int, float)):
            try:
                # Handle percentage strings like "10%"
                if isinstance(compare_value, str) and compare_value.endswith('%'):
                    return float(compare_value[:-1])
                return type(field_value)(compare_value)
            except:
                return compare_value
        return compare_value
    
    # -------------------------------------------------------------------------
    # Entity Loading
    # -------------------------------------------------------------------------
    
    def _load_all_entities(self) -> List[Dict[str, Any]]:
        """Load all entities with their current signal profiles."""
        entities = []
        
        try:
            # Get all entity profiles from store
            profiles = self.store.get_all_profiles()
            
            for profile in profiles:
                entity = self._profile_to_screenable(profile)
                if entity:
                    entities.append(entity)
            
            logger.debug(f"Loaded {len(entities)} entities for screening")
            
        except Exception as e:
            logger.error(f"Error loading entities: {e}")
            # Try loading from registry as fallback
            entities = self._load_from_registry()
        
        return entities
    
    def _profile_to_screenable(self, profile: Union[SignalProfile, Dict[str, Any]]) -> Dict[str, Any]:
        """Convert a SignalProfile to a screenable dictionary."""
        if isinstance(profile, dict):
            p = profile
        else:
            p = profile.dict() if hasattr(profile, 'dict') else profile.__dict__
        
        # Build screenable entity
        entity = {
            "entity_id": p.get("entity_id"),
            "entity_name": p.get("entity_name"),
            "entity_type": p.get("entity_type"),
            
            # Scores
            "technical_score": p.get("technical_score"),
            "company_score": p.get("company_score"),
            "financial_score": p.get("financial_score"),
            "product_score": p.get("product_score"),
            "media_score": p.get("media_score"),
            "composite_score": p.get("composite_score", 0),
            
            # Momentum
            "momentum_7d": p.get("momentum_7d"),
            "momentum_30d": p.get("momentum_30d"),
            
            # Divergence
            "has_divergence": p.get("active_divergences", []) != [],
            "divergence_strength": self._get_max_divergence_strength(p),
            
            # Metadata
            "sector": p.get("sector"),
            "region": p.get("region"),
            "last_signal_date": p.get("last_updated") or p.get("as_of"),
            
            # Additional data passthrough
            **{k: v for k, v in p.items() if k not in [
                "entity_id", "entity_name", "entity_type",
                "technical_score", "company_score", "financial_score",
                "product_score", "media_score", "composite_score",
                "momentum_7d", "momentum_30d", "sector", "region"
            ]}
        }
        
        return entity
    
    def _get_max_divergence_strength(self, profile: Dict[str, Any]) -> Optional[float]:
        """Get the maximum divergence strength from profile."""
        divergences = profile.get("active_divergences", [])
        if not divergences:
            return None
        strengths = [d.get("magnitude", 0) for d in divergences if isinstance(d, dict)]
        return max(strengths) if strengths else None
    
    def _load_from_registry(self) -> List[Dict[str, Any]]:
        """Fallback: load entities from registry file."""
        registry_path = Path(__file__).parent.parent / "config" / "entity_registry.json"
        if registry_path.exists():
            try:
                with open(registry_path) as f:
                    data = json.load(f)
                return data.get("entities", [])
            except:
                pass
        return []
    
    # -------------------------------------------------------------------------
    # Screener Persistence
    # -------------------------------------------------------------------------
    
    def save_screener(
        self,
        name: str,
        criteria: List[Criterion],
        screener: Optional[Screener] = None
    ) -> Screener:
        """Save a screener configuration."""
        if screener is None:
            screener = Screener(
                name=name,
                criteria=criteria,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
        else:
            screener.updated_at = datetime.utcnow()
        
        # Save to file
        filepath = self.screeners_path / f"{self._sanitize_name(name)}.json"
        with open(filepath, 'w') as f:
            json.dump(screener.dict(), f, indent=2, default=str)
        
        logger.info(f"Saved screener: {name} to {filepath}")
        return screener
    
    def load_screener(self, name: str) -> Optional[Screener]:
        """Load a screener by name."""
        # Try custom screeners first
        filepath = self.screeners_path / f"{self._sanitize_name(name)}.json"
        if filepath.exists():
            try:
                with open(filepath) as f:
                    data = json.load(f)
                return Screener(**data)
            except Exception as e:
                logger.error(f"Error loading screener {name}: {e}")
        
        # Try presets
        preset = self.get_preset_screener(name)
        if preset:
            return preset
        
        return None
    
    def delete_screener(self, name: str) -> bool:
        """Delete a saved screener."""
        filepath = self.screeners_path / f"{self._sanitize_name(name)}.json"
        if filepath.exists():
            filepath.unlink()
            logger.info(f"Deleted screener: {name}")
            return True
        return False
    
    def list_screeners(self, include_presets: bool = True) -> List[Dict[str, Any]]:
        """List all available screeners."""
        screeners = []
        
        # Custom screeners
        for filepath in self.screeners_path.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                screeners.append({
                    "name": data.get("name", filepath.stem),
                    "description": data.get("description"),
                    "is_preset": False,
                    "criteria_count": len(data.get("criteria", [])),
                    "last_run_at": data.get("last_run_at"),
                    "last_match_count": data.get("last_match_count"),
                    "category": data.get("category"),
                    "tags": data.get("tags", []),
                })
            except:
                pass
        
        # Presets
        if include_presets:
            presets = self.get_preset_screeners()
            for preset in presets:
                screeners.append({
                    "name": preset.name,
                    "description": preset.description,
                    "is_preset": True,
                    "criteria_count": len(preset.criteria),
                    "category": preset.category,
                    "tags": preset.tags,
                })
        
        return screeners
    
    # -------------------------------------------------------------------------
    # Preset Screeners
    # -------------------------------------------------------------------------
    
    def get_preset_screeners(self) -> List[Screener]:
        """Load preset screeners from config."""
        if not self.presets_path.exists():
            return []
        
        try:
            with open(self.presets_path) as f:
                data = json.load(f)
            
            presets = []
            for preset_data in data.get("presets", []):
                screener = self._parse_preset(preset_data)
                if screener:
                    presets.append(screener)
            
            return presets
            
        except Exception as e:
            logger.error(f"Error loading preset screeners: {e}")
            return []
    
    def get_preset_screener(self, name: str) -> Optional[Screener]:
        """Get a specific preset screener by name."""
        presets = self.get_preset_screeners()
        for preset in presets:
            if preset.name.lower() == name.lower() or self._sanitize_name(preset.name) == self._sanitize_name(name):
                return preset
        return None
    
    def _parse_preset(self, preset_data: Dict[str, Any]) -> Optional[Screener]:
        """Parse a preset definition into a Screener."""
        try:
            criteria = []
            for c in preset_data.get("criteria", []):
                # Handle field comparison (no value needed)
                value = c.get("value")
                compare_field = c.get("compare_field")
                
                criterion = Criterion(
                    field=c["field"],
                    operator=FilterOperator(c["operator"]),
                    value=value,
                    criterion_type=CriterionType(c.get("type", "score")),
                    compare_field=compare_field,
                    label=c.get("label"),
                    description=c.get("description")
                )
                criteria.append(criterion)
            
            return Screener(
                name=preset_data["name"],
                description=preset_data.get("description"),
                criteria=criteria,
                sort_by=preset_data.get("sort_by", "composite_score"),
                sort_order=preset_data.get("sort_order", "desc"),
                limit=preset_data.get("limit", 100),
                is_preset=True,
                category=preset_data.get("category"),
                tags=preset_data.get("tags", [])
            )
        except Exception as e:
            logger.error(f"Error parsing preset: {e}")
            return None
    
    # -------------------------------------------------------------------------
    # Utilities
    # -------------------------------------------------------------------------
    
    def _sanitize_name(self, name: str) -> str:
        """Convert name to filesystem-safe format."""
        return re.sub(r'[^\w\-]', '_', name.lower())
    
    def _summarize_criteria(self, criteria: List[Criterion]) -> str:
        """Generate human-readable summary of criteria."""
        parts = []
        for c in criteria:
            if c.compare_field:
                parts.append(f"{c.field} {c.operator} {c.compare_field}")
            else:
                value = f"{c.value}%" if c.criterion_type == CriterionType.MOMENTUM else c.value
                parts.append(f"{c.field} {c.operator} {value}")
        return " AND ".join(parts)
    
    def _summarize_group(self, group: CriteriaGroup) -> str:
        """Generate human-readable summary of criteria group."""
        parts = []
        for item in group.criteria:
            if isinstance(item, CriteriaGroup):
                parts.append(f"({self._summarize_group(item)})")
            else:
                if item.compare_field:
                    parts.append(f"{item.field} {item.operator} {item.compare_field}")
                else:
                    parts.append(f"{item.field} {item.operator} {item.value}")
        return f" {group.operator} ".join(parts)
    
    def get_available_fields(self) -> Dict[str, Dict[str, Any]]:
        """Get all screenable fields with metadata."""
        return SCREENABLE_FIELDS.copy()
    
    def validate_criterion(self, criterion: Criterion) -> Tuple[bool, Optional[str]]:
        """Validate a criterion is well-formed."""
        # Check field exists
        if criterion.field not in SCREENABLE_FIELDS:
            return False, f"Unknown field: {criterion.field}"
        
        field_info = SCREENABLE_FIELDS[criterion.field]
        
        # Check operator is valid for field type
        if field_info["type"] == "bool" and criterion.operator not in [FilterOperator.EQ, FilterOperator.NEQ]:
            return False, f"Boolean field '{criterion.field}' only supports = and != operators"
        
        # Check value is in range (if applicable)
        if "range" in field_info and criterion.value is not None:
            try:
                val = float(str(criterion.value).rstrip('%'))
                min_val, max_val = field_info["range"]
                if val < min_val or val > max_val:
                    return False, f"Value {val} out of range [{min_val}, {max_val}] for {criterion.field}"
            except:
                pass
        
        # Check enum values
        if "values" in field_info and criterion.value is not None:
            if criterion.operator == FilterOperator.EQ and criterion.value not in field_info["values"]:
                return False, f"Invalid value '{criterion.value}' for {criterion.field}. Valid: {field_info['values']}"
        
        return True, None
    
    def preview(self, criteria: List[Criterion], limit: int = 5) -> Dict[str, Any]:
        """Quick preview of how many entities would match."""
        result = self.screen(criteria, limit=limit)
        return {
            "total_entities": result.total_entities,
            "matching_count": result.matching_entities,
            "sample": result.results[:limit],
            "criteria_summary": result.criteria_summary
        }


# =============================================================================
# Factory Functions
# =============================================================================

def create_score_filter(field: str, operator: str, value: float) -> Criterion:
    """Helper to create a score filter criterion."""
    return Criterion(
        field=field,
        operator=FilterOperator(operator),
        value=value,
        criterion_type=CriterionType.SCORE
    )


def create_momentum_filter(field: str, operator: str, value: float) -> Criterion:
    """Helper to create a momentum filter criterion."""
    return Criterion(
        field=field,
        operator=FilterOperator(operator),
        value=value,
        criterion_type=CriterionType.MOMENTUM
    )


def create_field_comparison(field_a: str, operator: str, field_b: str) -> Criterion:
    """Helper to create a field comparison criterion."""
    op_map = {">": FilterOperator.FIELD_GT, "<": FilterOperator.FIELD_LT,
              ">=": FilterOperator.FIELD_GTE, "<=": FilterOperator.FIELD_LTE}
    return Criterion(
        field=field_a,
        operator=op_map.get(operator, FilterOperator.FIELD_GT),
        compare_field=field_b,
        criterion_type=CriterionType.COMPARISON,
        value=None
    )


def create_category_filter(field: str, values: Union[str, List[str]]) -> Criterion:
    """Helper to create a category filter criterion."""
    return Criterion(
        field=field,
        operator=FilterOperator.IN if isinstance(values, list) else FilterOperator.EQ,
        value=values,
        criterion_type=CriterionType.CATEGORY
    )


def create_date_filter(field: str, operator: str, value: str) -> Criterion:
    """Helper to create a date filter criterion."""
    return Criterion(
        field=field,
        operator=FilterOperator(operator),
        value=value,
        criterion_type=CriterionType.DATE
    )
