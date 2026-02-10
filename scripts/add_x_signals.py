# -*- coding: utf-8 -*-
"""
Add signals scraped from X/Twitter to briefAI signal radar.
Manual entry for real-time signals that can't be auto-scraped.
"""

import sys
from pathlib import Path
from datetime import datetime
import uuid

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_store import SignalStore
from utils.signal_models import (
    Entity, EntityType, SignalCategory, SignalSource,
    SignalObservation, SignalScore, SignalProfile, SignalDivergence,
    DivergenceType, DivergenceInterpretation, normalize_entity_id
)

# Category shortcuts
MEDIA = SignalCategory.MEDIA_SENTIMENT
FINANCIAL = SignalCategory.FINANCIAL
PRODUCT = SignalCategory.PRODUCT_TRACTION
TECHNICAL = SignalCategory.TECHNICAL
COMPANY_SIG = SignalCategory.COMPANY_PRESENCE


def add_x_signals():
    """Add signals from X/Twitter scraping session Jan 28, 2026."""
    
    store = SignalStore()
    
    # Create/ensure X source exists
    x_source_id = "x_twitter_manual"
    
    signals = [
        # 1. Anthropic - Dario Amodei Essay
        {
            "entity_name": "Anthropic",
            "entity_type": EntityType.COMPANY,
            "category": MEDIA,
            "raw_value": 8.5,
            "raw_data": {
                "source": "X/Twitter",
                "event": "CEO Essay: Adolescence of Technology",
                "headline": "Anthropic CEO Warns of Superhuman AI in 1-2 Years",
                "details": "Dario Amodei predicts AI surpassing humans in most domains. Lab-tested risks: Claude showing deception, blackmail, scheming. Policy calls: constitutional AI, chip controls.",
                "engagement": "15K+ posts, 1 day ago",
                "signal_type": "executive_statement",
                "market_impact": "high",
            },
            "confidence": 0.9,
        },
        
        # 2. DeepSeek - Imminent Release
        {
            "entity_name": "DeepSeek",
            "entity_type": EntityType.COMPANY,
            "category": MEDIA,
            "raw_value": 8.0,
            "raw_data": {
                "source": "X/Twitter",
                "event": "DeepSeek V4 Expected Before Lunar New Year",
                "headline": "DeepSeek about to release something big",
                "details": "Claiming GPT-5 level performance. Racing with Moonshot/Kimi. Developer sentiment: switching from Claude to DeepSeek for cost.",
                "engagement": "Trending in AI circles",
                "signal_type": "product_launch_imminent",
                "market_impact": "high",
            },
            "confidence": 0.75,
        },
        
        # 3. Moonshot/Kimi - K2.5 Release
        {
            "entity_name": "Moonshot AI",
            "entity_type": EntityType.COMPANY,
            "category": MEDIA,
            "raw_value": 7.5,
            "raw_data": {
                "source": "X/Twitter",
                "event": "Kimi K2.5 Released",
                "headline": "Moonshot dropped Kimi K2.5",
                "details": "Chinese AI company release. Claiming GPT-5 level performance. Part of pre-Lunar New Year AI race.",
                "engagement": "Trending",
                "signal_type": "product_launch",
                "market_impact": "medium-high",
            },
            "confidence": 0.85,
        },
        
        # 4. Intel + NVIDIA - Foundry Collaboration Rumor
        {
            "entity_name": "Intel",
            "entity_type": EntityType.COMPANY,
            "category": FINANCIAL,
            "raw_value": 7.5,
            "raw_data": {
                "source": "X/Twitter",
                "event": "Intel + NVIDIA Foundry Collaboration Rumor",
                "headline": "Intel Shares Jump on NVIDIA Foundry Collaboration Rumor",
                "details": "755 posts, 3 hours ago. Direct stock impact. Market signal.",
                "engagement": "755 posts",
                "signal_type": "partnership_rumor",
                "market_impact": "high",
                "ticker": "INTC",
            },
            "confidence": 0.7,
        },
        
        {
            "entity_name": "NVIDIA",
            "entity_type": EntityType.COMPANY,
            "category": FINANCIAL,
            "raw_value": 6.5,
            "raw_data": {
                "source": "X/Twitter",
                "event": "Intel + NVIDIA Foundry Collaboration Rumor",
                "headline": "Intel Shares Jump on NVIDIA Foundry Collaboration Rumor",
                "details": "NVIDIA potentially partnering with Intel for foundry. May be strategic move vs TSMC dependency.",
                "engagement": "755 posts",
                "signal_type": "partnership_rumor",
                "market_impact": "medium",
                "ticker": "NVDA",
            },
            "confidence": 0.7,
        },
        
        # 5. South Korea AI Law
        {
            "entity_name": "South Korea AI Policy",
            "entity_type": EntityType.COMPANY,  # No institution type, using company
            "category": MEDIA,
            "raw_value": 7.0,
            "raw_data": {
                "source": "X/Twitter",
                "event": "First AI-Specific Law in World",
                "headline": "South Korea: AI Basic Act effective Jan 22, 2026",
                "details": "First country with dedicated AI legislation. Regulatory precedent for Asia. May influence global AI governance.",
                "engagement": "Trending in policy circles",
                "signal_type": "regulatory",
                "market_impact": "medium-high",
            },
            "confidence": 0.95,
        },
        
        # 6. Trump Admin using Gemini
        {
            "entity_name": "Google",
            "entity_type": EntityType.COMPANY,
            "category": MEDIA,
            "raw_value": 6.5,
            "raw_data": {
                "source": "X/Twitter (via ProPublica)",
                "event": "Government AI Adoption",
                "headline": "Trump DOT Plans to Use Google Gemini AI to Write Regulations",
                "details": "Department of Transportation using Gemini for regulation drafting. Government AI adoption signal.",
                "engagement": "Breaking news",
                "signal_type": "government_adoption",
                "market_impact": "medium",
                "ticker": "GOOGL",
            },
            "confidence": 0.9,
        },
        
        # 7. Vercel ships agent API
        {
            "entity_name": "Vercel",
            "entity_type": EntityType.COMPANY,
            "category": PRODUCT,
            "raw_value": 7.0,
            "raw_data": {
                "source": "X/Twitter (@rauchg)",
                "event": "vercel api for agents",
                "headline": "Vercel ships vercel api - Claude Code auto-connects",
                "details": "Full Vercel platform API from terminal. Zero MCP setup. Developer tooling for AI agents.",
                "engagement": "8h ago, @rauchg (CEO)",
                "signal_type": "product_launch",
                "market_impact": "medium",
            },
            "confidence": 0.95,
        },
        
        # 8. IMF AI Preparedness Index
        {
            "entity_name": "IMF AI Index",
            "entity_type": EntityType.COMPANY,  # No institution type
            "category": MEDIA,
            "raw_value": 6.0,
            "raw_data": {
                "source": "X/Twitter",
                "event": "IMF AI Preparedness Index (AIPI)",
                "headline": "IMF Maps 174 Countries AI Readiness",
                "details": "International policy/macro signal. Country-level AI readiness rankings.",
                "engagement": "Policy discussion",
                "signal_type": "macro_indicator",
                "market_impact": "low-medium",
            },
            "confidence": 0.9,
        },
    ]
    
    print(f"Adding {len(signals)} signals from X/Twitter scrape...")
    print("=" * 60)
    
    for sig in signals:
        # Get or create entity
        entity = store.get_or_create_entity(
            name=sig["entity_name"],
            entity_type=sig["entity_type"],
        )
        print(f"Entity: {entity.name} ({entity.entity_type.value})")
        
        # Create observation
        obs = SignalObservation(
            id=str(uuid.uuid4()),
            entity_id=entity.id,
            source_id=x_source_id,
            category=sig["category"],
            observed_at=datetime.utcnow(),
            data_timestamp=datetime.utcnow(),
            raw_value=sig["raw_value"],
            raw_value_unit="sentiment_score",
            raw_data=sig["raw_data"],
            confidence=sig["confidence"],
        )
        
        store.add_observation(obs)
        headline = sig['raw_data'].get('headline', 'Signal')[:60]
        print(f"  Added: {headline}...")
        
        # Create score
        score = SignalScore(
            id=str(uuid.uuid4()),
            observation_id=obs.id,
            entity_id=entity.id,
            source_id=x_source_id,
            category=sig["category"],
            score=sig["raw_value"] * 10,  # Convert to 0-100 scale
            percentile=None,
            score_delta_7d=None,
            score_delta_30d=None,
        )
        store.add_score(score)
        print(f"  Score: {score.score}/100")
        print()
    
    print("=" * 60)
    print(f"Added {len(signals)} signals to briefAI")
    print("\nRun `python scripts/rebuild_profiles.py` to update signal radar.")


if __name__ == "__main__":
    add_x_signals()
