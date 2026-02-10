#!/usr/bin/env python3
"""
Entity Identifier Enrichment Script

Batch enriches entities with external identifiers:
- Crunchbase UUIDs
- Wikidata IDs
- Ticker symbols
- LEI codes

Also imports acquisition relationships from Crunchbase data.

Usage:
    python scripts/enrich_identifiers.py                    # Enrich all entities
    python scripts/enrich_identifiers.py --source crunchbase  # Only Crunchbase
    python scripts/enrich_identifiers.py --source wikidata    # Only Wikidata
    python scripts/enrich_identifiers.py --limit 100          # Limit to 100 entities
    python scripts/enrich_identifiers.py --entity-type company  # Only companies
    python scripts/enrich_identifiers.py --load-acquisitions  # Import acquisitions
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.entity_resolver import EntityResolver
from utils.signal_store import SignalStore
from utils.signal_models import EntityType
from scrapers.identifier_enricher import IdentifierEnricher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class EnrichmentRunner:
    """Runs batch entity enrichment."""

    def __init__(self):
        self.resolver = EntityResolver()
        self.store = SignalStore()
        self.enricher = IdentifierEnricher(self.resolver)

    def get_entities_to_enrich(
        self,
        entity_type: Optional[str] = None,
        limit: Optional[int] = None,
        skip_enriched: bool = True,
    ) -> List:
        """Get list of entities that need enrichment."""
        # Get all entities
        if entity_type:
            entity_type_enum = EntityType(entity_type)
            entities = self.store.get_all_entities(entity_type=entity_type_enum)
        else:
            entities = self.store.get_all_entities()

        # Filter out already-enriched if requested
        if skip_enriched:
            filtered = []
            for entity in entities:
                ext_ids = self.resolver.get_external_ids(entity.id)
                if not ext_ids or not (ext_ids.crunchbase_uuid or ext_ids.wikidata_id):
                    filtered.append(entity)
            entities = filtered

        if limit:
            entities = entities[:limit]

        return entities

    def run_enrichment(
        self,
        sources: List[str] = None,
        entity_type: Optional[str] = None,
        limit: Optional[int] = None,
        skip_enriched: bool = True,
    ) -> Dict:
        """
        Run batch enrichment.

        Args:
            sources: List of sources (crunchbase, wikidata)
            entity_type: Filter by entity type
            limit: Max entities to process
            skip_enriched: Skip already-enriched entities

        Returns:
            Statistics dict
        """
        if sources is None:
            sources = ["crunchbase", "wikidata"]

        stats = {
            "total_entities": 0,
            "processed": 0,
            "crunchbase_success": 0,
            "wikidata_success": 0,
            "errors": [],
            "enriched_entities": [],
        }

        # Get entities
        entities = self.get_entities_to_enrich(
            entity_type=entity_type,
            limit=limit,
            skip_enriched=skip_enriched,
        )

        stats["total_entities"] = len(entities)
        logger.info(f"Found {len(entities)} entities to enrich")

        if not entities:
            logger.info("No entities need enrichment")
            return stats

        for i, entity in enumerate(entities):
            try:
                results = self.enricher.enrich_entity(
                    entity.id,
                    entity.name,
                    sources=sources,
                )

                success_any = False
                if results.get("crunchbase"):
                    stats["crunchbase_success"] += 1
                    success_any = True
                if results.get("wikidata"):
                    stats["wikidata_success"] += 1
                    success_any = True

                if success_any:
                    stats["enriched_entities"].append({
                        "id": entity.id,
                        "name": entity.name,
                        "results": results,
                    })

                stats["processed"] += 1

                if (i + 1) % 10 == 0:
                    logger.info(
                        f"Progress: {i+1}/{len(entities)} "
                        f"(CB: {stats['crunchbase_success']}, WD: {stats['wikidata_success']})"
                    )

            except Exception as e:
                stats["errors"].append({
                    "entity_id": entity.id,
                    "name": entity.name,
                    "error": str(e),
                })
                logger.error(f"Error enriching {entity.name}: {e}")

        # Summary
        logger.info("\n" + "="*60)
        logger.info("Enrichment Complete")
        logger.info("="*60)
        logger.info(f"  Total entities: {stats['total_entities']}")
        logger.info(f"  Processed: {stats['processed']}")
        logger.info(f"  Crunchbase success: {stats['crunchbase_success']}")
        logger.info(f"  Wikidata success: {stats['wikidata_success']}")
        if stats["errors"]:
            logger.info(f"  Errors: {len(stats['errors'])}")

        return stats

    def run_acquisition_import(self) -> Dict:
        """
        Import acquisition relationships from Crunchbase data.

        Returns:
            Statistics dict
        """
        logger.info("Loading acquisition relationships...")

        count = self.enricher.load_acquisitions()

        stats = {
            "relationships_created": count,
        }

        logger.info(f"Created {count} acquisition relationships")
        return stats

    def show_coverage_report(self) -> Dict:
        """
        Generate coverage report for external identifiers.

        Returns:
            Coverage statistics
        """
        stats = self.resolver.get_stats()

        logger.info("\n" + "="*60)
        logger.info("External Identifier Coverage Report")
        logger.info("="*60)
        logger.info(f"  Total entities: {stats['total_entities']}")
        logger.info(f"  With Crunchbase UUID: {stats['with_crunchbase']} ({stats['with_crunchbase']/max(1,stats['total_entities'])*100:.1f}%)")
        logger.info(f"  With ticker symbol: {stats['with_ticker']} ({stats['with_ticker']/max(1,stats['total_entities'])*100:.1f}%)")
        logger.info(f"  With Wikidata ID: {stats['with_wikidata']} ({stats['with_wikidata']/max(1,stats['total_entities'])*100:.1f}%)")
        logger.info(f"  With LEI code: {stats['with_lei']} ({stats['with_lei']/max(1,stats['total_entities'])*100:.1f}%)")
        logger.info(f"  Total aliases: {stats['total_aliases']}")
        logger.info(f"  Total relationships: {stats['total_relationships']}")

        if stats.get("relationships_by_type"):
            logger.info("  Relationships by type:")
            for rel_type, count in stats["relationships_by_type"].items():
                logger.info(f"    - {rel_type}: {count}")

        return stats


def main():
    parser = argparse.ArgumentParser(
        description="Batch enrich entities with external identifiers"
    )
    parser.add_argument(
        "--source",
        type=str,
        choices=["crunchbase", "wikidata", "all"],
        default="all",
        help="Source to use for enrichment",
    )
    parser.add_argument(
        "--entity-type",
        type=str,
        choices=["company", "technology", "concept", "person"],
        help="Filter by entity type",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of entities to process",
    )
    parser.add_argument(
        "--include-enriched",
        action="store_true",
        help="Re-enrich entities that already have external IDs",
    )
    parser.add_argument(
        "--load-acquisitions",
        action="store_true",
        help="Import acquisition relationships from Crunchbase",
    )
    parser.add_argument(
        "--coverage-report",
        action="store_true",
        help="Show coverage report and exit",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Write results to JSON file",
    )

    args = parser.parse_args()

    runner = EnrichmentRunner()

    # Show coverage report if requested
    if args.coverage_report:
        runner.show_coverage_report()
        return

    # Determine sources
    if args.source == "all":
        sources = ["crunchbase", "wikidata"]
    else:
        sources = [args.source]

    results = {}

    # Load acquisitions if requested
    if args.load_acquisitions:
        results["acquisitions"] = runner.run_acquisition_import()

    # Run enrichment
    results["enrichment"] = runner.run_enrichment(
        sources=sources,
        entity_type=args.entity_type,
        limit=args.limit,
        skip_enriched=not args.include_enriched,
    )

    # Show coverage after enrichment
    results["coverage"] = runner.show_coverage_report()

    # Write output if requested
    if args.output:
        output_path = Path(args.output)

        # Remove non-serializable parts
        output_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "args": {
                "source": args.source,
                "entity_type": args.entity_type,
                "limit": args.limit,
            },
            "stats": {
                k: v for k, v in results.get("enrichment", {}).items()
                if k != "enriched_entities"
            },
            "coverage": results.get("coverage", {}),
        }

        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
        logger.info(f"Results written to {output_path}")


if __name__ == "__main__":
    main()
