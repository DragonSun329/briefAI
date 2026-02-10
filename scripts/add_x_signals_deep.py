# -*- coding: utf-8 -*-
"""
Deep dive X signals - additional context and entities from Jan 28, 2026 scrape.
"""

import sys
from pathlib import Path
from datetime import datetime
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_store import SignalStore
from utils.signal_models import (
    Entity, EntityType, SignalCategory, SignalSource,
    SignalObservation, SignalScore, normalize_entity_id
)

MEDIA = SignalCategory.MEDIA_SENTIMENT
FINANCIAL = SignalCategory.FINANCIAL
PRODUCT = SignalCategory.PRODUCT_TRACTION
TECHNICAL = SignalCategory.TECHNICAL
COMPANY_SIG = SignalCategory.COMPANY_PRESENCE


def add_deep_signals():
    """Add deeper context signals from X/Twitter."""
    
    store = SignalStore()
    x_source_id = "x_twitter_deep"
    
    signals = [
        # DeepSeek R2 Papers
        {
            "entity_name": "DeepSeek",
            "entity_type": EntityType.COMPANY,
            "category": TECHNICAL,
            "raw_value": 8.5,
            "raw_data": {
                "source": "X/Twitter (@fivewlabs)",
                "event": "DeepSeek R2 Research Papers",
                "headline": "DeepSeek ships two new papers on training efficiency",
                "details": "January 2026: Two breakthrough papers on training efficiency. Analysts calling it a breakthrough. Pressure on OpenAI and Google. Open-source approach gaining traction.",
                "signal_type": "research_breakthrough",
                "market_impact": "high",
                "related_entities": ["OpenAI", "Google"],
            },
            "confidence": 0.85,
        },
        
        # Dario Essay - Deep Details
        {
            "entity_name": "Anthropic",
            "entity_type": EntityType.COMPANY,
            "category": MEDIA,
            "raw_value": 9.0,
            "raw_data": {
                "source": "X/Twitter (@DarioAmodei)",
                "event": "Adolescence of Technology Essay - Engagement Metrics",
                "headline": "4.1M views, 2.7K reposts, 12K likes on Amodei essay",
                "details": "Original post: 457 replies, 2726 reposts, 12180 likes, 14612 bookmarks, 4.1M views. Massive engagement on AI safety/risk discussion. Key thesis: AI as 'adolescent' - powerful but risky if not guided.",
                "engagement_metrics": {
                    "views": 4101384,
                    "reposts": 2726,
                    "likes": 12180,
                    "bookmarks": 14612,
                    "replies": 457
                },
                "signal_type": "thought_leadership",
                "market_impact": "high",
            },
            "confidence": 0.95,
        },
        
        # Claude Deception Research
        {
            "entity_name": "Claude",
            "entity_type": EntityType.TECHNOLOGY,
            "category": TECHNICAL,
            "raw_value": 7.0,
            "raw_data": {
                "source": "X/Twitter (via Amodei essay)",
                "event": "Claude Lab-Tested Risks Disclosed",
                "headline": "Claude shows deception, blackmail, scheming in lab tests",
                "details": "Anthropic CEO discloses internal testing results: Claude models exhibited deception, blackmail, and scheming behaviors. Part of constitutional AI development process.",
                "signal_type": "safety_research",
                "market_impact": "medium",
                "sentiment": "cautionary",
            },
            "confidence": 0.9,
        },
        
        # Chinese AI Race - Kimi
        {
            "entity_name": "Moonshot AI",
            "entity_type": EntityType.COMPANY,
            "category": PRODUCT,
            "raw_value": 8.0,
            "raw_data": {
                "source": "X/Twitter",
                "event": "Kimi K2.5 Product Launch",
                "headline": "Kimi K2.5 released - GPT-5 level claims",
                "details": "Pre-Lunar New Year release. Part of Chinese AI race with DeepSeek. Open source, cost-competitive positioning. Developer migration from Claude/OpenAI.",
                "signal_type": "product_launch",
                "market_impact": "medium-high",
                "related_entities": ["DeepSeek", "OpenAI", "Anthropic"],
            },
            "confidence": 0.85,
        },
        
        # OpenAI Competitive Pressure
        {
            "entity_name": "OpenAI",
            "entity_type": EntityType.COMPANY,
            "category": MEDIA,
            "raw_value": 5.5,
            "raw_data": {
                "source": "X/Twitter (sentiment analysis)",
                "event": "Competitive Pressure from China",
                "headline": "OpenAI faces pressure from DeepSeek, Moonshot open-source push",
                "details": "Developer sentiment shifting: Chinese open-source models gaining traction. Cost advantage driving migration. 'Pressure on OpenAI and Google just went up.'",
                "signal_type": "competitive_threat",
                "market_impact": "medium",
                "sentiment": "bearish",
            },
            "confidence": 0.75,
        },
        
        # GLM-4.7 Release
        {
            "entity_name": "Zhipu AI",
            "entity_type": EntityType.COMPANY,
            "category": PRODUCT,
            "raw_value": 7.0,
            "raw_data": {
                "source": "X/Twitter",
                "event": "GLM-4.7 Release",
                "headline": "GLM-4.7 released as part of Chinese AI wave",
                "details": "Part of pre-Lunar New Year release cascade: GLM-4.7, minimax, qwen-3-max, kimi-2.5. Chinese AI ecosystem momentum.",
                "signal_type": "product_launch",
                "market_impact": "medium",
                "related_entities": ["Moonshot AI", "DeepSeek", "Alibaba"],
            },
            "confidence": 0.8,
        },
        
        # Qwen-3-Max
        {
            "entity_name": "Alibaba",
            "entity_type": EntityType.COMPANY,
            "category": PRODUCT,
            "raw_value": 7.0,
            "raw_data": {
                "source": "X/Twitter",
                "event": "Qwen-3-Max Release",
                "headline": "Qwen-3-Max released by Alibaba",
                "details": "Part of Chinese AI pre-Lunar New Year release wave. Competitive positioning against GPT-5.",
                "signal_type": "product_launch",
                "market_impact": "medium",
                "ticker": "BABA",
            },
            "confidence": 0.8,
        },
        
        # TSMC Angle on Intel-NVIDIA
        {
            "entity_name": "TSMC",
            "entity_type": EntityType.COMPANY,
            "category": FINANCIAL,
            "raw_value": 5.0,
            "raw_data": {
                "source": "X/Twitter (inference)",
                "event": "Intel-NVIDIA Foundry Impact",
                "headline": "Intel-NVIDIA collaboration may reduce TSMC dependency",
                "details": "If Intel foundry collaboration materializes, may be strategic move to diversify away from TSMC. Geopolitical supply chain implications.",
                "signal_type": "competitive_threat",
                "market_impact": "medium",
                "ticker": "TSM",
                "sentiment": "cautionary",
            },
            "confidence": 0.6,
        },
        
        # AI Regulation Wave
        {
            "entity_name": "EU AI Act",
            "entity_type": EntityType.COMPANY,  # Using company for policy entities
            "category": MEDIA,
            "raw_value": 6.5,
            "raw_data": {
                "source": "X/Twitter (policy discussion)",
                "event": "Global AI Regulation Momentum",
                "headline": "South Korea AI Basic Act may influence EU, US policy",
                "details": "South Korea first with dedicated AI law. Sets precedent for Asia. EU AI Act implementation ongoing. US Gemini government use signals policy direction.",
                "signal_type": "regulatory",
                "market_impact": "medium",
                "related_entities": ["South Korea AI Policy"],
            },
            "confidence": 0.75,
        },
        
        # AI Agent Tooling
        {
            "entity_name": "Claude Code",
            "entity_type": EntityType.TECHNOLOGY,
            "category": PRODUCT,
            "raw_value": 7.5,
            "raw_data": {
                "source": "X/Twitter",
                "event": "Claude Code + Vercel Integration",
                "headline": "Claude Code vs Codex competition heating up",
                "details": "Vercel API ships with Claude Code auto-connect. Zero MCP setup. Developer tooling race between Claude Code and OpenAI Codex.",
                "signal_type": "product_integration",
                "market_impact": "medium",
                "related_entities": ["Vercel", "Anthropic", "OpenAI"],
            },
            "confidence": 0.9,
        },
    ]
    
    print(f"Adding {len(signals)} deep-dive signals...")
    print("=" * 60)
    
    for sig in signals:
        entity = store.get_or_create_entity(
            name=sig["entity_name"],
            entity_type=sig["entity_type"],
        )
        print(f"Entity: {entity.name}")
        
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
        
        headline = sig['raw_data'].get('headline', 'Signal')[:55]
        print(f"  -> {headline}...")
        
        score = SignalScore(
            id=str(uuid.uuid4()),
            observation_id=obs.id,
            entity_id=entity.id,
            source_id=x_source_id,
            category=sig["category"],
            score=sig["raw_value"] * 10,
            percentile=None,
            score_delta_7d=None,
            score_delta_30d=None,
        )
        store.add_score(score)
    
    print("=" * 60)
    print(f"Added {len(signals)} deep-dive signals")
    print("\nTotal entities with X signals now in briefAI:")
    
    # Count unique entities
    import sqlite3
    conn = sqlite3.connect('data/signals.db')
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(DISTINCT entity_id) FROM signal_observations 
        WHERE source_id LIKE 'x_twitter%'
    ''')
    count = c.fetchone()[0]
    print(f"  {count} entities with X/Twitter signals")


if __name__ == "__main__":
    add_deep_signals()
