"""
Adversarial Pipeline

Orchestrates the three-agent workflow:
1. Hype-Man and Skeptic run in parallel
2. Arbiter synthesizes their outputs
3. Results stored in conviction_scores table
"""

import json
import sqlite3
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from loguru import logger

from agents.hypeman import HypeManAgent, HypeManOutput
from agents.skeptic import SkepticAgent, SkepticOutput
from agents.arbiter import ArbiterAgent, ArbiterOutput


class AdversarialPipeline:
    """
    Orchestrates the Hype-Man vs Skeptic adversarial analysis.

    Flow:
    1. Get trending entities from trend_radar.db
    2. Run Hype-Man and Skeptic in parallel for each entity
    3. Arbiter synthesizes the outputs
    4. Store results in conviction_scores table
    """

    def __init__(
        self,
        db_path: str = "data/trend_radar.db",
        llm_client=None,
        parallel: bool = True
    ):
        """
        Initialize the adversarial pipeline.

        Args:
            db_path: Path to trend_radar database
            llm_client: Shared LLM client (optional)
            parallel: Run agents in parallel (default True)
        """
        self.db_path = db_path
        self.llm_client = llm_client
        self.parallel = parallel

        # Initialize agents
        self.hypeman = HypeManAgent(llm_client=llm_client)
        self.skeptic = SkepticAgent(llm_client=llm_client)
        self.arbiter = ArbiterAgent(llm_client=llm_client)

        # Ensure database schema
        self._ensure_schema()

    def _ensure_schema(self):
        """Create conviction_scores table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conviction_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,

                -- Scores
                technical_velocity_score REAL,
                commercial_maturity_score REAL,
                brand_safety_score REAL,
                conviction_score REAL,

                -- Conflict
                conflict_intensity TEXT,
                recommendation TEXT,

                -- Theses
                bull_thesis TEXT,
                bear_thesis TEXT,
                synthesis TEXT,
                key_uncertainty TEXT,

                -- Red flags (JSON array)
                red_flags TEXT,
                missing_signals TEXT,

                -- Bonuses/Penalties
                momentum_bonus INTEGER DEFAULT 0,
                risk_penalty INTEGER DEFAULT 0,

                -- Metadata
                analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                llm_model TEXT,
                prompt_version TEXT,

                UNIQUE(entity_name, analyzed_at)
            )
        """)

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conviction_score
            ON conviction_scores(conviction_score DESC)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_conflict
            ON conviction_scores(conflict_intensity)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_recommendation
            ON conviction_scores(recommendation)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_entity_name
            ON conviction_scores(entity_name)
        """)

        conn.commit()
        conn.close()
        logger.info("Conviction scores schema ensured")

    def get_trending_entities(self, limit: int = 20, min_score: float = 50) -> List[Dict[str, Any]]:
        """
        Get trending entities from trend_radar.db.

        Args:
            limit: Maximum entities to return
            min_score: Minimum rising score to consider

        Returns:
            List of entity dicts with name and rising_score
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT entity_name, rising_score, mention_count
                FROM entity_trends
                WHERE rising_score >= ?
                ORDER BY rising_score DESC
                LIMIT ?
            """, (min_score, limit))

            entities = []
            for row in cursor.fetchall():
                entities.append({
                    "name": row[0],
                    "rising_score": row[1],
                    "mentions": row[2]
                })

            return entities

        except sqlite3.OperationalError as e:
            logger.warning(f"Could not query entity_trends: {e}")
            # Fallback to companies table
            cursor.execute("""
                SELECT name, total_funding
                FROM companies
                WHERE name IS NOT NULL
                ORDER BY total_funding DESC NULLS LAST
                LIMIT ?
            """, (limit,))

            entities = []
            for row in cursor.fetchall():
                entities.append({
                    "name": row[0],
                    "rising_score": 50,  # Default score
                    "mentions": 0
                })

            return entities

        finally:
            conn.close()

    def analyze_entity(self, entity_name: str) -> ArbiterOutput:
        """
        Run full adversarial analysis on a single entity.

        Args:
            entity_name: Name of the entity to analyze

        Returns:
            ArbiterOutput with conviction score
        """
        logger.info(f"Starting adversarial analysis: {entity_name}")

        if self.parallel:
            # Run Hype-Man and Skeptic in parallel
            with ThreadPoolExecutor(max_workers=2) as executor:
                hypeman_future = executor.submit(self.hypeman.analyze, entity_name)
                skeptic_future = executor.submit(self.skeptic.analyze, entity_name)

                hypeman_output = hypeman_future.result()
                skeptic_output = skeptic_future.result()
        else:
            # Sequential execution
            hypeman_output = self.hypeman.analyze(entity_name)
            skeptic_output = self.skeptic.analyze(entity_name)

        # Arbiter synthesizes
        arbiter_output = self.arbiter.synthesize(
            entity_name, hypeman_output, skeptic_output
        )

        logger.info(
            f"Analysis complete: {entity_name} | "
            f"Conviction: {arbiter_output.conviction_score} | "
            f"Recommendation: {arbiter_output.recommendation}"
        )

        return arbiter_output

    def store_result(self, result: ArbiterOutput, llm_model: str = "moonshot-v1-8k"):
        """
        Store analysis result in conviction_scores table.

        Args:
            result: ArbiterOutput to store
            llm_model: Model used for analysis
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO conviction_scores (
                    entity_name, entity_type,
                    technical_velocity_score, commercial_maturity_score, brand_safety_score,
                    conviction_score, conflict_intensity, recommendation,
                    bull_thesis, bear_thesis, synthesis, key_uncertainty,
                    red_flags, missing_signals,
                    momentum_bonus, risk_penalty,
                    llm_model, prompt_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.entity,
                result.entity_type,
                result.signal_breakdown.get("technical_velocity"),
                result.signal_breakdown.get("commercial_maturity"),
                result.signal_breakdown.get("brand_safety"),
                result.conviction_score,
                result.conflict_intensity,
                result.recommendation,
                result.verdict.get("bull_thesis"),
                result.verdict.get("bear_thesis"),
                result.verdict.get("synthesis"),
                result.verdict.get("key_uncertainty"),
                json.dumps([]),  # red_flags - TODO: pass through from skeptic
                json.dumps([]),  # missing_signals - TODO: pass through from skeptic
                result.momentum_bonus,
                result.risk_penalty,
                llm_model,
                "v1.0"
            ))

            conn.commit()
            logger.debug(f"Stored conviction score for: {result.entity}")

        except sqlite3.IntegrityError:
            logger.warning(f"Duplicate entry for {result.entity}, skipping")
        finally:
            conn.close()

    def run(
        self,
        entities: Optional[List[str]] = None,
        limit: int = 20,
        min_score: float = 50,
        store_results: bool = True
    ) -> List[ArbiterOutput]:
        """
        Run adversarial analysis on multiple entities.

        Args:
            entities: Specific entities to analyze (or None to use trending)
            limit: Max entities if using trending
            min_score: Min rising score if using trending
            store_results: Whether to store in database

        Returns:
            List of ArbiterOutput results
        """
        if entities is None:
            trending = self.get_trending_entities(limit=limit, min_score=min_score)
            entities = [e["name"] for e in trending]

        logger.info(f"Running adversarial analysis on {len(entities)} entities")

        results = []
        for entity_name in entities:
            try:
                result = self.analyze_entity(entity_name)
                results.append(result)

                if store_results:
                    self.store_result(result)

            except Exception as e:
                logger.error(f"Failed to analyze {entity_name}: {e}")
                continue

        # Summary
        alerts = [r for r in results if r.recommendation == "ALERT"]
        investigate = [r for r in results if r.recommendation == "INVESTIGATE"]

        logger.info(f"\nAnalysis complete:")
        logger.info(f"  Total: {len(results)}")
        logger.info(f"  ALERT: {len(alerts)}")
        logger.info(f"  INVESTIGATE: {len(investigate)}")

        return results

    def get_conviction_leaderboard(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get top entities by conviction score.

        Args:
            limit: Number of results to return

        Returns:
            List of conviction records
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                entity_name, entity_type, conviction_score,
                conflict_intensity, recommendation,
                technical_velocity_score, commercial_maturity_score,
                synthesis, analyzed_at
            FROM conviction_scores
            WHERE analyzed_at = (
                SELECT MAX(analyzed_at)
                FROM conviction_scores cs2
                WHERE cs2.entity_name = conviction_scores.entity_name
            )
            ORDER BY conviction_score DESC
            LIMIT ?
        """, (limit,))

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results

    def get_alerts(self) -> List[Dict[str, Any]]:
        """
        Get entities with ALERT or INVESTIGATE recommendation.

        Returns:
            List of entities needing attention
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                entity_name, entity_type, conviction_score,
                conflict_intensity, recommendation,
                bull_thesis, bear_thesis, synthesis,
                analyzed_at
            FROM conviction_scores
            WHERE recommendation IN ('ALERT', 'INVESTIGATE')
            AND analyzed_at = (
                SELECT MAX(analyzed_at)
                FROM conviction_scores cs2
                WHERE cs2.entity_name = conviction_scores.entity_name
            )
            ORDER BY
                CASE recommendation WHEN 'ALERT' THEN 1 ELSE 2 END,
                conviction_score DESC
        """)

        results = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run adversarial analysis pipeline")
    parser.add_argument("--entity", type=str, help="Analyze specific entity")
    parser.add_argument("--limit", type=int, default=10, help="Max entities to analyze")
    parser.add_argument("--min-score", type=float, default=50, help="Min rising score")
    parser.add_argument("--no-store", action="store_true", help="Don't store results")
    parser.add_argument("--leaderboard", action="store_true", help="Show conviction leaderboard")
    parser.add_argument("--alerts", action="store_true", help="Show current alerts")

    args = parser.parse_args()

    pipeline = AdversarialPipeline()

    if args.leaderboard:
        print("\n=== Conviction Leaderboard ===\n")
        for i, record in enumerate(pipeline.get_conviction_leaderboard(), 1):
            print(f"{i}. {record['entity_name']} ({record['entity_type']})")
            print(f"   Conviction: {record['conviction_score']} | {record['recommendation']}")
            print(f"   {record['synthesis']}\n")

    elif args.alerts:
        print("\n=== Active Alerts ===\n")
        for record in pipeline.get_alerts():
            print(f"[{record['recommendation']}] {record['entity_name']}")
            print(f"   Conviction: {record['conviction_score']} | Conflict: {record['conflict_intensity']}")
            print(f"   Bull: {record['bull_thesis'][:100]}...")
            print(f"   Bear: {record['bear_thesis'][:100]}...")
            print()

    elif args.entity:
        result = pipeline.analyze_entity(args.entity)
        print(json.dumps(result.to_dict(), indent=2))

        if not args.no_store:
            pipeline.store_result(result)
            print(f"\nStored result in conviction_scores table")

    else:
        results = pipeline.run(
            limit=args.limit,
            min_score=args.min_score,
            store_results=not args.no_store
        )

        print("\n=== Results Summary ===\n")
        for r in sorted(results, key=lambda x: x.conviction_score, reverse=True):
            print(f"{r.entity}: {r.conviction_score} ({r.recommendation})")
