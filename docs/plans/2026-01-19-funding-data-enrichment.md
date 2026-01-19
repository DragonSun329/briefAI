# Funding Data Enrichment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enrich 4,892 companies in trend_radar.db with Total Funding and ARR data from free sources, then Crunchbase manual fallback.

**Architecture:** Multi-source pipeline: Kaggle CSV → Wikidata SPARQL → Crunchbase clipboard fallback. Fuzzy name matching to join data.

**Tech Stack:** Python, SQLAlchemy, rapidfuzz, requests, pandas

---

## Task 1: Add Funding Fields to Company Model

**Files:**
- Modify: `.worktrees/trend-radar/trend_radar/models.py`
- Create: `.worktrees/trend-radar/trend_radar/migrations/add_funding_fields.py`

**Step 1: Write the migration script**

```python
# migrations/add_funding_fields.py
"""Add funding fields to companies table."""

from sqlalchemy import create_engine, text
import os

def migrate():
    db_url = os.getenv("TREND_RADAR_DB_URL", "sqlite:///data/trend_radar.db")
    engine = create_engine(db_url)

    with engine.connect() as conn:
        # Add funding columns
        columns = [
            ("total_funding", "REAL"),
            ("funding_stage", "VARCHAR(50)"),
            ("employee_count", "VARCHAR(50)"),
            ("funding_updated_at", "DATETIME"),
            ("arr", "REAL"),
            ("arr_source", "VARCHAR(100)"),
            ("arr_date", "VARCHAR(20)"),
        ]

        for col_name, col_type in columns:
            try:
                conn.execute(text(f"ALTER TABLE companies ADD COLUMN {col_name} {col_type}"))
                print(f"Added column: {col_name}")
            except Exception as e:
                if "duplicate column" in str(e).lower():
                    print(f"Column {col_name} already exists")
                else:
                    raise

        conn.commit()

    print("Migration complete!")

if __name__ == "__main__":
    migrate()
```

**Step 2: Update models.py with new columns**

Add to Company class in models.py:

```python
# Funding data
total_funding = Column(Float, nullable=True)          # In USD
funding_stage = Column(String(50), nullable=True)    # "Series F", "Seed"
employee_count = Column(String(50), nullable=True)   # "1001-5000"
funding_updated_at = Column(DateTime, nullable=True)

# ARR (optional)
arr = Column(Float, nullable=True)
arr_source = Column(String(100), nullable=True)
arr_date = Column(String(20), nullable=True)
```

**Step 3: Run migration**

```bash
cd .worktrees/trend-radar
python -m trend_radar.migrations.add_funding_fields
```

**Step 4: Verify columns added**

```bash
python -c "import sqlite3; conn = sqlite3.connect('data/trend_radar.db'); print([c[1] for c in conn.execute('PRAGMA table_info(companies)').fetchall()])"
```

**Step 5: Commit**

```bash
git add trend_radar/models.py trend_radar/migrations/
git commit -m "feat: add funding fields to Company model"
```

---

## Task 2: Download Kaggle Crunchbase Dataset

**Files:**
- Create: `data/kaggle/` directory
- Download: Crunchbase startup investments CSV

**Step 1: Create data directory**

```bash
mkdir -p data/kaggle
```

**Step 2: Download dataset manually**

Go to: https://www.kaggle.com/datasets/arindam235/startup-investments-crunchbase

Download and extract to `data/kaggle/investments_VC.csv`

Alternative datasets to try:
- https://www.kaggle.com/datasets/justinas/startup-investments
- https://www.kaggle.com/datasets/yanmaksi/big-startup-secsam-702702-702702

**Step 3: Verify file exists**

```bash
ls -la data/kaggle/
head -5 data/kaggle/investments_VC.csv
```

---

## Task 3: Create Kaggle Crunchbase Matcher

**Files:**
- Create: `scrapers/kaggle_crunchbase_matcher.py`
- Test: `tests/test_kaggle_matcher.py`

**Step 1: Write the failing test**

