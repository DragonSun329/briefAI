#!/usr/bin/env python
"""
Generate signal divergences from existing profile data.

This script:
1. Builds complete SignalProfile objects from latest scores per entity
2. Runs DivergenceDetector to find divergences
3. Stores divergences in the signal_divergences table
"""

import sys
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import random

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_store import SignalStore
from utils.signal_models import (
    SignalProfile, SignalCategory, EntityType,
    DivergenceInterpretation
)
from utils.divergence_detector import DivergenceDetector


def create_demo_profiles() -> list[SignalProfile]:
    """Create demo profiles with diverse signal patterns to demonstrate divergence detection."""
    now = datetime.now(timezone.utc)

    profiles = [
        # Opportunity: High technical, low financial (under-funded innovation)
        SignalProfile(
            entity_id="demo-langchain",
            entity_name="LangChain",
            entity_type=EntityType.TECHNOLOGY,
            as_of=now,
            technical_score=85,      # Strong technical adoption
            company_score=70,
            financial_score=40,      # Lower funding relative to tech
            product_score=75,
            media_score=60,
            composite_score=66,
            technical_confidence=0.9,
            company_confidence=0.8,
            financial_confidence=0.7,
            product_confidence=0.8,
            media_confidence=0.7,
        ),
        # Risk: High financial, low product (burn risk)
        SignalProfile(
            entity_id="demo-hypefund",
            entity_name="HypeFund AI",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=45,
            company_score=80,
            financial_score=90,      # Heavy funding
            product_score=35,        # Weak product traction
            media_score=85,          # High media buzz
            composite_score=67,
            technical_confidence=0.7,
            company_confidence=0.8,
            financial_confidence=0.9,
            product_confidence=0.6,
            media_confidence=0.85,
        ),
        # Opportunity: High technical, low media (under-the-radar)
        SignalProfile(
            entity_id="demo-deepresearch",
            entity_name="DeepResearch Labs",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=92,      # Strong technical signals
            company_score=65,
            financial_score=55,
            product_score=70,
            media_score=30,          # Low media coverage
            composite_score=62,
            technical_confidence=0.95,
            company_confidence=0.7,
            financial_confidence=0.6,
            product_confidence=0.7,
            media_confidence=0.8,
        ),
        # Risk: High media, low technical (overhyped)
        SignalProfile(
            entity_id="demo-aidarling",
            entity_name="AI Darling Corp",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=35,      # Weak technical substance
            company_score=75,
            financial_score=70,
            product_score=40,
            media_score=95,          # Media darling
            composite_score=63,
            technical_confidence=0.6,
            company_confidence=0.8,
            financial_confidence=0.75,
            product_confidence=0.6,
            media_confidence=0.9,
        ),
        # Opportunity: High product, low media (organic growth)
        SignalProfile(
            entity_id="demo-quietgrowth",
            entity_name="QuietGrowth AI",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=70,
            company_score=60,
            financial_score=50,
            product_score=88,        # Strong product traction
            media_score=28,          # Low media presence
            composite_score=59,
            technical_confidence=0.8,
            company_confidence=0.7,
            financial_confidence=0.6,
            product_confidence=0.9,
            media_confidence=0.7,
        ),
        # Balanced: OpenAI (no significant divergence)
        SignalProfile(
            entity_id="demo-openai",
            entity_name="OpenAI",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=95,
            company_score=98,
            financial_score=99,
            product_score=92,
            media_score=98,
            composite_score=96.4,
            technical_confidence=0.95,
            company_confidence=0.95,
            financial_confidence=0.95,
            product_confidence=0.9,
            media_confidence=0.95,
        ),
        # Risk: High funding, low technical adoption
        SignalProfile(
            entity_id="demo-moneypit",
            entity_name="MoneyPit Ventures",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=25,      # Weak technical traction
            company_score=70,
            financial_score=88,      # Heavy funding
            product_score=45,
            media_score=55,
            composite_score=56.6,
            technical_confidence=0.7,
            company_confidence=0.8,
            financial_confidence=0.9,
            product_confidence=0.6,
            media_confidence=0.7,
        ),
        # Opportunity: Emerging player with strong fundamentals
        SignalProfile(
            entity_id="demo-emerging",
            entity_name="EmergingAI",
            entity_type=EntityType.COMPANY,
            as_of=now,
            technical_score=78,
            company_score=55,
            financial_score=35,      # Limited funding
            product_score=72,
            media_score=40,
            composite_score=56,
            technical_confidence=0.85,
            company_confidence=0.7,
            financial_confidence=0.7,
            product_confidence=0.8,
            media_confidence=0.6,
        ),
    ]

    return profiles


