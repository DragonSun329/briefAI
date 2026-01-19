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
    r"\s*,?\s*limited$",
    r"\s*,?\s*incorporated$",
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


def load_kaggle_data(csv_path: str = "data/kaggle/comp.csv") -> pd.DataFrame:
    """Load and preprocess Kaggle Crunchbase data."""
    df = pd.read_csv(csv_path, encoding="utf-8", low_memory=False)

    # Convert funding to numeric
    df["funding_total_usd"] = pd.to_numeric(df["funding_total_usd"], errors="coerce")

    # Normalize names for matching
    df["normalized_name"] = df["name"].apply(normalize_name)

    return df


class KaggleMatcher:
    """Batch matcher for Kaggle Crunchbase data."""

    def __init__(self, csv_path: str = "data/kaggle/comp.csv"):
        self.df = load_kaggle_data(csv_path)
        self.records = self.df.to_dict("records")

        # Build name index for fast exact matching
        self._name_index = {}
        for r in self.records:
            norm = normalize_name(r.get("name", ""))
            if norm and norm not in self._name_index:
                self._name_index[norm] = r

        # Prepare list of normalized names for fuzzy matching
        self._normalized_names = list(self._name_index.keys())

        print(f"Loaded {len(self.df)} companies from Kaggle CSV")
        print(f"  With funding data: {self.df['funding_total_usd'].notna().sum()}")

    def match(self, company_name: str, threshold: int = 85) -> Optional[Dict[str, Any]]:
        """
        Match a single company name to Kaggle data.

        Args:
            company_name: Company name to match
            threshold: Minimum fuzzy match score (0-100)

        Returns:
            Matched record dict or None
        """
        normalized = normalize_name(company_name)

        # Exact match first (fast)
        if normalized in self._name_index:
            return self._name_index[normalized]

        # Fuzzy match (slower)
        result = process.extractOne(
            normalized,
            self._normalized_names,
            scorer=fuzz.ratio,
            score_cutoff=threshold
        )

        if result:
            matched_name = result[0]
            return self._name_index.get(matched_name)

        return None

    def match_batch(
        self,
        company_names: List[str],
        threshold: int = 85
    ) -> Dict[str, Optional[Dict[str, Any]]]:
        """Match multiple companies."""
        results = {}
        matched = 0
        for name in company_names:
            result = self.match(name, threshold)
            results[name] = result
            if result:
                matched += 1

        print(f"Matched {matched}/{len(company_names)} companies ({matched/len(company_names)*100:.1f}%)")
        return results

    def get_funding(self, company_name: str, threshold: int = 85) -> Optional[float]:
        """Get just the funding amount for a company."""
        result = self.match(company_name, threshold)
        if result:
            return result.get("funding_total_usd")
        return None


if __name__ == "__main__":
    # Test the matcher
    matcher = KaggleMatcher()

    test_companies = [
        "OpenAI",
        "Anthropic",
        "Airbnb",
        "Alibaba",
        "Google",
        "Some Random Company That Doesnt Exist",
    ]

    print("\nTest matches:")
    for name in test_companies:
        result = matcher.match(name)
        if result:
            funding = result.get("funding_total_usd", 0) or 0
            print(f"  {name} -> {result['name']}: ${funding/1e6:.1f}M")
        else:
            print(f"  {name} -> No match")
