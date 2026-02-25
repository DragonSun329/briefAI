# -*- coding: utf-8 -*-
"""
AI Verticals Scraper

Comprehensive scraper for AI+X verticals: funding, news, companies, trends.
Feeds into Gartner Hype Cycle and Trend Radar.
"""

import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import time
import feedparser


class AIVerticalsScraper:
    """Master scraper for all AI vertical industries."""
    
    # AI Verticals Taxonomy
    VERTICALS = {
        # Healthcare & Life Sciences
        "ai_healthcare": {
            "name": "AI + Healthcare",
            "description": "Medical AI, diagnostics, clinical decision support",
            "keywords": ["medical ai", "healthcare ai", "clinical ai", "diagnostics ai", "radiology ai"],
            "rss_feeds": ["https://www.fiercehealthcare.com/rss/xml"],
            "companies": ["Tempus", "PathAI", "Viz.ai", "Paige", "Rad AI", "Abridge"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.7,
        },
        "ai_drug_discovery": {
            "name": "AI + Drug Discovery",
            "description": "AI for pharma R&D, molecule design, clinical trials",
            "keywords": ["drug discovery ai", "pharma ai", "molecule ai", "alphafold", "protein folding"],
            "rss_feeds": [],
            "companies": ["Isomorphic Labs", "Recursion", "Insilico Medicine", "Generate Bio", "Exscientia"],
            "hype_phase": "peak_expectations",
            "maturity": 0.4,
        },
        
        # Finance
        "ai_fintech": {
            "name": "AI + Fintech",
            "description": "AI lending, credit risk, fraud detection, trading",
            "keywords": ["fintech ai", "credit ai", "lending ai", "fraud detection ai", "trading ai"],
            "rss_feeds": ["https://www.finextra.com/rss/headlines.aspx"],
            "companies": ["Upstart", "Zest AI", "Socure", "Alloy", "Ramp", "Brex"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.65,
        },
        "ai_trading": {
            "name": "AI + Trading/Quant",
            "description": "Algorithmic trading, market prediction, quant strategies",
            "keywords": ["algorithmic trading", "quant ai", "market prediction", "trading bot"],
            "rss_feeds": [],
            "companies": ["Two Sigma", "Citadel", "DE Shaw", "Renaissance", "Jane Street"],
            "hype_phase": "plateau_productivity",
            "maturity": 0.85,
        },
        
        # Education
        "ai_education": {
            "name": "AI + Education",
            "description": "Personalized learning, AI tutoring, edtech",
            "keywords": ["edtech ai", "tutoring ai", "personalized learning", "educational ai"],
            "rss_feeds": ["https://www.edsurge.com/feeds/articles"],
            "companies": ["Khanmigo", "Duolingo", "Synthesis", "Speak", "Quizlet"],
            "hype_phase": "peak_expectations",
            "maturity": 0.35,
        },
        
        # Legal
        "ai_legal": {
            "name": "AI + Legal",
            "description": "Legal research, contract analysis, compliance",
            "keywords": ["legal ai", "legaltech", "contract ai", "compliance ai", "e-discovery"],
            "rss_feeds": [],
            "companies": ["Harvey", "Casetext", "Spellbook", "EvenUp", "Ironclad"],
            "hype_phase": "validating",
            "maturity": 0.45,
        },
        
        # Creative
        "ai_creative": {
            "name": "AI + Creative/Media",
            "description": "Image/video generation, music, content creation",
            "keywords": ["generative ai", "ai art", "ai video", "ai music", "content generation"],
            "rss_feeds": [],
            "companies": ["Runway", "Pika", "Suno", "Udio", "ElevenLabs", "Midjourney"],
            "hype_phase": "peak_expectations",
            "maturity": 0.4,
        },
        
        # Robotics & Manufacturing
        "ai_robotics": {
            "name": "AI + Robotics",
            "description": "Humanoid robots, industrial automation, embodied AI",
            "keywords": ["robotics ai", "humanoid", "embodied ai", "industrial robot"],
            "rss_feeds": ["https://www.therobotreport.com/feed/"],
            "companies": ["Figure", "1X", "Covariant", "Boston Dynamics", "Physical Intelligence"],
            "hype_phase": "innovation_trigger",
            "maturity": 0.25,
        },
        "ai_manufacturing": {
            "name": "AI + Manufacturing",
            "description": "Smart factories, quality control, predictive maintenance",
            "keywords": ["manufacturing ai", "factory ai", "quality control ai", "predictive maintenance"],
            "rss_feeds": [],
            "companies": ["Bright Machines", "Machina Labs", "Landing AI", "Instrumental"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.55,
        },
        
        # Transportation
        "ai_autonomous_vehicles": {
            "name": "AI + Autonomous Vehicles",
            "description": "Self-driving cars, robotaxis, autonomous trucking",
            "keywords": ["autonomous vehicle", "self-driving", "robotaxi", "autonomous trucking"],
            "rss_feeds": [],
            "companies": ["Waymo", "Cruise", "Tesla", "Aurora", "Nuro", "Zoox"],
            "hype_phase": "trough_disillusionment",
            "maturity": 0.5,
        },
        
        # Agriculture
        "ai_agriculture": {
            "name": "AI + Agriculture",
            "description": "Precision farming, crop monitoring, autonomous tractors",
            "keywords": ["agtech ai", "precision agriculture", "crop ai", "farming ai"],
            "rss_feeds": [],
            "companies": ["John Deere", "Prospera", "Taranis", "Aigen", "Bowery"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.5,
        },
        
        # Real Estate
        "ai_real_estate": {
            "name": "AI + Real Estate",
            "description": "Property valuation, iBuying, property management",
            "keywords": ["proptech ai", "real estate ai", "property valuation", "ibuying"],
            "rss_feeds": [],
            "companies": ["Zillow", "Opendoor", "Redfin", "Cherre", "Entera"],
            "hype_phase": "trough_disillusionment",
            "maturity": 0.45,
        },
        
        # Insurance
        "ai_insurance": {
            "name": "AI + Insurance",
            "description": "Underwriting, claims processing, fraud detection",
            "keywords": ["insurtech ai", "insurance ai", "claims ai", "underwriting ai"],
            "rss_feeds": [],
            "companies": ["Lemonade", "Tractable", "Shift Technology", "Coalition", "Cape Analytics"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.55,
        },
        
        # Cybersecurity
        "ai_cybersecurity": {
            "name": "AI + Cybersecurity",
            "description": "Threat detection, security automation, vulnerability scanning",
            "keywords": ["cybersecurity ai", "threat detection", "security ai", "soc ai"],
            "rss_feeds": ["https://www.darkreading.com/rss_simple.asp"],
            "companies": ["CrowdStrike", "SentinelOne", "Darktrace", "Abnormal", "Snyk"],
            "hype_phase": "establishing",
            "maturity": 0.7,
        },
        
        # HR & Recruiting
        "ai_hr": {
            "name": "AI + HR/Recruiting",
            "description": "Talent acquisition, employee experience, workforce planning",
            "keywords": ["hr ai", "recruiting ai", "talent ai", "workforce ai"],
            "rss_feeds": [],
            "companies": ["Eightfold", "Phenom", "Beamery", "Lattice", "HireVue"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.55,
        },
        
        # Sales & Marketing
        "ai_sales": {
            "name": "AI + Sales",
            "description": "Revenue intelligence, AI SDRs, conversation analytics",
            "keywords": ["sales ai", "revenue ai", "sdr ai", "conversation intelligence"],
            "rss_feeds": [],
            "companies": ["Gong", "Clari", "Outreach", "11x", "Apollo"],
            "hype_phase": "establishing",
            "maturity": 0.6,
        },
        "ai_marketing": {
            "name": "AI + Marketing",
            "description": "Personalization, content generation, ad optimization",
            "keywords": ["marketing ai", "personalization ai", "ad optimization", "content ai"],
            "rss_feeds": [],
            "companies": ["Jasper", "Copy.ai", "Persado", "Albert", "Mutiny"],
            "hype_phase": "peak_expectations",
            "maturity": 0.45,
        },
        
        # Customer Service
        "ai_customer_service": {
            "name": "AI + Customer Service",
            "description": "AI chatbots, support automation, ticket resolution",
            "keywords": ["customer service ai", "chatbot", "support ai", "ticket ai"],
            "rss_feeds": [],
            "companies": ["Intercom", "Ada", "Forethought", "Sierra", "Decagon"],
            "hype_phase": "establishing",
            "maturity": 0.65,
        },
        
        # Supply Chain
        "ai_supply_chain": {
            "name": "AI + Supply Chain",
            "description": "Demand forecasting, logistics optimization, visibility",
            "keywords": ["supply chain ai", "logistics ai", "demand forecasting", "inventory ai"],
            "rss_feeds": [],
            "companies": ["Flexport", "Project44", "FourKites", "o9", "Altana"],
            "hype_phase": "slope_enlightenment",
            "maturity": 0.55,
        },
        
        # Construction
        "ai_construction": {
            "name": "AI + Construction",
            "description": "Site monitoring, safety, autonomous equipment",
            "keywords": ["construction ai", "site monitoring", "construction robot"],
            "rss_feeds": [],
            "companies": ["Procore", "Built Robotics", "Dusty Robotics", "OpenSpace", "ICON"],
            "hype_phase": "innovation_trigger",
            "maturity": 0.3,
        },
        
        # Gaming
        "ai_gaming": {
            "name": "AI + Gaming",
            "description": "AI NPCs, procedural generation, game testing",
            "keywords": ["game ai", "npc ai", "procedural generation", "game testing ai"],
            "rss_feeds": [],
            "companies": ["Inworld AI", "Convai", "Scenario", "modl.ai"],
            "hype_phase": "innovation_trigger",
            "maturity": 0.25,
        },
        
        # Climate & Energy
        "ai_climate": {
            "name": "AI + Climate/Energy",
            "description": "Carbon tracking, energy optimization, weather prediction",
            "keywords": ["climate ai", "energy ai", "carbon ai", "weather ai", "sustainability ai"],
            "rss_feeds": [],
            "companies": ["ClimateAI", "Pachama", "Tomorrow.io", "Kayrros"],
            "hype_phase": "validating",
            "maturity": 0.35,
        },
        
        # Science & Research
        "ai_science": {
            "name": "AI + Scientific Discovery",
            "description": "Materials science, physics simulation, research acceleration",
            "keywords": ["scientific ai", "materials ai", "research ai", "simulation ai"],
            "rss_feeds": [],
            "companies": ["DeepMind", "Microsoft Research", "Google Research"],
            "hype_phase": "validating",
            "maturity": 0.4,
        },
        
        # Government & Defense
        "ai_defense": {
            "name": "AI + Defense/Gov",
            "description": "Defense AI, government automation, public sector",
            "keywords": ["defense ai", "military ai", "government ai", "public sector ai"],
            "rss_feeds": [],
            "companies": ["Anduril", "Palantir", "Shield AI", "Scale AI Gov"],
            "hype_phase": "establishing",
            "maturity": 0.55,
        },
        
        # Retail & Commerce
        "ai_retail": {
            "name": "AI + Retail",
            "description": "Checkout-free, inventory management, personalization",
            "keywords": ["retail ai", "commerce ai", "checkout ai", "inventory ai"],
            "rss_feeds": [],
            "companies": ["Amazon", "Standard AI", "Grabango", "Vue.ai"],
            "hype_phase": "trough_disillusionment",
            "maturity": 0.5,
        },
        
        # Space
        "ai_space": {
            "name": "AI + Space",
            "description": "Satellite imagery, space traffic, Earth observation",
            "keywords": ["space ai", "satellite ai", "earth observation", "space tech"],
            "rss_feeds": [],
            "companies": ["Planet Labs", "Spire", "Orbital Sidekick", "SpaceX"],
            "hype_phase": "validating",
            "maturity": 0.35,
        },
    }
    
    # Hype cycle phase definitions
    HYPE_PHASES = {
        "innovation_trigger": {"name": "Innovation Trigger", "x_position": 10, "maturity_range": (0, 0.2)},
        "peak_expectations": {"name": "Peak of Inflated Expectations", "x_position": 30, "maturity_range": (0.2, 0.4)},
        "trough_disillusionment": {"name": "Trough of Disillusionment", "x_position": 50, "maturity_range": (0.4, 0.55)},
        "slope_enlightenment": {"name": "Slope of Enlightenment", "x_position": 70, "maturity_range": (0.55, 0.8)},
        "plateau_productivity": {"name": "Plateau of Productivity", "x_position": 90, "maturity_range": (0.8, 1.0)},
        "validating": {"name": "Validating", "x_position": 40, "maturity_range": (0.3, 0.5)},
        "establishing": {"name": "Establishing", "x_position": 65, "maturity_range": (0.5, 0.7)},
    }
    
    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "vertical_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def fetch_rss_news(self, vertical_id: str) -> List[Dict[str, Any]]:
        """Fetch news from RSS feeds for a vertical."""
        vertical = self.VERTICALS.get(vertical_id, {})
        feeds = vertical.get("rss_feeds", [])
        keywords = vertical.get("keywords", [])
        
        all_news = []
        for feed_url in feeds:
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:10]:
                    title = entry.get("title", "").lower()
                    summary = entry.get("summary", "").lower()
                    text = f"{title} {summary}"
                    
                    # Check keyword relevance
                    relevance = sum(1 for kw in keywords if kw.lower() in text)
                    
                    if relevance > 0:
                        all_news.append({
                            "title": entry.get("title", ""),
                            "url": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "source": feed_url,
                            "vertical": vertical_id,
                            "relevance": relevance,
                        })
                time.sleep(0.3)
            except Exception as e:
                pass
        
        return all_news
    
    def calculate_vertical_score(self, vertical_id: str) -> Dict[str, Any]:
        """Calculate momentum score for a vertical."""
        vertical = self.VERTICALS[vertical_id]
        
        # Base scores from maturity and phase
        maturity = vertical.get("maturity", 0.5)
        phase = vertical.get("hype_phase", "validating")
        
        # Calculate scores
        tech_momentum = maturity * 100
        hype_score = {
            "innovation_trigger": 40,
            "peak_expectations": 95,
            "trough_disillusionment": 30,
            "slope_enlightenment": 70,
            "plateau_productivity": 50,
            "validating": 55,
            "establishing": 45,
        }.get(phase, 50)
        
        # Investment attractiveness: combines tech maturity with contrarian hype positioning
        # Best score = high maturity + moderate hype (not over-hyped, not ignored)
        hype_penalty = (abs(hype_score - 50) / 50)  # 0-1, penalty for extreme hype or no hype
        investment_score = tech_momentum * (1 - 0.5 * hype_penalty)  # Maturity-weighted, hype-adjusted
        
        return {
            "vertical_id": vertical_id,
            "name": vertical["name"],
            "maturity": maturity,
            "hype_phase": phase,
            "tech_momentum_score": round(tech_momentum, 1),
            "hype_score": hype_score,
            "investment_score": round(investment_score, 1),
            "companies": vertical.get("companies", []),
        }
    
    def generate_hype_cycle_data(self) -> List[Dict[str, Any]]:
        """Generate data for Gartner Hype Cycle visualization."""
        hype_data = []
        
        for v_id, vertical in self.VERTICALS.items():
            phase = vertical.get("hype_phase", "validating")
            phase_info = self.HYPE_PHASES.get(phase, self.HYPE_PHASES["validating"])
            
            # Calculate Y position on hype curve
            x = phase_info["x_position"]
            # Hype curve formula
            y = (
                30 +
                60 * (2.718 ** (-((x - 30) ** 2) / 200)) -
                20 * (2.718 ** (-((x - 50) ** 2) / 100)) +
                30 * (1 / (1 + 2.718 ** (-(x - 70) / 10)))
            )
            
            hype_data.append({
                "id": v_id,
                "name": vertical["name"],
                "x": x + (hash(v_id) % 10 - 5),  # Slight jitter
                "y": y + (hash(v_id) % 6 - 3),
                "phase": phase,
                "phase_name": phase_info["name"],
                "maturity": vertical.get("maturity", 0.5),
                "companies": vertical.get("companies", [])[:5],
            })
        
        return hype_data
    
    def generate_radar_quadrant_data(self) -> List[Dict[str, Any]]:
        """Generate data for quadrant radar visualization."""
        quadrant_data = []
        
        for v_id, vertical in self.VERTICALS.items():
            score = self.calculate_vertical_score(v_id)
            
            quadrant_data.append({
                "id": v_id,
                "name": vertical["name"],
                "x": score["tech_momentum_score"],  # X = Technical maturity
                "y": score["hype_score"],  # Y = Hype/Capital interest
                "size": len(vertical.get("companies", [])) * 3,
                "phase": vertical.get("hype_phase"),
                "quadrant": self._determine_quadrant(
                    score["tech_momentum_score"], 
                    score["hype_score"]
                ),
            })
        
        return quadrant_data
    
    def _determine_quadrant(self, tech: float, hype: float) -> str:
        """Determine which quadrant a vertical belongs to."""
        if tech >= 50 and hype >= 50:
            return "hot"  # High tech, high hype - competitive
        elif tech >= 50 and hype < 50:
            return "mature"  # High tech, low hype - stable
        elif tech < 50 and hype >= 50:
            return "hyped"  # Low tech, high hype - risky
        else:
            return "emerging"  # Low tech, low hype - early
    
    def run(self) -> Dict[str, Any]:
        """Run full vertical analysis."""
        print("=" * 60)
        print("AI VERTICALS ANALYZER")
        print("=" * 60)
        
        results = {
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "verticals": {},
            "hype_cycle": [],
            "quadrant_data": [],
            "news": [],
            "summary": {},
        }
        
        # Analyze each vertical
        print("\nAnalyzing verticals...")
        for v_id in self.VERTICALS:
            print(f"  {self.VERTICALS[v_id]['name']}...")
            
            # Calculate scores
            score = self.calculate_vertical_score(v_id)
            results["verticals"][v_id] = score
            
            # Fetch news if RSS available
            news = self.fetch_rss_news(v_id)
            results["news"].extend(news)
        
        # Generate visualizations
        print("\nGenerating visualizations...")
        results["hype_cycle"] = self.generate_hype_cycle_data()
        results["quadrant_data"] = self.generate_radar_quadrant_data()
        
        # Summary by phase
        phase_counts = {}
        for v in results["hype_cycle"]:
            phase = v["phase_name"]
            phase_counts[phase] = phase_counts.get(phase, 0) + 1
        results["summary"]["by_phase"] = phase_counts
        
        # Summary by quadrant
        quadrant_counts = {}
        for v in results["quadrant_data"]:
            q = v["quadrant"]
            quadrant_counts[q] = quadrant_counts.get(q, 0) + 1
        results["summary"]["by_quadrant"] = quadrant_counts
        
        # Save
        output_file = self.output_dir / f"verticals_{datetime.now().strftime('%Y-%m-%d')}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nSaved to {output_file}")
        
        # Print summary
        print(f"\n{'=' * 60}")
        print("HYPE CYCLE DISTRIBUTION")
        print(f"{'=' * 60}")
        for phase, count in sorted(phase_counts.items(), key=lambda x: -x[1]):
            print(f"  {phase}: {count} verticals")
        
        print(f"\n{'=' * 60}")
        print("QUADRANT DISTRIBUTION")
        print(f"{'=' * 60}")
        print(f"  Hot (high tech + high hype): {quadrant_counts.get('hot', 0)}")
        print(f"  Mature (high tech + low hype): {quadrant_counts.get('mature', 0)}")
        print(f"  Hyped (low tech + high hype): {quadrant_counts.get('hyped', 0)}")
        print(f"  Emerging (low tech + low hype): {quadrant_counts.get('emerging', 0)}")
        
        # Top opportunities
        print(f"\n{'=' * 60}")
        print("TOP OPPORTUNITIES (High tech, moderate hype)")
        print(f"{'=' * 60}")
        sorted_verticals = sorted(
            results["verticals"].values(),
            key=lambda x: x["investment_score"],
            reverse=True
        )
        for v in sorted_verticals[:8]:
            print(f"  {v['name']}: {v['investment_score']:.0f} score | {v['hype_phase']}")
        
        return results


if __name__ == "__main__":
    scraper = AIVerticalsScraper()
    scraper.run()
