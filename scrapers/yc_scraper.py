"""
Y Combinator Companies Scraper

Tracks AI startups from Y Combinator's company directory to monitor
emerging companies and startup trends in the AI space.

Source: https://www.ycombinator.com/companies
- Public directory, no API key needed
- Filterable by tags including AI
"""

import requests
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
import re


class YCScraper:
    """Scraper for Y Combinator AI companies."""

    # YC's Algolia search endpoint (public)
    ALGOLIA_URL = "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"
    ALGOLIA_APP_ID = "45BWZJ1SGC"
    ALGOLIA_API_KEY = "MjBjYjRiMzY0NzdhZWY0NjExY2NhZjYxMGIxYjc2MTAwNWFkNTkwNTc4NjgxYjU0YzFhYTY2ZGQ5OGY5NDMxZnJlc3RyaWN0SW5kaWNlcz0lNUIlMjJZQ0NvbXBhbnlfcHJvZHVjdGlvbiUyMiU1RCZ0YWdGaWx0ZXJzPSU1QiUyMnljX2JhdGNoJTNBIiU1RA=="
    
    # Alternative: Direct API endpoint
    BASE_URL = "https://www.ycombinator.com/companies"
    API_URL = "https://api.ycombinator.com/v0.1/companies"

    # AI-related tags/keywords to filter
    AI_KEYWORDS = [
        "artificial intelligence",
        "machine learning",
        "ai",
        "ml",
        "nlp",
        "natural language processing",
        "computer vision",
        "deep learning",
        "generative ai",
        "llm",
        "large language model",
        "chatbot",
        "automation",
        "neural network",
    ]

    # Industries to track
    AI_INDUSTRIES = [
        "Artificial Intelligence",
        "Machine Learning",
        "Generative AI",
        "B2B Software and Services",
        "Developer Tools",
    ]

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        })

    def search_algolia(self, query: str = "", filters: str = "", page: int = 0) -> Dict[str, Any]:
        """Search YC companies via Algolia."""
        headers = {
            "x-algolia-application-id": self.ALGOLIA_APP_ID,
            "x-algolia-api-key": self.ALGOLIA_API_KEY,
            "Content-Type": "application/json",
        }
        
        payload = {
            "requests": [{
                "indexName": "YCCompany_production",
                "params": f"query={query}&hitsPerPage=100&page={page}&filters={filters}"
            }]
        }
        
        try:
            resp = self.session.post(
                self.ALGOLIA_URL,
                headers=headers,
                json=payload,
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("results", [{}])[0]
        except Exception as e:
            print(f"  Error searching Algolia: {e}")
            return {}

    def fetch_ai_companies_via_web(self) -> List[Dict[str, Any]]:
        """Fetch AI companies by scraping the directory page."""
        companies = []
        
        # Try fetching the JSON data embedded in the page
        url = f"{self.BASE_URL}?tags=AI"
        
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            
            # Try to extract JSON data from script tags
            html = resp.text
            
            # Look for __NEXT_DATA__ which contains company data
            match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                page_props = data.get("props", {}).get("pageProps", {})
                companies_data = page_props.get("companies", [])
                
                for company in companies_data:
                    companies.append(company)
                    
        except Exception as e:
            print(f"  Error fetching web data: {e}")
        
        return companies

    def fetch_ai_companies_via_api(self) -> List[Dict[str, Any]]:
        """Fetch AI companies using YC's public REST API (most reliable)."""
        all_companies = []
        seen_ids = set()
        
        # YC public API supports tag filtering
        ai_tags = ["AI", "Machine Learning", "Generative AI", "NLP"]
        
        for tag in ai_tags:
            print(f"    API tag: {tag}")
            page = 1
            while page <= 3:  # Max 3 pages per tag
                try:
                    url = f"{self.API_URL}"
                    params = {"tags": tag, "page": page}
                    resp = self.session.get(url, params=params, timeout=30)
                    resp.raise_for_status()
                    data = resp.json()
                    
                    companies = data.get("companies", [])
                    if not companies:
                        break
                    
                    for company in companies:
                        company_id = company.get("id") or company.get("slug")
                        if company_id and company_id not in seen_ids:
                            seen_ids.add(company_id)
                            all_companies.append(company)
                    
                    # Check if there are more pages
                    total_pages = data.get("totalPages", 1)
                    if page >= total_pages:
                        break
                    page += 1
                    time.sleep(0.3)
                    
                except Exception as e:
                    print(f"    Error fetching YC API (tag={tag}, page={page}): {e}")
                    break
        
        return all_companies

    def fetch_ai_companies(self) -> List[Dict[str, Any]]:
        """Fetch AI companies from YC directory."""
        all_companies = []
        
        # Primary: Use YC public REST API (most reliable)
        print("  Searching AI companies via YC API...")
        all_companies = self.fetch_ai_companies_via_api()
        
        if all_companies:
            return all_companies
        
        # Fallback: Try Algolia (may have rotated keys)
        print("  YC API returned nothing, trying Algolia...")
        seen_ids = set()
        
        for keyword in ["artificial intelligence", "machine learning", "AI", "LLM", "generative"]:
            print(f"    Searching: {keyword}")
            result = self.search_algolia(query=keyword)
            
            hits = result.get("hits", [])
            for company in hits:
                company_id = company.get("id") or company.get("objectID")
                if company_id and company_id not in seen_ids:
                    seen_ids.add(company_id)
                    all_companies.append(company)
            
            time.sleep(0.3)
        
        # Also search by industry filter
        for industry in self.AI_INDUSTRIES:
            print(f"    Industry: {industry}")
            result = self.search_algolia(filters=f'industries:"{industry}"')
            
            hits = result.get("hits", [])
            for company in hits:
                company_id = company.get("id") or company.get("objectID")
                if company_id and company_id not in seen_ids:
                    seen_ids.add(company_id)
                    all_companies.append(company)
            
            time.sleep(0.3)
        
        # Last resort: web scraping
        if not all_companies:
            print("  Algolia search failed, trying web scraping...")
            all_companies = self.fetch_ai_companies_via_web()
        
        return all_companies

    def extract_company_data(self, company: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant fields from a company (handles both Algolia and REST API formats)."""
        # REST API uses camelCase (oneLiner), Algolia uses snake_case (one_liner)
        one_liner = company.get("one_liner") or company.get("oneLiner") or ""
        long_desc = company.get("long_description") or company.get("longDescription") or ""
        team_size = company.get("team_size") or company.get("teamSize") or 0
        is_hiring = company.get("isHiring", False)
        
        return {
            "id": company.get("id") or company.get("objectID"),
            "name": company.get("name", ""),
            "slug": company.get("slug", ""),
            "one_liner": one_liner[:200] if one_liner else "",
            "long_description": long_desc[:500] if long_desc else "",
            "website": company.get("website", ""),
            "batch": company.get("batch", ""),
            "status": company.get("status", ""),
            "industries": company.get("industries", []),
            "regions": company.get("regions", []),
            "team_size": team_size,
            "is_hiring": is_hiring,
            "launched_at": company.get("launched_at"),
            "tags": company.get("tags", []),
        }

    def categorize_company(self, company: Dict[str, Any]) -> str:
        """Categorize a company into AI trend buckets."""
        name = (company.get("name") or "").lower()
        one_liner = (company.get("one_liner") or "").lower()
        description = (company.get("long_description") or "").lower()
        industries = [i.lower() for i in company.get("industries", [])]
        combined = f"{name} {one_liner} {description} {' '.join(industries)}"

        # AI Agents / Automation
        if any(x in combined for x in ["agent", "automation", "workflow", "copilot", "assistant"]):
            return "ai-agents"

        # LLM / Foundation models
        if any(x in combined for x in ["llm", "language model", "chatbot", "conversational", "gpt"]):
            return "llm-foundation"

        # Infrastructure
        if any(x in combined for x in ["infrastructure", "mlops", "vector", "database", "deployment"]):
            return "ai-infrastructure"

        # Computer Vision
        if any(x in combined for x in ["vision", "image", "video", "visual", "detection"]):
            return "computer-vision"

        # AI Coding
        if any(x in combined for x in ["code", "developer", "programming", "ide"]):
            return "ai-coding"

        # Healthcare AI
        if any(x in combined for x in ["health", "medical", "clinical", "drug", "biotech"]):
            return "ai-healthcare"

        # Fintech AI
        if any(x in combined for x in ["finance", "fintech", "trading", "banking", "payments"]):
            return "fintech-ai"

        # Generative AI
        if any(x in combined for x in ["generative", "content", "creative", "generate"]):
            return "ai-image-generation"

        return "ai-general"

    def analyze_batch_trends(self, companies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze trends by YC batch."""
        batch_counts = {}
        recent_batches = []
        
        for company in companies:
            batch = company.get("batch", "Unknown")
            if batch:
                batch_counts[batch] = batch_counts.get(batch, 0) + 1
        
        # Sort batches (format: W23, S23, W24, etc.)
        def batch_sort_key(b):
            if b == "Unknown":
                return (0, "")
            try:
                season = b[0]  # W or S
                year = int(b[1:])
                # Convert to comparable number (W24 > S23 > W23)
                return (year * 10 + (5 if season == 'W' else 0), b)
            except:
                return (0, b)
        
        sorted_batches = sorted(batch_counts.items(), key=lambda x: batch_sort_key(x[0]), reverse=True)
        
        return {
            "batch_distribution": dict(sorted_batches[:10]),
            "most_recent_batches": sorted_batches[:5],
            "total_batches": len(batch_counts),
        }

    def compute_signals(self, companies: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Compute trend signals from YC company data."""
        bucket_signals = {}
        status_counts = {"Active": 0, "Acquired": 0, "Inactive": 0, "Public": 0}
        hiring_count = 0

        for company in companies:
            bucket = company.get("bucket", "ai-general")
            status = company.get("status", "Unknown")
            is_hiring = company.get("is_hiring", False)

            if bucket not in bucket_signals:
                bucket_signals[bucket] = {
                    "company_count": 0,
                    "hiring_count": 0,
                    "top_companies": [],
                }

            bucket_signals[bucket]["company_count"] += 1
            if is_hiring:
                bucket_signals[bucket]["hiring_count"] += 1
                hiring_count += 1

            # Track status
            if status in status_counts:
                status_counts[status] += 1
            elif status:
                status_counts["Active"] += 1  # Default to active

            # Top companies
            if len(bucket_signals[bucket]["top_companies"]) < 5:
                bucket_signals[bucket]["top_companies"].append({
                    "name": company.get("name"),
                    "one_liner": company.get("one_liner", "")[:100],
                    "batch": company.get("batch"),
                    "is_hiring": is_hiring,
                })

        # Add interpretations
        total_companies = len(companies)
        for bucket, data in bucket_signals.items():
            if total_companies > 0:
                data["company_share"] = data["company_count"] / total_companies
            else:
                data["company_share"] = 0

            share = data["company_share"]
            if share > 0.2:
                data["signal_interpretation"] = "Dominant category - major YC investment focus"
            elif share > 0.1:
                data["signal_interpretation"] = "Strong category - significant startup activity"
            elif share > 0.05:
                data["signal_interpretation"] = "Growing category - emerging startup interest"
            else:
                data["signal_interpretation"] = "Niche category - specialized startups"

        # Batch analysis
        batch_trends = self.analyze_batch_trends(companies)

        return {
            "bucket_signals": bucket_signals,
            "status_distribution": status_counts,
            "total_hiring": hiring_count,
            "batch_trends": batch_trends,
        }

    def run(self, save: bool = True) -> Dict[str, Any]:
        """Run the scraper and return results."""
        print("Fetching Y Combinator AI companies...")
        
        # Fetch companies
        companies = self.fetch_ai_companies()
        print(f"  Retrieved {len(companies)} AI companies")

        # Process companies
        processed = []
        for company in companies:
            data = self.extract_company_data(company)
            data["bucket"] = self.categorize_company(company)
            processed.append(data)

        # Sort by batch (most recent first)
        def batch_key(c):
            batch = c.get("batch", "")
            if not batch:
                return 0
            try:
                season = batch[0]
                year = int(batch[1:])
                return year * 10 + (5 if season == 'W' else 0)
            except:
                return 0
        
        processed.sort(key=batch_key, reverse=True)

        # Compute signals
        signals = self.compute_signals(processed)

        result = {
            "source": "yc_companies",
            "scraped_at": datetime.now().isoformat(),
            "total_companies": len(processed),
            "companies": processed,
            "signals": signals,
            "bucket_signals": signals.get("bucket_signals", {}),
        }

        if save:
            date_str = datetime.now().strftime("%Y-%m-%d")
            output_file = self.output_dir / f"yc_companies_{date_str}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Saved to {output_file}")

        return result


def main():
    """Main entry point."""
    scraper = YCScraper()
    result = scraper.run()

    print("\n" + "=" * 60)
    print("Y COMBINATOR AI COMPANIES SUMMARY")
    print("=" * 60)
    print(f"Total AI companies: {result['total_companies']}")

    print("\nRecent AI Companies (by batch):")
    print("-" * 60)
    for i, company in enumerate(result['companies'][:15], 1):
        hiring = "🟢 Hiring" if company.get('is_hiring') else ""
        print(f"{i}. {company['name']} ({company['batch']})")
        print(f"   {company['one_liner'][:60]}...")
        print(f"   Bucket: {company['bucket']} {hiring}")
        print()

    print("\nBatch Distribution:")
    for batch, count in result['signals']['batch_trends']['batch_distribution'].items():
        print(f"  {batch}: {count} companies")

    print("\nSignals by Bucket:")
    print("-" * 60)
    for bucket, data in sorted(result['bucket_signals'].items(),
                               key=lambda x: -x[1]['company_count']):
        print(f"{bucket}:")
        print(f"   Companies: {data['company_count']} | Hiring: {data['hiring_count']}")
        print(f"   Share: {data['company_share']*100:.1f}%")
        print(f"   Signal: {data['signal_interpretation']}")
        print()


if __name__ == "__main__":
    main()
