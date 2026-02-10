#!/usr/bin/env python3
"""
Hiring Signals Scraper for briefAI.

Tracks AI company hiring trends via public job board APIs.
Uses Indeed/Adzuna APIs (free tiers available).
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests
from loguru import logger

class HiringSignalsScraper:
    """Scrapes hiring signals from job boards."""
    
    def __init__(self):
        self.output_dir = Path("data/alternative_signals")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Target AI companies
        self.companies = [
            "OpenAI", "Anthropic", "Google DeepMind", "Meta AI",
            "Microsoft AI", "NVIDIA", "AMD", "Intel",
            "Cohere", "Mistral", "Stability AI", "Runway",
            "Scale AI", "Databricks", "Snowflake", "Palantir",
            "Hugging Face", "LangChain", "Pinecone", "Weaviate",
            "Character AI", "Inflection", "xAI", "Perplexity",
            "Cursor", "Replit", "GitHub Copilot", "Tabnine"
        ]
        
        # AI-related job keywords
        self.ai_keywords = [
            "machine learning", "deep learning", "AI engineer",
            "LLM", "large language model", "NLP", "computer vision",
            "ML engineer", "data scientist", "AI research",
            "prompt engineer", "AI safety", "MLOps"
        ]
        
        # Adzuna API (free tier: 250 calls/day)
        self.adzuna_app_id = os.getenv("ADZUNA_APP_ID", "")
        self.adzuna_api_key = os.getenv("ADZUNA_API_KEY", "")
    
    def search_adzuna(self, query: str, country: str = "us") -> Dict:
        """Search Adzuna job API."""
        if not self.adzuna_app_id or not self.adzuna_api_key:
            return {"count": 0, "error": "No Adzuna API keys"}
        
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        params = {
            "app_id": self.adzuna_app_id,
            "app_key": self.adzuna_api_key,
            "what": query,
            "results_per_page": 10,
            "content-type": "application/json"
        }
        
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "count": data.get("count", 0),
                    "mean_salary": data.get("mean", 0),
                    "sample_jobs": [
                        {
                            "title": j.get("title"),
                            "company": j.get("company", {}).get("display_name"),
                            "location": j.get("location", {}).get("display_name"),
                            "salary_min": j.get("salary_min"),
                            "salary_max": j.get("salary_max")
                        }
                        for j in data.get("results", [])[:5]
                    ]
                }
            else:
                return {"count": 0, "error": f"API error: {resp.status_code}"}
        except Exception as e:
            return {"count": 0, "error": str(e)}
    
    def get_company_hiring_signals(self) -> List[Dict]:
        """Get hiring signals for tracked companies."""
        signals = []
        
        for company in self.companies:
            # Search for AI jobs at this company
            query = f'"{company}" AND (AI OR "machine learning")'
            result = self.search_adzuna(query)
            
            if result.get("count", 0) > 0:
                signals.append({
                    "entity": company,
                    "signal_type": "hiring",
                    "job_count": result["count"],
                    "mean_salary": result.get("mean_salary", 0),
                    "sample_jobs": result.get("sample_jobs", []),
                    "timestamp": datetime.now().isoformat()
                })
                logger.info(f"{company}: {result['count']} AI jobs")
        
        return signals
    
    def get_keyword_trends(self) -> List[Dict]:
        """Get hiring trends by AI keyword."""
        trends = []
        
        for keyword in self.ai_keywords:
            result = self.search_adzuna(keyword)
            
            trends.append({
                "keyword": keyword,
                "job_count": result.get("count", 0),
                "mean_salary": result.get("mean_salary", 0),
                "timestamp": datetime.now().isoformat()
            })
            logger.info(f"Keyword '{keyword}': {result.get('count', 0)} jobs")
        
        return trends
    
    def calculate_hiring_score(self, signals: List[Dict]) -> Dict:
        """Calculate hiring momentum scores."""
        scores = {}
        
        for signal in signals:
            entity = signal.get("entity", "")
            job_count = signal.get("job_count", 0)
            
            # Simple score: log scale of job count
            import math
            score = math.log10(job_count + 1) * 2 if job_count > 0 else 0
            score = min(10, max(0, score))  # Clamp to 0-10
            
            scores[entity] = {
                "hiring_score": round(score, 2),
                "job_count": job_count,
                "interpretation": (
                    "aggressive_hiring" if score > 7 else
                    "moderate_hiring" if score > 4 else
                    "low_hiring"
                )
            }
        
        return scores
    
    def run(self) -> Dict:
        """Run the hiring signals scraper."""
        logger.info("Starting Hiring Signals Scraper")
        
        # Get company-specific signals
        company_signals = self.get_company_hiring_signals()
        
        # Get keyword trends
        keyword_trends = self.get_keyword_trends()
        
        # Calculate scores
        hiring_scores = self.calculate_hiring_score(company_signals)
        
        result = {
            "source": "hiring_signals",
            "timestamp": datetime.now().isoformat(),
            "company_signals": company_signals,
            "keyword_trends": keyword_trends,
            "hiring_scores": hiring_scores,
            "summary": {
                "companies_tracked": len(company_signals),
                "total_ai_jobs": sum(s.get("job_count", 0) for s in company_signals),
                "keywords_tracked": len(keyword_trends)
            }
        }
        
        # Save results
        output_file = self.output_dir / f"hiring_signals_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved hiring signals to {output_file}")
        return result


def run() -> Dict:
    """Entry point for run_all_scrapers.py"""
    scraper = HiringSignalsScraper()
    return scraper.run()


if __name__ == "__main__":
    result = run()
    print(json.dumps(result.get("summary", {}), indent=2))