```python
# tests/test_kaggle_matcher.py
import pytest
from scrapers.kaggle_crunchbase_matcher import normalize_name, match_company

def test_normalize_name():
    assert normalize_name("OpenAI, Inc.") == "openai"
    assert normalize_name("Anthropic PBC") == "anthropic"
    assert normalize_name("Meta AI") == "meta ai"

def test_match_company_exact():
    kaggle_data = [
        {"name": "OpenAI", "funding_total_usd": 17900000000},
        {"name": "Anthropic", "funding_total_usd": 7300000000},
    ]
    result = match_company("OpenAI", kaggle_data)
    assert result is not None
    assert result["funding_total_usd"] == 17900000000

def test_match_company_fuzzy():
    kaggle_data = [
        {"name": "OpenAI Inc.", "funding_total_usd": 17900000000},
    ]
    result = match_company("OpenAI", kaggle_data, threshold=80)
    assert result is not None
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_kaggle_matcher.py -v
```

Expected: FAIL (module not found)

**Step 3: Write the matcher implementation**

```python
# scrapers/kaggle_crunchbase_matcher.py
"""Match companies to Kaggle Crunchbase dataset."""

import re
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Any
from rapidfuzz import fuzz, process

# Common suffixes to remove for matching
SUFFIXES = [
    r"\s*,?\s*inc\.?$",
    r"\s*,?\s*llc\.?$",
    r"\s*,?\s*ltd\.?$",
    r"\s*,?\s*corp\.?$",
    r"\s*,?\s*pbc\.?$",
    r"\s*,?\s*co\.?$",
]

def normalize_name(name: str) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""

    name = name.lower().strip()

    # Remove common suffixes
    for suffix in SUFFIXES:
        name = re.sub(suffix, "", name, flags=re.IGNORECASE)

    # Remove extra whitespace
    name = re.sub(r"\s+", " ", name).strip()

    return name


def load_kaggle_data(csv_path: str = "data/kaggle/investments_VC.csv") -> pd.DataFrame:
    """Load and preprocess Kaggle Crunchbase data."""
    df = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)

    # Normalize names
    df["normalized_name"] = df["name"].apply(normalize_name)

    # Group by company and sum funding
    funding_by_company = df.groupby("normalized_name").agg({
        "name": "first",
        "funding_total_usd": "max",
        "funding_rounds": "max",
        "status": "first",
        "category_list": "first",
    }).reset_index()

    return funding_by_company


def match_company(
    company_name: str,
    kaggle_data: List[Dict[str, Any]],
    threshold: int = 85
) -> Optional[Dict[str, Any]]:
    """
    Match a company name to Kaggle data using fuzzy matching.

    Args:
        company_name: Company name to match
        kaggle_data: List of dicts with 'name' and funding fields
        threshold: Minimum fuzzy match score (0-100)

    Returns:
        Matched record or None
    """
    normalized = normalize_name(company_name)

    # First try exact match
    for record in kaggle_data:
        if normalize_name(record.get("name", "")) == normalized:
            return record

    # Fuzzy match
    names = [normalize_name(r.get("name", "")) for r in kaggle_data]
    result = process.extractOne(normalized, names, scorer=fuzz.ratio)

    if result and result[1] >= threshold:
        matched_name = result[0]
        for record in kaggle_data:
            if normalize_name(record.get("name", "")) == matched_name:
                return record

    return None


class KaggleMatcher:
    """Batch matcher for Kaggle Crunchbase data."""

    def __init__(self, csv_path: str = "data/kaggle/investments_VC.csv"):
        self.df = load_kaggle_data(csv_path)
        self.records = self.df.to_dict("records")
        self._name_index = {
            normalize_name(r["name"]): r for r in self.records
        }

    def match(self, company_name: str, threshold: int = 85) -> Optional[Dict[str, Any]]:
        """Match a single company."""
        normalized = normalize_name(company_name)

        # Exact match first
        if normalized in self._name_index:
            return self._name_index[normalized]

        # Fuzzy match
        return match_company(company_name, self.records, threshold)

    def match_batch(
        self,
        company_names: List[str],
        threshold: int = 85
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Match multiple companies."""
        results = {}
        for name in company_names:
            results[name] = self.match(name, threshold)
        return results
```

**Step 4: Run tests**

```bash
pytest tests/test_kaggle_matcher.py -v
```

**Step 5: Commit**

```bash
git add scrapers/kaggle_crunchbase_matcher.py tests/test_kaggle_matcher.py
git commit -m "feat: add Kaggle Crunchbase matcher with fuzzy matching"
```