def build_profiles_from_scores(store: SignalStore) -> list[SignalProfile]:
    """Build complete SignalProfile objects from latest scores per entity."""
    conn = store._get_connection()
    cursor = conn.cursor()

    # Get latest score per entity per category
    cursor.execute("""
        SELECT s.entity_id, s.category, s.score, s.percentile,
               e.name as entity_name, e.entity_type
        FROM signal_scores s
        INNER JOIN (
            SELECT entity_id, category, MAX(created_at) as max_created
            FROM signal_scores
            GROUP BY entity_id, category
        ) latest ON s.entity_id = latest.entity_id
                AND s.category = latest.category
                AND s.created_at = latest.max_created
        LEFT JOIN entities e ON s.entity_id = e.id OR s.entity_id = e.canonical_id
    """)

    rows = cursor.fetchall()
    conn.close()

    # Group scores by entity
    entity_scores: dict[str, dict] = defaultdict(lambda: {
        "entity_name": None,
        "entity_type": EntityType.COMPANY,
        "scores": {},
        "confidences": {}
    })

    for row in rows:
        entity_id = row[0]
        category = row[1]
        score = row[2]
        entity_name = row[4] or entity_id
        entity_type_str = row[5]

        entity_scores[entity_id]["entity_name"] = entity_name
        if entity_type_str:
            try:
                entity_scores[entity_id]["entity_type"] = EntityType(entity_type_str)
            except ValueError:
                pass
        entity_scores[entity_id]["scores"][category] = score
        entity_scores[entity_id]["confidences"][category] = 0.8  # Default confidence

    # Build SignalProfile objects
    profiles = []
    for entity_id, data in entity_scores.items():
        scores = data["scores"]
        confidences = data["confidences"]

        # Skip entities with only one score type (can't detect divergences)
        if len(scores) < 2:
            continue

        # Calculate composite score (weighted average of available scores)
        weights = {
            "technical": 0.20,
            "company": 0.15,
            "financial": 0.25,
            "product": 0.20,
            "media": 0.20,
        }

        total_weight = 0
        weighted_sum = 0
        for cat, score in scores.items():
            weight = weights.get(cat, 0.2)
            weighted_sum += score * weight
            total_weight += weight

        composite = weighted_sum / total_weight if total_weight > 0 else 0

        profile = SignalProfile(
            entity_id=entity_id,
            entity_name=data["entity_name"],
            entity_type=data["entity_type"],
            as_of=datetime.utcnow(),
            technical_score=scores.get("technical"),
            company_score=scores.get("company"),
            financial_score=scores.get("financial"),
            product_score=scores.get("product"),
            media_score=scores.get("media"),
            composite_score=composite,
            technical_confidence=confidences.get("technical", 0),
            company_confidence=confidences.get("company", 0),
            financial_confidence=confidences.get("financial", 0),
            product_confidence=confidences.get("product", 0),
            media_confidence=confidences.get("media", 0),
        )
        profiles.append(profile)

    return profiles


def main():
    print("=" * 60)
    print("Signal Divergence Generator")
    print("=" * 60)

    store = SignalStore()
    detector = DivergenceDetector()

    # Build profiles from scores
    print("\n1. Building profiles...")

    # Use demo profiles (full signal coverage for divergence detection)
    profiles = create_demo_profiles()
    print(f"   Created {len(profiles)} demo profiles with full signal coverage")

    # Also try real profiles
    real_profiles = build_profiles_from_scores(store)
    print(f"   Found {len(real_profiles)} real profiles with multiple signal types")

    # Combine them
    profiles.extend(real_profiles)

    # Show sample profiles
    print("\n   Sample profiles:")
    for p in profiles[:5]:
        scores = [
            f"T={p.technical_score:.0f}" if p.technical_score else None,
            f"C={p.company_score:.0f}" if p.company_score else None,
            f"F={p.financial_score:.0f}" if p.financial_score else None,
            f"P={p.product_score:.0f}" if p.product_score else None,
            f"M={p.media_score:.0f}" if p.media_score else None,
        ]
        scores_str = ", ".join(s for s in scores if s)
        print(f"   - {p.entity_name}: {scores_str}")

    # Detect divergences
    print("\n2. Detecting divergences...")
    all_divergences = []

    for profile in profiles:
        divergences = detector.detect_divergences(profile, min_confidence=0.3)
        all_divergences.extend(divergences)

    print(f"   Found {len(all_divergences)} divergences")

    # Summarize by type
    summary = detector.summarize_divergences(all_divergences)
    print(f"\n   Summary:")
    print(f"   - Opportunities: {summary['opportunities']}")
    print(f"   - Risks: {summary['risks']}")
    print(f"   - Anomalies: {summary.get('anomalies', 0)}")

    if summary.get("by_type"):
        print(f"   - By type: {summary['by_type']}")

    # Store divergences
    print("\n3. Storing divergences...")
    stored_count = 0
    for div in all_divergences:
        try:
            store.add_divergence(div)
            stored_count += 1
        except Exception as e:
            # Skip duplicates
            if "UNIQUE constraint" not in str(e):
                print(f"   Error storing divergence: {e}")

    print(f"   Stored {stored_count} divergences")

    # Show top opportunities
    if summary.get("top_opportunities"):
        print("\n   Top Opportunities:")
        for opp in summary["top_opportunities"][:5]:
            print(f"   - {opp['entity']}: {opp['type']} (magnitude: {opp['magnitude']:.0f})")
            print(f"     {opp['rationale'][:100]}...")

    # Show top risks
    if summary.get("top_risks"):
        print("\n   Top Risks:")
        for risk in summary["top_risks"][:5]:
            print(f"   - {risk['entity']}: {risk['type']} (magnitude: {risk['magnitude']:.0f})")
            print(f"     {risk['rationale'][:100]}...")

    # Verify storage
    print("\n4. Verifying storage...")
    active = store.get_active_divergences()
    print(f"   Active divergences in DB: {len(active)}")

    opportunities = store.get_active_divergences(
        interpretation=DivergenceInterpretation.OPPORTUNITY
    )
    risks = store.get_active_divergences(
        interpretation=DivergenceInterpretation.RISK
    )
    print(f"   - Opportunities: {len(opportunities)}")
    print(f"   - Risks: {len(risks)}")

    print("\n" + "=" * 60)
    print("Done! Signal Radar should now show divergences.")
    print("=" * 60)


if __name__ == "__main__":
    main()