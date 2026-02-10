"""
Import Chinese AI companies from trend_radar.db into signals.db.

Sources:
- HongShan (红杉中国): 147 companies
- Matrix China: 149 companies
- ZhenFund (真格基金): 56 companies
- Qiming (启明创投): 50 companies
- 5Y Capital (五源资本): 35 companies
- Baidu Ventures (百度风投): 33 companies
- Sinovation (创新工场): 23 companies
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any
import json

# Add parent to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_models import (
    Entity, EntityType, SignalCategory, SignalObservation, SignalScore,
    normalize_entity_id
)
from utils.signal_store import SignalStore
from utils.signal_scorers import CompanyScorer


# Chinese VC source IDs in trend_radar.db
CHINESE_VC_SOURCES = [
    ('sinovation_ventures', 'Sinovation Ventures', 0.85),
    ('qiming_ventures', 'Qiming Venture Partners', 0.85),
    ('zhenfund', 'ZhenFund', 0.80),
    ('matrix_china', 'Matrix Partners China', 0.90),
    ('5y_capital', '5Y Capital', 0.80),
    ('baidu_ventures', 'Baidu Ventures', 0.85),
    ('hongshan_china', 'HongShan', 0.95),
    ('sourcecode_capital', 'Source Code Capital', 0.80),
]


def get_trend_radar_companies() -> List[Dict[str, Any]]:
    """Get Chinese AI companies from trend_radar.db."""
    db_path = Path(__file__).parent.parent / ".worktrees" / "trend-radar" / "data" / "trend_radar.db"

    if not db_path.exists():
        print(f"trend_radar.db not found at {db_path}")
        return []

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    companies = []
    source_ids = [s[0] for s in CHINESE_VC_SOURCES]
    placeholders = ','.join(['?' for _ in source_ids])

    # Get companies with their VC backers
    cursor.execute(f'''
        SELECT
            c.id,
            c.name,
            c.normalized_name,
            c.source_count,
            c.first_seen_global,
            c.last_seen_global,
            GROUP_CONCAT(o.source_id) as sources
        FROM companies c
        JOIN observations o ON c.id = o.company_id
        WHERE o.source_id IN ({placeholders})
        GROUP BY c.id
        ORDER BY c.source_count DESC, c.name
    ''', source_ids)

    for row in cursor.fetchall():
        companies.append({
            'id': row[0],
            'name': row[1],
            'normalized_name': row[2],
            'source_count': row[3],
            'first_seen': row[4],
            'last_seen': row[5],
            'vc_sources': row[6].split(',') if row[6] else [],
        })

    conn.close()
    return companies


def import_to_signals_db(
    data_dir: Path = None,
    db_path: Path = None,
) -> Dict[str, int]:
    """
    Import Chinese VC portfolio companies into signals.db.

    Returns:
        Dict with import statistics
    """
    data_dir = data_dir or Path(__file__).parent.parent / "data"
    db_path = db_path or data_dir / "signals.db"

    store = SignalStore(db_path)
    scorer = CompanyScorer()

    companies = get_trend_radar_companies()
    print(f"Found {len(companies)} Chinese AI companies from VCs")

    entities_created = 0
    observations_created = 0
    scores_created = 0

    for company in companies:
        name = company['name'].strip()
        if not name or len(name) < 2:
            continue

        # Skip navigation/UI elements
        skip_names = ['companies', 'portfolio', 'home', 'about', 'team', 'news', 'menu', 'all', 'founded']
        if name.lower() in skip_names:
            continue

        canonical_id = normalize_entity_id(name)

        # Create entity
        entity = Entity(
            canonical_id=canonical_id,
            name=name,
            entity_type=EntityType.COMPANY,
        )
        store.upsert_entity(entity)
        entities_created += 1

        # Calculate score based on VC coverage
        num_vcs = len(company['vc_sources'])
        vc_names = company['vc_sources']

        # Higher score for more VC coverage and top-tier VCs
        base_score = min(num_vcs * 20, 60)  # Up to 60 for 3+ VCs

        # Bonus for top-tier VCs
        tier1_vcs = ['hongshan_china', 'matrix_china', 'qiming_ventures']
        has_tier1 = any(vc in tier1_vcs for vc in vc_names)
        if has_tier1:
            base_score += 20

        # Bonus for Baidu/Sinovation (AI-focused)
        ai_vcs = ['baidu_ventures', 'sinovation_ventures']
        has_ai_vc = any(vc in ai_vcs for vc in vc_names)
        if has_ai_vc:
            base_score += 10

        score_value = min(base_score, 100)

        raw_data = {
            'source': 'chinese_vc_portfolio',
            'vc_count': num_vcs,
            'vc_sources': vc_names,
            'first_seen': company['first_seen'],
            'last_seen': company['last_seen'],
        }

        observation = SignalObservation(
            entity_id=entity.id,
            source_id='chinese_vc_aggregate',
            category=SignalCategory.COMPANY_PRESENCE,
            raw_value=num_vcs,
            raw_value_unit='vc_count',
            raw_data=raw_data,
            confidence=0.85,
        )
        store.add_observation(observation)
        observations_created += 1

        score = SignalScore(
            observation_id=observation.id,
            entity_id=entity.id,
            source_id='chinese_vc_aggregate',
            category=SignalCategory.COMPANY_PRESENCE,
            score=score_value,
        )
        store.add_score(score)
        scores_created += 1

    print(f"Imported {entities_created} entities, {observations_created} observations, {scores_created} scores")
    return {
        'entities': entities_created,
        'observations': observations_created,
        'scores': scores_created,
    }


def main():
    print("=" * 60)
    print("IMPORTING CHINESE AI COMPANIES")
    print("=" * 60)
    print()

    # Show available companies
    companies = get_trend_radar_companies()

    print(f"Total Chinese VC portfolio companies: {len(companies)}")
    print()

    # Group by VC
    from collections import defaultdict
    by_vc = defaultdict(list)
    for c in companies:
        for vc in c['vc_sources']:
            by_vc[vc].append(c['name'])

    print("Companies by VC:")
    for vc, names in sorted(by_vc.items(), key=lambda x: -len(x[1])):
        print(f"  {vc}: {len(names)} companies")

    print()
    print("Sample companies (multi-VC backed):")
    multi_vc = [c for c in companies if len(c['vc_sources']) >= 2]
    for c in multi_vc[:15]:
        print(f"  - {c['name']} ({len(c['vc_sources'])} VCs: {', '.join(c['vc_sources'][:3])})")

    print()
    print("=" * 60)
    print("RUNNING IMPORT")
    print("=" * 60)

    results = import_to_signals_db()

    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Entities created: {results['entities']}")
    print(f"Observations: {results['observations']}")
    print(f"Scores: {results['scores']}")


if __name__ == "__main__":
    main()
