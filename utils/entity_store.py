"""
Entity Store — Unified entity access layer for briefAI.

Bridges the two existing entity systems:
- trend_radar.db: companies (4793) + observations (5311) — scraper-facing
- signals.db: entities (2093) + signal_profiles + signal_observations — analytics-facing

Provides a single API for all agents and modules to:
1. Look up entities by name, alias, ticker, or ID
2. Get cross-DB entity profiles (signals + observations + mentions)
3. Track entity mentions across all source types
4. Get entity context for any agent query

Design principle: READ from both DBs, don't migrate.
Future: once stable, gradually unify into a single store.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from loguru import logger

try:
    from rapidfuzz import fuzz, process as rfprocess
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class EntityType(str, Enum):
    COMPANY = "company"
    PROJECT = "project"       # OSS project, product
    MODEL = "model"           # AI model (GPT-4, Claude, etc.)
    PERSON = "person"
    SECTOR = "sector"         # Industry sector
    UNKNOWN = "unknown"


@dataclass
class UnifiedEntity:
    """
    Single entity representation merged from both DBs.

    This is the object agents receive — they don't need to know
    which DB the data came from.
    """
    # Identity
    id: str                              # Preferred: signals.db UUID, fallback: trend_radar.db int
    canonical_name: str
    entity_type: EntityType = EntityType.UNKNOWN
    aliases: List[str] = field(default_factory=list)

    # Metadata
    description: Optional[str] = None
    website: Optional[str] = None
    country: Optional[str] = None
    founded_year: Optional[int] = None
    cn_name: Optional[str] = None
    sector: Optional[str] = None
    ticker: Optional[str] = None

    # Cross-DB references
    signals_db_id: Optional[str] = None   # UUID from signals.db
    trend_radar_id: Optional[int] = None  # INT from trend_radar.db

    # Timestamps
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None

    # Aggregated metrics (filled on request)
    source_count: int = 0
    mention_count_7d: int = 0
    mention_count_30d: int = 0
    composite_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["entity_type"] = self.entity_type.value
        return {k: v for k, v in d.items() if v is not None and v != [] and v != 0}


@dataclass
class EntityMention:
    """A single mention of an entity in a source."""
    entity_id: str
    source_type: str           # "news", "github", "arxiv", "hiring", etc.
    source_name: str           # Specific source (e.g., "hackernews", "a16z_portfolio")
    title: Optional[str] = None
    date: Optional[str] = None
    url: Optional[str] = None
    score: Optional[float] = None
    raw_data: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


# ---------------------------------------------------------------------------
# Source type mapping
# ---------------------------------------------------------------------------

SOURCE_TYPE_MAP = {
    # VC portfolios → company intelligence
    "a16z_portfolio": "vc_portfolio",
    "yc_companies": "vc_portfolio",
    "sequoia_portfolio": "vc_portfolio",
    # Tech news
    "hackernews": "hackernews",
    "producthunt": "product_hunt",
    "reddit": "reddit",
    # Code/research
    "github": "github",
    "huggingface": "huggingface",
    "arxiv": "arxiv",
    # Social
    "twitter": "social",
    "threads": "social",
    # Jobs/hiring
    "linkedin": "hiring",
    # Default
    "news": "news",
}


def _classify_source(source_id: str) -> str:
    """Map a source_id to a source type category."""
    source_lower = (source_id or "").lower()
    for key, category in SOURCE_TYPE_MAP.items():
        if key in source_lower:
            return category
    return "news"


# ---------------------------------------------------------------------------
# Entity Store
# ---------------------------------------------------------------------------

class EntityStore:
    """
    Unified read layer over trend_radar.db and signals.db.

    Usage:
        store = EntityStore()
        entity = store.find("OpenAI")
        mentions = store.get_mentions("openai", days=14)
        profile = store.get_signal_profile("openai")
    """

    def __init__(
        self,
        trend_radar_path: str = "data/trend_radar.db",
        signals_path: str = "data/signals.db",
    ):
        self.trend_radar_path = Path(trend_radar_path)
        self.signals_path = Path(signals_path)
        # Cache canonical names for fuzzy matching
        self._name_cache: Optional[Dict[str, str]] = None  # normalized_name -> canonical_name
        self._id_cache: Optional[Dict[str, str]] = None     # canonical_name -> id

    # -------------------------------------------------------------------
    # Public API: Find
    # -------------------------------------------------------------------

    def find(self, query: str) -> Optional[UnifiedEntity]:
        """
        Find an entity by name, alias, ticker, or ID.
        Searches both DBs and merges results.

        Args:
            query: Entity name, ticker, or alias

        Returns:
            UnifiedEntity or None
        """
        query_lower = query.strip().lower()

        # 1. Try exact match in signals.db
        entity = self._find_signals_db(query_lower)

        # 2. Try exact match in trend_radar.db
        tr_entity = self._find_trend_radar(query_lower)

        # 3. Merge if both found, prefer signals.db as primary
        if entity and tr_entity:
            entity = self._merge_entities(entity, tr_entity)
        elif tr_entity and not entity:
            entity = tr_entity

        # 4. Fuzzy match if nothing found
        if not entity and RAPIDFUZZ_AVAILABLE:
            entity = self._fuzzy_find(query)

        return entity

    def find_many(self, queries: List[str]) -> Dict[str, Optional[UnifiedEntity]]:
        """Find multiple entities. Returns {query: entity_or_none}."""
        return {q: self.find(q) for q in queries}

    # -------------------------------------------------------------------
    # Public API: Mentions
    # -------------------------------------------------------------------

    def get_mentions(
        self,
        entity_name: str,
        days: int = 14,
        source_types: Optional[List[str]] = None,
    ) -> List[EntityMention]:
        """
        Get all mentions of an entity across all sources.

        This is the core data for cross-source trend detection.
        """
        mentions = []
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        # From trend_radar.db: observations (VC portfolios, scraper sightings)
        mentions.extend(self._get_trend_radar_mentions(entity_name, cutoff))

        # From signals.db: signal_observations (scored signals)
        mentions.extend(self._get_signals_mentions(entity_name, cutoff))

        # Filter by source type if requested
        if source_types:
            mentions = [m for m in mentions if m.source_type in source_types]

        # Sort by date
        mentions.sort(key=lambda m: m.date or "", reverse=True)
        return mentions

    def get_mention_velocity(self, entity_name: str) -> Dict[str, Any]:
        """Quick mention velocity stats for an entity."""
        mentions_7d = self.get_mentions(entity_name, days=7)
        mentions_30d = self.get_mentions(entity_name, days=30)

        count_7d = len(mentions_7d)
        count_30d = len(mentions_30d)
        weekly_avg = count_30d / 4.3 if count_30d > 0 else 0

        # Source diversity
        sources_7d = set(m.source_type for m in mentions_7d)
        sources_30d = set(m.source_type for m in mentions_30d)

        return {
            "7d": count_7d,
            "30d": count_30d,
            "weekly_avg": round(weekly_avg, 1),
            "accelerating": count_7d > weekly_avg * 1.5,
            "source_diversity_7d": len(sources_7d),
            "source_diversity_30d": len(sources_30d),
            "source_types_7d": sorted(sources_7d),
            "source_types_30d": sorted(sources_30d),
        }

    # -------------------------------------------------------------------
    # Public API: Signal Profile
    # -------------------------------------------------------------------

    def get_signal_profile(self, entity_name: str) -> Optional[Dict[str, Any]]:
        """Get the latest signal profile from signals.db."""
        if not self.signals_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(self.signals_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM signal_profiles
                WHERE entity_name LIKE ?
                ORDER BY created_at DESC
                LIMIT 1
            """, [f"%{entity_name}%"])
            row = cursor.fetchone()
            conn.close()

            if row:
                return dict(row)
        except Exception as e:
            logger.debug(f"Signal profile lookup failed: {e}")

        return None

    # -------------------------------------------------------------------
    # Public API: List / Search
    # -------------------------------------------------------------------

    def search(self, query: str, limit: int = 20) -> List[UnifiedEntity]:
        """Search entities by name (substring + fuzzy)."""
        results = []
        query_lower = query.lower()

        # Exact/substring from both DBs
        if self.signals_path.exists():
            try:
                conn = sqlite3.connect(str(self.signals_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM entities WHERE LOWER(name) LIKE ? LIMIT ?",
                    [f"%{query_lower}%", limit]
                )
                for row in cursor.fetchall():
                    results.append(self._row_to_entity_signals(dict(row)))
                conn.close()
            except Exception as e:
                logger.debug(f"Entity search (signals.db) failed: {e}")

        if self.trend_radar_path.exists():
            try:
                conn = sqlite3.connect(str(self.trend_radar_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM companies WHERE LOWER(name) LIKE ? OR LOWER(cn_name) LIKE ? LIMIT ?",
                    [f"%{query_lower}%", f"%{query_lower}%", limit]
                )
                for row in cursor.fetchall():
                    tr_ent = self._row_to_entity_trend_radar(dict(row))
                    # Deduplicate against signals.db results
                    if not any(r.canonical_name.lower() == tr_ent.canonical_name.lower() for r in results):
                        results.append(tr_ent)
                conn.close()
            except Exception as e:
                logger.debug(f"Entity search (trend_radar.db) failed: {e}")

        return results[:limit]

    def list_top_entities(self, limit: int = 50) -> List[UnifiedEntity]:
        """List top entities by composite score."""
        entities = []

        if self.signals_path.exists():
            try:
                conn = sqlite3.connect(str(self.signals_path))
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT e.*, sp.composite_score, sp.media_score
                    FROM entities e
                    LEFT JOIN signal_profiles sp ON e.id = sp.entity_id
                    ORDER BY sp.composite_score DESC NULLS LAST
                    LIMIT ?
                """, [limit])
                for row in cursor.fetchall():
                    ent = self._row_to_entity_signals(dict(row))
                    ent.composite_score = row["composite_score"]
                    entities.append(ent)
                conn.close()
            except Exception as e:
                logger.debug(f"Top entities query failed: {e}")

        return entities

    def get_source_diversity(self, entity_name: str, days: int = 14) -> Dict[str, int]:
        """Get mention count by source type for an entity."""
        mentions = self.get_mentions(entity_name, days=days)
        diversity: Dict[str, int] = {}
        for m in mentions:
            diversity[m.source_type] = diversity.get(m.source_type, 0) + 1
        return dict(sorted(diversity.items(), key=lambda x: x[1], reverse=True))

    # -------------------------------------------------------------------
    # Private: DB lookups
    # -------------------------------------------------------------------

    def _find_signals_db(self, query_lower: str) -> Optional[UnifiedEntity]:
        """Find entity in signals.db."""
        if not self.signals_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(self.signals_path))
            conn.row_factory = sqlite3.Row

            # Try canonical_id match
            cursor = conn.execute(
                "SELECT * FROM entities WHERE canonical_id = ? LIMIT 1",
                [query_lower]
            )
            row = cursor.fetchone()

            # Try name match
            if not row:
                cursor = conn.execute(
                    "SELECT * FROM entities WHERE LOWER(name) = ? LIMIT 1",
                    [query_lower]
                )
                row = cursor.fetchone()

            conn.close()

            if row:
                return self._row_to_entity_signals(dict(row))
        except Exception as e:
            logger.debug(f"Signals DB lookup failed: {e}")

        return None

    def _find_trend_radar(self, query_lower: str) -> Optional[UnifiedEntity]:
        """Find entity in trend_radar.db."""
        if not self.trend_radar_path.exists():
            return None

        try:
            conn = sqlite3.connect(str(self.trend_radar_path))
            conn.row_factory = sqlite3.Row

            # Try normalized_name
            cursor = conn.execute(
                "SELECT * FROM companies WHERE normalized_name = ? LIMIT 1",
                [query_lower]
            )
            row = cursor.fetchone()

            # Try name
            if not row:
                cursor = conn.execute(
                    "SELECT * FROM companies WHERE LOWER(name) = ? LIMIT 1",
                    [query_lower]
                )
                row = cursor.fetchone()

            # Try cn_name
            if not row:
                cursor = conn.execute(
                    "SELECT * FROM companies WHERE cn_name = ? LIMIT 1",
                    [query_lower]
                )
                row = cursor.fetchone()

            conn.close()

            if row:
                return self._row_to_entity_trend_radar(dict(row))
        except Exception as e:
            logger.debug(f"Trend Radar DB lookup failed: {e}")

        return None

    def _fuzzy_find(self, query: str, threshold: int = 85) -> Optional[UnifiedEntity]:
        """Fuzzy match entity name using rapidfuzz."""
        if not RAPIDFUZZ_AVAILABLE:
            return None

        self._build_name_cache()
        if not self._name_cache:
            return None

        names = list(self._name_cache.keys())
        result = rfprocess.extractOne(query.lower(), names, scorer=fuzz.WRatio)

        if result and result[1] >= threshold:
            canonical = self._name_cache[result[0]]
            return self.find(canonical)

        return None

    def _build_name_cache(self):
        """Build name cache for fuzzy matching (lazy, once per instance)."""
        if self._name_cache is not None:
            return

        self._name_cache = {}

        if self.signals_path.exists():
            try:
                conn = sqlite3.connect(str(self.signals_path))
                cursor = conn.execute("SELECT canonical_id, name FROM entities")
                for row in cursor.fetchall():
                    self._name_cache[row[0].lower()] = row[1]
                    self._name_cache[row[1].lower()] = row[1]
                conn.close()
            except Exception:
                pass

        if self.trend_radar_path.exists():
            try:
                conn = sqlite3.connect(str(self.trend_radar_path))
                cursor = conn.execute("SELECT normalized_name, name FROM companies")
                for row in cursor.fetchall():
                    if row[0] and row[0].lower() not in self._name_cache:
                        self._name_cache[row[0].lower()] = row[1]
                    if row[1] and row[1].lower() not in self._name_cache:
                        self._name_cache[row[1].lower()] = row[1]
                conn.close()
            except Exception:
                pass

    # -------------------------------------------------------------------
    # Private: Mentions from each DB
    # -------------------------------------------------------------------

    def _get_trend_radar_mentions(self, entity_name: str, cutoff: str) -> List[EntityMention]:
        """Get mentions from trend_radar.db observations."""
        mentions = []
        if not self.trend_radar_path.exists():
            return mentions

        try:
            conn = sqlite3.connect(str(self.trend_radar_path))
            conn.row_factory = sqlite3.Row

            # Find company ID(s)
            cursor = conn.execute(
                "SELECT id FROM companies WHERE LOWER(name) LIKE ? OR normalized_name LIKE ? OR cn_name LIKE ?",
                [f"%{entity_name.lower()}%", f"%{entity_name.lower()}%", f"%{entity_name}%"]
            )
            company_ids = [row["id"] for row in cursor.fetchall()]

            if company_ids:
                placeholders = ",".join("?" * len(company_ids))
                cursor = conn.execute(f"""
                    SELECT o.*, s.name as source_name, s.type as source_type
                    FROM observations o
                    JOIN sources s ON o.source_id = s.id
                    WHERE o.company_id IN ({placeholders})
                    AND o.last_seen >= ?
                    ORDER BY o.last_seen DESC
                """, [*company_ids, cutoff[:10]])  # cutoff as date

                for row in cursor.fetchall():
                    mentions.append(EntityMention(
                        entity_id=str(row["company_id"]),
                        source_type=_classify_source(row["source_id"]),
                        source_name=row["source_name"] or row["source_id"],
                        title=row["source_name"],
                        date=row["last_seen"],
                        raw_data=json.loads(row["raw_data"]) if row["raw_data"] else None,
                    ))

            conn.close()
        except Exception as e:
            logger.debug(f"Trend radar mentions lookup failed: {e}")

        return mentions

    def _get_signals_mentions(self, entity_name: str, cutoff: str) -> List[EntityMention]:
        """Get mentions from signals.db signal_observations."""
        mentions = []
        if not self.signals_path.exists():
            return mentions

        try:
            conn = sqlite3.connect(str(self.signals_path))
            conn.row_factory = sqlite3.Row

            # Find entity ID
            cursor = conn.execute(
                "SELECT id FROM entities WHERE LOWER(name) LIKE ? OR canonical_id LIKE ?",
                [f"%{entity_name.lower()}%", f"%{entity_name.lower()}%"]
            )
            entity_ids = [row["id"] for row in cursor.fetchall()]

            if entity_ids:
                placeholders = ",".join("?" * len(entity_ids))
                cursor = conn.execute(f"""
                    SELECT so.*, ss.name as src_name, ss.category as src_category
                    FROM signal_observations so
                    LEFT JOIN signal_sources ss ON so.source_id = ss.id
                    WHERE so.entity_id IN ({placeholders})
                    AND so.observed_at >= ?
                    ORDER BY so.observed_at DESC
                """, [*entity_ids, cutoff])

                for row in cursor.fetchall():
                    row_dict = dict(row)
                    mentions.append(EntityMention(
                        entity_id=row_dict.get("entity_id", ""),
                        source_type=_classify_source(row_dict.get("src_category") or row_dict.get("source_id") or ""),
                        source_name=row_dict.get("src_name") or row_dict.get("source_id") or "unknown",
                        date=row_dict.get("observed_at"),
                        score=row_dict.get("raw_value"),
                    ))

            conn.close()
        except Exception as e:
            logger.debug(f"Signals mentions lookup failed: {e}")

        return mentions

    # -------------------------------------------------------------------
    # Private: Row converters
    # -------------------------------------------------------------------

    def _row_to_entity_signals(self, row: Dict) -> UnifiedEntity:
        """Convert signals.db entity row to UnifiedEntity."""
        aliases = []
        if row.get("aliases"):
            try:
                aliases = json.loads(row["aliases"])
            except (json.JSONDecodeError, TypeError):
                pass

        return UnifiedEntity(
            id=row.get("id", ""),
            canonical_name=row.get("name", ""),
            entity_type=EntityType(row.get("entity_type", "unknown")),
            aliases=aliases,
            description=row.get("description"),
            website=row.get("website"),
            founded_year=int(row["founded_date"][:4]) if row.get("founded_date") else None,
            signals_db_id=row.get("id"),
            first_seen=row.get("created_at"),
            last_seen=row.get("updated_at"),
        )

    def _row_to_entity_trend_radar(self, row: Dict) -> UnifiedEntity:
        """Convert trend_radar.db company row to UnifiedEntity."""
        return UnifiedEntity(
            id=f"tr_{row.get('id', '')}",
            canonical_name=row.get("name", ""),
            entity_type=EntityType.COMPANY,
            description=row.get("description"),
            website=row.get("website"),
            country=row.get("country"),
            founded_year=row.get("founded_year"),
            cn_name=row.get("cn_name"),
            trend_radar_id=row.get("id"),
            first_seen=row.get("first_seen_global"),
            last_seen=row.get("last_seen_global"),
            source_count=row.get("source_count", 0),
        )

    def _merge_entities(self, signals_ent: UnifiedEntity, tr_ent: UnifiedEntity) -> UnifiedEntity:
        """Merge signals.db entity with trend_radar.db entity. signals.db wins on conflicts."""
        # Fill gaps from trend_radar
        if not signals_ent.description and tr_ent.description:
            signals_ent.description = tr_ent.description
        if not signals_ent.website and tr_ent.website:
            signals_ent.website = tr_ent.website
        if not signals_ent.country and tr_ent.country:
            signals_ent.country = tr_ent.country
        if not signals_ent.founded_year and tr_ent.founded_year:
            signals_ent.founded_year = tr_ent.founded_year
        if not signals_ent.cn_name and tr_ent.cn_name:
            signals_ent.cn_name = tr_ent.cn_name

        # Cross-references
        signals_ent.trend_radar_id = tr_ent.trend_radar_id
        signals_ent.source_count = max(signals_ent.source_count, tr_ent.source_count)

        # Use earliest first_seen
        if tr_ent.first_seen and (not signals_ent.first_seen or tr_ent.first_seen < signals_ent.first_seen):
            signals_ent.first_seen = tr_ent.first_seen

        return signals_ent
