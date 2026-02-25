# -*- coding: utf-8 -*-
"""
Blog RSS Scraper — HN Top Blogs (Opinion Leader Layer)

Scrapes independent blogs that dominate Hacker News.
These are leading indicators: when Simon Willison writes about a tool,
it hits HN front page hours later. When gwern publishes analysis,
it shapes discourse for weeks.

Source: https://gist.github.com/emschwartz/e6d2bf860ccc367fe37ff953ba6de66b
"The Most Popular Blogs of Hacker News in 2025"
"""

import socket
socket.setdefaulttimeout(15)

import feedparser
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
import json
import time
import hashlib
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")


@dataclass
class BlogPost:
    """A blog post from an independent author."""
    id: str
    title: str
    url: str
    blog: str
    blog_id: str
    author: Optional[str]
    published_at: Optional[datetime]
    summary: str
    categories: List[str]
    ai_relevance_score: float
    sentiment_keywords: List[str]
    tier: str  # "tier1" (top influencers), "tier2" (strong), "tier3" (niche)


class BlogLLMScorer:
    """LLM-based scoring, categorization, and trend synthesis for blog posts."""

    CATEGORIES = [
        "AI/ML",        # AI, machine learning, LLM, deep learning
        "Security",     # Security, privacy, vulnerabilities, crypto
        "Engineering",  # Software engineering, architecture, systems design
        "Tools/OSS",    # Developer tools, open source projects, frameworks
        "Opinion",      # Industry takes, personal essays, career
        "Other",        # Anything else
    ]

    BATCH_SIZE = 15  # Posts per LLM call (fits context, saves credits)

    def __init__(self):
        self.client = None
        self.model = None
        self._init_llm()

    def _init_llm(self):
        """Initialize LLM client via OpenRouter (free Gemini Flash)."""
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            print("  [LLM] No OPENROUTER_API_KEY, skipping AI scoring")
            return

        try:
            import openai
            self.client = openai.OpenAI(
                api_key=key,
                base_url="https://openrouter.ai/api/v1",
            )
            self.model = "google/gemini-2.0-flash-001"
            print(f"  [LLM] Using OpenRouter ({self.model})")
        except ImportError:
            print("  [LLM] openai package not installed, skipping AI scoring")

    def score_batch(self, posts: List[Dict]) -> List[Dict]:
        """Score a batch of posts with LLM. Returns posts with added fields."""
        if not self.client or not posts:
            return posts

        # Build the article list for the prompt
        article_lines = []
        for i, p in enumerate(posts):
            article_lines.append(
                f"{i+1}. [{p['blog']}] {p['title']}\n"
                f"   Summary: {p.get('summary', '')[:200]}"
            )
        articles_text = "\n".join(article_lines)

        prompt = f"""Score these blog posts for a tech/AI intelligence brief.

For each article, return a JSON array with one object per article:
{{
  "index": <1-based index>,
  "relevance": <1-10, how relevant to AI/tech industry trends>,
  "quality": <1-10, depth of insight, originality>,
  "timeliness": <1-10, how timely/current>,
  "category": "<one of: AI/ML, Security, Engineering, Tools/OSS, Opinion, Other>",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "one_line": "<one sentence: why this matters, in English>"
}}

Articles:
{articles_text}

Return ONLY the JSON array, no markdown fences, no explanation."""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=3000,
            )
            raw = resp.choices[0].message.content.strip()

            # Clean markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            scores = json.loads(raw)

            # Merge scores back into posts
            score_map = {s["index"]: s for s in scores}
            for i, p in enumerate(posts):
                s = score_map.get(i + 1, {})
                p["llm_relevance"] = s.get("relevance", 0)
                p["llm_quality"] = s.get("quality", 0)
                p["llm_timeliness"] = s.get("timeliness", 0)
                p["llm_score"] = round(
                    (s.get("relevance", 0) * 0.4 +
                     s.get("quality", 0) * 0.4 +
                     s.get("timeliness", 0) * 0.2) / 10, 3
                )
                p["llm_category"] = s.get("category", "Other")
                p["llm_keywords"] = s.get("keywords", [])
                p["llm_summary"] = s.get("one_line", "")

            return posts

        except json.JSONDecodeError as e:
            print(f"    [LLM] JSON parse error: {e}")
            return posts
        except Exception as e:
            print(f"    [LLM] Scoring error: {e}")
            return posts

    def synthesize_trends(self, posts: List[Dict]) -> List[Dict]:
        """Identify 2-3 macro trends across today's blog posts."""
        if not self.client or len(posts) < 5:
            return []

        # Use top-scored posts for trend synthesis
        scored = [p for p in posts if p.get("llm_score", 0) > 0]
        scored.sort(key=lambda p: -p.get("llm_score", 0))
        top = scored[:25]

        titles = "\n".join(
            f"- [{p['blog']}] {p['title']} (score:{p.get('llm_score',0):.2f}, cat:{p.get('llm_category','?')})"
            for p in top
        )

        prompt = f"""Analyze these top blog posts from today's Hacker News popular blogs and identify 2-3 macro trends.

Posts:
{titles}

Return a JSON array of trend objects:
[
  {{
    "trend": "<short trend name>",
    "description": "<2-3 sentences explaining the trend and why it matters>",
    "evidence": ["<title 1>", "<title 2>"],
    "category": "<primary category>",
    "strength": <1-10, how strong is this signal>
  }}
]

Return ONLY the JSON array."""

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1500,
            )
            raw = resp.choices[0].message.content.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            return json.loads(raw)

        except Exception as e:
            print(f"    [LLM] Trend synthesis error: {e}")
            return []


