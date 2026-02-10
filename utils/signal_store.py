"""
Signal Storage Layer

SQLite-based storage for multi-dimensional signal analysis.
Handles Entity, SignalObservation, SignalScore, SignalProfile, and SignalDivergence.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import sqlite3
import json

from utils.signal_models import (
    Entity, EntityType, SignalCategory, SignalSource,
    SignalObservation, SignalScore, SignalProfile, SignalDivergence,
    DivergenceType, DivergenceInterpretation,
    normalize_entity_id, detect_entity_type
)


class SignalStore:
    """
    SQLite storage for signal analysis data.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize signal store.

        Args:
            db_path: Path to SQLite database. Defaults to data/signals.db
        """
        if db_path is None:
            db_path = str(Path(__file__).parent.parent / "data" / "signals.db")

        self.db_path = db_path
        self._ensure_tables()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """Create tables if they don't exist."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Entities table
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
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_canonical ON entities(canonical_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)")

        # Signal sources table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_sources (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                url TEXT,
                update_frequency TEXT DEFAULT 'daily',
                latency_hours INTEGER DEFAULT 0,
                confidence_base REAL DEFAULT 0.7,
                requires_api_key INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Signal observations table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_observations (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                category TEXT NOT NULL,
                observed_at TIMESTAMP NOT NULL,
                data_timestamp TIMESTAMP,
                raw_value REAL,
                raw_value_unit TEXT,
                raw_data TEXT,
                confidence REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_entity ON signal_observations(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_category ON signal_observations(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_observations_observed ON signal_observations(observed_at)")

        # Signal scores table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_scores (
                id TEXT PRIMARY KEY,
                observation_id TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                category TEXT NOT NULL,
                score REAL NOT NULL,
                percentile REAL,
                score_delta_7d REAL,
                score_delta_30d REAL,
                period_start TIMESTAMP,
                period_end TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (observation_id) REFERENCES signal_observations(id),
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_entity ON signal_scores(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scores_category ON signal_scores(category)")

        # Signal profiles table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_profiles (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                as_of TIMESTAMP NOT NULL,
                technical_score REAL,
                company_score REAL,
                financial_score REAL,
                product_score REAL,
                media_score REAL,
                composite_score REAL NOT NULL,
                technical_confidence REAL DEFAULT 0,
                company_confidence REAL DEFAULT 0,
                financial_confidence REAL DEFAULT 0,
                product_confidence REAL DEFAULT 0,
                media_confidence REAL DEFAULT 0,
                momentum_7d REAL,
                momentum_30d REAL,
                data_freshness TEXT,
                top_signals TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_entity ON signal_profiles(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_profiles_asof ON signal_profiles(as_of)")

        # Signal divergences table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signal_divergences (
                id TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL,
                entity_name TEXT NOT NULL,
                divergence_type TEXT NOT NULL,
                high_signal_category TEXT NOT NULL,
                high_signal_score REAL NOT NULL,
                low_signal_category TEXT NOT NULL,
                low_signal_score REAL NOT NULL,
                divergence_magnitude REAL NOT NULL,
                confidence REAL NOT NULL,
                interpretation TEXT NOT NULL,
                interpretation_rationale TEXT,
                detected_at TIMESTAMP NOT NULL,
                first_detected_at TIMESTAMP,
                resolved_at TIMESTAMP,
                evidence_signals TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (entity_id) REFERENCES entities(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_divergences_entity ON signal_divergences(entity_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_divergences_detected ON signal_divergences(detected_at)")

        conn.commit()
        conn.close()

    # =========================================================================
    # Entity Operations
    # =========================================================================

    def upsert_entity(self, entity: Entity) -> Entity:
        """Insert or update an entity."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO entities (
                id, canonical_id, name, entity_type, aliases, description,
                website, founded_date, headquarters, parent_entity,
                related_entities, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_id) DO UPDATE SET
                name = excluded.name,
                entity_type = excluded.entity_type,
                aliases = excluded.aliases,
                description = excluded.description,
                website = excluded.website,
                founded_date = excluded.founded_date,
                headquarters = excluded.headquarters,
                parent_entity = excluded.parent_entity,
                related_entities = excluded.related_entities,
                updated_at = excluded.updated_at
        """, (
            entity.id,
            entity.canonical_id,
            entity.name,
            entity.entity_type.value,
            json.dumps(entity.aliases),
            entity.description,
            entity.website,
            entity.founded_date,
            entity.headquarters,
            entity.parent_entity,
            json.dumps(entity.related_entities),
            entity.created_at.isoformat(),
            datetime.utcnow().isoformat()
        ))

        conn.commit()
        conn.close()
        return entity

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID or canonical_id."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM entities WHERE id = ? OR canonical_id = ?
        """, (entity_id, entity_id))

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_entity(row)
        return None

    def get_or_create_entity(
        self,
        name: str,
        entity_type: Optional[EntityType] = None,
        source_category: Optional[SignalCategory] = None,
        **kwargs
    ) -> Entity:
        """Get existing entity or create new one."""
        canonical_id = normalize_entity_id(name)

        existing = self.get_entity(canonical_id)
        if existing:
            return existing

        # Detect entity type if not provided
        if entity_type is None:
            entity_type = detect_entity_type(name, source_category)

        entity = Entity(
            canonical_id=canonical_id,
            name=name,
            entity_type=entity_type,
            **kwargs
        )
        return self.upsert_entity(entity)

    def get_all_entities(self, entity_type: Optional[EntityType] = None) -> List[Entity]:
        """Get all entities, optionally filtered by type."""
        conn = self._get_connection()
        cursor = conn.cursor()

        if entity_type:
            cursor.execute("SELECT * FROM entities WHERE entity_type = ?", (entity_type.value,))
        else:
            cursor.execute("SELECT * FROM entities")

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_entity(row) for row in rows]

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert database row to Entity object."""
        return Entity(
            id=row["id"],
            canonical_id=row["canonical_id"],
            name=row["name"],
            entity_type=EntityType(row["entity_type"]),
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            description=row["description"],
            website=row["website"],
            founded_date=row["founded_date"],
            headquarters=row["headquarters"],
            parent_entity=row["parent_entity"],
            related_entities=json.loads(row["related_entities"]) if row["related_entities"] else [],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            updated_at=datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else datetime.utcnow(),
        )

    # =========================================================================
    # Observation Operations
    # =========================================================================

    def add_observation(
        self, 
        obs: SignalObservation, 
        skip_dedup: bool = False
    ) -> Optional[SignalObservation]:
        """
        Add a signal observation with deduplication.
        
        Args:
            obs: The observation to add
            skip_dedup: If True, skip deduplication check (for bulk imports)
            
        Returns:
            The observation if added, None if duplicate was detected
        """
        # Deduplication check
        if not skip_dedup:
            try:
                from utils.signal_dedup import SignalDeduplicator
                dedup = SignalDeduplicator(self.db_path)
                
                is_dup, existing_id = dedup.is_duplicate(
                    obs.entity_id,
                    obs.raw_data,
                    obs.observed_at,
                    obs.source_id
                )
                
                if is_dup:
                    # Log but don't add duplicate
                    return None
                    
            except ImportError:
                pass  # Dedup module not available, proceed without
            except Exception:
                pass  # Dedup failed, proceed anyway
        
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signal_observations (
                id, entity_id, source_id, category, observed_at, data_timestamp,
                raw_value, raw_value_unit, raw_data, confidence, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            obs.id,
            obs.entity_id,
            obs.source_id,
            obs.category.value,
            obs.observed_at.isoformat(),
            obs.data_timestamp.isoformat() if obs.data_timestamp else None,
            obs.raw_value,
            obs.raw_value_unit,
            json.dumps(obs.raw_data),
            obs.confidence,
            obs.created_at.isoformat()
        ))

        conn.commit()
        conn.close()
        
        # Register fingerprint for future dedup
        if not skip_dedup:
            try:
                from utils.signal_dedup import SignalDeduplicator
                dedup = SignalDeduplicator(self.db_path)
                dedup.register_signal(
                    obs.id, obs.entity_id, obs.raw_data, obs.observed_at, obs.source_id
                )
            except Exception:
                pass
        
        return obs

    def get_latest_observation(
        self,
        entity_id: str,
        category: SignalCategory
    ) -> Optional[SignalObservation]:
        """Get most recent observation for entity in category."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM signal_observations
            WHERE entity_id = ? AND category = ?
            ORDER BY observed_at DESC LIMIT 1
        """, (entity_id, category.value))

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_observation(row)
        return None

    def _row_to_observation(self, row: sqlite3.Row) -> SignalObservation:
        """Convert database row to SignalObservation object."""
        return SignalObservation(
            id=row["id"],
            entity_id=row["entity_id"],
            source_id=row["source_id"],
            category=SignalCategory(row["category"]),
            observed_at=datetime.fromisoformat(row["observed_at"]),
            data_timestamp=datetime.fromisoformat(row["data_timestamp"]) if row["data_timestamp"] else None,
            raw_value=row["raw_value"],
            raw_value_unit=row["raw_value_unit"],
            raw_data=json.loads(row["raw_data"]) if row["raw_data"] else {},
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
        )

    # =========================================================================
    # Score Operations
    # =========================================================================

    def add_score(self, score: SignalScore) -> SignalScore:
        """Add a signal score."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signal_scores (
                id, observation_id, entity_id, source_id, category,
                score, percentile, score_delta_7d, score_delta_30d,
                period_start, period_end, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            score.id,
            score.observation_id,
            score.entity_id,
            score.source_id,
            score.category.value,
            score.score,
            score.percentile,
            score.score_delta_7d,
            score.score_delta_30d,
            score.period_start.isoformat() if score.period_start else None,
            score.period_end.isoformat() if score.period_end else None,
            score.created_at.isoformat()
        ))

        conn.commit()
        conn.close()
        return score

    def get_latest_score(
        self,
        entity_id: str,
        category: SignalCategory
    ) -> Optional[SignalScore]:
        """Get most recent score for entity in category."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM signal_scores
            WHERE entity_id = ? AND category = ?
            ORDER BY created_at DESC LIMIT 1
        """, (entity_id, category.value))

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_score(row)
        return None

    def get_historical_scores(
        self,
        entity_id: str,
        category: SignalCategory,
        days: int = 30
    ) -> List[SignalScore]:
        """Get historical scores for trend analysis."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        cursor.execute("""
            SELECT * FROM signal_scores
            WHERE entity_id = ? AND category = ? AND created_at >= ?
            ORDER BY created_at ASC
        """, (entity_id, category.value, cutoff))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_score(row) for row in rows]

    def get_scores_for_entity(self, entity_id: str) -> List[SignalScore]:
        """Get all scores for an entity (latest per category)."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get latest score per category for this entity
        cursor.execute("""
            SELECT s.* FROM signal_scores s
            INNER JOIN (
                SELECT entity_id, category, MAX(created_at) as max_created
                FROM signal_scores
                WHERE entity_id = ?
                GROUP BY entity_id, category
            ) latest ON s.entity_id = latest.entity_id
                     AND s.category = latest.category
                     AND s.created_at = latest.max_created
        """, (entity_id,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_score(row) for row in rows]

    def _row_to_score(self, row: sqlite3.Row) -> SignalScore:
        """Convert database row to SignalScore object."""
        return SignalScore(
            id=row["id"],
            observation_id=row["observation_id"],
            entity_id=row["entity_id"],
            source_id=row["source_id"],
            category=SignalCategory(row["category"]),
            score=row["score"],
            percentile=row["percentile"],
            score_delta_7d=row["score_delta_7d"],
            score_delta_30d=row["score_delta_30d"],
            period_start=datetime.fromisoformat(row["period_start"]) if row["period_start"] else None,
            period_end=datetime.fromisoformat(row["period_end"]) if row["period_end"] else None,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
        )

    # =========================================================================
    # Profile Operations
    # =========================================================================

    def save_profile(self, profile: SignalProfile) -> SignalProfile:
        """Save a signal profile."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signal_profiles (
                id, entity_id, entity_name, entity_type, as_of,
                technical_score, company_score, financial_score, product_score, media_score,
                composite_score,
                technical_confidence, company_confidence, financial_confidence,
                product_confidence, media_confidence,
                momentum_7d, momentum_30d, data_freshness, top_signals, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            profile.id,
            profile.entity_id,
            profile.entity_name,
            profile.entity_type.value,
            profile.as_of.isoformat(),
            profile.technical_score,
            profile.company_score,
            profile.financial_score,
            profile.product_score,
            profile.media_score,
            profile.composite_score,
            profile.technical_confidence,
            profile.company_confidence,
            profile.financial_confidence,
            profile.product_confidence,
            profile.media_confidence,
            profile.momentum_7d,
            profile.momentum_30d,
            json.dumps({k: v.isoformat() if isinstance(v, datetime) else v for k, v in profile.data_freshness.items()}),
            json.dumps(profile.top_signals),
            profile.created_at.isoformat()
        ))

        conn.commit()
        conn.close()
        return profile

    def get_latest_profile(self, entity_id: str) -> Optional[SignalProfile]:
        """Get most recent profile for entity."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT * FROM signal_profiles
            WHERE entity_id = ?
            ORDER BY as_of DESC LIMIT 1
        """, (entity_id,))

        row = cursor.fetchone()
        conn.close()

        if row:
            return self._row_to_profile(row)
        return None

    def get_top_profiles(
        self,
        limit: int = 20,
        entity_type: Optional[EntityType] = None
    ) -> List[SignalProfile]:
        """Get top profiles by composite score."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Get latest profile per entity
        if entity_type:
            cursor.execute("""
                SELECT * FROM signal_profiles p1
                WHERE as_of = (
                    SELECT MAX(as_of) FROM signal_profiles p2
                    WHERE p2.entity_id = p1.entity_id
                ) AND entity_type = ?
                ORDER BY composite_score DESC
                LIMIT ?
            """, (entity_type.value, limit))
        else:
            cursor.execute("""
                SELECT * FROM signal_profiles p1
                WHERE as_of = (
                    SELECT MAX(as_of) FROM signal_profiles p2
                    WHERE p2.entity_id = p1.entity_id
                )
                ORDER BY composite_score DESC
                LIMIT ?
            """, (limit,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_profile(row) for row in rows]

    def _row_to_profile(self, row: sqlite3.Row) -> SignalProfile:
        """Convert database row to SignalProfile object."""
        data_freshness = json.loads(row["data_freshness"]) if row["data_freshness"] else {}
        # Convert ISO strings back to datetime
        for k, v in data_freshness.items():
            if isinstance(v, str):
                try:
                    data_freshness[k] = datetime.fromisoformat(v)
                except:
                    pass

        return SignalProfile(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            entity_type=EntityType(row["entity_type"]),
            as_of=datetime.fromisoformat(row["as_of"]),
            technical_score=row["technical_score"],
            company_score=row["company_score"],
            financial_score=row["financial_score"],
            product_score=row["product_score"],
            media_score=row["media_score"],
            composite_score=row["composite_score"],
            technical_confidence=row["technical_confidence"],
            company_confidence=row["company_confidence"],
            financial_confidence=row["financial_confidence"],
            product_confidence=row["product_confidence"],
            media_confidence=row["media_confidence"],
            momentum_7d=row["momentum_7d"],
            momentum_30d=row["momentum_30d"],
            data_freshness=data_freshness,
            top_signals=json.loads(row["top_signals"]) if row["top_signals"] else [],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
        )

    # =========================================================================
    # Divergence Operations
    # =========================================================================

    def add_divergence(self, divergence: SignalDivergence) -> SignalDivergence:
        """Add a signal divergence."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO signal_divergences (
                id, entity_id, entity_name, divergence_type,
                high_signal_category, high_signal_score,
                low_signal_category, low_signal_score,
                divergence_magnitude, confidence,
                interpretation, interpretation_rationale,
                detected_at, first_detected_at, resolved_at,
                evidence_signals, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            divergence.id,
            divergence.entity_id,
            divergence.entity_name,
            divergence.divergence_type.value,
            divergence.high_signal_category.value,
            divergence.high_signal_score,
            divergence.low_signal_category.value,
            divergence.low_signal_score,
            divergence.divergence_magnitude,
            divergence.confidence,
            divergence.interpretation.value,
            divergence.interpretation_rationale,
            divergence.detected_at.isoformat(),
            divergence.first_detected_at.isoformat() if divergence.first_detected_at else None,
            divergence.resolved_at.isoformat() if divergence.resolved_at else None,
            json.dumps(divergence.evidence_signals),
            divergence.created_at.isoformat()
        ))

        conn.commit()
        conn.close()
        return divergence

    def get_active_divergences(
        self,
        entity_id: Optional[str] = None,
        interpretation: Optional[DivergenceInterpretation] = None
    ) -> List[SignalDivergence]:
        """Get active (unresolved) divergences."""
        conn = self._get_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM signal_divergences WHERE resolved_at IS NULL"
        params = []

        if entity_id:
            query += " AND entity_id = ?"
            params.append(entity_id)

        if interpretation:
            query += " AND interpretation = ?"
            params.append(interpretation.value)

        query += " ORDER BY divergence_magnitude DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_divergence(row) for row in rows]

    def _row_to_divergence(self, row: sqlite3.Row) -> SignalDivergence:
        """Convert database row to SignalDivergence object."""
        return SignalDivergence(
            id=row["id"],
            entity_id=row["entity_id"],
            entity_name=row["entity_name"],
            divergence_type=DivergenceType(row["divergence_type"]),
            high_signal_category=SignalCategory(row["high_signal_category"]),
            high_signal_score=row["high_signal_score"],
            low_signal_category=SignalCategory(row["low_signal_category"]),
            low_signal_score=row["low_signal_score"],
            divergence_magnitude=row["divergence_magnitude"],
            confidence=row["confidence"],
            interpretation=DivergenceInterpretation(row["interpretation"]),
            interpretation_rationale=row["interpretation_rationale"],
            detected_at=datetime.fromisoformat(row["detected_at"]),
            first_detected_at=datetime.fromisoformat(row["first_detected_at"]) if row["first_detected_at"] else None,
            resolved_at=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
            evidence_signals=json.loads(row["evidence_signals"]) if row["evidence_signals"] else [],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
        )

    # =========================================================================
    # Statistics
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        conn = self._get_connection()
        cursor = conn.cursor()

        stats = {}

        cursor.execute("SELECT COUNT(*) FROM entities")
        stats["total_entities"] = cursor.fetchone()[0]

        cursor.execute("SELECT entity_type, COUNT(*) FROM entities GROUP BY entity_type")
        stats["entities_by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) FROM signal_observations")
        stats["total_observations"] = cursor.fetchone()[0]

        cursor.execute("SELECT category, COUNT(*) FROM signal_observations GROUP BY category")
        stats["observations_by_category"] = {row[0]: row[1] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) FROM signal_scores")
        stats["total_scores"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM signal_profiles")
        stats["total_profiles"] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM signal_divergences WHERE resolved_at IS NULL")
        stats["active_divergences"] = cursor.fetchone()[0]

        conn.close()
        return stats
