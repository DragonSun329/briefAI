"""
Hypothesis Renderer - Report-Ready Output Helper.

Part of Hypothesis Engine v2.0.

Converts hypothesis bundles into structured JSON for daily reports,
dashboards, and downstream consumers.

Usage:
    from utils.hypothesis_renderer import render_hypothesis_summary
    
    summary = render_hypothesis_summary(bundle)
    # Returns structured JSON ready for reports

No UI formatting - just structured data.
"""

import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger


# =============================================================================
# RENDERER FUNCTIONS
# =============================================================================

def render_hypothesis_summary(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """
    Render a hypothesis bundle into a concise daily-report structure.
    
    Args:
        bundle: MetaHypothesisBundle as dict (from bundle.to_dict())
    
    Returns:
        Structured JSON for report inclusion:
        {
            "concept_name": str,
            "confidence": float,
            "main_hypothesis": {
                "title": str,
                "mechanism": str,
                "claim": str,
                "predicted_signals": [...]
            },
            "falsifiers": [...],
            "watchlist": [...]
        }
    """
    if not bundle:
        return {
            'concept_name': 'Unknown',
            'confidence': 0.0,
            'main_hypothesis': None,
            'falsifiers': [],
            'watchlist': [],
        }
    
    concept_name = bundle.get('concept_name', 'Unknown')
    bundle_confidence = bundle.get('bundle_confidence', 0.0)
    hypotheses = bundle.get('hypotheses', [])
    watchlist = bundle.get('what_to_watch_next', [])
    
    # Get the selected (top) hypothesis
    main_hyp = None
    falsifiers = []
    
    if hypotheses:
        # Find selected hypothesis or use first
        selected_id = bundle.get('selected_hypothesis_id', '')
        top_hyp = hypotheses[0]
        
        for h in hypotheses:
            if h.get('hypothesis_id') == selected_id:
                top_hyp = h
                break
        
        main_hyp = {
            'title': top_hyp.get('title', ''),
            'mechanism': top_hyp.get('mechanism', ''),
            'claim': top_hyp.get('claim', ''),
            'why_now': top_hyp.get('why_now', ''),
            'confidence': top_hyp.get('confidence', 0.0),
            'review_required': top_hyp.get('review_required', False),
            'predicted_signals': [
                {
                    'category': p.get('category', ''),
                    'description': p.get('description', ''),
                    'timeframe_days': p.get('expected_timeframe_days', 14),
                    'metric': p.get('metric', ''),
                    'direction': p.get('direction', ''),
                    'speculative': p.get('speculative', False),
                }
                for p in top_hyp.get('predicted_next_signals', [])
            ],
        }
        
        falsifiers = top_hyp.get('falsifiers', [])
    
    return {
        'concept_name': concept_name,
        'confidence': bundle_confidence,
        'main_hypothesis': main_hyp,
        'falsifiers': falsifiers,
        'watchlist': watchlist,
    }


def render_daily_report(bundles: List[Dict[str, Any]], date: str = None) -> Dict[str, Any]:
    """
    Render multiple bundles into a complete daily report structure.
    
    Args:
        bundles: List of MetaHypothesisBundle dicts
        date: Date string (defaults to today)
    
    Returns:
        Complete daily report JSON:
        {
            "date": str,
            "generated_at": str,
            "summary": {...},
            "hypotheses": [...]
        }
    """
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    
    summaries = []
    total_confidence = 0.0
    mechanisms_used = {}
    review_count = 0
    
    for bundle in bundles:
        summary = render_hypothesis_summary(bundle)
        summaries.append(summary)
        
        # Aggregate stats
        total_confidence += summary['confidence']
        
        if summary['main_hypothesis']:
            mech = summary['main_hypothesis']['mechanism']
            mechanisms_used[mech] = mechanisms_used.get(mech, 0) + 1
            
            if summary['main_hypothesis']['review_required']:
                review_count += 1
    
    avg_confidence = total_confidence / len(bundles) if bundles else 0.0
    
    return {
        'date': date,
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_hypotheses': len(summaries),
            'average_confidence': round(avg_confidence, 3),
            'requiring_review': review_count,
            'mechanisms': mechanisms_used,
        },
        'hypotheses': summaries,
    }


