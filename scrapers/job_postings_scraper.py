# -*- coding: utf-8 -*-
"""
Job Postings Scraper

Scrapes AI job postings from Greenhouse, Lever, and company career pages.
Hiring signals indicate growth and strategic direction.
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import time
import re
from bs4 import BeautifulSoup


@dataclass
class JobSignal:
    """A job posting signal."""
    id: str
    company: str
    title: str
    location: str
    department: str
    url: str
    posted_at: Optional[str]
    ai_relevance: float
    source: str


class JobPostingsScraper:
    """Scraper for AI company job postings."""
    
    # Companies with Greenhouse boards
    GREENHOUSE_COMPANIES = {
        "anthropic": "Anthropic",
        "openai": "OpenAI", 
        "cohere": "Cohere",
        "huggingface": "Hugging Face",
        "scale": "Scale AI",
        "databricks": "Databricks",
        "anyscale": "Anyscale",
        "weights-and-biases": "Weights & Biases",
        "deepmind": "DeepMind",
        "stability": "Stability AI",
        "midjourney": "Midjourney",
        "runway": "Runway",
        "adept": "Adept",
        "inflection": "Inflection AI",
        "characterai": "Character.AI",
        "perplexityai": "Perplexity",
        "mistral": "Mistral AI",
    }
    
    # Companies with Lever boards
    LEVER_COMPANIES = {
        "figma": "Figma",
        "notion": "Notion",
        "linear": "Linear",
        "vercel": "Vercel",
        "supabase": "Supabase",
        "replit": "Replit",
    }
    
    # AI-related job keywords
    AI_KEYWORDS = [
        "machine learning", "ml engineer", "deep learning",
        "ai research", "nlp", "natural language",
        "computer vision", "data scientist",
        "llm", "language model", "generative ai",
        "research scientist", "research engineer",
        "applied scientist", "ml ops", "mlops",
        "ai safety", "alignment", "interpretability",
    ]
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "job_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_greenhouse_jobs(self, board_token: str, company_name: str) -> List[Dict[str, Any]]:
        """Fetch jobs from Greenhouse board."""
        try:
            url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
            resp = requests.get(url, timeout=15)
            
            if resp.status_code != 200:
                return []
            
            data = resp.json()
            jobs = data.get("jobs", [])
            
            ai_jobs = []
            for job in jobs:
                title = job.get("title", "").lower()
                
                # Check AI relevance
                relevance = 0
                for kw in self.AI_KEYWORDS:
                    if kw in title:
                        relevance += 1
                
                # Include all jobs but mark AI relevance
                ai_jobs.append({
                    "id": f"gh_{board_token}_{job.get('id')}",
                    "company": company_name,
                    "title": job.get("title"),
                    "location": job.get("location", {}).get("name", "Remote"),
                    "department": ", ".join([d.get("name", "") for d in job.get("departments", [])]),
                    "url": job.get("absolute_url"),
                    "posted_at": job.get("updated_at"),
                    "ai_relevance": min(relevance / 2, 1.0),
                    "source": "greenhouse",
                })
            
            return ai_jobs
            
        except Exception as e:
            print(f"    Error fetching {company_name}: {e}")
            return []
    
    def fetch_lever_jobs(self, company_slug: str, company_name: str) -> List[Dict[str, Any]]:
        """Fetch jobs from Lever board."""
        try:
            url = f"https://api.lever.co/v0/postings/{company_slug}"
            resp = requests.get(url, timeout=15)
            
            if resp.status_code != 200:
                return []
            
            jobs = resp.json()
            
            ai_jobs = []
            for job in jobs:
                title = job.get("text", "").lower()
                
                relevance = 0
                for kw in self.AI_KEYWORDS:
                    if kw in title:
                        relevance += 1
                
                ai_jobs.append({
                    "id": f"lv_{company_slug}_{job.get('id')}",
                    "company": company_name,
                    "title": job.get("text"),
                    "location": job.get("categories", {}).get("location", "Remote"),
                    "department": job.get("categories", {}).get("team", ""),
                    "url": job.get("hostedUrl"),
                    "posted_at": None,
                    "ai_relevance": min(relevance / 2, 1.0),
                    "source": "lever",
                })
            
            return ai_jobs
            
        except Exception as e:
            print(f"    Error fetching {company_name}: {e}")
            return []
    
    def run(self) -> Dict[str, Any]:
        """Run job postings scraper."""
        print("=" * 60)
        print("JOB POSTINGS SCRAPER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "jobs": [],
            "summary": {},
        }
        
        # Greenhouse boards
        print("\nFetching from Greenhouse...")
        for slug, name in self.GREENHOUSE_COMPANIES.items():
            print(f"  {name}...")
            jobs = self.fetch_greenhouse_jobs(slug, name)
            if jobs:
                print(f"    {len(jobs)} jobs ({sum(1 for j in jobs if j['ai_relevance'] > 0)} AI-related)")
                results["jobs"].extend(jobs)
            time.sleep(0.3)
        
        # Lever boards
        print("\nFetching from Lever...")
        for slug, name in self.LEVER_COMPANIES.items():
            print(f"  {name}...")
            jobs = self.fetch_lever_jobs(slug, name)
            if jobs:
                print(f"    {len(jobs)} jobs")
                results["jobs"].extend(jobs)
            time.sleep(0.3)
        
        # Summary by company
        company_counts = {}
        ai_job_count = 0
        for job in results["jobs"]:
            company_counts[job["company"]] = company_counts.get(job["company"], 0) + 1
            if job["ai_relevance"] > 0:
                ai_job_count += 1
        
        results["summary"] = {
            "total_jobs": len(results["jobs"]),
            "ai_related_jobs": ai_job_count,
            "companies": len(company_counts),
            "by_company": dict(sorted(company_counts.items(), key=lambda x: -x[1])),
        }
        
        # Save
        output_file = self.output_dir / f"jobs_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Summary
        print(f"\n{'=' * 60}")
        print(f"SUMMARY")
        print(f"{'=' * 60}")
        print(f"Total jobs: {results['summary']['total_jobs']}")
        print(f"AI-related: {results['summary']['ai_related_jobs']}")
        print(f"\nTop hiring:")
        for company, count in list(results["summary"]["by_company"].items())[:10]:
            print(f"  {company}: {count} jobs")
        
        return results


if __name__ == "__main__":
    scraper = JobPostingsScraper()
    scraper.run()