---

## Task 4: Create Wikidata Funding Fetcher

**Files:**
- Create: `scrapers/wikidata_funding_fetcher.py`
- Test: `tests/test_wikidata_fetcher.py`

**Step 1: Write the failing test**

```python
# tests/test_wikidata_fetcher.py
import pytest
from scrapers.wikidata_funding_fetcher import WikidataFetcher

@pytest.mark.integration
def test_fetch_openai_funding():
    fetcher = WikidataFetcher()
    result = fetcher.fetch_company("OpenAI")
    # OpenAI should be in Wikidata
    assert result is not None or result == {}  # May not have funding data
```

**Step 2: Write the implementation**

```python
# scrapers/wikidata_funding_fetcher.py
"""Fetch funding data from Wikidata using SPARQL."""

import requests
from typing import Dict, Optional, List

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

FUNDING_QUERY = """
SELECT ?company ?companyLabel ?totalFunding ?employeeCount ?foundingDate
WHERE {{
  ?company wdt:P31 wd:Q4830453.  # instance of business
  ?company rdfs:label ?companyLabel.
  FILTER(LANG(?companyLabel) = "en")
  FILTER(CONTAINS(LCASE(?companyLabel), "{search_term}"))

  OPTIONAL {{ ?company wdt:P2769 ?totalFunding. }}  # total assets/funding
  OPTIONAL {{ ?company wdt:P1128 ?employeeCount. }}  # employees
  OPTIONAL {{ ?company wdt:P571 ?foundingDate. }}   # inception
}}
LIMIT 10
"""

AI_COMPANIES_QUERY = """
SELECT ?company ?companyLabel ?totalAssets ?employeeCount
WHERE {
  ?company wdt:P31 wd:Q4830453.  # business
  ?company wdt:P452 ?industry.
  ?industry wdt:P279* wd:Q11660.  # AI industry

  OPTIONAL { ?company wdt:P2769 ?totalAssets. }
  OPTIONAL { ?company wdt:P1128 ?employeeCount. }

  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 1000
"""


class WikidataFetcher:
    """Fetch company funding data from Wikidata."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "BriefAI/1.0 (funding-enricher)"

    def _query(self, sparql: str) -> List[Dict]:
        """Execute SPARQL query."""
        response = self.session.get(
            WIKIDATA_ENDPOINT,
            params={"query": sparql, "format": "json"},
            timeout=30
        )
        response.raise_for_status()

        data = response.json()
        results = []

        for binding in data.get("results", {}).get("bindings", []):
            record = {}
            for key, value in binding.items():
                record[key] = value.get("value")
            results.append(record)

        return results

    def fetch_company(self, company_name: str) -> Optional[Dict]:
        """Fetch funding data for a specific company."""
        search_term = company_name.lower()
        query = FUNDING_QUERY.format(search_term=search_term)

        try:
            results = self._query(query)
            if results:
                return results[0]
        except Exception as e:
            print(f"Wikidata query failed for {company_name}: {e}")

        return None

    def fetch_ai_companies(self) -> List[Dict]:
        """Fetch all AI companies with funding data."""
        try:
            return self._query(AI_COMPANIES_QUERY)
        except Exception as e:
            print(f"Wikidata AI companies query failed: {e}")
            return []
```

**Step 3: Run test**

```bash
pytest tests/test_wikidata_fetcher.py -v -m integration
```

**Step 4: Commit**

```bash
git add scrapers/wikidata_funding_fetcher.py tests/test_wikidata_fetcher.py
git commit -m "feat: add Wikidata SPARQL funding fetcher"
```

---

## Task 5: Create Main Funding Enricher Pipeline

**Files:**
- Create: `scrapers/funding_enricher.py`

**Step 1: Write the enricher**

