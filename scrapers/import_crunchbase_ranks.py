"""
Import Crunchbase companies with CB Rank into trend_radar database.

This script imports all companies from a Crunchbase JSON export file,
updating existing companies with their CB rank or creating new ones.

Usage:
    python scrapers/import_crunchbase_ranks.py <json_file> [--dry-run]
"""

import argparse
import json
import re
import sys
import os
from pathlib import Path
from datetime import datetime

# Add paths for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / ".worktrees" / "trend-radar"))

# Set database URL
os.environ["TREND_RADAR_DB_URL"] = f"sqlite:///{project_root / '.worktrees' / 'trend-radar' / 'data' / 'trend_radar.db'}"

from trend_radar.models import Company, get_session


def normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    # Remove common suffixes
    suffixes = [", Inc.", ", Inc", " Inc.", " Inc", ", LLC", " LLC", " Ltd.", " Ltd", " Co.", " Co"]
    result = name.strip()
    for suffix in suffixes:
        if result.endswith(suffix):
            result = result[:-len(suffix)]
    # Lowercase and remove special chars for matching
    return re.sub(r'[^a-z0-9]', '', result.lower())


def parse_funding(funding_str):
    """Parse funding string like '$33.7B' to float."""
    if not funding_str or funding_str == '-':
        return None

    # Remove $ and commas
    s = str(funding_str).replace('$', '').replace(',', '').strip()

    multipliers = {'B': 1_000_000_000, 'M': 1_000_000, 'K': 1_000}

    for suffix, mult in multipliers.items():
        if s.upper().endswith(suffix):
            try:
                return float(s[:-1]) * mult
            except ValueError:
                return None

    try:
        return float(s)
    except ValueError:
        return None


def main():
    parser = argparse.ArgumentParser(description="Import Crunchbase CB ranks")
    parser.add_argument("json_file", help="Path to Crunchbase JSON export")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        print(f"Error: File not found: {json_path}")
        sys.exit(1)

    # Load Crunchbase data
    print(f"Loading Crunchbase data from: {json_path}")
    with open(json_path, encoding='utf-8') as f:
        cb_data = json.load(f)

    print(f"Found {len(cb_data)} companies in Crunchbase export")

    # Get database session
    session = get_session()

    # Build lookup of existing companies by normalized name
    existing = {c.normalized_name: c for c in session.query(Company).all()}
    print(f"Found {len(existing)} existing companies in database")

    # Track stats
    updated = 0
    created = 0
    skipped = 0

    for entry in cb_data:
        name = entry.get('name', '').strip()
        cb_rank = entry.get('cb_rank')

        if not name or not cb_rank:
            skipped += 1
            continue

        norm_name = normalize_name(name)

        if norm_name in existing:
            # Update existing company
            company = existing[norm_name]
            if not args.dry_run:
                company.cb_rank = cb_rank
                # Update other fields if available and not set
                if entry.get('estimated_revenue') and not company.estimated_revenue:
                    company.estimated_revenue = entry['estimated_revenue']
                if entry.get('employee_count') and not company.employee_count:
                    company.employee_count = entry['employee_count']
                if entry.get('founded_year') and not company.founded_year:
                    company.founded_year = entry['founded_year']
                if entry.get('total_funding') and not company.total_funding:
                    funding = parse_funding(entry['total_funding'])
                    if funding:
                        company.total_funding = funding
                if entry.get('website') and not company.website:
                    company.website = entry['website']
                if entry.get('description') and not company.description:
                    company.description = entry['description']
            updated += 1
        else:
            # Create new company
            if not args.dry_run:
                company = Company(
                    name=name,
                    normalized_name=norm_name,
                    cb_rank=cb_rank,
                    website=entry.get('website'),
                    description=entry.get('description'),
                    founded_year=entry.get('founded_year'),
                    total_funding=parse_funding(entry.get('total_funding')),
                    employee_count=entry.get('employee_count'),
                    estimated_revenue=entry.get('estimated_revenue'),
                    funding_stage=entry.get('funding_stage'),
                )
                session.add(company)
                existing[norm_name] = company  # Add to lookup
            created += 1

    # Commit changes
    if not args.dry_run:
        session.commit()
        print("\nChanges committed to database")
    else:
        print("\n(Dry run - no changes saved)")

    print(f"\nSummary:")
    print(f"  Updated existing: {updated}")
    print(f"  Created new:      {created}")
    print(f"  Skipped (no rank): {skipped}")
    print(f"  Total with CB rank: {updated + created}")

    # Verify
    if not args.dry_run:
        count = session.query(Company).filter(Company.cb_rank.isnot(None)).count()
        print(f"\nVerification: {count} companies now have CB rank in database")

    session.close()


if __name__ == "__main__":
    main()