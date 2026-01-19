"""
Funding Data Enrichment Pipeline

Enriches companies in trend_radar.db with funding data from:
1. Kaggle Crunchbase CSV (primary)
2. Wikidata SPARQL (fallback)

Usage:
    python scrapers/funding_enricher.py [--dry-run] [--limit N] [--skip-wikidata]
"""

import argparse
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

# Add paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / ".worktrees" / "trend-radar"))

# Set database URL
os.environ["TREND_RADAR_DB_URL"] = f"sqlite:///{project_root / '.worktrees' / 'trend-radar' / 'data' / 'trend_radar.db'}"

from sqlalchemy.orm import Session
from trend_radar.models import Company, get_session

from kaggle_crunchbase_matcher import KaggleMatcher
from wikidata_funding_fetcher import WikidataFetcher


def parse_funding_amount(value) -> float:
    """Parse funding amount from various formats."""
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    # Parse string like "$33B" or "33,000,000"
    value = str(value).replace(",", "").replace("$", "").strip()

    multipliers = {
        "B": 1_000_000_000,
        "M": 1_000_000,
        "K": 1_000,
    }

    for suffix, mult in multipliers.items():
        if value.upper().endswith(suffix):
            try:
                return float(value[:-1]) * mult
            except ValueError:
                return None

    try:
        return float(value)
    except ValueError:
        return None


def enrich_from_kaggle(
    session: Session,
    companies: List[Company],
    matcher: KaggleMatcher,
    dry_run: bool = False
) -> Tuple[int, int, List[str]]:
    """
    Enrich companies from Kaggle Crunchbase data.

    Returns: (matched_count, unmatched_count, unmatched_names)
    """
    matched = 0
    unmatched = 0
    unmatched_names = []

    for i, company in enumerate(companies):
        if (i + 1) % 500 == 0:
            print(f"  Progress: {i + 1}/{len(companies)}")

        result = matcher.match(company.name)

        if result:
            funding = parse_funding_amount(result.get("funding_total_usd"))
            if funding and funding > 0:
                if not dry_run:
                    company.total_funding = funding
                    company.funding_updated_at = datetime.now(timezone.utc)
                matched += 1
            else:
                unmatched += 1
                unmatched_names.append(company.name)
        else:
            unmatched += 1
            unmatched_names.append(company.name)

    return matched, unmatched, unmatched_names


def enrich_from_wikidata(
    session: Session,
    companies: List[Company],
    fetcher: WikidataFetcher,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Enrich companies from Wikidata (for those without funding).

    Returns: (matched_count, unmatched_count)
    """
    matched = 0
    unmatched = 0

    # Only try companies without funding
    unfunded = [c for c in companies if c.total_funding is None]

    print(f"  Checking {len(unfunded)} unfunded companies against Wikidata...")

    for i, company in enumerate(unfunded):
        if (i + 1) % 100 == 0:
            print(f"  Progress: {i + 1}/{len(unfunded)}")

        result = fetcher.fetch_company(company.name)

        if result and result.get("totalAssets"):
            funding = parse_funding_amount(result["totalAssets"])
            if funding and funding > 0:
                if not dry_run:
                    company.total_funding = funding
                    company.funding_updated_at = datetime.now(timezone.utc)
                matched += 1
                print(f"    [Wikidata] {company.name}: ${funding:,.0f}")
            else:
                unmatched += 1
        else:
            unmatched += 1

    return matched, unmatched


def main():
    parser = argparse.ArgumentParser(description="Enrich company funding data")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    parser.add_argument("--limit", type=int, help="Limit companies to process")
    parser.add_argument("--kaggle-csv", default="data/kaggle/comp.csv")
    parser.add_argument("--skip-wikidata", action="store_true", help="Skip Wikidata lookup")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("=" * 60)
    print("Funding Data Enrichment Pipeline")
    print("=" * 60)

    # Load companies
    session = get_session()
    query = session.query(Company)
    if args.limit:
        query = query.limit(args.limit)
    companies = query.all()

    print(f"\nLoaded {len(companies)} companies from database")

    # Count already funded
    already_funded = len([c for c in companies if c.total_funding is not None])
    print(f"Already have funding data: {already_funded}")

    # Phase 1: Kaggle Crunchbase
    print(f"\n--- Phase 1: Kaggle Crunchbase Matching ---")

    kaggle_csv = project_root / args.kaggle_csv
    if kaggle_csv.exists():
        matcher = KaggleMatcher(str(kaggle_csv))
        k_matched, k_unmatched, unmatched_names = enrich_from_kaggle(
            session, companies, matcher, args.dry_run
        )
        print(f"\nKaggle results: {k_matched} matched, {k_unmatched} unmatched")
    else:
        print(f"Kaggle CSV not found: {kaggle_csv}")
        k_matched = 0
        unmatched_names = [c.name for c in companies]

    # Commit after Kaggle phase
    if not args.dry_run and k_matched > 0:
        session.commit()
        print(f"  Committed {k_matched} updates")

    # Phase 2: Wikidata (optional)
    w_matched = 0
    if not args.skip_wikidata:
        print(f"\n--- Phase 2: Wikidata SPARQL ---")
        fetcher = WikidataFetcher()
        w_matched, w_unmatched = enrich_from_wikidata(
            session, companies, fetcher, args.dry_run
        )
        print(f"\nWikidata results: {w_matched} matched, {w_unmatched} unmatched")

        # Commit after Wikidata phase
        if not args.dry_run and w_matched > 0:
            session.commit()
            print(f"  Committed {w_matched} updates")
    else:
        print("\n--- Skipping Wikidata (--skip-wikidata) ---")

    # Report unmatched for manual lookup
    still_unfunded = [c for c in companies if c.total_funding is None]
    if still_unfunded:
        print(f"\n--- Companies needing manual lookup ({len(still_unfunded)}) ---")

        unfunded_file = project_root / "data" / "unfunded_companies.txt"
        with open(unfunded_file, "w", encoding="utf-8") as f:
            f.write(f"# Unfunded companies - {datetime.now().isoformat()}\n")
            f.write(f"# Total: {len(still_unfunded)}\n\n")
            for c in still_unfunded:
                f.write(f"{c.name}\n")

        print(f"  Saved to: {unfunded_file}")
        print(f"  Sample unfunded companies:")
        for c in still_unfunded[:10]:
            print(f"    - {c.name}")
        if len(still_unfunded) > 10:
            print(f"    ... and {len(still_unfunded) - 10} more")

    # Summary
    funded_count = len([c for c in companies if c.total_funding is not None])
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print("=" * 60)
    print(f"Total companies:     {len(companies)}")
    print(f"With funding data:   {funded_count}")
    print(f"Without funding:     {len(companies) - funded_count}")
    print(f"Coverage:            {funded_count/len(companies)*100:.1f}%")
    print(f"\nNew matches this run:")
    print(f"  Kaggle:            {k_matched}")
    print(f"  Wikidata:          {w_matched}")
    print(f"  Total new:         {k_matched + w_matched}")

    if args.dry_run:
        print("\n(Dry run - no changes saved)")
    print("=" * 60)


if __name__ == "__main__":
    main()
