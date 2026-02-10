#!/usr/bin/env python3
"""
Ground Truth Expander for briefAI Backtesting

Mines multiple data sources to create 50+ validated events for backtesting:
1. Crunchbase funding rounds (AI companies, 2024-2025)
2. Known AI breakout events
3. GitHub trending repos (AI/ML)
4. Major product launches

This gives us real events to validate prediction accuracy.
"""

import csv
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict

# Add project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# AI-related keywords for filtering
AI_KEYWORDS = [
    'artificial intelligence', 'machine learning', 'deep learning', 'neural network',
    'nlp', 'natural language', 'computer vision', 'robotics', 'automation',
    'ai', 'ml', 'llm', 'large language model', 'generative ai', 'gen ai',
    'chatbot', 'conversational ai', 'predictive analytics', 'data science',
    'autonomous', 'cognitive', 'intelligent', 'smart'
]

# Known AI companies (high confidence)
KNOWN_AI_COMPANIES = {
    'openai', 'anthropic', 'cohere', 'mistral', 'deepmind', 'stability ai',
    'hugging face', 'huggingface', 'midjourney', 'runway', 'jasper', 'copy.ai',
    'scale ai', 'labelbox', 'datarobot', 'h2o.ai', 'databricks', 'snowflake',
    'palantir', 'c3.ai', 'uipath', 'automation anywhere', 'celonis',
    'grammarly', 'notion', 'figma', 'canva', 'adobe', 'nvidia', 'amd', 'intel',
    'google', 'microsoft', 'amazon', 'meta', 'apple', 'tesla', 'baidu',
    'alibaba', 'tencent', 'bytedance', 'sensetime', 'megvii', 'deepseek',
    'zhipu', 'moonshot', 'minimax', 'baichuan', '01.ai', 'xai', 'inflection',
    'character.ai', 'perplexity', 'you.com', 'neeva', 'adept', 'aleph alpha',
    'covariant', 'figure', 'physical intelligence', 'skild', '1x', 'sanctuary',
    'cursor', 'replit', 'sourcegraph', 'tabnine', 'codeium', 'anysphere',
    'langchain', 'llamaindex', 'pinecone', 'weaviate', 'chroma', 'qdrant',
    'together ai', 'fireworks', 'anyscale', 'modal', 'replicate', 'banana',
    'runway ml', 'pika', 'luma', 'kling', 'sora', 'gen-2', 'stable diffusion',
    'elevenlabs', 'play.ht', 'resemble', 'descript', 'synthesia', 'heygen',
    'd-id', 'hour one', 'colossyan', 'rephrase', 'tavus'
}


def is_ai_company(name: str, categories: str) -> bool:
    """Check if a company is AI-related."""
    name_lower = name.lower()
    categories_lower = categories.lower() if categories else ''
    
    # Check known companies
    for known in KNOWN_AI_COMPANIES:
        if known in name_lower:
            return True
    
    # Check categories
    for keyword in AI_KEYWORDS:
        if keyword in categories_lower or keyword in name_lower:
            return True
    
    return False


def load_crunchbase_rounds(kaggle_path: Path) -> List[Dict[str, Any]]:
    """Load funding rounds from Crunchbase Kaggle data."""
    rounds_file = kaggle_path / "round.csv"
    
    if not rounds_file.exists():
        print(f"Warning: {rounds_file} not found")
        return []
    
    rounds = []
    with open(rounds_file, 'r', encoding='utf-8', errors='ignore') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                # Parse date
                funded_at = row.get('funded_at', '')
                if not funded_at:
                    continue
                
                # Parse amount
                amount_str = row.get('raised_amount_usd', '0')
                amount = int(float(amount_str)) if amount_str else 0
                
                rounds.append({
                    'company_name': row.get('company_name', ''),
                    'company_permalink': row.get('company_permalink', ''),
                    'categories': row.get('company_category_list', ''),
                    'country': row.get('company_country_code', ''),
                    'round_type': row.get('funding_round_type', ''),
                    'round_code': row.get('funding_round_code', ''),
                    'funded_at': funded_at,
                    'amount_usd': amount,
                })
            except (ValueError, TypeError):
                continue
    
    return rounds


