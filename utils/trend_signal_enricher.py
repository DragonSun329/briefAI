"""
Trend Signal Enricher for Trend Radar Validation System.

Orchestrates entity resolution and validation for trend signals.
Takes raw TrendSignals, adds entity resolution and validation, outputs ValidatedTrendSignals.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.entity_matcher import EntityMatcher, EntityResolution, EntityCandidate
from utils.signal_validator import SignalValidator, ValidationResult, SourceMatch
from utils.snapshot_builder import SnapshotBuilder


@dataclass
class TrendSignal:
    """Raw trend signal from TrendAggregator."""
    entity_id: str
    entity_name: str
    signal_type: str  # velocity_spike, new_entity, sustained_growth, etc.
    current_week: str
    momentum_score: float
    article_count: int = 0
    week_over_week_change: float = 0.0
    context: str = ""


@dataclass
class ValidatedTrendSignal:
    """Enriched trend signal with entity resolution and validation."""

    # Original signal data
    entity_id: str
    entity_name: str
    entity_type: str
    signal_type: str
    current_week: str
    momentum_score: float
    article_count: int
    week_over_week_change: float

    # Entity resolution
    canonical_key: Optional[str]
    canonical_name: Optional[str]
    resolution_confidence: float
    resolution_path: str
    ambiguity_flags: List[str]

    # Validation
    validation_score: float
    validation_coverage: float
    validation_strength: float
    validation_status: str  # high_confidence, validated, insufficient_data, unvalidated
    categories_found: List[str]
    tier_distribution: Dict[int, int]
    corroborating_sources: List[str]
    validation_fail_reasons: Dict[str, str]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    @property
    def is_validated(self) -> bool:
        """Check if signal meets validation threshold."""
        return self.validation_status in ("high_confidence", "validated")


class TrendSignalEnricher:
    """
    Enriches raw trend signals with entity resolution and validation.

    Uses snapshots for offline, reproducible validation.
    """

    def __init__(
        self,
        snapshot_dir: Optional[Path] = None,
        matcher: Optional[EntityMatcher] = None,
        validator: Optional[SignalValidator] = None,
    ):
        data_dir = Path(__file__).parent.parent / "data"
        self.snapshot_dir = snapshot_dir or data_dir / "snapshots"

        # Initialize components
        self.matcher = matcher or EntityMatcher()
        self.validator = validator or SignalValidator()
        self.snapshot_builder = SnapshotBuilder(snapshots_dir=self.snapshot_dir)

        # Load latest snapshot
        self._snapshot: Optional[Dict[str, Any]] = None
        self._snapshot_date: Optional[str] = None

    def load_snapshot(self, snapshot_date: Optional[str] = None) -> bool:
        """
        Load a snapshot for validation.

        Args:
            snapshot_date: Specific date (YYYY-MM-DD) or None for latest

        Returns:
            True if snapshot loaded successfully
        """
        if snapshot_date:
            self._snapshot = self.snapshot_builder.load_snapshot(snapshot_date)
            self._snapshot_date = snapshot_date
        else:
            self._snapshot = self.snapshot_builder.load_latest_snapshot()
            if self._snapshot:
                self._snapshot_date = self._snapshot.get("snapshot_date")

        return self._snapshot is not None

    def build_and_load_snapshot(self) -> bool:
        """Build a fresh snapshot and load it."""
        self._snapshot = self.snapshot_builder.build_snapshot(save=True)
        self._snapshot_date = self._snapshot.get("snapshot_date")
        return True

    def enrich(
        self,
        signals: List[TrendSignal],
        snapshot_date: Optional[str] = None,
    ) -> List[ValidatedTrendSignal]:
        """
        Enrich raw trend signals with entity resolution and validation.

        Args:
            signals: List of raw TrendSignal objects
            snapshot_date: Optional snapshot date to use

        Returns:
            List of ValidatedTrendSignal objects
        """
        # Ensure snapshot is loaded
        if self._snapshot is None or (snapshot_date and snapshot_date != self._snapshot_date):
            if not self.load_snapshot(snapshot_date):
                # Build fresh snapshot if none available
                self.build_and_load_snapshot()

        validated_signals: List[ValidatedTrendSignal] = []

        for signal in signals:
            validated = self._enrich_signal(signal)
            validated_signals.append(validated)

        return validated_signals

    def _enrich_signal(self, signal: TrendSignal) -> ValidatedTrendSignal:
        """Enrich a single signal with resolution and validation."""

        # Step 1: Resolve entity
        resolution = self.matcher.resolve_entity(
            name=signal.entity_name,
            source="news",  # Primary detection is from news
            context=signal.context,
        )

        # Step 2: Find corroboration in snapshot
        matches = self._find_corroboration(signal, resolution)

        # Step 3: Compute validation
        data_health = self._snapshot.get("data_health", {}) if self._snapshot else {}
        validation = self.validator.compute_validation(
            matches=matches,
            resolution=resolution,
            data_health=data_health,
        )

        # Step 4: Apply resolution confidence discount
        # If entity resolution is uncertain, validation score should be discounted
        # This prevents "wrong entity but multi-source match" false positives
        raw_validation_score = validation.validation_score
        resolution_discount = resolution.resolution_confidence
        final_validation_score = raw_validation_score * resolution_discount

        # Step 5: Build validated signal
        return ValidatedTrendSignal(
            # Original signal
            entity_id=signal.entity_id,
            entity_name=signal.entity_name,
            entity_type=resolution.primary_type or "unknown",
            signal_type=signal.signal_type,
            current_week=signal.current_week,
            momentum_score=signal.momentum_score,
            article_count=signal.article_count,
            week_over_week_change=signal.week_over_week_change,

            # Resolution
            canonical_key=resolution.primary_match,
            canonical_name=resolution.primary_name,
            resolution_confidence=resolution.resolution_confidence,
            resolution_path=resolution.resolution_path,
            ambiguity_flags=resolution.ambiguity_flags,

            # Validation (with resolution discount applied)
            validation_score=final_validation_score,
            validation_coverage=validation.validation_coverage,
            validation_strength=validation.validation_strength,
            validation_status=self.validator.get_validation_status(validation),
            categories_found=validation.categories_found,
            tier_distribution=validation.tier_distribution,
            corroborating_sources=list(validation.corroborating_sources.keys()),
            validation_fail_reasons=validation.validation_fail_reasons,
        )

    def _find_corroboration(
        self,
        signal: TrendSignal,
        resolution: EntityResolution,
    ) -> Dict[str, SourceMatch]:
        """
        Find corroborating evidence for a signal in the snapshot.

        Searches each source for matches to the resolved entity.
        """
        if not self._snapshot:
            return {}

        matches: Dict[str, SourceMatch] = {}
        sources = self._snapshot.get("sources", {})

        # Search entity name and canonical name
        search_terms = [signal.entity_name.lower()]
        if resolution.primary_name:
            search_terms.append(resolution.primary_name.lower())
        if resolution.primary_match:
            # Add products for the entity
            entity = self.matcher.get_entity(resolution.primary_match)
            if entity:
                for product in entity.get("products", []):
                    search_terms.append(product.lower())
                for alias in entity.get("aliases", []):
                    search_terms.append(alias.lower())

        # Dedupe search terms
        search_terms = list(set(search_terms))

        # Search each source
        for source, source_info in sources.items():
            source_data = source_info.get("data", {})
            scraped_at = source_info.get("scraped_at", "")

            match = self._search_source(
                source=source,
                data=source_data,
                search_terms=search_terms,
                resolution=resolution,
                scraped_at=scraped_at,
            )

            if match:
                matches[source] = match

        return matches

    def _search_source(
        self,
        source: str,
        data: Dict[str, Any],
        search_terms: List[str],
        resolution: EntityResolution,
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search a single source for matches."""

        # Source-specific search logic
        if source == "github":
            return self._search_github(data, search_terms, resolution, scraped_at)
        elif source == "huggingface":
            return self._search_huggingface(data, search_terms, resolution, scraped_at)
        elif source in ("reddit", "hackernews"):
            return self._search_social(source, data, search_terms, scraped_at)
        elif source in ("polymarket", "manifold", "metaculus"):
            return self._search_predictive(source, data, search_terms, scraped_at)
        elif source == "crunchbase":
            return self._search_crunchbase(data, search_terms, resolution, scraped_at)
        elif source == "arxiv":
            return self._search_arxiv(data, search_terms, scraped_at)
        elif source == "podcast":
            return self._search_podcast(data, search_terms, scraped_at)
        else:
            return self._search_generic(source, data, search_terms, scraped_at)

    def _search_github(
        self,
        data: Dict[str, Any],
        search_terms: List[str],
        resolution: EntityResolution,
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search GitHub data for matches."""

        # Check orgs first (Tier 1 match if org matches)
        if resolution.primary_match:
            entity = self.matcher.get_entity(resolution.primary_match)
            if entity:
                github_orgs = entity.get("github_orgs", [])
                orgs_data = data.get("orgs", [])

                for org_data in orgs_data:
                    org_name = org_data.get("name", "").lower()
                    if org_name in [o.lower() for o in github_orgs]:
                        return SourceMatch(
                            source="github",
                            category="technical",
                            match_tier=1,
                            confidence=1.0,
                            matched_item=f"org:{org_name}",
                            matched_at=scraped_at,
                            metadata={"type": "org", "data": org_data},
                        )

        # Check trending repos (Tier 2/3)
        repos = data.get("trending_repos", [])
        for repo in repos:
            repo_name = repo.get("name", "").lower()
            repo_desc = repo.get("description", "").lower()
            owner = repo.get("owner", "").lower()

            # Check for term matches
            for term in search_terms:
                if term in repo_name or term in owner:
                    return SourceMatch(
                        source="github",
                        category="technical",
                        match_tier=2,
                        confidence=0.6,
                        matched_item=f"{owner}/{repo_name}",
                        matched_at=scraped_at,
                        metadata={"type": "repo", "data": repo},
                    )
                elif term in repo_desc:
                    return SourceMatch(
                        source="github",
                        category="technical",
                        match_tier=3,
                        confidence=0.2,
                        matched_item=f"{owner}/{repo_name}",
                        matched_at=scraped_at,
                        metadata={"type": "repo", "data": repo},
                    )

        return None

    def _search_huggingface(
        self,
        data: Dict[str, Any],
        search_terms: List[str],
        resolution: EntityResolution,
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search HuggingFace data for matches."""

        # Check namespace match first (Tier 1)
        if resolution.primary_match:
            entity = self.matcher.get_entity(resolution.primary_match)
            if entity:
                hf_namespaces = entity.get("hf_namespaces", [])
                models = data.get("models", [])

                for model in models:
                    model_id = model.get("id", "")
                    namespace = model_id.split("/")[0].lower() if "/" in model_id else ""

                    if namespace in [ns.lower() for ns in hf_namespaces]:
                        return SourceMatch(
                            source="huggingface",
                            category="technical",
                            match_tier=1,
                            confidence=1.0,
                            matched_item=model_id,
                            matched_at=scraped_at,
                            metadata={"type": "model", "data": model},
                        )

        # Check model names and tags (Tier 2/3)
        models = data.get("models", [])
        for model in models:
            model_id = model.get("id", "").lower()
            tags = [t.lower() for t in model.get("tags", [])]

            for term in search_terms:
                if term in model_id:
                    return SourceMatch(
                        source="huggingface",
                        category="technical",
                        match_tier=2,
                        confidence=0.6,
                        matched_item=model_id,
                        matched_at=scraped_at,
                        metadata={"type": "model", "data": model},
                    )
                elif any(term in tag for tag in tags):
                    return SourceMatch(
                        source="huggingface",
                        category="technical",
                        match_tier=3,
                        confidence=0.2,
                        matched_item=model_id,
                        matched_at=scraped_at,
                        metadata={"type": "model", "data": model},
                    )

        return None

    def _search_social(
        self,
        source: str,
        data: Dict[str, Any],
        search_terms: List[str],
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search Reddit/HackerNews data for matches."""
        posts = data.get("posts", [])

        for post in posts:
            title = post.get("title", "").lower()
            text = post.get("selftext", post.get("text", "")).lower()

            for term in search_terms:
                if term in title:
                    return SourceMatch(
                        source=source,
                        category="social",
                        match_tier=2,
                        confidence=0.5,
                        matched_item=title[:50],
                        matched_at=scraped_at,
                        metadata={"type": "post", "score": post.get("score", 0)},
                    )
                elif term in text:
                    return SourceMatch(
                        source=source,
                        category="social",
                        match_tier=3,
                        confidence=0.2,
                        matched_item=title[:50],
                        matched_at=scraped_at,
                        metadata={"type": "post", "score": post.get("score", 0)},
                    )

        return None

    def _search_predictive(
        self,
        source: str,
        data: Dict[str, Any],
        search_terms: List[str],
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search prediction market data for matches."""
        markets = data.get("markets", data.get("questions", []))

        for market in markets:
            title = market.get("title", market.get("question", "")).lower()
            description = market.get("description", "").lower()

            for term in search_terms:
                if term in title:
                    return SourceMatch(
                        source=source,
                        category="predictive",
                        match_tier=2,
                        confidence=0.5,
                        matched_item=title[:50],
                        matched_at=scraped_at,
                        metadata={"type": "market"},
                    )
                elif term in description:
                    return SourceMatch(
                        source=source,
                        category="predictive",
                        match_tier=3,
                        confidence=0.2,
                        matched_item=title[:50],
                        matched_at=scraped_at,
                        metadata={"type": "market"},
                    )

        return None

    def _search_crunchbase(
        self,
        data: Dict[str, Any],
        search_terms: List[str],
        resolution: EntityResolution,
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search Crunchbase data for matches."""
        companies = data.get("companies", [])

        # Check for exact company match (Tier 1)
        if resolution.primary_name:
            canonical_lower = resolution.primary_name.lower()
            for company in companies:
                name = company.get("name", "").lower()
                if name == canonical_lower:
                    return SourceMatch(
                        source="crunchbase",
                        category="financial",
                        match_tier=1,
                        confidence=1.0,
                        matched_item=company.get("name", ""),
                        matched_at=scraped_at,
                        metadata={"type": "company", "data": company},
                    )

        # Check for partial matches (Tier 2/3)
        for company in companies:
            name = company.get("name", "").lower()
            desc = company.get("short_description", "").lower()

            for term in search_terms:
                if term in name:
                    return SourceMatch(
                        source="crunchbase",
                        category="financial",
                        match_tier=2,
                        confidence=0.6,
                        matched_item=company.get("name", ""),
                        matched_at=scraped_at,
                        metadata={"type": "company"},
                    )
                elif term in desc:
                    return SourceMatch(
                        source="crunchbase",
                        category="financial",
                        match_tier=3,
                        confidence=0.2,
                        matched_item=company.get("name", ""),
                        matched_at=scraped_at,
                        metadata={"type": "company"},
                    )

        return None

    def _search_arxiv(
        self,
        data: Dict[str, Any],
        search_terms: List[str],
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Search arXiv data for matches."""
        papers = data.get("papers", [])

        for paper in papers:
            title = paper.get("title", "").lower()
            abstract = paper.get("abstract", "").lower()
            authors = " ".join(paper.get("authors", [])).lower()

            for term in search_terms:
                if term in title:
                    return SourceMatch(
                        source="arxiv",
                        category="technical",
                        match_tier=2,
                        confidence=0.6,
                        matched_item=title[:50],
                        matched_at=scraped_at,
                        metadata={"type": "paper", "authors": paper.get("authors", [])},
                    )
                elif term in abstract or term in authors:
                    return SourceMatch(
                        source="arxiv",
                        category="technical",
                        match_tier=3,
                        confidence=0.2,
                        matched_item=title[:50],
                        matched_at=scraped_at,
                        metadata={"type": "paper"},
                    )

        return None

    def _search_podcast(
        self,
        data: Dict[str, Any],
        search_terms: List[str],
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """
        Search podcast transcript data for matches.

        Podcasts are high-value media signals since they feature expert discussions.
        Mentions by credible podcast hosts carry strong validation weight.
        """
        episodes = data.get("episodes", [])

        for episode in episodes:
            title = episode.get("title", "").lower()
            content = episode.get("content", "").lower()
            entities = [e.lower() for e in episode.get("entities", [])]
            channel = episode.get("podcast_channel", "")
            credibility = episode.get("credibility_score", 7)

            for term in search_terms:
                # Tier 1: Entity is in the episode's extracted entities list (LLM extracted)
                if term in entities:
                    # Higher tier for credibility >= 8 (expert hosts)
                    match_tier = 1 if credibility >= 8 else 2
                    confidence = min(credibility / 10, 1.0)

                    return SourceMatch(
                        source="podcast",
                        category="media",
                        match_tier=match_tier,
                        confidence=confidence,
                        matched_item=f"{channel}: {title[:40]}",
                        matched_at=scraped_at,
                        metadata={
                            "type": "episode",
                            "channel": channel,
                            "credibility": credibility,
                            "entity_extracted": True,
                        },
                    )

                # Tier 2: Entity is in the title (main topic of episode)
                elif term in title:
                    return SourceMatch(
                        source="podcast",
                        category="media",
                        match_tier=2,
                        confidence=0.7,
                        matched_item=f"{channel}: {title[:40]}",
                        matched_at=scraped_at,
                        metadata={
                            "type": "episode",
                            "channel": channel,
                            "credibility": credibility,
                            "in_title": True,
                        },
                    )

                # Tier 3: Entity mentioned in transcript content
                elif term in content:
                    # Count mentions for confidence boost
                    mention_count = content.count(term)
                    confidence = min(0.2 + (mention_count * 0.05), 0.5)

                    return SourceMatch(
                        source="podcast",
                        category="media",
                        match_tier=3,
                        confidence=confidence,
                        matched_item=f"{channel}: {title[:40]}",
                        matched_at=scraped_at,
                        metadata={
                            "type": "episode",
                            "channel": channel,
                            "mention_count": mention_count,
                        },
                    )

        return None

    def _search_generic(
        self,
        source: str,
        data: Dict[str, Any],
        search_terms: List[str],
        scraped_at: str,
    ) -> Optional[SourceMatch]:
        """Generic search for unrecognized sources."""
        # Try to find any list of items to search
        for key, value in data.items():
            if not isinstance(value, list):
                continue

            for item in value:
                if not isinstance(item, dict):
                    continue

                # Search all string fields
                for field_name, field_value in item.items():
                    if not isinstance(field_value, str):
                        continue

                    field_lower = field_value.lower()
                    for term in search_terms:
                        if term in field_lower:
                            # Determine category from source
                            category = self.validator.source_to_category.get(source, "media")
                            return SourceMatch(
                                source=source,
                                category=category,
                                match_tier=3,
                                confidence=0.2,
                                matched_item=field_value[:50],
                                matched_at=scraped_at,
                                metadata={"type": key, "field": field_name},
                            )

        return None

    def format_enriched_signals(
        self,
        signals: List[ValidatedTrendSignal],
        show_all: bool = False,
    ) -> str:
        """
        Format enriched signals as human-readable output.

        Args:
            signals: List of validated signals
            show_all: If False, only show validated signals
        """
        if not show_all:
            signals = [s for s in signals if s.is_validated]

        if not signals:
            return "No validated signals found."

        lines = [f"=== Trend Signals ({signals[0].current_week}) ===\n"]

        for i, signal in enumerate(signals, 1):
            lines.append(f"{i}. {signal.canonical_name or signal.entity_name} ({signal.entity_type})")
            lines.append(f"   Signal: {signal.signal_type} ({'+' if signal.week_over_week_change > 0 else ''}{signal.week_over_week_change:.0%})")
            lines.append(f"   Momentum: {signal.momentum_score:.0%}")

            # Validation summary
            lines.append(f"   Validation: {signal.validation_score:.0%} ({signal.validation_status})")
            lines.append(f"   └─ Coverage: {len(signal.corroborating_sources)} sources")

            # Tier distribution
            tier_strs = [f"Tier {t}: {c}" for t, c in signal.tier_distribution.items() if c > 0]
            if tier_strs:
                lines.append(f"   └─ Strength: {', '.join(tier_strs)}")

            # Sources
            if signal.corroborating_sources:
                lines.append(f"   └─ Sources: {', '.join(signal.corroborating_sources)}")

            # Fail reasons (only for non-validated)
            if not signal.is_validated and signal.validation_fail_reasons:
                fail_summary = ", ".join(f"{k}={v}" for k, v in list(signal.validation_fail_reasons.items())[:3])
                lines.append(f"   └─ Fail: {fail_summary}")

            lines.append("")

        return "\n".join(lines)


# Convenience function
def enrich_signals(
    signals: List[TrendSignal],
    snapshot_date: Optional[str] = None,
) -> List[ValidatedTrendSignal]:
    """Enrich signals using default configuration."""
    enricher = TrendSignalEnricher()
    return enricher.enrich(signals, snapshot_date)
