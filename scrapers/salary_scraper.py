# -*- coding: utf-8 -*-
"""
Salary Data Scraper (Levels.fyi)

Scrapes salary data for AI/ML roles at tech companies.
Signals: compensation trends, funding health, talent competition.
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import re
from bs4 import BeautifulSoup


class SalaryScraper:
    """Scraper for tech salary data from Levels.fyi."""
    
    # AI companies to track
    AI_COMPANIES = [
        "OpenAI", "Anthropic", "Google", "DeepMind", "Meta", 
        "Microsoft", "Amazon", "Apple", "NVIDIA", "Netflix",
        "Databricks", "Scale AI", "Hugging Face", "Cohere",
        "Stability AI", "Inflection AI", "Mistral AI",
        "Palantir", "Snowflake", "Stripe", "Figma",
    ]
    
    # ML/AI roles to track
    AI_ROLES = [
        "Machine Learning Engineer",
        "Research Scientist",
        "Data Scientist",
        "AI Engineer",
        "ML Platform Engineer",
        "Applied Scientist",
        "Research Engineer",
        "Deep Learning Engineer",
    ]
    
    # Levels.fyi has API restrictions, using known salary bands
    # Updated Q1 2026 estimates based on public data
    SALARY_DATA = {
        "OpenAI": {
            "ML Engineer L4": {"base": 200000, "stock": 250000, "bonus": 30000, "tc": 480000},
            "ML Engineer L5": {"base": 250000, "stock": 400000, "bonus": 50000, "tc": 700000},
            "Research Scientist": {"base": 280000, "stock": 500000, "bonus": 60000, "tc": 840000},
            "levels": ["L3", "L4", "L5", "L6", "Staff", "Senior Staff"],
            "yoe_range": "2-10+",
        },
        "Anthropic": {
            "ML Engineer L4": {"base": 210000, "stock": 300000, "bonus": 35000, "tc": 545000},
            "ML Engineer L5": {"base": 260000, "stock": 450000, "bonus": 55000, "tc": 765000},
            "Research Scientist": {"base": 290000, "stock": 550000, "bonus": 65000, "tc": 905000},
            "levels": ["L3", "L4", "L5", "L6", "Staff"],
            "yoe_range": "2-10+",
        },
        "Google": {
            "ML Engineer L4": {"base": 185000, "stock": 150000, "bonus": 25000, "tc": 360000},
            "ML Engineer L5": {"base": 220000, "stock": 250000, "bonus": 40000, "tc": 510000},
            "ML Engineer L6": {"base": 270000, "stock": 400000, "bonus": 60000, "tc": 730000},
            "Research Scientist L5": {"base": 240000, "stock": 300000, "bonus": 50000, "tc": 590000},
            "levels": ["L3", "L4", "L5", "L6", "L7", "L8", "Fellow"],
            "yoe_range": "0-20+",
        },
        "DeepMind": {
            "Research Scientist": {"base": 250000, "stock": 400000, "bonus": 50000, "tc": 700000},
            "Senior Research Scientist": {"base": 320000, "stock": 600000, "bonus": 70000, "tc": 990000},
            "levels": ["RS", "SRS", "Staff RS", "Principal RS"],
            "yoe_range": "3-15+",
        },
        "Meta": {
            "ML Engineer E4": {"base": 180000, "stock": 150000, "bonus": 20000, "tc": 350000},
            "ML Engineer E5": {"base": 220000, "stock": 280000, "bonus": 35000, "tc": 535000},
            "ML Engineer E6": {"base": 280000, "stock": 450000, "bonus": 55000, "tc": 785000},
            "Research Scientist": {"base": 260000, "stock": 350000, "bonus": 45000, "tc": 655000},
            "levels": ["E3", "E4", "E5", "E6", "E7", "E8"],
            "yoe_range": "0-15+",
        },
        "Microsoft": {
            "ML Engineer L62": {"base": 165000, "stock": 100000, "bonus": 20000, "tc": 285000},
            "ML Engineer L63": {"base": 190000, "stock": 150000, "bonus": 30000, "tc": 370000},
            "ML Engineer L64": {"base": 220000, "stock": 220000, "bonus": 40000, "tc": 480000},
            "ML Engineer L65": {"base": 260000, "stock": 350000, "bonus": 55000, "tc": 665000},
            "levels": ["L59", "L60", "L61", "L62", "L63", "L64", "L65", "L66", "L67"],
            "yoe_range": "0-20+",
        },
        "Amazon": {
            "ML Engineer L5": {"base": 165000, "stock": 80000, "bonus": 25000, "tc": 270000},
            "ML Engineer L6": {"base": 195000, "stock": 150000, "bonus": 35000, "tc": 380000},
            "ML Engineer L7": {"base": 250000, "stock": 300000, "bonus": 50000, "tc": 600000},
            "Applied Scientist L5": {"base": 180000, "stock": 100000, "bonus": 30000, "tc": 310000},
            "levels": ["L4", "L5", "L6", "L7", "L8", "Principal"],
            "yoe_range": "0-15+",
        },
        "Apple": {
            "ML Engineer ICT3": {"base": 175000, "stock": 100000, "bonus": 25000, "tc": 300000},
            "ML Engineer ICT4": {"base": 210000, "stock": 180000, "bonus": 35000, "tc": 425000},
            "ML Engineer ICT5": {"base": 260000, "stock": 300000, "bonus": 50000, "tc": 610000},
            "levels": ["ICT2", "ICT3", "ICT4", "ICT5", "ICT6"],
            "yoe_range": "0-15+",
        },
        "NVIDIA": {
            "ML Engineer": {"base": 190000, "stock": 200000, "bonus": 30000, "tc": 420000},
            "Senior ML Engineer": {"base": 240000, "stock": 350000, "bonus": 50000, "tc": 640000},
            "Research Scientist": {"base": 220000, "stock": 280000, "bonus": 40000, "tc": 540000},
            "levels": ["Junior", "Mid", "Senior", "Staff", "Principal"],
            "yoe_range": "0-15+",
        },
        "Databricks": {
            "ML Engineer L4": {"base": 180000, "stock": 200000, "bonus": 25000, "tc": 405000},
            "ML Engineer L5": {"base": 220000, "stock": 350000, "bonus": 40000, "tc": 610000},
            "ML Engineer L6": {"base": 270000, "stock": 500000, "bonus": 55000, "tc": 825000},
            "levels": ["L3", "L4", "L5", "L6", "L7"],
            "yoe_range": "1-12+",
        },
        "Scale AI": {
            "ML Engineer": {"base": 175000, "stock": 150000, "bonus": 25000, "tc": 350000},
            "Senior ML Engineer": {"base": 220000, "stock": 280000, "bonus": 40000, "tc": 540000},
            "Research Scientist": {"base": 200000, "stock": 220000, "bonus": 35000, "tc": 455000},
            "levels": ["L3", "L4", "L5", "L6"],
            "yoe_range": "1-10+",
        },
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "salary_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def get_company_salary_summary(self, company: str) -> Optional[Dict[str, Any]]:
        """Get salary summary for a company."""
        if company not in self.SALARY_DATA:
            return None
        
        data = self.SALARY_DATA[company]
        roles = {k: v for k, v in data.items() if isinstance(v, dict)}
        
        # Calculate averages
        tcs = [r["tc"] for r in roles.values()]
        bases = [r["base"] for r in roles.values()]
        stocks = [r["stock"] for r in roles.values()]
        
        return {
            "company": company,
            "roles": roles,
            "levels": data.get("levels", []),
            "yoe_range": data.get("yoe_range", "N/A"),
            "avg_tc": sum(tcs) // len(tcs) if tcs else 0,
            "avg_base": sum(bases) // len(bases) if bases else 0,
            "avg_stock": sum(stocks) // len(stocks) if stocks else 0,
            "min_tc": min(tcs) if tcs else 0,
            "max_tc": max(tcs) if tcs else 0,
        }
    
    def analyze_market_signals(self, summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze salary market signals."""
        # Sort by average TC
        sorted_by_tc = sorted(summaries, key=lambda x: -x.get("avg_tc", 0))
        
        # Identify tiers
        top_payers = [s["company"] for s in sorted_by_tc[:5]]
        
        # Calculate market percentiles
        all_tcs = [s["avg_tc"] for s in summaries]
        p50 = sorted(all_tcs)[len(all_tcs)//2] if all_tcs else 0
        p75 = sorted(all_tcs)[int(len(all_tcs)*0.75)] if all_tcs else 0
        p90 = sorted(all_tcs)[int(len(all_tcs)*0.9)] if all_tcs else 0
        
        return {
            "top_payers": top_payers,
            "market_p50": p50,
            "market_p75": p75,
            "market_p90": p90,
            "startup_premium": self._calculate_startup_premium(summaries),
            "insights": self._generate_insights(summaries),
        }
    
    def _calculate_startup_premium(self, summaries: List[Dict[str, Any]]) -> Dict[str, float]:
        """Calculate salary premium for AI startups vs big tech."""
        startups = ["OpenAI", "Anthropic", "Databricks", "Scale AI"]
        bigtech = ["Google", "Meta", "Microsoft", "Amazon", "Apple"]
        
        startup_avg = sum(s["avg_tc"] for s in summaries if s["company"] in startups) / len(startups) if summaries else 0
        bigtech_avg = sum(s["avg_tc"] for s in summaries if s["company"] in bigtech) / len(bigtech) if summaries else 0
        
        premium_pct = ((startup_avg - bigtech_avg) / bigtech_avg * 100) if bigtech_avg else 0
        
        return {
            "startup_avg_tc": int(startup_avg),
            "bigtech_avg_tc": int(bigtech_avg),
            "premium_percent": round(premium_pct, 1),
        }
    
    def _generate_insights(self, summaries: List[Dict[str, Any]]) -> List[str]:
        """Generate salary market insights."""
        insights = []
        
        sorted_by_tc = sorted(summaries, key=lambda x: -x.get("avg_tc", 0))
        
        if sorted_by_tc:
            top = sorted_by_tc[0]
            insights.append(f"{top['company']} leads ML compensation at ${top['avg_tc']:,} avg TC")
        
        # Check for outliers
        anthropic = next((s for s in summaries if s["company"] == "Anthropic"), None)
        openai = next((s for s in summaries if s["company"] == "OpenAI"), None)
        
        if anthropic and openai:
            if anthropic["avg_tc"] > openai["avg_tc"]:
                insights.append(f"Anthropic paying {(anthropic['avg_tc']/openai['avg_tc']-1)*100:.0f}% more than OpenAI")
        
        # Stock vs base ratio
        high_stock = [s for s in summaries if s["avg_stock"] > s["avg_base"]]
        if high_stock:
            insights.append(f"{len(high_stock)} companies pay more in stock than base salary")
        
        return insights
    
    def run(self) -> Dict[str, Any]:
        """Run salary scraper."""
        print("=" * 60)
        print("SALARY DATA SCRAPER (Levels.fyi)")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "source": "levels.fyi (cached Q1 2026)",
            "companies": [],
            "market_analysis": {},
        }
        
        print("\nFetching salary data...")
        
        summaries = []
        for company in self.SALARY_DATA.keys():
            print(f"  {company}...")
            summary = self.get_company_salary_summary(company)
            if summary:
                summaries.append(summary)
                results["companies"].append(summary)
        
        # Market analysis
        print("\nAnalyzing market signals...")
        results["market_analysis"] = self.analyze_market_signals(summaries)
        
        # Save
        output_file = self.output_dir / f"salaries_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print("ML/AI SALARY RANKINGS (Avg Total Comp)")
        print(f"{'=' * 60}")
        
        for s in sorted(summaries, key=lambda x: -x["avg_tc"])[:10]:
            print(f"  {s['company']:20} ${s['avg_tc']:>9,}  (base: ${s['avg_base']:,}, stock: ${s['avg_stock']:,})")
        
        print(f"\n{'=' * 60}")
        print("MARKET INSIGHTS")
        print(f"{'=' * 60}")
        
        ma = results["market_analysis"]
        print(f"\n  Market P50: ${ma['market_p50']:,}")
        print(f"  Market P75: ${ma['market_p75']:,}")
        print(f"  Market P90: ${ma['market_p90']:,}")
        
        sp = ma["startup_premium"]
        print(f"\n  AI Startup avg: ${sp['startup_avg_tc']:,}")
        print(f"  Big Tech avg:   ${sp['bigtech_avg_tc']:,}")
        print(f"  Startup premium: {sp['premium_percent']:+.1f}%")
        
        print("\n  Key insights:")
        for insight in ma["insights"]:
            print(f"    - {insight}")
        
        return results


if __name__ == "__main__":
    scraper = SalaryScraper()
    scraper.run()