def load_known_events() -> List[Dict[str, Any]]:
    """Load curated known AI events (high confidence)."""
    return [
        # 2024 Major Events
        {
            "entity_id": "openai",
            "entity_name": "OpenAI",
            "event_type": "funding",
            "event_date": "2024-10-02",
            "breakout_date": "2024-10-02",
            "details": "$6.6B funding round at $157B valuation",
            "amount_usd": 6_600_000_000,
            "sources": ["bloomberg", "wsj", "techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "anthropic",
            "entity_name": "Anthropic",
            "event_type": "funding",
            "event_date": "2024-09-01",
            "breakout_date": "2024-09-01",
            "details": "$4B Amazon investment",
            "amount_usd": 4_000_000_000,
            "sources": ["bloomberg", "wsj"],
            "confidence": "high"
        },
        {
            "entity_id": "xai",
            "entity_name": "xAI",
            "event_type": "funding",
            "event_date": "2024-05-27",
            "breakout_date": "2024-05-27",
            "details": "$6B Series B",
            "amount_usd": 6_000_000_000,
            "sources": ["bloomberg", "techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "perplexity",
            "entity_name": "Perplexity",
            "event_type": "funding",
            "event_date": "2024-04-23",
            "breakout_date": "2024-04-25",
            "details": "$62.7M Series B at $1B+ valuation",
            "amount_usd": 62_700_000,
            "sources": ["techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "mistral",
            "entity_name": "Mistral AI",
            "event_type": "funding",
            "event_date": "2024-06-11",
            "breakout_date": "2024-06-12",
            "details": "€600M Series B",
            "amount_usd": 640_000_000,
            "sources": ["bloomberg", "techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "cohere",
            "entity_name": "Cohere",
            "event_type": "funding",
            "event_date": "2024-07-22",
            "breakout_date": "2024-07-23",
            "details": "$500M Series D",
            "amount_usd": 500_000_000,
            "sources": ["techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "scale-ai",
            "entity_name": "Scale AI",
            "event_type": "funding",
            "event_date": "2024-05-21",
            "breakout_date": "2024-05-22",
            "details": "$1B at $13.8B valuation",
            "amount_usd": 1_000_000_000,
            "sources": ["bloomberg", "forbes"],
            "confidence": "high"
        },
        {
            "entity_id": "figure",
            "entity_name": "Figure",
            "event_type": "funding",
            "event_date": "2024-02-29",
            "breakout_date": "2024-03-01",
            "details": "$675M Series B for humanoid robots",
            "amount_usd": 675_000_000,
            "sources": ["techcrunch", "bloomberg"],
            "confidence": "high"
        },
        {
            "entity_id": "physical-intelligence",
            "entity_name": "Physical Intelligence",
            "event_type": "funding",
            "event_date": "2024-11-04",
            "breakout_date": "2024-11-05",
            "details": "$400M at $2.4B valuation",
            "amount_usd": 400_000_000,
            "sources": ["techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "skild",
            "entity_name": "Skild AI",
            "event_type": "funding",
            "event_date": "2024-07-16",
            "breakout_date": "2024-07-17",
            "details": "$300M at $1.5B valuation",
            "amount_usd": 300_000_000,
            "sources": ["techcrunch"],
            "confidence": "high"
        },
        # Product Launches
        {
            "entity_id": "claude-3",
            "entity_name": "Claude 3",
            "event_type": "product_launch",
            "event_date": "2024-03-04",
            "breakout_date": "2024-03-04",
            "details": "Claude 3 Opus/Sonnet/Haiku release",
            "sources": ["anthropic", "techcrunch", "wired"],
            "confidence": "high"
        },
        {
            "entity_id": "gpt-4o",
            "entity_name": "GPT-4o",
            "event_type": "product_launch",
            "event_date": "2024-05-13",
            "breakout_date": "2024-05-13",
            "details": "GPT-4o multimodal release",
            "sources": ["openai", "techcrunch", "verge"],
            "confidence": "high"
        },
        {
            "entity_id": "gemini-1.5",
            "entity_name": "Gemini 1.5",
            "event_type": "product_launch",
            "event_date": "2024-02-15",
            "breakout_date": "2024-02-15",
            "details": "Gemini 1.5 with 1M context",
            "sources": ["google", "techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "llama-3",
            "entity_name": "Llama 3",
            "event_type": "product_launch",
            "event_date": "2024-04-18",
            "breakout_date": "2024-04-18",
            "details": "Meta Llama 3 open release",
            "sources": ["meta", "techcrunch", "verge"],
            "confidence": "high"
        },
        {
            "entity_id": "sora",
            "entity_name": "Sora",
            "event_type": "product_launch",
            "event_date": "2024-02-15",
            "breakout_date": "2024-02-15",
            "details": "OpenAI Sora video generation announce",
            "sources": ["openai", "nytimes", "wired"],
            "confidence": "high"
        },
        # 2025 Events
        {
            "entity_id": "deepseek-v3",
            "entity_name": "DeepSeek V3",
            "event_type": "product_launch",
            "event_date": "2025-01-20",
            "breakout_date": "2025-01-21",
            "details": "DeepSeek V3 release causing market attention",
            "sources": ["techcrunch", "wired", "nytimes"],
            "confidence": "high"
        },
        {
            "entity_id": "cursor",
            "entity_name": "Cursor",
            "event_type": "breakout",
            "event_date": "2024-10-15",
            "breakout_date": "2024-12-15",
            "details": "AI IDE mainstream adoption",
            "sources": ["techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "windsurf",
            "entity_name": "Windsurf",
            "event_type": "product_launch",
            "event_date": "2024-11-13",
            "breakout_date": "2024-11-15",
            "details": "Codeium Windsurf AI IDE launch",
            "sources": ["techcrunch"],
            "confidence": "high"
        },
        # Chinese AI
        {
            "entity_id": "qwen-2.5",
            "entity_name": "Qwen 2.5",
            "event_type": "product_launch",
            "event_date": "2024-09-19",
            "breakout_date": "2024-09-20",
            "details": "Alibaba Qwen 2.5 series release",
            "sources": ["alibaba", "techcrunch"],
            "confidence": "high"
        },
        {
            "entity_id": "zhipu-glm4",
            "entity_name": "GLM-4",
            "event_type": "product_launch",
            "event_date": "2024-01-16",
            "breakout_date": "2024-01-17",
            "details": "Zhipu AI GLM-4 release",
            "sources": ["jiqizhixin"],
            "confidence": "medium"
        },
        {
            "entity_id": "kimi-moonshot",
            "entity_name": "Kimi",
            "event_type": "breakout",
            "event_date": "2024-03-18",
            "breakout_date": "2024-03-20",
            "details": "Moonshot Kimi 200K context goes viral in China",
            "sources": ["36kr", "jiqizhixin"],
            "confidence": "medium"
        },
    ]


def filter_ai_funding_rounds(
    rounds: List[Dict], 
    min_amount: int = 10_000_000,
    start_year: int = 2024
) -> List[Dict[str, Any]]:
    """Filter for significant AI funding rounds."""
    ai_rounds = []
    
    for r in rounds:
        # Filter by date
        try:
            funded_date = datetime.strptime(r['funded_at'], '%Y-%m-%d')
            if funded_date.year < start_year:
                continue
        except ValueError:
            continue
        
        # Filter by amount
        if r['amount_usd'] < min_amount:
            continue
        
        # Filter by AI relevance
        if not is_ai_company(r['company_name'], r['categories']):
            continue
        
        # Create event
        event = {
            "entity_id": r['company_permalink'].split('/')[-1],
            "entity_name": r['company_name'],
            "event_type": "funding",
            "event_date": r['funded_at'],
            "breakout_date": r['funded_at'],  # Assume same-day for funding
            "details": f"{r['round_type']} {r['round_code'] or ''} round".strip(),
            "amount_usd": r['amount_usd'],
            "round_type": r['round_type'],
            "country": r['country'],
            "sources": ["crunchbase"],
            "confidence": "medium"  # Lower than curated events
        }
        ai_rounds.append(event)
    
    return ai_rounds


def deduplicate_events(events: List[Dict]) -> List[Dict]:
    """Remove duplicate events."""
    seen = set()
    unique = []
    
    for event in events:
        # Create unique key
        key = (
            event['entity_id'].lower(),
            event['event_type'],
            event['event_date'][:7]  # Year-month granularity
        )
        
        if key not in seen:
            seen.add(key)
            unique.append(event)
    
    return unique


def create_ground_truth_format(events: List[Dict]) -> Dict[str, Any]:
    """Convert events to ground truth format for backtesting."""
    breakout_events = []
    
    for event in events:
        entry = {
            "entity_id": event['entity_id'],
            "entity_name": event['entity_name'],
            "entity_type": "company" if event['event_type'] == 'funding' else "product",
            "category": event.get('category', 'ai'),
            "early_signal_date": (
                datetime.strptime(event['event_date'], '%Y-%m-%d') - timedelta(days=14)
            ).strftime('%Y-%m-%d'),
            "breakout_date": event['breakout_date'],
            "mainstream_sources": [
                {"source": s, "date": event['breakout_date']} 
                for s in event.get('sources', ['techcrunch'])
            ],
            "expected_signals": ["news_velocity", "github_trending"] if event['event_type'] != 'funding' else ["funding_signal", "news_velocity"],
            "notes": event.get('details', ''),
        }
        
        if 'amount_usd' in event:
            entry['funding_amount_usd'] = event['amount_usd']
        
        breakout_events.append(entry)
    
    return {
        "_meta": {
            "version": "2.0",
            "description": "Expanded ground truth for backtesting (auto-generated + curated)",
            "last_updated": datetime.now().strftime('%Y-%m-%d'),
            "event_count": len(breakout_events),
            "sources": ["curated", "crunchbase"],
        },
        "breakout_events": breakout_events,
        "mainstream_outlets": {
            "tier1": ["nytimes", "wsj", "washingtonpost", "bbc", "bloomberg"],
            "tier2": ["techcrunch", "wired", "theverge", "arstechnica", "reuters"],
            "tier3": ["venturebeat", "zdnet", "engadget", "forbes"]
        },
        "detection_window_weeks": 8
    }


def main():
    print("=" * 60)
    print("GROUND TRUTH EXPANDER")
    print("=" * 60)
    print()
    
    kaggle_path = project_root / "data" / "kaggle"
    config_path = project_root / "config"
    
    # Step 1: Load Crunchbase rounds
    print("Loading Crunchbase funding rounds...")
    rounds = load_crunchbase_rounds(kaggle_path)
    print(f"  Loaded {len(rounds)} total funding rounds")
    
    # Step 2: Filter for AI companies
    print("\nFiltering for AI companies (2024+, >$10M)...")
    ai_rounds = filter_ai_funding_rounds(rounds, min_amount=10_000_000, start_year=2024)
    print(f"  Found {len(ai_rounds)} AI funding rounds")
    
    # Step 3: Load curated events
    print("\nLoading curated high-confidence events...")
    curated = load_known_events()
    print(f"  Loaded {len(curated)} curated events")
    
    # Step 4: Combine and deduplicate
    print("\nCombining and deduplicating...")
    all_events = curated + ai_rounds
    unique_events = deduplicate_events(all_events)
    print(f"  Total unique events: {len(unique_events)}")
    
    # Step 5: Create ground truth file
    print("\nCreating ground truth file...")
    ground_truth = create_ground_truth_format(unique_events)
    
    output_path = config_path / "ground_truth_expanded.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved to: {output_path}")
    
    # Step 6: Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total events: {len(unique_events)}")
    print(f"  - Curated (high confidence): {len(curated)}")
    print(f"  - Crunchbase (medium confidence): {len(ai_rounds)}")
    print()
    
    # Event type breakdown
    by_type = defaultdict(int)
    for e in unique_events:
        by_type[e['event_type']] += 1
    
    print("By event type:")
    for t, count in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {count}")
    
    # Top funding rounds
    funding_events = [e for e in unique_events if e.get('amount_usd')]
    funding_events.sort(key=lambda x: -x.get('amount_usd', 0))
    
    print("\nTop 10 funding rounds:")
    for e in funding_events[:10]:
        amount = e['amount_usd']
        if amount >= 1_000_000_000:
            amount_str = f"${amount/1_000_000_000:.1f}B"
        else:
            amount_str = f"${amount/1_000_000:.0f}M"
        print(f"  {e['entity_name']}: {amount_str}")
    
    print("\n✓ Ground truth expanded successfully!")
    print(f"  Run backfill: python scripts/backfill_predictions.py run --start-date 2024-01-01")
    
    return output_path


if __name__ == "__main__":
    main()
