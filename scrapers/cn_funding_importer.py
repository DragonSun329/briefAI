"""
Import CN AI funding data into trend_radar database.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path


def import_cn_funding(funding_file: Path, db_path: Path, dry_run: bool = False):
    """Import CN AI funding data into trend_radar.db companies table."""

    # Load funding data
    with open(funding_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    companies = data.get('companies', [])
    print(f"Loaded {len(companies)} companies from {funding_file.name}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check current schema
    cursor.execute("PRAGMA table_info(companies)")
    columns = {row[1] for row in cursor.fetchall()}

    # Add funding columns if they don't exist
    new_columns = [
        ("total_funding", "REAL"),
        ("funding_stage", "TEXT"),
        ("funding_updated_at", "TEXT"),
        ("cn_name", "TEXT"),
    ]

    for col_name, col_type in new_columns:
        if col_name not in columns:
            print(f"Adding column: {col_name}")
            cursor.execute(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}")
            columns.add(col_name)  # Track that we added it

    # Import funding data
    updated = 0
    inserted = 0

    for company in companies:
        name = company['name']
        cn_name = company.get('cn_name')
        funding_usd = company.get('best_estimate_usd_m')
        category = company.get('category')

        if funding_usd:
            funding_usd = funding_usd * 1_000_000  # Convert M to raw USD

        # Check if company exists
        cursor.execute("SELECT id, total_funding FROM companies WHERE name = ? OR normalized_name = ?",
                      (name, name.lower().replace(' ', '-')))
        existing = cursor.fetchone()

        if existing:
            company_id, current_funding = existing
            # Update if we have better data
            if funding_usd and (not current_funding or funding_usd > current_funding):
                print(f"  UPDATE: {name} ({cn_name}) - ${funding_usd/1e6:.0f}M")
                if not dry_run:
                    cursor.execute("""
                        UPDATE companies
                        SET total_funding = ?,
                            cn_name = COALESCE(?, cn_name),
                            funding_updated_at = ?,
                            country = 'China'
                        WHERE id = ?
                    """, (funding_usd, cn_name, datetime.now().isoformat(), company_id))
                updated += 1
        else:
            # Insert new company
            print(f"  INSERT: {name} ({cn_name}) - ${funding_usd/1e6:.0f}M" if funding_usd else f"  INSERT: {name} ({cn_name})")
            if not dry_run:
                cursor.execute("""
                    INSERT INTO companies (name, normalized_name, cn_name, total_funding, country, funding_updated_at, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'China', ?, ?, ?)
                """, (
                    name,
                    name.lower().replace(' ', '-'),
                    cn_name,
                    funding_usd,
                    datetime.now().isoformat(),
                    datetime.now().isoformat(),
                    datetime.now().isoformat()
                ))
            inserted += 1

    if not dry_run:
        conn.commit()

    conn.close()

    print(f"\nSummary:")
    print(f"  Updated: {updated}")
    print(f"  Inserted: {inserted}")
    print(f"  {'(DRY RUN - no changes made)' if dry_run else 'Changes committed'}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import CN AI funding data")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--funding-file", type=str, help="Path to funding JSON file")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # Find latest funding file
    if args.funding_file:
        funding_file = Path(args.funding_file)
    else:
        funding_files = sorted(base_dir.glob("data/alternative_signals/cn_ai_funding_*.json"), reverse=True)
        if not funding_files:
            print("No CN AI funding files found")
            return
        funding_file = funding_files[0]

    db_path = base_dir / "data" / "trend_radar.db"

    print(f"Funding file: {funding_file}")
    print(f"Database: {db_path}")
    print()

    import_cn_funding(funding_file, db_path, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