def render_watchlist_aggregate(bundles: List[Dict[str, Any]], top_n: int = 10) -> List[Dict[str, Any]]:
    """
    Aggregate watchlist items across all bundles.
    
    Args:
        bundles: List of MetaHypothesisBundle dicts
        top_n: Maximum items to return
    
    Returns:
        List of watchlist items with source context:
        [
            {
                "item": str,
                "source_concept": str,
                "confidence": float
            },
            ...
        ]
    """
    all_items = []
    
    for bundle in bundles:
        concept = bundle.get('concept_name', 'Unknown')
        confidence = bundle.get('bundle_confidence', 0.0)
        watchlist = bundle.get('what_to_watch_next', [])
        
        for item in watchlist:
            all_items.append({
                'item': item,
                'source_concept': concept,
                'confidence': confidence,
            })
    
    # Sort by confidence descending
    all_items.sort(key=lambda x: x['confidence'], reverse=True)
    
    # Deduplicate similar items
    seen = set()
    unique_items = []
    
    for item in all_items:
        normalized = item['item'].lower()[:40]
        if normalized not in seen:
            seen.add(normalized)
            unique_items.append(item)
            if len(unique_items) >= top_n:
                break
    
    return unique_items


def render_mechanism_breakdown(bundles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Render mechanism breakdown for analysis.
    
    Args:
        bundles: List of MetaHypothesisBundle dicts
    
    Returns:
        Mechanism analysis structure:
        {
            "by_mechanism": {
                "enterprise_adoption": {
                    "count": int,
                    "avg_confidence": float,
                    "concepts": [str]
                },
                ...
            },
            "total": int
        }
    """
    mechanism_data = {}
    
    for bundle in bundles:
        hypotheses = bundle.get('hypotheses', [])
        if not hypotheses:
            continue
        
        top_hyp = hypotheses[0]
        mechanism = top_hyp.get('mechanism', 'unknown')
        confidence = top_hyp.get('confidence', 0.0)
        concept = bundle.get('concept_name', 'Unknown')
        
        if mechanism not in mechanism_data:
            mechanism_data[mechanism] = {
                'count': 0,
                'total_confidence': 0.0,
                'concepts': [],
            }
        
        mechanism_data[mechanism]['count'] += 1
        mechanism_data[mechanism]['total_confidence'] += confidence
        mechanism_data[mechanism]['concepts'].append(concept)
    
    # Compute averages
    result = {}
    for mech, data in mechanism_data.items():
        avg_conf = data['total_confidence'] / data['count'] if data['count'] > 0 else 0.0
        result[mech] = {
            'count': data['count'],
            'avg_confidence': round(avg_conf, 3),
            'concepts': data['concepts'][:5],  # Limit to 5 examples
        }
    
    return {
        'by_mechanism': result,
        'total': len(bundles),
    }


def render_confidence_tiers(bundles: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group bundles by confidence tier.
    
    Args:
        bundles: List of MetaHypothesisBundle dicts
    
    Returns:
        Tiered structure:
        {
            "high": [...],    # confidence >= 0.7
            "medium": [...],  # 0.5 <= confidence < 0.7
            "low": [...]      # confidence < 0.5
        }
    """
    tiers = {
        'high': [],
        'medium': [],
        'low': [],
    }
    
    for bundle in bundles:
        confidence = bundle.get('bundle_confidence', 0.0)
        summary = {
            'concept_name': bundle.get('concept_name', 'Unknown'),
            'confidence': confidence,
            'mechanism': bundle.get('hypotheses', [{}])[0].get('mechanism', 'unknown') if bundle.get('hypotheses') else 'none',
        }
        
        if confidence >= 0.7:
            tiers['high'].append(summary)
        elif confidence >= 0.5:
            tiers['medium'].append(summary)
        else:
            tiers['low'].append(summary)
    
    # Sort each tier by confidence
    for tier in tiers.values():
        tier.sort(key=lambda x: x['confidence'], reverse=True)
    
    return tiers


def render_evidence_quality_report(bundles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Render evidence quality analysis.
    
    Args:
        bundles: List of MetaHypothesisBundle dicts
    
    Returns:
        Evidence quality structure:
        {
            "strong_evidence": int,
            "moderate_evidence": int,
            "weak_evidence": int,
            "speculative_predictions_total": int,
            "observable_predictions_total": int
        }
    """
    strong = 0
    moderate = 0
    weak = 0
    speculative_count = 0
    observable_count = 0
    
    for bundle in bundles:
        confidence = bundle.get('bundle_confidence', 0.0)
        
        # Classify evidence strength
        if confidence >= 0.75:
            strong += 1
        elif confidence >= 0.55:
            moderate += 1
        else:
            weak += 1
        
        # Count prediction types
        for hyp in bundle.get('hypotheses', []):
            for pred in hyp.get('predicted_next_signals', []):
                if pred.get('speculative', False):
                    speculative_count += 1
                if pred.get('metric') or pred.get('direction'):
                    observable_count += 1
    
    return {
        'strong_evidence': strong,
        'moderate_evidence': moderate,
        'weak_evidence': weak,
        'speculative_predictions_total': speculative_count,
        'observable_predictions_total': observable_count,
    }


# =============================================================================
# FILE I/O HELPERS
# =============================================================================

def load_hypothesis_bundles(path: Path) -> List[Dict[str, Any]]:
    """
    Load hypothesis bundles from JSON file.
    
    Args:
        path: Path to hypotheses JSON file
    
    Returns:
        List of bundle dicts
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('bundles', [])
    except Exception as e:
        logger.error(f"Failed to load hypothesis bundles from {path}: {e}")
        return []


def save_rendered_report(report: Dict[str, Any], output_path: Path) -> bool:
    """
    Save rendered report to JSON file.
    
    Args:
        report: Report dict to save
        output_path: Output file path
    
    Returns:
        True if successful
    """
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved rendered report to {output_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save report to {output_path}: {e}")
        return False


# =============================================================================
# CLI
# =============================================================================

def main():
    """CLI for hypothesis renderer."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Render hypothesis bundles into report formats')
    parser.add_argument('input', type=Path, help='Input hypotheses JSON file')
    parser.add_argument('--output', '-o', type=Path, help='Output file (default: stdout)')
    parser.add_argument('--format', '-f', choices=['summary', 'daily', 'watchlist', 'mechanisms', 'tiers', 'quality'],
                       default='daily', help='Output format')
    args = parser.parse_args()
    
    # Load bundles
    bundles = load_hypothesis_bundles(args.input)
    if not bundles:
        print(f"No bundles found in {args.input}")
        return 1
    
    # Render based on format
    if args.format == 'summary':
        # Single bundle summary (use first)
        result = render_hypothesis_summary(bundles[0])
    elif args.format == 'daily':
        result = render_daily_report(bundles)
    elif args.format == 'watchlist':
        result = {'watchlist': render_watchlist_aggregate(bundles)}
    elif args.format == 'mechanisms':
        result = render_mechanism_breakdown(bundles)
    elif args.format == 'tiers':
        result = render_confidence_tiers(bundles)
    elif args.format == 'quality':
        result = render_evidence_quality_report(bundles)
    else:
        result = render_daily_report(bundles)
    
    # Output
    if args.output:
        save_rendered_report(result, args.output)
    else:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0


if __name__ == '__main__':
    exit(main())
