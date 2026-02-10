#!/usr/bin/env python3
"""
Entity Deduplication Script

One-time cleanup script to find and merge duplicate entities.
Creates audit trail for all merges and preserves historical data.

Usage:
    python scripts/dedupe_entities.py --dry-run        # Preview without changes
    python scripts/dedupe_entities.py --threshold 90   # Set similarity threshold
    python scripts/dedupe_entities.py --interactive    # Confirm each merge
    python scripts/dedupe_entities.py                  # Run with defaults
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.entity_resolver import (
    EntityResolver,
    ResolutionDecision,
    MergeAuditRecord,
)
from utils.signal_store import SignalStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class EntityDeduplicator:
    """
    Finds and merges duplicate entities with audit trail.
    """

    def __init__(self):
        self.resolver = EntityResolver()
        self.store = SignalStore()

    def find_duplicates(
        self,
        threshold: int = 90,
        limit: int = 500,
    ) -> List[Tuple[str, str, str, str, float]]:
        """
        Find potential duplicate entities.

        Returns list of (id1, name1, id2, name2, similarity) tuples.
        """
        logger.info(f"Searching for duplicates with threshold {threshold}...")

        # Get duplicates from resolver
        duplicates = self.resolver.find_duplicates(threshold=threshold, limit=limit)

        # Fetch names for each duplicate pair
        results = []
        for id1, id2, similarity in duplicates:
            entity1 = self.store.get_entity(id1)
            entity2 = self.store.get_entity(id2)

            if entity1 and entity2:
                results.append((id1, entity1.name, id2, entity2.name, similarity))

        logger.info(f"Found {len(results)} potential duplicates")
        return results

    def get_entity_stats(self, entity_id: str) -> Dict:
        """Get statistics about an entity for merge decision."""
        conn = self.resolver._get_connection()
        cursor = conn.cursor()

        stats = {"entity_id": entity_id}

        # Count observations
        cursor.execute(
            "SELECT COUNT(*) FROM signal_observations WHERE entity_id = ?",
            (entity_id,)
        )
        stats["observation_count"] = cursor.fetchone()[0]

        # Count scores
        cursor.execute(
            "SELECT COUNT(*) FROM signal_scores WHERE entity_id = ?",
            (entity_id,)
        )
        stats["score_count"] = cursor.fetchone()[0]

        # Check for external IDs
        cursor.execute(
            "SELECT * FROM entity_external_ids WHERE entity_id = ?",
            (entity_id,)
        )
        row = cursor.fetchone()
        stats["has_external_ids"] = row is not None
        if row:
            stats["external_ids"] = {
                "crunchbase": row["crunchbase_uuid"],
                "ticker": row["ticker_symbol"],
                "wikidata": row["wikidata_id"],
            }

        # Get entity details
        entity = self.store.get_entity(entity_id)
        if entity:
            stats["name"] = entity.name
            stats["canonical_id"] = entity.canonical_id
            stats["entity_type"] = entity.entity_type.value
            stats["created_at"] = entity.created_at.isoformat() if entity.created_at else None

        conn.close()
        return stats

    def decide_survivor(
        self,
        id1: str,
        id2: str,
    ) -> Tuple[str, str, str]:
        """
        Decide which entity should survive a merge.

        Returns (survivor_id, merged_id, reason).

        Decision criteria:
        1. Entity with more data (observations, scores)
        2. Entity with external IDs
        3. Older entity (earlier created_at)
        """
        stats1 = self.get_entity_stats(id1)
        stats2 = self.get_entity_stats(id2)

        # Score based on data volume
        score1 = stats1["observation_count"] + stats1["score_count"]
        score2 = stats2["observation_count"] + stats2["score_count"]

        # Bonus for external IDs
        if stats1["has_external_ids"]:
            score1 += 10
        if stats2["has_external_ids"]:
            score2 += 10

        # Decide
        if score1 > score2:
            return id1, id2, f"More data ({score1} vs {score2})"
        elif score2 > score1:
            return id2, id1, f"More data ({score2} vs {score1})"
        else:
            # Fall back to creation date (older survives)
            if stats1.get("created_at") and stats2.get("created_at"):
                if stats1["created_at"] < stats2["created_at"]:
                    return id1, id2, "Older entity"
                else:
                    return id2, id1, "Older entity"
            return id1, id2, "Equal priority, first chosen"

    def merge_duplicate(
        self,
        merged_id: str,
        survivor_id: str,
        similarity: float,
        reason: str,
        dry_run: bool = False,
    ) -> bool:
        """
        Merge one entity into another.

        Args:
            merged_id: Entity to merge away
            survivor_id: Entity to keep
            similarity: Similarity score that triggered merge
            reason: Reason for merge decision
            dry_run: If True, don't actually merge

        Returns:
            True if merge was successful (or would be in dry run)
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would merge {merged_id} into {survivor_id} ({reason})")
            return True

        return self.resolver.merge_entities(
            merged_id=merged_id,
            surviving_id=survivor_id,
            decision=ResolutionDecision.AUTO_FUZZY,
            confidence=similarity,
            reason=reason,
            merged_by="dedupe_script",
        )

    def run_deduplication(
        self,
        threshold: int = 90,
        dry_run: bool = False,
        interactive: bool = False,
        limit: int = 500,
    ) -> Dict:
        """
        Run full deduplication process.

        Args:
            threshold: Minimum similarity score (0-100)
            dry_run: Preview without making changes
            interactive: Prompt for confirmation on each merge
            limit: Maximum duplicates to process

        Returns:
            Statistics dict
        """
        stats = {
            "duplicates_found": 0,
            "merges_attempted": 0,
            "merges_successful": 0,
            "merges_skipped": 0,
            "errors": [],
        }

        # Find duplicates
        duplicates = self.find_duplicates(threshold=threshold, limit=limit)
        stats["duplicates_found"] = len(duplicates)

        if not duplicates:
            logger.info("No duplicates found!")
            return stats

        logger.info(f"\n{'='*60}")
        logger.info(f"Found {len(duplicates)} potential duplicates")
        logger.info(f"{'='*60}\n")

        for i, (id1, name1, id2, name2, similarity) in enumerate(duplicates):
            logger.info(f"\n[{i+1}/{len(duplicates)}] Potential duplicate:")
            logger.info(f"  Entity 1: {name1} ({id1[:12]}...)")
            logger.info(f"  Entity 2: {name2} ({id2[:12]}...)")
            logger.info(f"  Similarity: {similarity:.1%}")

            # Get stats for both
            stats1 = self.get_entity_stats(id1)
            stats2 = self.get_entity_stats(id2)

            logger.info(f"  Stats 1: obs={stats1['observation_count']}, scores={stats1['score_count']}, ext_ids={stats1['has_external_ids']}")
            logger.info(f"  Stats 2: obs={stats2['observation_count']}, scores={stats2['score_count']}, ext_ids={stats2['has_external_ids']}")

            # Decide survivor
            survivor_id, merged_id, reason = self.decide_survivor(id1, id2)
            survivor_name = name1 if survivor_id == id1 else name2
            merged_name = name1 if merged_id == id1 else name2

            logger.info(f"  Decision: Keep '{survivor_name}', merge '{merged_name}'")
            logger.info(f"  Reason: {reason}")

            # Interactive confirmation
            if interactive and not dry_run:
                response = input("  Proceed with merge? [y/N/q]: ").strip().lower()
                if response == "q":
                    logger.info("Quitting...")
                    break
                if response != "y":
                    stats["merges_skipped"] += 1
                    logger.info("  Skipped")
                    continue

            # Perform merge
            stats["merges_attempted"] += 1

            try:
                success = self.merge_duplicate(
                    merged_id=merged_id,
                    survivor_id=survivor_id,
                    similarity=similarity,
                    reason=reason,
                    dry_run=dry_run,
                )

                if success:
                    stats["merges_successful"] += 1
                    if not dry_run:
                        logger.info(f"  ✓ Merged successfully")
                else:
                    stats["errors"].append(f"Failed to merge {merged_id} into {survivor_id}")
                    logger.error(f"  ✗ Merge failed")

            except Exception as e:
                stats["errors"].append(f"Error merging {merged_id}: {str(e)}")
                logger.error(f"  ✗ Error: {e}")

        # Summary
        logger.info(f"\n{'='*60}")
        logger.info("Deduplication Complete")
        logger.info(f"{'='*60}")
        logger.info(f"  Duplicates found: {stats['duplicates_found']}")
        logger.info(f"  Merges attempted: {stats['merges_attempted']}")
        logger.info(f"  Merges successful: {stats['merges_successful']}")
        logger.info(f"  Merges skipped: {stats['merges_skipped']}")
        if stats["errors"]:
            logger.info(f"  Errors: {len(stats['errors'])}")

        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Find and merge duplicate entities"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=90,
        help="Minimum similarity threshold (0-100, default: 90)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without making them",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Confirm each merge interactively",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of duplicates to process",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Write results to JSON file",
    )

    args = parser.parse_args()

    # Run deduplication
    deduper = EntityDeduplicator()
    stats = deduper.run_deduplication(
        threshold=args.threshold,
        dry_run=args.dry_run,
        interactive=args.interactive,
        limit=args.limit,
    )

    # Write output if requested
    if args.output:
        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "threshold": args.threshold,
                "dry_run": args.dry_run,
                "stats": stats,
            }, f, indent=2)
        logger.info(f"Results written to {output_path}")

    # Exit code based on errors
    sys.exit(1 if stats["errors"] else 0)


if __name__ == "__main__":
    main()