class BlogRSSScraper:
    """Scraper for HN's most popular independent blogs."""

    # Tier 1: Highest-influence blogs with strong AI/tech signal
    # These authors shape HN discourse and industry thinking
    BLOG_FEEDS = {
        # === TIER 1: Top AI/Tech Opinion Leaders ===
        "simonwillison": {
            "name": "Simon Willison",
            "url": "https://simonwillison.net/atom/everything/",
            "tier": "tier1",
            "focus": ["ai_tools", "llm", "open_source"],
            "why": "Most prolific AI tooling blogger, LLM practitioner",
        },
        "gwern": {
            "name": "gwern",
            "url": "https://gwern.substack.com/feed",
            "tier": "tier1",
            "focus": ["ai_research", "analysis", "forecasting"],
            "why": "Deep AI research essays, scaling laws, forecasting",
        },
        "paulgraham": {
            "name": "Paul Graham",
            "url": "http://www.aaronsw.com/2002/feeds/pgessays.rss",
            "tier": "tier1",
            "focus": ["startups", "thinking", "technology"],
            "why": "YC founder, shapes startup/tech thinking",
        },
        "overreacted": {
            "name": "Dan Abramov (overreacted)",
            "url": "https://overreacted.io/rss.xml",
            "tier": "tier1",
            "focus": ["frontend", "engineering", "react"],
            "why": "React core team, massive dev influence",
        },
        "antirez": {
            "name": "antirez (Salvatore Sanfilippo)",
            "url": "http://antirez.com/rss",
            "tier": "tier1",
            "focus": ["systems", "engineering", "redis"],
            "why": "Redis creator, systems engineering thought leader",
        },
        "mitchellh": {
            "name": "Mitchell Hashimoto",
            "url": "https://mitchellh.com/feed.xml",
            "tier": "tier1",
            "focus": ["infrastructure", "engineering", "ghostty"],
            "why": "HashiCorp founder, infra/devtools influence",
        },
        "garymarcus": {
            "name": "Gary Marcus",
            "url": "https://garymarcus.substack.com/feed",
            "tier": "tier1",
            "focus": ["ai_criticism", "agi", "policy"],
            "why": "Leading AI skeptic, shapes safety/hype discourse",
        },

        # === TIER 2: Strong Signal Blogs ===
        "krebsonsecurity": {
            "name": "Krebs on Security",
            "url": "https://krebsonsecurity.com/feed/",
            "tier": "tier2",
            "focus": ["security", "cybercrime"],
            "why": "Top infosec journalist",
        },
        "daringfireball": {
            "name": "Daring Fireball (John Gruber)",
            "url": "https://daringfireball.net/feeds/main",
            "tier": "tier2",
            "focus": ["apple", "tech_culture", "product"],
            "why": "Apple/tech commentary kingmaker",
        },
        "pluralistic": {
            "name": "Cory Doctorow (Pluralistic)",
            "url": "https://pluralistic.net/feed/",
            "tier": "tier2",
            "focus": ["policy", "antitrust", "tech_culture"],
            "why": "Tech policy, enshittification, antitrust",
        },
        "rachelbythebay": {
            "name": "rachelbythebay",
            "url": "https://rachelbythebay.com/w/atom.xml",
            "tier": "tier2",
            "focus": ["systems", "war_stories", "engineering"],
            "why": "Systems engineering war stories, highly respected",
        },
        "lcamtuf": {
            "name": "lcamtuf (Michal Zalewski)",
            "url": "https://lcamtuf.substack.com/feed",
            "tier": "tier2",
            "focus": ["security", "engineering", "hardware"],
            "why": "Google security legend, deep technical",
        },
        "troyhunt": {
            "name": "Troy Hunt",
            "url": "https://www.troyhunt.com/rss/",
            "tier": "tier2",
            "focus": ["security", "privacy", "breaches"],
            "why": "Have I Been Pwned, security awareness",
        },
        "lucumr": {
            "name": "Armin Ronacher (lucumr)",
            "url": "https://lucumr.pocoo.org/feed.atom",
            "tier": "tier2",
            "focus": ["python", "rust", "engineering"],
            "why": "Flask/Sentry creator, Python/Rust thought leader",
        },
        "xeiaso": {
            "name": "Xe Iaso",
            "url": "https://xeiaso.net/blog.rss",
            "tier": "tier2",
            "focus": ["devops", "ai", "engineering"],
            "why": "Prolific, covers AI tooling + infrastructure",
        },
        "matklad": {
            "name": "matklad (Alex Kladov)",
            "url": "https://matklad.github.io/feed.xml",
            "tier": "tier2",
            "focus": ["rust", "compilers", "engineering"],
            "why": "rust-analyzer creator, systems engineering",
        },
        "dynomight": {
            "name": "Dynomight",
            "url": "https://dynomight.net/feed.xml",
            "tier": "tier2",
            "focus": ["science", "analysis", "data"],
            "why": "Data-driven essays, rigorous analysis",
        },
        "dwarkesh": {
            "name": "Dwarkesh Patel",
            "url": "https://www.dwarkeshpatel.com/feed",
            "tier": "tier2",
            "focus": ["ai_interviews", "technology", "progress"],
            "why": "Top AI interview podcast, shapes narratives",
        },
        "steveblank": {
            "name": "Steve Blank",
            "url": "https://steveblank.com/feed/",
            "tier": "tier2",
            "focus": ["startups", "strategy", "innovation"],
            "why": "Lean startup godfather",
        },
        "oldnewthing": {
            "name": "The Old New Thing (Raymond Chen)",
            "url": "https://devblogs.microsoft.com/oldnewthing/feed",
            "tier": "tier2",
            "focus": ["windows", "systems", "engineering"],
            "why": "Microsoft legend, 20+ years of systems insights",
        },
        "righto": {
            "name": "Ken Shirriff (righto)",
            "url": "https://www.righto.com/feeds/posts/default",
            "tier": "tier2",
            "focus": ["hardware", "chips", "reverse_engineering"],
            "why": "Chip reverse engineering, hardware deep dives",
        },
        "eli_greenplace": {
            "name": "Eli Bendersky",
            "url": "https://eli.thegreenplace.net/feeds/all.atom.xml",
            "tier": "tier2",
            "focus": ["compilers", "go", "engineering"],
            "why": "Google engineer, compilers/Go deep dives",
        },
        "construction_physics": {
            "name": "Construction Physics",
            "url": "https://www.construction-physics.com/feed",
            "tier": "tier2",
            "focus": ["infrastructure", "economics", "progress"],
            "why": "Progress studies, infrastructure economics",
        },

        # === TIER 3: Niche but HN-beloved ===
        "jeffgeerling": {
            "name": "Jeff Geerling",
            "url": "https://www.jeffgeerling.com/blog.xml",
            "tier": "tier3",
            "focus": ["homelab", "raspberry_pi", "devops"],
            "why": "Homelab/Pi king, hardware accessibility",
        },
        "seangoedecke": {
            "name": "Sean Goedecke",
            "url": "https://www.seangoedecke.com/rss.xml",
            "tier": "tier3",
            "focus": ["engineering", "career"],
            "why": "GitHub engineer, eng culture essays",
        },
        "ericmigi": {
            "name": "Eric Migicovsky",
            "url": "https://ericmigi.com/rss.xml",
            "tier": "tier3",
            "focus": ["hardware", "startups", "pebble"],
            "why": "Pebble founder, hardware startup lessons",
        },
        "shkspr": {
            "name": "Terence Eden",
            "url": "https://shkspr.mobi/blog/feed/",
            "tier": "tier3",
            "focus": ["web_standards", "open_source", "policy"],
            "why": "Web standards, open source advocacy",
        },
        "hillelwayne": {
            "name": "Hillel Wayne",
            "url": "https://buttondown.com/hillelwayne/rss",
            "tier": "tier3",
            "focus": ["formal_methods", "engineering", "cs_history"],
            "why": "Formal methods advocate, CS history",
        },
        "fabiensanglard": {
            "name": "Fabien Sanglard",
            "url": "https://fabiensanglard.net/rss.xml",
            "tier": "tier3",
            "focus": ["game_engines", "graphics", "reverse_engineering"],
            "why": "Game engine deep dives",
        },
        "berthub": {
            "name": "Bert Hubert",
            "url": "https://berthub.eu/articles/index.xml",
            "tier": "tier3",
            "focus": ["dns", "networking", "policy"],
            "why": "PowerDNS creator, EU tech policy",
        },
        "computer_rip": {
            "name": "computer.rip (J. B. Crawford)",
            "url": "https://computer.rip/rss.xml",
            "tier": "tier3",
            "focus": ["telecom", "infrastructure", "history"],
            "why": "Telecom/infrastructure history deep dives",
        },
        "minimaxir": {
            "name": "Max Woolf (minimaxir)",
            "url": "https://minimaxir.com/index.xml",
            "tier": "tier3",
            "focus": ["ai", "data_science", "llm"],
            "why": "AI/LLM practitioner, ChatGPT analysis",
        },
        "geoffreylitt": {
            "name": "Geoffrey Litt",
            "url": "https://www.geoffreylitt.com/feed.xml",
            "tier": "tier3",
            "focus": ["end_user_programming", "ai_tools"],
            "why": "End-user programming, AI-powered tools research",
        },
        "grantslatton": {
            "name": "Grant Slatton",
            "url": "https://grantslatton.com/rss.xml",
            "tier": "tier3",
            "focus": ["engineering", "startups"],
            "why": "Engineering essays, viral HN posts",
        },
        "keygen": {
            "name": "Keygen",
            "url": "https://keygen.sh/blog/feed.xml",
            "tier": "tier3",
            "focus": ["licensing", "business", "indie"],
            "why": "Indie SaaS, software licensing",
        },
        "experimental_history": {
            "name": "Experimental History",
            "url": "https://www.experimental-history.com/feed",
            "tier": "tier3",
            "focus": ["science", "psychology", "culture"],
            "why": "Science/psychology essays, HN favorite",
        },
        "wheresyoured": {
            "name": "Where's Your Ed At",
            "url": "https://www.wheresyoured.at/rss/",
            "tier": "tier3",
            "focus": ["tech_criticism", "ai_hype", "culture"],
            "why": "Tech criticism, AI hype analysis",
        },
        "miguelgrinberg": {
            "name": "Miguel Grinberg",
            "url": "https://blog.miguelgrinberg.com/feed",
            "tier": "tier3",
            "focus": ["python", "web", "tutorials"],
            "why": "Flask mega-tutorial author, Python web",
        },
    }

    # AI-related keywords for relevance scoring
    AI_KEYWORDS = {
        "high": [
            "artificial intelligence", "machine learning", "deep learning",
            "llm", "large language model", "gpt", "chatgpt", "claude",
            "anthropic", "openai", "deepmind", "gemini", "copilot",
            "neural network", "transformer", "diffusion", "generative ai",
            "ai agent", "rag", "fine-tuning", "prompt engineering",
            "reasoning model", "chain of thought", "multimodal",
        ],
        "medium": [
            "ai", "ml", "automation", "model", "training",
            "inference", "gpu", "chip", "semiconductor", "nvidia",
            "data center", "cloud computing", "autonomous",
            "embedding", "vector database", "token", "context window",
        ],
        "low": [
            "technology", "software", "startup", "funding",
            "robot", "computer", "digital", "algorithm",
        ],
    }

    SENTIMENT_KEYWORDS = {
        "positive": [
            "breakthrough", "revolutionary", "launch", "release", "announces",
            "partnership", "funding", "raises", "growth", "record", "success",
            "impressive", "game-changer", "exciting",
        ],
        "negative": [
            "layoff", "cuts", "decline", "concern", "risk", "lawsuit",
            "investigation", "delay", "fail", "struggle", "warning",
            "overrated", "hype", "bubble", "enshittification",
        ],
    }

    def __init__(self, output_dir: Optional[Path] = None):
        self.output_dir = output_dir or Path(__file__).parent.parent / "data" / "alternative_signals"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BriefAI/2.0 (Blog Aggregator; contact@briefai.dev)"
        })
        self.session.timeout = 15

    def fetch_feed(self, blog_id: str) -> List[Dict[str, Any]]:
        """Fetch and parse a blog RSS feed."""
        config = self.BLOG_FEEDS[blog_id]

        try:
            # feedparser can hang on slow feeds, use requests first
            resp = self.session.get(config["url"], timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            if feed.bozo and not feed.entries:
                print(f"    Warning: {blog_id} feed parse error - {feed.bozo_exception}")
                return []

            entries = []
            for entry in feed.entries[:20]:  # 20 per blog is plenty
                entries.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", entry.get("description", ""))[:500],
                    "published": entry.get("published", entry.get("updated", "")),
                    "author": entry.get("author", config["name"]),
                    "tags": [t.get("term", "") for t in entry.get("tags", [])],
                })

            return entries

        except requests.exceptions.Timeout:
            print(f"    Timeout fetching {blog_id}")
            return []
        except requests.exceptions.ConnectionError:
            print(f"    Connection error for {blog_id} (DNS/network)")
            return []
        except Exception as e:
            print(f"    Error fetching {blog_id}: {e}")
            return []

    def calculate_ai_relevance(self, text: str) -> float:
        """Calculate AI relevance score (0-1) based on keywords."""
        text_lower = text.lower()
        score = 0.0

        for kw in self.AI_KEYWORDS["high"]:
            if kw in text_lower:
                score += 0.3

        for kw in self.AI_KEYWORDS["medium"]:
            if kw in text_lower:
                score += 0.15

        for kw in self.AI_KEYWORDS["low"]:
            if kw in text_lower:
                score += 0.05

        return min(score, 1.0)

    def extract_sentiment_keywords(self, text: str) -> List[str]:
        """Extract sentiment-indicating keywords."""
        text_lower = text.lower()
        found = []

        for kw in self.SENTIMENT_KEYWORDS["positive"]:
            if kw in text_lower:
                found.append(f"+{kw}")
        for kw in self.SENTIMENT_KEYWORDS["negative"]:
            if kw in text_lower:
                found.append(f"-{kw}")

        return found

    def parse_published_date(self, date_str: str) -> Optional[str]:
        """Parse date string, return ISO format or None."""
        if not date_str:
            return None

        formats = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S %Z",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f%z",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).isoformat()
            except ValueError:
                continue

        # feedparser sometimes provides a struct_time-compatible tuple
        return None

    def is_recent(self, date_str: str, days: int = 7) -> bool:
        """Check if a date string is within the last N days."""
        if not date_str:
            return True  # Include undated posts (assume recent)

        try:
            dt = datetime.fromisoformat(date_str)
            # Remove timezone for comparison
            if dt.tzinfo:
                dt = dt.replace(tzinfo=None)
            return dt > datetime.now() - timedelta(days=days)
        except (ValueError, TypeError):
            return True

    def run(self) -> Dict[str, Any]:
        """Run the blog scraper."""
        print(f"\nScraping {len(self.BLOG_FEEDS)} independent blogs...")

        all_posts = []
        stats = {"tier1": 0, "tier2": 0, "tier3": 0, "errors": 0, "total_fetched": 0}

        for blog_id, config in self.BLOG_FEEDS.items():
            print(f"  [{blog_id}] fetching...", end=" ", flush=True)
            entries = self.fetch_feed(blog_id)

            if not entries:
                print("no entries")
                stats["errors"] += 1
                continue

            print(f"{len(entries)} entries")
            stats["total_fetched"] += len(entries)

            for entry in entries:
                published = self.parse_published_date(entry["published"])

                # Only include posts from last 7 days
                if not self.is_recent(published):
                    continue

                full_text = f"{entry['title']} {entry['summary']}"
                ai_relevance = self.calculate_ai_relevance(full_text)

                url_hash = hashlib.md5(entry["link"].encode()).hexdigest()[:12]

                post = {
                    "id": f"blog_{blog_id}_{url_hash}",
                    "title": entry["title"],
                    "url": entry["link"],
                    "blog": config["name"],
                    "blog_id": blog_id,
                    "author": entry["author"],
                    "published_at": published,
                    "summary": entry["summary"],
                    "categories": entry["tags"] + config["focus"],
                    "ai_relevance_score": round(ai_relevance, 3),
                    "sentiment_keywords": self.extract_sentiment_keywords(full_text),
                    "tier": config["tier"],
                }

                all_posts.append(post)
                stats[config["tier"]] += 1

            time.sleep(0.5)  # Be polite

        # === LLM SCORING PHASE ===
        scorer = BlogLLMScorer()
        if scorer.client and all_posts:
            print(f"\n  [LLM] Scoring {len(all_posts)} posts in batches of {scorer.BATCH_SIZE}...")
            for i in range(0, len(all_posts), scorer.BATCH_SIZE):
                batch = all_posts[i:i + scorer.BATCH_SIZE]
                batch_num = i // scorer.BATCH_SIZE + 1
                total_batches = (len(all_posts) + scorer.BATCH_SIZE - 1) // scorer.BATCH_SIZE
                print(f"    Batch {batch_num}/{total_batches}...", end=" ", flush=True)
                scored = scorer.score_batch(batch)
                all_posts[i:i + scorer.BATCH_SIZE] = scored
                scored_count = sum(1 for p in scored if p.get("llm_score", 0) > 0)
                print(f"{scored_count}/{len(batch)} scored")
                time.sleep(0.5)

            # Trend synthesis
            print("  [LLM] Synthesizing trends...", flush=True)
            trends = scorer.synthesize_trends(all_posts)
            print(f"    Found {len(trends)} trends")
        else:
            trends = []

        # Sort: by LLM score (if available), then keyword score
        all_posts.sort(key=lambda p: -(p.get("llm_score", 0) or p.get("ai_relevance_score", 0)))

        # Category distribution
        cat_dist = {}
        for p in all_posts:
            cat = p.get("llm_category", "Unscored")
            cat_dist[cat] = cat_dist.get(cat, 0) + 1

        # Save
        today = datetime.now().strftime("%Y-%m-%d")
        output_path = self.output_dir / f"blog_signals_{today}.json"

        result = {
            "scraped_at": datetime.now().isoformat(),
            "source": "blog_rss",
            "description": "Independent blogs popular on Hacker News (opinion leader layer)",
            "stats": {**stats, "category_distribution": cat_dist},
            "trends": trends,
            "post_count": len(all_posts),
            "posts": all_posts,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        print(f"\n  Blogs scraped: {len(self.BLOG_FEEDS)} ({stats['errors']} errors)")
        print(f"  Recent posts: {len(all_posts)} (T1:{stats['tier1']} T2:{stats['tier2']} T3:{stats['tier3']})")
        if cat_dist:
            print(f"  Categories: {cat_dist}")
        if trends:
            for t in trends:
                print(f"  [TREND] {t.get('trend', '?')} (strength: {t.get('strength', '?')})")
        print(f"Saved to {output_path}")

        return result


if __name__ == "__main__":
    scraper = BlogRSSScraper()
    scraper.run()
