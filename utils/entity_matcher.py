"""
Entity Matcher for Trend Radar Validation System.

Resolves raw entity names to canonical entities using a three-tier matching strategy:
- Tier 1: Registry lookup or exact match (confidence 1.0)
- Tier 2: Org/namespace prefix match (confidence 0.6)
- Tier 3: Substring match (confidence 0.2)

Includes coherence checks to upgrade Tier 2 matches to higher confidence.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from functools import lru_cache


@dataclass
class EntityCandidate:
    """A candidate entity match with confidence score."""
    canonical_key: str
    canonical_name: str
    entity_type: str
    match_tier: int  # 1, 2, or 3
    match_method: str  # "registry", "alias", "org_prefix", "hf_namespace", "product", "substring"
    base_confidence: float
    coherence_boosts: List[str] = field(default_factory=list)

    @property
    def confidence(self) -> float:
        """Final confidence including coherence boosts."""
        boost = sum(COHERENCE_BOOST_VALUES.get(b, 0) for b in self.coherence_boosts)
        return min(1.0, self.base_confidence + boost)


@dataclass
class EntityResolution:
    """Result of entity resolution with all candidates."""
    primary_match: Optional[str]  # Best canonical key
    primary_name: Optional[str]  # Best canonical name
    primary_type: Optional[str]  # company, model, org, etc.
    candidates: List[EntityCandidate]
    resolution_confidence: float  # 0-1
    ambiguity_flags: List[str]  # ["common_name", "multiple_orgs", etc.]
    resolution_path: str  # "registry" | "tier1" | "tier2" | "tier3" | "rejected"
    raw_input: str
    normalized_input: str
    # Versioning for reproducibility
    normalization_version: str = "1.0"
    rules_fired: List[str] = field(default_factory=list)  # ["strip_suffix:ai", "lowercase", etc.]


# Coherence boost values
COHERENCE_BOOST_VALUES = {
    "domain_coherence": 0.3,
    "readme_mention": 0.2,
    "model_card_mention": 0.2,
    "namespace_match": 0.1,
    "author_affiliation": 0.2,
}

# Tier confidence values
TIER_CONFIDENCE = {
    1: 1.0,
    2: 0.6,
    3: 0.2,
}


class EntityMatcher:
    """
    Resolves raw entity names to canonical entities.

    Uses a three-tier matching strategy with coherence checks.
    """

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        ambiguity_path: Optional[Path] = None,
        source_categories_path: Optional[Path] = None,
    ):
        config_dir = Path(__file__).parent.parent / "config"

        self.registry_path = registry_path or config_dir / "entity_registry.json"
        self.ambiguity_path = ambiguity_path or config_dir / "ambiguous_entities.json"
        self.source_categories_path = source_categories_path or config_dir / "source_categories.json"

        self.registry = self._load_json(self.registry_path)
        self.ambiguity = self._load_json(self.ambiguity_path)
        self.source_categories = self._load_json(self.source_categories_path)

        # Extract meta and build lookup indices
        self._registry_meta = self.registry.pop("_meta", {})
        self._ambiguity_meta = self.ambiguity.pop("_meta", {})
        self._source_meta = self.source_categories.pop("_meta", {})

        # Build fast lookup indices
        self._build_indices()

    def _load_json(self, path: Path) -> dict:
        """Load JSON file."""
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _build_indices(self):
        """Build lookup indices for fast matching."""
        # Normalized key → canonical key
        self._normalized_to_canonical: Dict[str, str] = {}

        # Alias → canonical key
        self._alias_to_canonical: Dict[str, str] = {}

        # GitHub org → canonical key
        self._github_org_to_canonical: Dict[str, str] = {}

        # HuggingFace namespace → canonical key
        self._hf_namespace_to_canonical: Dict[str, str] = {}

        # Product → canonical key
        self._product_to_canonical: Dict[str, str] = {}

        # Website domain → canonical key
        self._domain_to_canonical: Dict[str, str] = {}

        for key, entity in self.registry.items():
            # Normalized key
            self._normalized_to_canonical[key] = key

            # Aliases
            for alias in entity.get("aliases", []):
                normalized_alias = self._normalize(alias)
                self._alias_to_canonical[normalized_alias] = key

            # GitHub orgs
            for org in entity.get("github_orgs", []):
                self._github_org_to_canonical[org.lower()] = key

            # HuggingFace namespaces
            for ns in entity.get("hf_namespaces", []):
                self._hf_namespace_to_canonical[ns.lower()] = key

            # Products
            for product in entity.get("products", []):
                normalized_product = self._normalize(product)
                self._product_to_canonical[normalized_product] = key

            # Website domain
            website = entity.get("website", "")
            if website:
                domain = website.replace("https://", "").replace("http://", "").split("/")[0]
                self._domain_to_canonical[domain.lower()] = key

        # Build ambiguous term lookup
        self._ambiguous_terms: Dict[str, dict] = {}
        for item in self.ambiguity.get("ambiguous_terms", []):
            term = item["term"].lower()
            self._ambiguous_terms[term] = item

        # Build allowlist sets
        self._allowlist_phrases: Set[str] = set(
            phrase.lower() for phrase in self.ambiguity.get("allowlist_phrases", [])
        )
        self._allowlist_domains: Set[str] = set(
            domain.lower() for domain in self.ambiguity.get("allowlist_domains", [])
        )

        # Compile denylist patterns
        self._denylist_patterns = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in self.ambiguity.get("denylist_patterns", [])
        ]
        self._denylist_exact: Set[str] = set(
            term.lower() for term in self.ambiguity.get("denylist_exact", [])
        )

        # Get source metadata
        self._source_metadata = self.source_categories.get("source_metadata", {})

    def _normalize(self, name: str, track_rules: bool = False) -> str:
        """
        Normalize entity name for matching.

        - Lowercase
        - Strip punctuation
        - Strip common suffixes (inc, corp, ai, labs, co, llc)

        If track_rules=True, returns tuple (normalized, rules_fired).
        """
        if not name:
            return "" if not track_rules else ("", [])

        rules_fired = []

        # Lowercase
        normalized = name.lower().strip()
        if normalized != name:
            rules_fired.append("lowercase")

        # Strip punctuation (keep alphanumeric, spaces, hyphens, dots)
        before_punct = normalized
        normalized = re.sub(r"[^\w\s\-\.]", "", normalized)
        if normalized != before_punct:
            rules_fired.append("strip_punctuation")

        # Strip common suffixes
        suffixes = self._registry_meta.get("suffixes_stripped", ["inc", "corp", "ai", "labs", "co", "llc"])
        for suffix in suffixes:
            pattern = rf"\b{suffix}\.?$"
            before_suffix = normalized
            normalized = re.sub(pattern, "", normalized, flags=re.IGNORECASE).strip()
            if normalized != before_suffix:
                rules_fired.append(f"strip_suffix:{suffix}")

        # Collapse whitespace
        before_ws = normalized
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized != before_ws:
            rules_fired.append("collapse_whitespace")

        if track_rules:
            return normalized, rules_fired
        return normalized

    def _check_denylist(self, name: str) -> bool:
        """Check if name matches denylist patterns or exact terms."""
        normalized = name.lower().strip()

        # Check exact denylist
        if normalized in self._denylist_exact:
            return True

        # Check length constraints
        min_len = self.ambiguity.get("min_entity_length", 2)
        max_len = self.ambiguity.get("max_entity_length", 50)
        if len(normalized) < min_len or len(normalized) > max_len:
            return True

        # Check patterns
        for pattern in self._denylist_patterns:
            if pattern.search(normalized):
                return True

        return False

    def _check_allowlist(self, text: str, url: Optional[str] = None) -> bool:
        """Check if text or URL is in allowlist (bypasses ambiguity checks)."""
        text_lower = text.lower()

        # Check allowlist phrases
        for phrase in self._allowlist_phrases:
            if phrase in text_lower:
                return True

        # Check allowlist domains in URL
        if url:
            url_lower = url.lower()
            for domain in self._allowlist_domains:
                if domain in url_lower:
                    return True

        return False

    def _check_ambiguity(self, name: str, context: str = "") -> Tuple[bool, Optional[str]]:
        """
        Check if name is ambiguous and needs context validation.

        Returns (is_ambiguous, reason).
        """
        normalized = name.lower().strip()

        if normalized not in self._ambiguous_terms:
            return False, None

        term_info = self._ambiguous_terms[normalized]
        require_context = term_info.get("require_context", [])
        reason = term_info.get("reason", "Ambiguous term")

        # Check if any required context is present
        context_lower = context.lower()
        for ctx in require_context:
            if ctx.lower() in context_lower:
                return False, None  # Context validates the term

        return True, reason

    def _get_source_tier_cap(self, source: str) -> int:
        """Get the maximum match tier allowed for a source."""
        source_meta = self._source_metadata.get(source, {})
        return source_meta.get("default_match_tier_cap", 3)

    def resolve_entity(
        self,
        name: str,
        source: str = "",
        context: str = "",
        url: Optional[str] = None,
    ) -> EntityResolution:
        """
        Resolve raw name to canonical entity with candidates.

        Args:
            name: Raw entity name to resolve
            source: Source type (e.g., "github", "huggingface", "reddit")
            context: Additional context text for ambiguity resolution
            url: Optional URL for domain-based validation

        Returns:
            EntityResolution with primary match and all candidates
        """
        raw_input = name
        normalized, rules_fired = self._normalize(name, track_rules=True)

        # Get normalization version from registry meta
        norm_version = self._registry_meta.get("version", "1.0.0")

        # Check denylist first
        if self._check_denylist(name):
            return EntityResolution(
                primary_match=None,
                primary_name=None,
                primary_type=None,
                candidates=[],
                resolution_confidence=0.0,
                ambiguity_flags=["denylisted"],
                resolution_path="rejected",
                raw_input=raw_input,
                normalized_input=normalized,
                normalization_version=norm_version,
                rules_fired=rules_fired + ["denylist_match"],
            )

        candidates: List[EntityCandidate] = []
        ambiguity_flags: List[str] = []

        # Get source tier cap
        tier_cap = self._get_source_tier_cap(source)

        # Check allowlist (bypasses ambiguity)
        is_allowlisted = self._check_allowlist(name, url) or self._check_allowlist(context, url)

        # Check ambiguity
        if not is_allowlisted:
            is_ambiguous, ambiguity_reason = self._check_ambiguity(name, context)
            if is_ambiguous:
                ambiguity_flags.append("ambiguous_term")
                if ambiguity_reason:
                    ambiguity_flags.append(f"reason:{ambiguity_reason}")

        # Tier 1: Registry lookup (exact key or alias)
        tier1_candidates = self._tier1_match(normalized, source)
        candidates.extend(tier1_candidates)

        # Tier 2: Org/namespace prefix match
        if tier_cap >= 2:
            tier2_candidates = self._tier2_match(name, source)
            candidates.extend(tier2_candidates)

        # Tier 3: Substring match (only if no better matches)
        if tier_cap >= 3 and not candidates:
            tier3_candidates = self._tier3_match(name, source)
            candidates.extend(tier3_candidates)

        # Apply tier cap penalty for ambiguous terms
        if "ambiguous_term" in ambiguity_flags and not is_allowlisted:
            # Reject tier 3 matches for ambiguous terms
            candidates = [c for c in candidates if c.match_tier <= 2]
            # Reduce confidence for tier 2 matches
            for c in candidates:
                if c.match_tier == 2:
                    c.base_confidence *= 0.5

        # Sort by confidence (descending)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        # Determine primary match
        if candidates:
            best = candidates[0]
            primary_match = best.canonical_key
            primary_name = best.canonical_name
            primary_type = best.entity_type
            resolution_confidence = best.confidence
            resolution_path = f"tier{best.match_tier}"

            # Check for multiple high-confidence candidates
            if len(candidates) > 1 and candidates[1].confidence > 0.5:
                ambiguity_flags.append("multiple_candidates")
        else:
            primary_match = None
            primary_name = None
            primary_type = None
            resolution_confidence = 0.0
            resolution_path = "rejected"

        # Track which matching rules were applied
        if candidates:
            rules_fired.append(f"match:{resolution_path}")
            if "ambiguous_term" in ambiguity_flags:
                rules_fired.append("ambiguity_penalty")
            if is_allowlisted:
                rules_fired.append("allowlist_bypass")

        return EntityResolution(
            primary_match=primary_match,
            primary_name=primary_name,
            primary_type=primary_type,
            candidates=candidates,
            resolution_confidence=resolution_confidence,
            ambiguity_flags=ambiguity_flags,
            resolution_path=resolution_path,
            raw_input=raw_input,
            normalized_input=normalized,
            normalization_version=norm_version,
            rules_fired=rules_fired,
        )

    def _tier1_match(self, normalized: str, source: str) -> List[EntityCandidate]:
        """Tier 1: Registry lookup or exact match."""
        candidates = []

        # Direct key lookup
        if normalized in self._normalized_to_canonical:
            key = self._normalized_to_canonical[normalized]
            entity = self.registry[key]
            candidates.append(EntityCandidate(
                canonical_key=key,
                canonical_name=entity["canonical_name"],
                entity_type=entity.get("entity_type", "company"),
                match_tier=1,
                match_method="registry",
                base_confidence=TIER_CONFIDENCE[1],
            ))

        # Alias lookup
        elif normalized in self._alias_to_canonical:
            key = self._alias_to_canonical[normalized]
            entity = self.registry[key]
            candidates.append(EntityCandidate(
                canonical_key=key,
                canonical_name=entity["canonical_name"],
                entity_type=entity.get("entity_type", "company"),
                match_tier=1,
                match_method="alias",
                base_confidence=TIER_CONFIDENCE[1],
            ))

        return candidates

    def _tier2_match(self, name: str, source: str) -> List[EntityCandidate]:
        """Tier 2: Org/namespace prefix match."""
        candidates = []
        name_lower = name.lower().strip()

        # GitHub org match
        if source == "github":
            # Check if name matches a known org
            if name_lower in self._github_org_to_canonical:
                key = self._github_org_to_canonical[name_lower]
                entity = self.registry[key]
                candidates.append(EntityCandidate(
                    canonical_key=key,
                    canonical_name=entity["canonical_name"],
                    entity_type=entity.get("entity_type", "company"),
                    match_tier=2,
                    match_method="org_prefix",
                    base_confidence=TIER_CONFIDENCE[2],
                ))

            # Check if name starts with known org (e.g., "openai/gpt-4")
            for org, key in self._github_org_to_canonical.items():
                if name_lower.startswith(f"{org}/"):
                    entity = self.registry[key]
                    candidates.append(EntityCandidate(
                        canonical_key=key,
                        canonical_name=entity["canonical_name"],
                        entity_type=entity.get("entity_type", "company"),
                        match_tier=2,
                        match_method="org_prefix",
                        base_confidence=TIER_CONFIDENCE[2],
                    ))
                    break

        # HuggingFace namespace match
        elif source == "huggingface":
            if name_lower in self._hf_namespace_to_canonical:
                key = self._hf_namespace_to_canonical[name_lower]
                entity = self.registry[key]
                candidates.append(EntityCandidate(
                    canonical_key=key,
                    canonical_name=entity["canonical_name"],
                    entity_type=entity.get("entity_type", "company"),
                    match_tier=2,
                    match_method="hf_namespace",
                    base_confidence=TIER_CONFIDENCE[2],
                ))

            # Check namespace prefix
            for ns, key in self._hf_namespace_to_canonical.items():
                if name_lower.startswith(f"{ns}/"):
                    entity = self.registry[key]
                    candidates.append(EntityCandidate(
                        canonical_key=key,
                        canonical_name=entity["canonical_name"],
                        entity_type=entity.get("entity_type", "company"),
                        match_tier=2,
                        match_method="hf_namespace",
                        base_confidence=TIER_CONFIDENCE[2],
                    ))
                    break

        # Product match (any source)
        normalized = self._normalize(name)
        if normalized in self._product_to_canonical:
            key = self._product_to_canonical[normalized]
            entity = self.registry[key]
            candidates.append(EntityCandidate(
                canonical_key=key,
                canonical_name=entity["canonical_name"],
                entity_type="product",  # Mark as product match
                match_tier=2,
                match_method="product",
                base_confidence=TIER_CONFIDENCE[2],
            ))

        return candidates

    def _tier3_match(self, name: str, source: str) -> List[EntityCandidate]:
        """Tier 3: Substring match."""
        candidates = []
        name_lower = name.lower()

        # Check if any canonical name or alias is a substring
        for key, entity in self.registry.items():
            canonical = entity["canonical_name"].lower()

            # Check if canonical name is in the input
            if canonical in name_lower or name_lower in canonical:
                candidates.append(EntityCandidate(
                    canonical_key=key,
                    canonical_name=entity["canonical_name"],
                    entity_type=entity.get("entity_type", "company"),
                    match_tier=3,
                    match_method="substring",
                    base_confidence=TIER_CONFIDENCE[3],
                ))
                continue

            # Check aliases
            for alias in entity.get("aliases", []):
                if alias.lower() in name_lower or name_lower in alias.lower():
                    candidates.append(EntityCandidate(
                        canonical_key=key,
                        canonical_name=entity["canonical_name"],
                        entity_type=entity.get("entity_type", "company"),
                        match_tier=3,
                        match_method="substring",
                        base_confidence=TIER_CONFIDENCE[3],
                    ))
                    break

        return candidates

    def apply_coherence_boost(
        self,
        candidate: EntityCandidate,
        coherence_type: str,
    ) -> EntityCandidate:
        """
        Apply a coherence boost to a candidate.

        Valid coherence types:
        - domain_coherence: GitHub org links to company website
        - readme_mention: README mentions company name
        - model_card_mention: HuggingFace model card mentions company
        - namespace_match: GitHub org = HuggingFace namespace
        - author_affiliation: Paper author affiliated with company
        """
        if coherence_type in COHERENCE_BOOST_VALUES:
            if coherence_type not in candidate.coherence_boosts:
                candidate.coherence_boosts.append(coherence_type)
        return candidate

    def get_entity(self, canonical_key: str) -> Optional[dict]:
        """Get entity definition by canonical key."""
        return self.registry.get(canonical_key)

    def get_all_entities(self) -> Dict[str, dict]:
        """Get all entities in registry."""
        return self.registry.copy()

    def get_products_for_entity(self, canonical_key: str) -> List[str]:
        """Get list of products for an entity."""
        entity = self.registry.get(canonical_key)
        if entity:
            return entity.get("products", [])
        return []

    def validate_registry(self) -> Dict[str, List[str]]:
        """
        Validate registry for conflicts and collisions.

        Returns dict of issue_type → list of issues.

        Conflict types:
        - HARD: alias_collisions, org_collisions, missing_fields (blocking)
        - SOFT: domain_conflicts (warning only - could be same parent company)
        """
        issues: Dict[str, List[str]] = {
            # HARD conflicts (blocking)
            "alias_collisions": [],
            "org_collisions": [],
            "missing_fields": [],
            # SOFT conflicts (warnings)
            "domain_conflicts": [],
            "product_overlaps": [],
        }

        # Check for domain conflicts (SOFT - same parent company is OK)
        domain_to_keys: Dict[str, List[str]] = {}
        for key, entity in self.registry.items():
            website = entity.get("website", "")
            if website:
                domain = website.replace("https://", "").replace("http://", "").split("/")[0].lower()
                if domain in domain_to_keys:
                    domain_to_keys[domain].append(key)
                else:
                    domain_to_keys[domain] = [key]

        for domain, keys in domain_to_keys.items():
            if len(keys) > 1:
                issues["domain_conflicts"].append(f"{domain}: {keys}")

        # Check for alias collisions (HARD - must be unique)
        alias_to_keys: Dict[str, List[str]] = {}
        for key, entity in self.registry.items():
            for alias in entity.get("aliases", []):
                normalized = self._normalize(alias)
                # Skip if alias is same as own key
                if normalized == key:
                    continue
                if normalized in alias_to_keys:
                    alias_to_keys[normalized].append(key)
                else:
                    alias_to_keys[normalized] = [key]

        for alias, keys in alias_to_keys.items():
            if len(keys) > 1:
                issues["alias_collisions"].append(f"{alias}: {keys}")

        # Check for GitHub org collisions (HARD - org should map to one entity)
        org_to_keys: Dict[str, List[str]] = {}
        for key, entity in self.registry.items():
            for org in entity.get("github_orgs", []):
                org_lower = org.lower()
                if org_lower in org_to_keys:
                    org_to_keys[org_lower].append(key)
                else:
                    org_to_keys[org_lower] = [key]

        for org, keys in org_to_keys.items():
            if len(keys) > 1:
                issues["org_collisions"].append(f"{org}: {keys}")

        # Check for HuggingFace namespace collisions (HARD)
        hf_to_keys: Dict[str, List[str]] = {}
        for key, entity in self.registry.items():
            for ns in entity.get("hf_namespaces", []):
                ns_lower = ns.lower()
                if ns_lower in hf_to_keys:
                    hf_to_keys[ns_lower].append(key)
                else:
                    hf_to_keys[ns_lower] = [key]

        for ns, keys in hf_to_keys.items():
            if len(keys) > 1:
                issues["org_collisions"].append(f"hf:{ns}: {keys}")

        # Check for product overlaps (SOFT - some products are co-developed)
        product_to_keys: Dict[str, List[str]] = {}
        for key, entity in self.registry.items():
            for product in entity.get("products", []):
                prod_normalized = self._normalize(product)
                if prod_normalized in product_to_keys:
                    product_to_keys[prod_normalized].append(key)
                else:
                    product_to_keys[prod_normalized] = [key]

        for product, keys in product_to_keys.items():
            if len(keys) > 1:
                issues["product_overlaps"].append(f"{product}: {keys}")

        # Check for missing required fields (HARD)
        required_fields = ["canonical_name", "entity_type"]
        for key, entity in self.registry.items():
            for field in required_fields:
                if field not in entity:
                    issues["missing_fields"].append(f"{key}: missing {field}")

        return issues

    def has_hard_conflicts(self) -> bool:
        """Check if registry has any blocking (hard) conflicts."""
        issues = self.validate_registry()
        hard_conflict_types = ["alias_collisions", "org_collisions", "missing_fields"]
        return any(len(issues.get(t, [])) > 0 for t in hard_conflict_types)


# Convenience function for quick matching
def match_entity(
    name: str,
    source: str = "",
    context: str = "",
) -> EntityResolution:
    """Quick entity matching using default config paths."""
    matcher = EntityMatcher()
    return matcher.resolve_entity(name, source, context)
