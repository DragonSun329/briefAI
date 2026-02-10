#!/usr/bin/env python
"""
Import Crunchbase scraped data into the trend_radar database.

Updates Company records with:
- country (for market filtering)
- hq_location (full location string)
- cb_rank (if different/better)
- total_funding (from funding_usd)
- employee_count
- estimated_revenue
- founded_year

Usage:
    python scrapers/import_crunchbase_data.py [--json-file PATH] [--dry-run]
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add project paths
sys.path.insert(0, str(Path(__file__).parent.parent))
_trend_radar_path = Path(__file__).parent.parent / ".worktrees" / "trend-radar"
sys.path.append(str(_trend_radar_path))

import os
os.environ["TREND_RADAR_DB_URL"] = f"sqlite:///{(_trend_radar_path / 'data' / 'trend_radar.db').as_posix()}"

from trend_radar.models import get_session, Company
from loguru import logger


def normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    return name.lower().strip().replace(".", "").replace(",", "").replace(" inc", "").replace(" llc", "").replace(" ltd", "")


def load_crunchbase_data(json_path: Path) -> list:
    """Load and fix Crunchbase scraped data."""
    with open(json_path, "r", encoding="utf-8") as f:
        companies = json.load(f)

    # Country name list for validation
    country_names = [
        'United States', 'China', 'United Kingdom', 'Germany', 'France', 'Canada',
        'Israel', 'India', 'Japan', 'Singapore', 'Australia', 'Netherlands', 'Sweden',
        'Switzerland', 'South Korea', 'Brazil', 'Spain', 'Italy', 'Ireland', 'Belgium',
        'Austria', 'Finland', 'Norway', 'Denmark', 'Poland', 'Taiwan', 'Hong Kong',
        'Indonesia', 'Thailand', 'Vietnam', 'Malaysia', 'Philippines', 'Mexico',
        'Argentina', 'Chile', 'Colombia', 'UAE', 'Saudi Arabia', 'Egypt', 'Nigeria',
        'South Africa', 'New Zealand', 'Portugal', 'Czech Republic', 'Hungary',
        'Romania', 'Greece', 'Turkey', 'Russia', 'Ukraine'
    ]

    # Region patterns to detect swapped fields
    region_patterns = [
        'Bay Area', 'Silicon Valley', 'Greater', 'West Coast', 'East Coast',
        'Midwest', 'Southern US', 'Western US', 'Northeastern US', 'New England',
        'EMEA', 'APAC', 'Middle East', 'Latin America', 'Northern Europe',
        'Southeast Asia', 'North Africa'
    ]

    def is_region(text):
        if not text:
            return False
        for pat in region_patterns:
            if pat.lower() in text.lower():
                return True
        return False

    def extract_country(text):
        if not text:
            return None
        for country in country_names:
            if country.lower() in text.lower():
                return country
        return None

    def is_location(text):
        return extract_country(text) is not None

    # Fix swapped region/location fields
    fixed = 0
    for c in companies:
        old_location = c.get('hq_location', '')
        old_industries = c.get('industries', '')

        # If hq_location looks like a region and industries looks like a location
        if is_region(old_location) and is_location(old_industries):
            c['hq_region'] = old_location
            c['hq_location'] = old_industries

            parts = old_industries.split(',')
            parts = [p.strip() for p in parts]
            if len(parts) >= 3:
                c['city'] = parts[0]
                c['state'] = parts[1]
                c['country'] = parts[2]
            elif len(parts) == 2:
                c['city'] = parts[0]
                c['country'] = parts[1]

            c['industries'] = None
            fixed += 1

        # Ensure country is valid
        if c.get('country') and c['country'] not in country_names:
            real_country = extract_country(c.get('hq_location', ''))
            if real_country:
                c['country'] = real_country

    logger.info(f"Fixed {fixed} companies with swapped region/location")
    return companies


def import_crunchbase_data(json_path: Path, dry_run: bool = False):
    """Import Crunchbase data into the database."""

    # Load and fix the scraped data
    cb_companies = load_crunchbase_data(json_path)
    logger.info(f"Loaded {len(cb_companies)} companies from {json_path}")

    # Build lookup by normalized name
    cb_lookup = {}
    for c in cb_companies:
        name = c.get('name')
        if name:
            key = normalize_name(name)
            cb_lookup[key] = c

    logger.info(f"Built lookup with {len(cb_lookup)} unique company names")

    # Get database session
    session = get_session()

    try:
        # Get all companies from database
        db_companies = session.query(Company).all()
        logger.info(f"Found {len(db_companies)} companies in database")

        # Track statistics
        stats = {
            'matched': 0,
            'updated_country': 0,
            'updated_location': 0,
            'updated_funding': 0,
            'updated_employees': 0,
            'updated_revenue': 0,
            'updated_founded': 0,
            'updated_rank': 0,
            'updated_trend': 0,
            'no_match': 0,
        }

        for db_company in db_companies:
            key = normalize_name(db_company.name)
            cb_data = cb_lookup.get(key)

            if not cb_data:
                stats['no_match'] += 1
                continue

            stats['matched'] += 1
            updates = []

            # Update country
            new_country = cb_data.get('country')
            if new_country and new_country != db_company.country:
                if not dry_run:
                    db_company.country = new_country
                updates.append(f"country: {db_company.country} -> {new_country}")
                stats['updated_country'] += 1

            # Update hq_location (full location string)
            new_location = cb_data.get('hq_location')
            if new_location and hasattr(db_company, 'hq_location'):
                if getattr(db_company, 'hq_location', None) != new_location:
                    if not dry_run:
                        db_company.hq_location = new_location
                    updates.append(f"hq_location: {new_location}")
                    stats['updated_location'] += 1

            # Update total_funding (from funding_usd)
            new_funding = cb_data.get('funding_usd')
            if new_funding and hasattr(db_company, 'total_funding'):
                if not getattr(db_company, 'total_funding', None) or new_funding > db_company.total_funding:
                    if not dry_run:
                        db_company.total_funding = new_funding
                    updates.append(f"total_funding: ${new_funding/1e6:.1f}M")
                    stats['updated_funding'] += 1

            # Update employee_count
            new_employees = cb_data.get('employees')
            if new_employees and hasattr(db_company, 'employee_count'):
                if getattr(db_company, 'employee_count', None) != new_employees:
                    if not dry_run:
                        db_company.employee_count = new_employees
                    updates.append(f"employee_count: {new_employees}")
                    stats['updated_employees'] += 1

            # Update estimated_revenue
            new_revenue = cb_data.get('estimated_revenue')
            if new_revenue and hasattr(db_company, 'estimated_revenue'):
                if getattr(db_company, 'estimated_revenue', None) != new_revenue:
                    if not dry_run:
                        db_company.estimated_revenue = new_revenue
                    updates.append(f"estimated_revenue: {new_revenue}")
                    stats['updated_revenue'] += 1

            # Update founded_year
            new_founded = cb_data.get('founded_year')
            if new_founded and hasattr(db_company, 'founded_year'):
                if not getattr(db_company, 'founded_year', None):
                    if not dry_run:
                        db_company.founded_year = new_founded
                    updates.append(f"founded_year: {new_founded}")
                    stats['updated_founded'] += 1

            # Update cb_rank (only if better/lower rank)
            new_rank = cb_data.get('cb_rank')
            if new_rank and hasattr(db_company, 'cb_rank'):
                current_rank = getattr(db_company, 'cb_rank', None)
                if not current_rank or new_rank < current_rank:
                    if not dry_run:
                        db_company.cb_rank = new_rank
                    updates.append(f"cb_rank: {current_rank} -> {new_rank}")
                    stats['updated_rank'] += 1

            # Update cb_trend_score
            new_trend = cb_data.get('trend_score')
            if new_trend is not None and hasattr(db_company, 'cb_trend_score'):
                current_trend = getattr(db_company, 'cb_trend_score', None)
                if current_trend != new_trend:
                    if not dry_run:
                        db_company.cb_trend_score = new_trend
                    updates.append(f"cb_trend_score: {new_trend:+.1f}")
                    stats['updated_trend'] += 1

            if updates:
                logger.debug(f"{db_company.name}: {', '.join(updates)}")

        if not dry_run:
            session.commit()
            logger.info("Changes committed to database")
        else:
            logger.info("DRY RUN - no changes committed")

        # Print summary
        print("\n" + "=" * 60)
        print("IMPORT SUMMARY")
        print("=" * 60)
        print(f"Companies in JSON:     {len(cb_companies)}")
        print(f"Companies in DB:       {len(db_companies)}")
        print(f"Matched by name:       {stats['matched']}")
        print(f"No match found:        {stats['no_match']}")
        print()
        print("Updates:")
        print(f"  Country:             {stats['updated_country']}")
        print(f"  Location:            {stats['updated_location']}")
        print(f"  Funding:             {stats['updated_funding']}")
        print(f"  Employees:           {stats['updated_employees']}")
        print(f"  Revenue:             {stats['updated_revenue']}")
        print(f"  Founded Year:        {stats['updated_founded']}")
        print(f"  CB Rank:             {stats['updated_rank']}")
        print(f"  Trend Score:         {stats['updated_trend']}")
        print("=" * 60)

        return stats

    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Import Crunchbase data into database")
    parser.add_argument(
        "--json-file",
        type=str,
        default=str(Path.home() / "Downloads" / "crunchbase_ai_companies_2026-01-21.json"),
        help="Path to Crunchbase JSON file"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes"
    )
    args = parser.parse_args()

    json_path = Path(args.json_file)
    if not json_path.exists():
        logger.error(f"JSON file not found: {json_path}")
        sys.exit(1)

    import_crunchbase_data(json_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()