"""
Identifier Enricher - Fetch external IDs for entities.

Populates entity_external_ids with:
- Crunchbase UUIDs (from Kaggle dataset)
- Ticker symbols (from Wikidata SPARQL)
- LEI codes (from Wikidata SPARQL)
- Wikidata IDs (from Wikidata search)
- Domain extraction

This enricher is designed to be run as a batch process or incrementally.
"""

import csv
import logging
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from rapidfuzz import fuzz

from utils.entity_resolver import (
    EntityResolver,
    ExternalIdentifiers,
    RelationshipType,
    EntityRelationship,
)

logger = logging.getLogger(__name__)


class IdentifierEnricher:
    """
    Enriches entities with external identifiers.

    Sources:
    - Crunchbase: Kaggle dataset (data/kaggle/comp.csv)
    - Wikidata: SPARQL queries for tickers, LEI codes
    - Domain: Extracted from website field
    """

    WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
    WIKIDATA_SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"

    # Rate limiting
    WIKIDATA_DELAY = 1.0  # Seconds between Wikidata requests

    def __init__(self, resolver: Optional[EntityResolver] = None):
        """Initialize enricher."""
        self.resolver = resolver or EntityResolver()
        self._last_wikidata_request = 0.0

        # Load Crunchbase data
        self._crunchbase_data: Dict[str, Dict[str, Any]] = {}
        self._load_crunchbase_data()

    def _load_crunchbase_data(self):
        """Load Crunchbase data from Kaggle CSV."""
        csv_path = Path(__file__).parent.parent / "data" / "kaggle" / "comp.csv"

        if not csv_path.exists():
            logger.warning(f"Crunchbase CSV not found at {csv_path}")
            return

        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Index by normalized name
                    name = row.get("name", "").lower().strip()
                    if name:
                        self._crunchbase_data[name] = row

            logger.info(f"Loaded {len(self._crunchbase_data)} companies from Crunchbase CSV")
        except Exception as e:
            logger.error(f"Failed to load Crunchbase data: {e}")

    def _rate_limit_wikidata(self):
        """Apply rate limiting for Wikidata requests."""
        elapsed = time.time() - self._last_wikidata_request
        if elapsed < self.WIKIDATA_DELAY:
            time.sleep(self.WIKIDATA_DELAY - elapsed)
        self._last_wikidata_request = time.time()

    # =========================================================================
    # Crunchbase Enrichment
    # =========================================================================

    def match_crunchbase(
        self,
        name: str,
        threshold: int = 85,
    ) -> Optional[Dict[str, Any]]:
        """
        Match a company name to Crunchbase data.

        Returns the matched row from the CSV or None.
        """
        normalized = self.resolver.normalize_name(name)

        # Exact match first
        if normalized in self._crunchbase_data:
            return self._crunchbase_data[normalized]

        # Fuzzy match
        if not self._crunchbase_data:
            return None

        matches = []
        for cb_name, data in self._crunchbase_data.items():
            score = fuzz.ratio(normalized, cb_name)
            if score >= threshold:
                matches.append((cb_name, data, score))

        if matches:
            matches.sort(key=lambda x: x[2], reverse=True)
            return matches[0][1]

        return None

    def enrich_from_crunchbase(
        self,
        entity_id: str,
        entity_name: str,
        threshold: int = 85,
    ) -> bool:
        """
        Enrich an entity with Crunchbase data.

        Returns True if enrichment was successful.
        """
        match = self.match_crunchbase(entity_name, threshold)

        if not match:
            logger.debug(f"No Crunchbase match for {entity_name}")
            return False

        # Extract identifiers
        ids = ExternalIdentifiers()

        # Crunchbase permalink as UUID
        permalink = match.get("permalink", "")
        if permalink:
            ids.crunchbase_permalink = permalink
            # Extract UUID from permalink (e.g., /organization/openai -> openai)
            if permalink.startswith("/organization/"):
                ids.crunchbase_uuid = permalink.replace("/organization/", "")

        # Extract domain from homepage_url
        homepage = match.get("homepage_url", "")
        if homepage:
            domain = homepage.replace("https://", "").replace("http://", "").split("/")[0]
            if domain:
                ids.domain = domain

        # Store the identifiers
        if ids.crunchbase_uuid or ids.domain:
            self.resolver.set_external_ids(entity_id, ids)
            logger.info(f"Enriched {entity_name} with Crunchbase data: {ids.to_dict()}")
            return True

        return False

    # =========================================================================
    # Wikidata Enrichment
    # =========================================================================

    def search_wikidata(self, name: str) -> Optional[str]:
        """
        Search Wikidata for an entity and return its QID.

        Returns Wikidata ID (e.g., Q123456) or None.
        """
        self._rate_limit_wikidata()

        try:
            params = {
                "action": "wbsearchentities",
                "search": name,
                "language": "en",
                "format": "json",
                "limit": 5,
                "type": "item",
            }

            response = requests.get(
                self.WIKIDATA_SEARCH_ENDPOINT,
                params=params,
                headers={"User-Agent": "briefAI/1.0 (entity enrichment)"},
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("search", [])
            if results:
                # Look for company/organization results
                for result in results:
                    description = result.get("description", "").lower()
                    if any(kw in description for kw in ["company", "corporation", "organization", "startup", "technology"]):
                        return result["id"]

                # Fall back to first result if no company match
                return results[0]["id"]

            return None

        except Exception as e:
            logger.error(f"Wikidata search failed for {name}: {e}")
            return None

    def get_wikidata_identifiers(self, qid: str) -> Dict[str, Optional[str]]:
        """
        Fetch identifiers from Wikidata for a given QID.

        Returns dict with ticker, exchange, lei_code.
        """
        self._rate_limit_wikidata()

        query = f"""
        SELECT ?ticker ?exchange ?exchangeLabel ?lei ?isin WHERE {{
          OPTIONAL {{ wd:{qid} wdt:P414 ?exchange. }}
          OPTIONAL {{ wd:{qid} wdt:P249 ?ticker. }}
          OPTIONAL {{ wd:{qid} wdt:P1278 ?lei. }}
          OPTIONAL {{ wd:{qid} wdt:P946 ?isin. }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
        }}
        LIMIT 1
        """

        try:
            response = requests.get(
                self.WIKIDATA_SPARQL_ENDPOINT,
                params={"query": query, "format": "json"},
                headers={"User-Agent": "briefAI/1.0 (entity enrichment)"},
                timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            results = data.get("results", {}).get("bindings", [])
            if not results:
                return {}

            result = results[0]
            identifiers = {}

            if "ticker" in result:
                identifiers["ticker_symbol"] = result["ticker"]["value"]

            if "exchangeLabel" in result:
                exchange_label = result["exchangeLabel"]["value"]
                # Map to common abbreviations
                exchange_map = {
                    "New York Stock Exchange": "NYSE",
                    "NASDAQ": "NASDAQ",
                    "London Stock Exchange": "LSE",
                    "Tokyo Stock Exchange": "TSE",
                    "Hong Kong Stock Exchange": "HKEX",
                }
                identifiers["exchange"] = exchange_map.get(exchange_label, exchange_label)

            if "lei" in result:
                identifiers["lei_code"] = result["lei"]["value"]

            return identifiers

        except Exception as e:
            logger.error(f"Wikidata SPARQL failed for {qid}: {e}")
            return {}

    def enrich_from_wikidata(
        self,
        entity_id: str,
        entity_name: str,
    ) -> bool:
        """
        Enrich an entity with Wikidata identifiers.

        Returns True if enrichment was successful.
        """
        # First, search for Wikidata ID
        qid = self.search_wikidata(entity_name)

        if not qid:
            logger.debug(f"No Wikidata match for {entity_name}")
            return False

        # Fetch identifiers
        wikidata_ids = self.get_wikidata_identifiers(qid)

        # Build ExternalIdentifiers
        ids = ExternalIdentifiers(wikidata_id=qid)

        if "ticker_symbol" in wikidata_ids:
            ids.ticker_symbol = wikidata_ids["ticker_symbol"]
        if "exchange" in wikidata_ids:
            ids.exchange = wikidata_ids["exchange"]
        if "lei_code" in wikidata_ids:
            ids.lei_code = wikidata_ids["lei_code"]

        # Store
        self.resolver.set_external_ids(entity_id, ids)
        logger.info(f"Enriched {entity_name} with Wikidata: {ids.to_dict()}")

        return True

    # =========================================================================
    # Acquisition/Relationship Enrichment
    # =========================================================================

    def load_acquisitions(self) -> int:
        """
        Load acquisition data from Kaggle CSV into entity relationships.

        Returns number of relationships created.
        """
        csv_path = Path(__file__).parent.parent / "data" / "kaggle" / "acq.csv"

        if not csv_path.exists():
            logger.warning(f"Acquisitions CSV not found at {csv_path}")
            return 0

        count = 0
        try:
            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    company_name = row.get("company_name", "")
                    acquirer_name = row.get("acquirer_name", "")
                    acquired_at = row.get("acquired_at", "")
                    price_amount = row.get("price_amount", "")

                    if not company_name or not acquirer_name:
                        continue

                    # Resolve both entities
                    company_result = self.resolver.resolve(company_name, source="crunchbase")
                    acquirer_result = self.resolver.resolve(acquirer_name, source="crunchbase")

                    if not company_result.entity_id or not acquirer_result.entity_id:
                        continue

                    # Create relationship
                    from datetime import datetime

                    effective_date = None
                    if acquired_at:
                        try:
                            effective_date = datetime.strptime(acquired_at, "%Y-%m-%d")
                        except ValueError:
                            pass

                    metadata = {}
                    if price_amount:
                        try:
                            metadata["price_usd"] = float(price_amount)
                        except ValueError:
                            pass

                    relationship = EntityRelationship(
                        source_entity_id=company_result.entity_id,
                        target_entity_id=acquirer_result.entity_id,
                        relationship_type=RelationshipType.ACQUIRED,
                        effective_date=effective_date,
                        metadata=metadata,
                        source="crunchbase_kaggle",
                    )

                    self.resolver.add_relationship(relationship)
                    count += 1

                    if count % 100 == 0:
                        logger.info(f"Loaded {count} acquisitions...")

            logger.info(f"Loaded {count} acquisition relationships")
            return count

        except Exception as e:
            logger.error(f"Failed to load acquisitions: {e}")
            return count

    # =========================================================================
    # Batch Enrichment
    # =========================================================================

    def enrich_entity(
        self,
        entity_id: str,
        entity_name: str,
        sources: List[str] = None,
    ) -> Dict[str, bool]:
        """
        Enrich a single entity from multiple sources.

        Args:
            entity_id: Entity database ID
            entity_name: Entity display name
            sources: List of sources to use (crunchbase, wikidata). Default: all.

        Returns:
            Dict mapping source -> success boolean
        """
        if sources is None:
            sources = ["crunchbase", "wikidata"]

        results = {}

        if "crunchbase" in sources:
            results["crunchbase"] = self.enrich_from_crunchbase(entity_id, entity_name)

        if "wikidata" in sources:
            results["wikidata"] = self.enrich_from_wikidata(entity_id, entity_name)

        return results

    def enrich_all_entities(
        self,
        sources: List[str] = None,
        limit: Optional[int] = None,
        skip_enriched: bool = True,
    ) -> Dict[str, int]:
        """
        Enrich all entities in the database.

        Args:
            sources: List of sources to use
            limit: Maximum entities to process
            skip_enriched: Skip entities that already have external IDs

        Returns:
            Dict with statistics
        """
        if sources is None:
            sources = ["crunchbase", "wikidata"]

        # Get all entities
        from utils.signal_store import SignalStore
        store = SignalStore()
        entities = store.get_all_entities()

        if limit:
            entities = entities[:limit]

        stats = {
            "total": len(entities),
            "processed": 0,
            "crunchbase_success": 0,
            "wikidata_success": 0,
            "skipped": 0,
        }

        for entity in entities:
            # Check if already enriched
            if skip_enriched:
                existing_ids = self.resolver.get_external_ids(entity.id)
                if existing_ids and (existing_ids.crunchbase_uuid or existing_ids.wikidata_id):
                    stats["skipped"] += 1
                    continue

            results = self.enrich_entity(entity.id, entity.name, sources)

            if results.get("crunchbase"):
                stats["crunchbase_success"] += 1
            if results.get("wikidata"):
                stats["wikidata_success"] += 1

            stats["processed"] += 1

            if stats["processed"] % 10 == 0:
                logger.info(f"Processed {stats['processed']}/{len(entities)} entities...")

        logger.info(f"Enrichment complete: {stats}")
        return stats

    # =========================================================================
    # Manual Enrichment Helpers
    # =========================================================================

    def set_ticker(self, entity_id: str, ticker: str, exchange: str = None):
        """Manually set ticker symbol for an entity."""
        ids = self.resolver.get_external_ids(entity_id) or ExternalIdentifiers()
        ids.ticker_symbol = ticker.upper()
        if exchange:
            ids.exchange = exchange
        self.resolver.set_external_ids(entity_id, ids)
        logger.info(f"Set ticker {ticker} for entity {entity_id}")

    def set_wikidata(self, entity_id: str, qid: str):
        """Manually set Wikidata ID for an entity."""
        if not qid.startswith("Q"):
            qid = f"Q{qid}"
        ids = self.resolver.get_external_ids(entity_id) or ExternalIdentifiers()
        ids.wikidata_id = qid
        self.resolver.set_external_ids(entity_id, ids)
        logger.info(f"Set Wikidata {qid} for entity {entity_id}")

    def set_lei(self, entity_id: str, lei: str):
        """Manually set LEI code for an entity."""
        ids = self.resolver.get_external_ids(entity_id) or ExternalIdentifiers()
        ids.lei_code = lei
        self.resolver.set_external_ids(entity_id, ids)
        logger.info(f"Set LEI {lei} for entity {entity_id}")


# Convenience function
def enrich_entity(entity_id: str, entity_name: str) -> Dict[str, bool]:
    """Quick enrichment of a single entity."""
    enricher = IdentifierEnricher()
    return enricher.enrich_entity(entity_id, entity_name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    enricher = IdentifierEnricher()

    # Test Crunchbase matching
    print("\n=== Testing Crunchbase Matching ===")
    test_companies = ["OpenAI", "Anthropic", "Google", "Airbnb"]
    for name in test_companies:
        match = enricher.match_crunchbase(name)
        if match:
            print(f"  {name} -> {match.get('name')}: {match.get('funding_total_usd', 0)}")
        else:
            print(f"  {name} -> No match")

    # Test Wikidata search
    print("\n=== Testing Wikidata Search ===")
    for name in ["Microsoft", "NVIDIA", "OpenAI"]:
        qid = enricher.search_wikidata(name)
        if qid:
            ids = enricher.get_wikidata_identifiers(qid)
            print(f"  {name} -> {qid}: {ids}")
        else:
            print(f"  {name} -> No Wikidata match")
