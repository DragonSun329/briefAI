"""
Vertical Tagger

Tags entities (companies, technologies) to industry verticals using:
1. Direct company name matching
2. Keyword matching in descriptions/news
3. Bucket-to-vertical inference (entity in 'ai-healthcare' bucket → 'ai_healthcare' vertical)
4. Multi-vertical support (one entity can serve multiple verticals)

This creates the entity → vertical dimension for the multi-dimensional cube.
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class VerticalMatch:
    """Result of matching an entity to a vertical."""
    vertical_id: str
    vertical_name: str
    confidence: float  # 0-1
    match_reason: str  # "company", "keyword", "bucket", "cross_ref"
    matched_terms: List[str] = field(default_factory=list)


@dataclass
class Vertical:
    """An industry vertical definition."""
    id: str
    name: str
    keywords: List[str]
    companies: List[str]
    related_buckets: List[str]
    
    def __hash__(self):
        return hash(self.id)


class VerticalTagger:
    """
    Tags entities to industry verticals.
    
    Usage:
        tagger = VerticalTagger()
        matches = tagger.tag_entity(
            name="Tempus",
            description="AI for precision medicine",
            buckets=["ai-healthcare"]
        )
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize tagger with vertical definitions.
        
        Args:
            config_path: Path to entity_vertical_mapping.json. Uses default if None.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "entity_vertical_mapping.json"
        
        self.config_path = config_path
        self.verticals: Dict[str, Vertical] = {}
        self.cross_references: Dict[str, List[str]] = {}
        
        # Build reverse indices for fast lookup
        self._company_index: Dict[str, Set[str]] = {}      # normalized company → vertical_ids
        self._keyword_index: Dict[str, Set[str]] = {}      # keyword → vertical_ids
        self._bucket_index: Dict[str, Set[str]] = {}       # bucket_id → vertical_ids
        
        self._load_config()
        self._build_indices()
    
    def _load_config(self):
        """Load vertical definitions from config."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Vertical config not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Load verticals
        for vertical_id, vertical_data in config.get("verticals", {}).items():
            self.verticals[vertical_id] = Vertical(
                id=vertical_id,
                name=vertical_data.get("name", vertical_id),
                keywords=vertical_data.get("keywords", []),
                companies=vertical_data.get("companies", []),
                related_buckets=vertical_data.get("related_buckets", [])
            )
        
        # Load cross-references (entities that span multiple verticals)
        cross_refs = config.get("cross_references", {}).get("multi_vertical_entities", {})
        self.cross_references = cross_refs
    
    def _normalize(self, text: str) -> str:
        """Normalize text for matching."""
        if not text:
            return ""
        return re.sub(r'[^a-z0-9]', '', text.lower())
    
    def _build_indices(self):
        """Build reverse indices for fast lookup."""
        for vertical in self.verticals.values():
            # Index companies
            for company in vertical.companies:
                key = self._normalize(company)
                if key not in self._company_index:
                    self._company_index[key] = set()
                self._company_index[key].add(vertical.id)
            
            # Index keywords
            for keyword in vertical.keywords:
                key = self._normalize(keyword)
                if key not in self._keyword_index:
                    self._keyword_index[key] = set()
                self._keyword_index[key].add(vertical.id)
            
            # Index related buckets
            for bucket_id in vertical.related_buckets:
                if bucket_id not in self._bucket_index:
                    self._bucket_index[bucket_id] = set()
                self._bucket_index[bucket_id].add(vertical.id)
        
        # Index cross-references
        for entity_name, verticals in self.cross_references.items():
            key = self._normalize(entity_name)
            if key not in self._company_index:
                self._company_index[key] = set()
            self._company_index[key].update(verticals)
    
    def tag_entity(
        self,
        name: str,
        description: Optional[str] = None,
        buckets: Optional[List[str]] = None,
        entity_type: str = "company",
        min_confidence: float = 0.3
    ) -> List[VerticalMatch]:
        """
        Tag an entity to industry verticals.
        
        Args:
            name: Entity name (company name, tech name)
            description: Optional description text to match keywords
            buckets: Optional list of bucket IDs the entity belongs to
            entity_type: Type of entity (company, technology, concept)
            min_confidence: Minimum confidence threshold (0-1)
        
        Returns:
            List of VerticalMatch objects, sorted by confidence (desc)
        """
        matches: Dict[str, VerticalMatch] = {}
        
        # 1. Direct company name match (highest confidence)
        name_key = self._normalize(name)
        if name_key in self._company_index:
            for vertical_id in self._company_index[name_key]:
                vertical = self.verticals.get(vertical_id)
                if vertical:
                    matches[vertical_id] = VerticalMatch(
                        vertical_id=vertical_id,
                        vertical_name=vertical.name,
                        confidence=0.95,
                        match_reason="company",
                        matched_terms=[name]
                    )
        
        # 2. Keyword matching in description
        if description:
            desc_lower = description.lower()
            for vertical in self.verticals.values():
                if vertical.id in matches:
                    continue  # Already matched with higher confidence
                
                matched_keywords = []
                for keyword in vertical.keywords:
                    if keyword.lower() in desc_lower:
                        matched_keywords.append(keyword)
                
                if matched_keywords:
                    # Confidence based on number of keyword matches
                    confidence = min(0.5 + 0.1 * len(matched_keywords), 0.85)
                    matches[vertical.id] = VerticalMatch(
                        vertical_id=vertical.id,
                        vertical_name=vertical.name,
                        confidence=confidence,
                        match_reason="keyword",
                        matched_terms=matched_keywords
                    )
        
        # 3. Bucket-to-vertical inference
        if buckets:
            for bucket_id in buckets:
                if bucket_id in self._bucket_index:
                    for vertical_id in self._bucket_index[bucket_id]:
                        if vertical_id in matches:
                            # Boost existing match confidence
                            matches[vertical_id].confidence = min(
                                matches[vertical_id].confidence + 0.1, 0.95
                            )
                            if bucket_id not in matches[vertical_id].matched_terms:
                                matches[vertical_id].matched_terms.append(f"bucket:{bucket_id}")
                        else:
                            vertical = self.verticals.get(vertical_id)
                            if vertical:
                                matches[vertical_id] = VerticalMatch(
                                    vertical_id=vertical_id,
                                    vertical_name=vertical.name,
                                    confidence=0.6,
                                    match_reason="bucket",
                                    matched_terms=[f"bucket:{bucket_id}"]
                                )
        
        # Filter by min confidence and sort
        result = [m for m in matches.values() if m.confidence >= min_confidence]
        result.sort(key=lambda x: x.confidence, reverse=True)
        
        return result
    
    def get_vertical_companies(self, vertical_id: str) -> List[str]:
        """Get all companies in a vertical."""
        vertical = self.verticals.get(vertical_id)
        if vertical:
            return vertical.companies
        return []
    
    def get_entity_verticals(self, entity_name: str) -> List[str]:
        """Get all vertical IDs for an entity (quick lookup)."""
        key = self._normalize(entity_name)
        if key in self._company_index:
            return list(self._company_index[key])
        return []
    
    def get_bucket_verticals(self, bucket_id: str) -> List[str]:
        """Get vertical IDs related to a bucket."""
        return list(self._bucket_index.get(bucket_id, set()))
    
    def tag_from_buckets(self, bucket_ids: List[str]) -> Dict[str, float]:
        """
        Get vertical weights from bucket memberships.
        
        Returns:
            Dict mapping vertical_id → weight (0-1)
        """
        vertical_weights: Dict[str, float] = {}
        
        for bucket_id in bucket_ids:
            verticals = self._bucket_index.get(bucket_id, set())
            for vertical_id in verticals:
                if vertical_id not in vertical_weights:
                    vertical_weights[vertical_id] = 0.0
                vertical_weights[vertical_id] += 0.3  # Each bucket adds weight
        
        # Normalize to max 1.0
        for vid in vertical_weights:
            vertical_weights[vid] = min(vertical_weights[vid], 1.0)
        
        return vertical_weights
    
    def list_verticals(self) -> List[Dict[str, Any]]:
        """List all verticals with metadata."""
        return [
            {
                "id": v.id,
                "name": v.name,
                "company_count": len(v.companies),
                "keyword_count": len(v.keywords),
                "related_buckets": v.related_buckets
            }
            for v in self.verticals.values()
        ]


# Singleton instance for convenience
_tagger: Optional[VerticalTagger] = None


def get_vertical_tagger() -> VerticalTagger:
    """Get singleton VerticalTagger instance."""
    global _tagger
    if _tagger is None:
        _tagger = VerticalTagger()
    return _tagger


def tag_entity_to_verticals(
    name: str,
    description: Optional[str] = None,
    buckets: Optional[List[str]] = None
) -> List[VerticalMatch]:
    """Convenience function to tag an entity."""
    return get_vertical_tagger().tag_entity(name, description, buckets)
