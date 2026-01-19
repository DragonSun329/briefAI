"""Fetch funding data from Wikidata using SPARQL."""

import requests
import time
from typing import Dict, Optional, List

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"

# Query to search for a company by name
COMPANY_SEARCH_QUERY = '''
SELECT ?company ?companyLabel ?totalAssets ?employeeCount ?website
WHERE {{
  ?company wdt:P31/wdt:P279* wd:Q4830453.  # instance of business enterprise
  ?company rdfs:label ?label.
  FILTER(LANG(?label) = "en")
  FILTER(CONTAINS(LCASE(?label), "{search_term}"))

  OPTIONAL {{ ?company wdt:P2403 ?totalAssets. }}  # total assets
  OPTIONAL {{ ?company wdt:P1128 ?employeeCount. }}  # employees
  OPTIONAL {{ ?company wdt:P856 ?website. }}  # official website

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT 5
'''

# Query for all AI/tech companies with funding data
AI_COMPANIES_QUERY = '''
SELECT ?company ?companyLabel ?totalAssets ?employeeCount
WHERE {
  ?company wdt:P31/wdt:P279* wd:Q4830453.  # business
  ?company wdt:P452 ?industry.

  # Industries related to AI/tech
  VALUES ?industry {
    wd:Q11660    # AI
    wd:Q21198    # computer science
    wd:Q80993    # software engineering
    wd:Q1301371  # software company
  }

  OPTIONAL { ?company wdt:P2403 ?totalAssets. }
  OPTIONAL { ?company wdt:P1128 ?employeeCount. }

  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
LIMIT 2000
'''


class WikidataFetcher:
    """Fetch company funding data from Wikidata."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "BriefAI/1.0 (funding-enricher; contact@example.com)"
        self._cache = {}

    def _query(self, sparql: str) -> List[Dict]:
        """Execute SPARQL query with rate limiting."""
        time.sleep(0.5)  # Rate limit

        try:
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

        except requests.exceptions.RequestException as e:
            print(f"Wikidata query failed: {e}")
            return []

    def fetch_company(self, company_name: str) -> Optional[Dict]:
        """
        Fetch funding data for a specific company.

        Args:
            company_name: Company name to search for

        Returns:
            Dict with company data or None
        """
        # Check cache
        cache_key = company_name.lower()
        if cache_key in self._cache:
            return self._cache[cache_key]

        search_term = company_name.lower()
        query = COMPANY_SEARCH_QUERY.format(search_term=search_term)

        results = self._query(query)

        if results:
            # Return first result with assets/employees
            for r in results:
                if r.get("totalAssets") or r.get("employeeCount"):
                    self._cache[cache_key] = r
                    return r

            # Otherwise return first result
            self._cache[cache_key] = results[0]
            return results[0]

        self._cache[cache_key] = None
        return None

    def fetch_ai_companies(self) -> List[Dict]:
        """
        Fetch all AI/tech companies with funding data.

        Returns:
            List of company dicts
        """
        return self._query(AI_COMPANIES_QUERY)

    def get_funding(self, company_name: str) -> Optional[float]:
        """
        Get total assets/funding for a company.

        Args:
            company_name: Company name to search

        Returns:
            Funding amount in USD or None
        """
        result = self.fetch_company(company_name)
        if result and result.get("totalAssets"):
            try:
                return float(result["totalAssets"])
            except (ValueError, TypeError):
                return None
        return None


if __name__ == "__main__":
    # Test the fetcher
    fetcher = WikidataFetcher()

    test_companies = [
        "OpenAI",
        "Anthropic",
        "Google",
        "Microsoft",
        "Apple",
    ]

    print("Testing Wikidata fetcher:")
    for name in test_companies:
        result = fetcher.fetch_company(name)
        if result:
            label = result.get("companyLabel", "?")
            assets = result.get("totalAssets", "N/A")
            employees = result.get("employeeCount", "N/A")
            print(f"  {name} -> {label}: assets={assets}, employees={employees}")
        else:
            print(f"  {name} -> No result")