```python
# scrapers/funding_enricher.py
"""
Funding Data Enrichment Pipeline

Usage:
    python scrapers/funding_enricher.py [--dry-run] [--limit N]
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent / ".worktrees" / "trend-radar"))

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
            return float(value[:-1]) * mult

    try:
        return float(value)
    except:
        return None


def enrich_from_kaggle(
    companies: List[Company],
    matcher: KaggleMatcher,
    dry_run: bool = False
) -> Tuple[int, int, List[str]]:
    """
    Enrich companies from Kaggle Crunchbase data.

    Returns: (matched, unmatched, unmatched_names)
    """
    matched = 0
    unmatched = 0
    unmatched_names = []

    for company in companies:
        result = matcher.match(company.name)

        if result:
            funding = parse_funding_amount(result.get("funding_total_usd"))
            if funding:
                if not dry_run:
                    company.total_funding = funding
                    company.funding_updated_at = datetime.utcnow()
                matched += 1
                print(f"  ✓ {company.name}: ${funding:,.0f}")
            else:
                unmatched += 1
                unmatched_names.append(company.name)
        else:
            unmatched += 1
            unmatched_names.append(company.name)

    return matched, unmatched, unmatched_names


def enrich_from_wikidata(
    companies: List[Company],
    fetcher: WikidataFetcher,
    dry_run: bool = False
) -> Tuple[int, int]:
    """
    Enrich companies from Wikidata (for those without funding).

    Returns: (matched, unmatched)
    """
    matched = 0
    unmatched = 0

    # Only try companies without funding
    unfunded = [c for c in companies if c.total_funding is None]

    for company in unfunded:
        result = fetcher.fetch_company(company.name)

        if result and result.get("totalFunding"):
            funding = parse_funding_amount(result["totalFunding"])
            if funding:
                if not dry_run:
                    company.total_funding = funding
                    company.funding_updated_at = datetime.utcnow()
                matched += 1
                print(f"  ✓ {company.name}: ${funding:,.0f} (Wikidata)")
            else:
                unmatched += 1
        else:
            unmatched += 1

    return matched, unmatched


def main():
    parser = argparse.ArgumentParser(description="Enrich company funding data")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")
    parser.add_argument("--limit", type=int, help="Limit companies to process")
    parser.add_argument("--kaggle-csv", default="data/kaggle/investments_VC.csv")
    parser.add_argument("--skip-wikidata", action="store_true")
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

    # Phase 1: Kaggle Crunchbase
    print(f"\n--- Phase 1: Kaggle Crunchbase Matching ---")

    kaggle_csv = Path(args.kaggle_csv)
    if kaggle_csv.exists():
        matcher = KaggleMatcher(str(kaggle_csv))
        k_matched, k_unmatched, unmatched_names = enrich_from_kaggle(
            companies, matcher, args.dry_run
        )
        print(f"\nKaggle: {k_matched} matched, {k_unmatched} unmatched")
    else:
        print(f"Kaggle CSV not found: {kaggle_csv}")
        print("Download from: https://www.kaggle.com/datasets/arindam235/startup-investments-crunchbase")
        k_matched = 0
        unmatched_names = [c.name for c in companies]

    # Phase 2: Wikidata
    if not args.skip_wikidata:
        print(f"\n--- Phase 2: Wikidata SPARQL ---")
        fetcher = WikidataFetcher()
        w_matched, w_unmatched = enrich_from_wikidata(
            companies, fetcher, args.dry_run
        )
        print(f"\nWikidata: {w_matched} matched, {w_unmatched} unmatched")

    # Save changes
    if not args.dry_run:
        session.commit()
        print("\n✓ Changes saved to database")
    else:
        print("\n(Dry run - no changes saved)")

    # Report unmatched for manual lookup
    still_unfunded = [c for c in companies if c.total_funding is None]
    if still_unfunded:
        print(f"\n--- Companies needing manual Crunchbase lookup ({len(still_unfunded)}) ---")
        with open("data/unfunded_companies.txt", "w") as f:
            for c in still_unfunded[:100]:
                f.write(f"{c.name}\n")
                print(f"  - {c.name}")
            if len(still_unfunded) > 100:
                print(f"  ... and {len(still_unfunded) - 100} more")
                f.write(f"\n# And {len(still_unfunded) - 100} more\n")
        print(f"\nFull list saved to: data/unfunded_companies.txt")

    # Summary
    funded = len([c for c in companies if c.total_funding is not None])
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {funded}/{len(companies)} companies now have funding data")
    print(f"Coverage: {funded/len(companies)*100:.1f}%")
    print("=" * 60)


if __name__ == "__main__":
    main()
```

**Step 2: Test dry run**

```bash
python scrapers/funding_enricher.py --dry-run --limit 100
```

**Step 3: Run full enrichment**

```bash
python scrapers/funding_enricher.py
```

**Step 4: Commit**

```bash
git add scrapers/funding_enricher.py
git commit -m "feat: add main funding enrichment pipeline"
```

---

## Task 6: Update Shortlist Schema and Query

**Files:**
- Modify: `.worktrees/trend-radar/trend_radar/schemas.py`
- Modify: `.worktrees/trend-radar/trend_radar/shortlist.py`

**Step 1: Add funding fields to ShortlistEntry**

In `schemas.py`:

```python
class ShortlistEntry(BaseModel):
    # ... existing fields ...

    # Add funding fields
    total_funding: Optional[float] = None
    funding_stage: Optional[str] = None
    employee_count: Optional[str] = None
```

**Step 2: Update build_shortlist_entry in shortlist.py**

```python
def build_shortlist_entry(company: Company) -> ShortlistEntry:
    # ... existing code ...

    return ShortlistEntry(
        # ... existing fields ...
        total_funding=company.total_funding,
        funding_stage=company.funding_stage,
        employee_count=company.employee_count,
    )
```

**Step 3: Commit**

```bash
git add trend_radar/schemas.py trend_radar/shortlist.py
git commit -m "feat: add funding fields to shortlist schema"
```

---

## Task 7: Update Frontend to Show Funding

**Files:**
- Modify: `app.py` (AI Shortlist tab)

**Step 1: Add Total Funding column to table**

In app.py, update the shortlist table rendering:

```python
# In the shortlist table building section
shortlist_data.append({
    'Name / 名称': entry.name,
    'Category / 类别': f"{entry.category_zh} ({entry.category})",
    'Stage / 阶段': entry.funding_stage_zh or entry.funding_stage or "-",
    'Total Funding': format_funding(entry.total_funding),  # NEW
    'Sources': entry.source_count,
    'Rising Score': f"{entry.rising_score:.1f}" if entry.rising_score else "-",
})
```

**Step 2: Add format_funding helper**

```python
def format_funding(amount: float) -> str:
    """Format funding amount for display."""
    if amount is None:
        return "-"
    if amount >= 1_000_000_000:
        return f"${amount/1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"${amount/1_000_000:.0f}M"
    if amount >= 1_000:
        return f"${amount/1_000:.0f}K"
    return f"${amount:.0f}"
```

**Step 3: Remove hardcoded AI_COMPANY_DATA dict**

Delete the `AI_COMPANY_DATA` dictionary and the "Biggest" subtab that uses it - now all data comes from the database.

**Step 4: Test the UI**

```bash
streamlit run app.py
```

**Step 5: Commit**

```bash
git add app.py
git commit -m "feat: show total funding in AI Shortlist table"
```

---

## Task 8: Test End-to-End

**Step 1: Run the full pipeline**

```bash
# 1. Run migration
cd .worktrees/trend-radar
python -m trend_radar.migrations.add_funding_fields

# 2. Download Kaggle dataset (manual)

# 3. Run enrichment
cd ../..
python scrapers/funding_enricher.py

# 4. Check results
python -c "
from trend_radar.models import get_session, Company
session = get_session()
funded = session.query(Company).filter(Company.total_funding.isnot(None)).count()
total = session.query(Company).count()
print(f'Funded: {funded}/{total} ({funded/total*100:.1f}%)')
"

# 5. Start UI
streamlit run app.py
```

**Step 2: Verify in UI**

- Open AI Shortlist tab
- Check that Total Funding column shows data
- Filter by category and verify funding shows

---

## Summary

| Task | Description | Estimated Coverage |
|------|-------------|-------------------|
| 1 | Add funding columns to DB | - |
| 2 | Download Kaggle CSV | - |
| 3 | Kaggle matcher | ~60-70% (3,000+ companies) |
| 4 | Wikidata fetcher | ~10% additional (500 companies) |
| 5 | Main enricher pipeline | - |
| 6 | Update shortlist schema | - |
| 7 | Update frontend | - |
| 8 | End-to-end test | - |

**Expected final coverage:** 70-80% of 4,892 companies with funding data.
**Remaining ~20%:** Use Crunchbase clipboard scraper for manual lookup.