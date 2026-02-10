#!/usr/bin/env python
"""
Analyst Brief Generator - The First Real Product Surface.

Part of briefAI Phase 1: Make It Useful.

This script reads all internal artifacts and produces ONE human-readable report:
    data/briefs/analyst_brief_YYYY-MM-DD.md

The brief has 4 sections:
1. What Actually Happened (Events) - Top high-confidence event clusters
2. What Is Changing (Trends) - Meta-signals ranked by belief × velocity × independence
3. What We Think Will Happen (Predictions) - Top hypotheses with measurable signals
4. What Changed Today (Belief Updates) - THE KILLER FEATURE

Usage:
    python scripts/generate_analyst_brief.py
    python scripts/generate_analyst_brief.py --date 2026-02-10
    python scripts/generate_analyst_brief.py --output custom_brief.md
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_BRIEFS_DIR = DEFAULT_DATA_DIR / "briefs"

# Limits
MAX_EVENTS = 5
MAX_TRENDS = 7
MAX_PREDICTIONS = 5
MAX_BELIEF_UPDATES = 10


# =============================================================================
# DATA LOADERS
# =============================================================================

def load_json_file(path: Path) -> Optional[Dict]:
    """Load JSON file if it exists."""
    if not path.exists():
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return None


def load_jsonl_file(path: Path) -> List[Dict]:
    """Load JSONL file if it exists."""
    if not path.exists():
        return []
    
    results = []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    results.append(json.loads(line))
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
    
    return results


def load_cluster_feed(data_dir: Path, date: str) -> Optional[Dict]:
    """Load cluster feed for a date."""
    path = data_dir / "clusters" / f"cluster_feed_{date}.json"
    return load_json_file(path)


def load_meta_signals(data_dir: Path, date: str) -> Optional[Dict]:
    """Load meta-signals for a date."""
    path = data_dir / "meta_signals" / f"meta_signals_{date}.json"
    return load_json_file(path)


def load_hypotheses(data_dir: Path, date: str) -> Optional[Dict]:
    """Load hypotheses for a date."""
    path = data_dir / "hypotheses" / f"hypotheses_{date}.json"
    return load_json_file(path)


def load_beliefs(data_dir: Path) -> Dict[str, Dict]:
    """Load current belief states."""
    path = data_dir / "predictions" / "beliefs.json"
    return load_json_file(path) or {}


def load_evidence(data_dir: Path, date: str) -> List[Dict]:
    """Load evidence for a date."""
    path = data_dir / "predictions" / f"evidence_{date}.jsonl"
    return load_jsonl_file(path)


def load_belief_history(data_dir: Path, hypothesis_id: str, days: int = 7) -> List[Dict]:
    """Load recent belief history for a hypothesis."""
    path = data_dir / "predictions" / "belief_history.jsonl"
    
    if not path.exists():
        return []
    
    history = []
    cutoff = datetime.now() - timedelta(days=days)
    
    for entry in load_jsonl_file(path):
        if entry.get('hypothesis_id') != hypothesis_id:
            continue
        
        try:
            ts = datetime.fromisoformat(entry.get('timestamp', ''))
            if ts >= cutoff:
                history.append(entry)
        except Exception:
            pass
    
    return history


# =============================================================================
# SECTION 1: WHAT ACTUALLY HAPPENED (EVENTS)
# =============================================================================

def generate_events_section(cluster_feed: Optional[Dict], max_events: int = MAX_EVENTS) -> str:
    """Generate the Events section from cluster feed."""
    lines = []
    lines.append("## 1. What Actually Happened")
    lines.append("")
    
    if not cluster_feed:
        lines.append("*No cluster data available for today.*")
        lines.append("")
        return "\n".join(lines)
    
    clusters = cluster_feed.get('clusters', [])
    
    if not clusters:
        lines.append("*No significant event clusters detected today.*")
        lines.append("")
        return "\n".join(lines)
    
    # Sort by confidence/signal count
    sorted_clusters = sorted(
        clusters,
        key=lambda c: (c.get('confidence', 0), c.get('signal_count', 0)),
        reverse=True
    )[:max_events]
    
    for i, cluster in enumerate(sorted_clusters, 1):
        title = cluster.get('title', cluster.get('concept_name', 'Untitled'))
        confidence = cluster.get('confidence', 0)
        signal_count = cluster.get('signal_count', 0)
        summary = cluster.get('summary', cluster.get('description', ''))
        
        # Truncate summary
        if len(summary) > 200:
            summary = summary[:197] + "..."
        
        lines.append(f"### {i}. {title}")
        lines.append(f"**Confidence:** {confidence:.0%} | **Signals:** {signal_count}")
        lines.append("")
        if summary:
            lines.append(f"{summary}")
            lines.append("")
        
        # Key sources
        sources = cluster.get('sources', cluster.get('top_sources', []))
        if sources:
            lines.append("**Sources:** " + ", ".join(sources[:3]))
            lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# SECTION 2: WHAT IS CHANGING (TRENDS)
# =============================================================================

def calculate_trend_score(meta: Dict, beliefs: Dict) -> float:
    """
    Calculate trend ranking score.
    
    Score = belief_confidence × velocity × independence_score
    """
    meta_id = meta.get('meta_id', '')
    
    # Get belief confidence (use prior if no belief state)
    belief_state = beliefs.get(meta_id, {})
    confidence = belief_state.get('posterior_confidence', 
                 meta.get('confidence', 0.5))
    
    # Get velocity (rate of change)
    velocity = meta.get('velocity', meta.get('momentum', 1.0))
    
    # Get independence score
    independence = meta.get('independence_score', 
                   meta.get('source_diversity', 0.5))
    
    return confidence * velocity * independence


def generate_trends_section(
    meta_signals: Optional[Dict],
    beliefs: Dict,
    max_trends: int = MAX_TRENDS,
) -> str:
    """Generate the Trends section from meta-signals."""
    lines = []
    lines.append("## 2. What Is Changing")
    lines.append("")
    
    if not meta_signals:
        lines.append("*No meta-signal data available for today.*")
        lines.append("")
        return "\n".join(lines)
    
    metas = meta_signals.get('meta_signals', [])
    
    if not metas:
        lines.append("*No significant trends detected today.*")
        lines.append("")
        return "\n".join(lines)
    
    # Calculate scores and sort
    scored = [
        (meta, calculate_trend_score(meta, beliefs))
        for meta in metas
    ]
    sorted_metas = sorted(scored, key=lambda x: x[1], reverse=True)[:max_trends]
    
    for meta, score in sorted_metas:
        concept = meta.get('concept_name', meta.get('title', 'Unnamed'))
        meta_id = meta.get('meta_id', '')
        
        # Get belief state for trajectory
        belief_state = beliefs.get(meta_id, {})
        posterior = belief_state.get('posterior_confidence')
        prior = belief_state.get('prior_confidence')
        
        # Determine trend direction
        if posterior and prior:
            change = posterior - prior
            if change > 0.02:
                arrow = "↑"
            elif change < -0.02:
                arrow = "↓"
            else:
                arrow = "→"
            confidence_str = f"{prior:.0%} {arrow} {posterior:.0%}"
        else:
            confidence = meta.get('confidence', score)
            confidence_str = f"{confidence:.0%}"
        
        # Categories
        categories = meta.get('categories', [])
        cat_str = ", ".join(categories[:3]) if categories else "general"
        
        lines.append(f"- **{concept}** ({confidence_str})")
        lines.append(f"  - Categories: {cat_str}")
        
        # Key evidence
        evidence = meta.get('key_evidence', meta.get('supporting_signals', []))
        if evidence and isinstance(evidence, list):
            lines.append(f"  - Evidence: {evidence[0] if evidence else 'N/A'}")
        
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# SECTION 3: WHAT WE THINK WILL HAPPEN (PREDICTIONS)
# =============================================================================

def generate_predictions_section(
    hypotheses: Optional[Dict],
    beliefs: Dict,
    max_predictions: int = MAX_PREDICTIONS,
) -> str:
    """Generate the Predictions section from hypotheses."""
    lines = []
    lines.append("## 3. What We Think Will Happen")
    lines.append("")
    
    if not hypotheses:
        lines.append("*No hypothesis data available for today.*")
        lines.append("")
        return "\n".join(lines)
    
    bundles = hypotheses.get('bundles', [])
    
    if not bundles:
        lines.append("*No predictions generated today.*")
        lines.append("")
        return "\n".join(lines)
    
    # Flatten and sort hypotheses by confidence
    all_hyps = []
    for bundle in bundles:
        concept = bundle.get('concept_name', '')
        for hyp in bundle.get('hypotheses', []):
            hyp_id = hyp.get('hypothesis_id', '')
            
            # Get belief-adjusted confidence
            belief_state = beliefs.get(hyp_id, {})
            confidence = belief_state.get('posterior_confidence',
                        hyp.get('confidence', 0.5))
            
            all_hyps.append({
                'concept': concept,
                'hypothesis': hyp,
                'confidence': confidence,
                'hyp_id': hyp_id,
            })
    
    sorted_hyps = sorted(all_hyps, key=lambda x: x['confidence'], reverse=True)[:max_predictions]
    
    for item in sorted_hyps:
        hyp = item['hypothesis']
        concept = item['concept']
        confidence = item['confidence']
        
        title = hyp.get('title', 'Untitled')
        mechanism = hyp.get('mechanism', 'unknown')
        
        lines.append(f"### {title}")
        lines.append(f"**Concept:** {concept}")
        lines.append(f"**Confidence:** {confidence:.0%} | **Mechanism:** {mechanism}")
        lines.append("")
        
        # Predicted signals
        predictions = hyp.get('predicted_next_signals', [])
        if predictions:
            lines.append("**What to watch:**")
            for pred in predictions[:3]:
                category = pred.get('category', '')
                desc = pred.get('description', '')
                timeframe = pred.get('expected_timeframe_days', '?')
                measurable = "📊" if pred.get('measurable', False) else "📝"
                
                lines.append(f"- {measurable} [{category}] {desc} ({timeframe}d)")
            lines.append("")
        
        # Falsifiers
        falsifiers = hyp.get('falsifiers', [])
        if falsifiers:
            lines.append("**Would be wrong if:**")
            for f in falsifiers[:2]:
                if isinstance(f, dict):
                    lines.append(f"- {f.get('description', f)}")
                else:
                    lines.append(f"- {f}")
            lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# SECTION 4: WHAT CHANGED TODAY (BELIEF UPDATES) — THE KILLER FEATURE
# =============================================================================

def generate_belief_updates_section(
    evidence: List[Dict],
    beliefs: Dict,
    hypotheses: Optional[Dict],
    max_updates: int = MAX_BELIEF_UPDATES,
) -> str:
    """
    Generate the Belief Updates section.
    
    THIS IS THE KILLER FEATURE.
    
    Shows which beliefs changed and why.
    """
    lines = []
    lines.append("## 4. What Changed Today")
    lines.append("")
    lines.append("*Belief updates based on today's evidence.*")
    lines.append("")
    
    if not evidence:
        lines.append("*No new evidence collected today.*")
        lines.append("")
        return "\n".join(lines)
    
    # Build hypothesis title lookup
    hyp_titles = {}
    hyp_concepts = {}
    if hypotheses:
        for bundle in hypotheses.get('bundles', []):
            concept = bundle.get('concept_name', '')
            for hyp in bundle.get('hypotheses', []):
                hyp_id = hyp.get('hypothesis_id', '')
                hyp_titles[hyp_id] = hyp.get('title', 'Untitled')
                hyp_concepts[hyp_id] = concept
    
    # Group evidence by hypothesis
    evidence_by_hyp: Dict[str, List[Dict]] = defaultdict(list)
    for e in evidence:
        hyp_id = e.get('hypothesis_id', '')
        evidence_by_hyp[hyp_id].append(e)
    
    # Calculate belief changes
    updates = []
    for hyp_id, ev_list in evidence_by_hyp.items():
        belief_state = beliefs.get(hyp_id, {})
        
        prior = belief_state.get('prior_confidence', 0.5)
        posterior = belief_state.get('posterior_confidence', prior)
        change = posterior - prior
        
        # Skip if no significant change
        if abs(change) < 0.01:
            continue
        
        # Summarize evidence
        support_count = sum(1 for e in ev_list if e.get('direction') == 'support')
        contradict_count = sum(1 for e in ev_list if e.get('direction') == 'contradict')
        
        # Find strongest evidence
        strongest = max(ev_list, key=lambda e: abs(e.get('evidence_score', 0)))
        
        updates.append({
            'hyp_id': hyp_id,
            'title': hyp_titles.get(hyp_id, hyp_id),
            'concept': hyp_concepts.get(hyp_id, ''),
            'prior': prior,
            'posterior': posterior,
            'change': change,
            'support_count': support_count,
            'contradict_count': contradict_count,
            'strongest': strongest,
            'evidence_count': len(ev_list),
        })
    
    # Sort by absolute change
    sorted_updates = sorted(updates, key=lambda x: abs(x['change']), reverse=True)[:max_updates]
    
    if not sorted_updates:
        lines.append("*No significant belief changes today.*")
        lines.append("")
        return "\n".join(lines)
    
    for update in sorted_updates:
        title = update['title']
        concept = update['concept']
        prior = update['prior']
        posterior = update['posterior']
        change = update['change']
        
        # Direction arrow
        if change > 0:
            arrow = "↑"
            direction = "strengthened"
        else:
            arrow = "↓"
            direction = "weakened"
        
        lines.append(f"### {title}")
        if concept:
            lines.append(f"*{concept}*")
        lines.append("")
        
        # The money line
        lines.append(f"**Confidence: {prior:.0%} {arrow} {posterior:.0%}** ({change:+.0%})")
        lines.append("")
        
        # Reason
        strongest = update['strongest']
        metric = strongest.get('canonical_metric', 'unknown')
        pct_change = strongest.get('percent_change', 0)
        entity = strongest.get('entity', '')
        
        if pct_change:
            pct_str = f"{pct_change:+.0%}" if isinstance(pct_change, float) else str(pct_change)
        else:
            pct_str = "changed"
        
        reason = f"{entity} {metric.replace('_', ' ')} {pct_str}"
        lines.append(f"**Reason:** {reason}")
        lines.append("")
        
        # Evidence summary
        support = update['support_count']
        contradict = update['contradict_count']
        total = update['evidence_count']
        
        lines.append(f"**Evidence:** {support} supporting, {contradict} contradicting ({total} total)")
        lines.append("")
    
    return "\n".join(lines)


# =============================================================================
# BRIEF GENERATOR
# =============================================================================

class AnalystBriefGenerator:
    """Generates the daily analyst brief."""
    
    def __init__(self, data_dir: Path = None, output_dir: Path = None):
        """Initialize generator."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        if output_dir is None:
            output_dir = DEFAULT_BRIEFS_DIR
        
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, date: str = None) -> Tuple[str, Path]:
        """
        Generate the analyst brief for a date.
        
        Args:
            date: Date string (YYYY-MM-DD), defaults to today
        
        Returns:
            Tuple of (brief content, output path)
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"Generating analyst brief for {date}")
        
        # Load all data sources
        cluster_feed = load_cluster_feed(self.data_dir, date)
        meta_signals = load_meta_signals(self.data_dir, date)
        hypotheses = load_hypotheses(self.data_dir, date)
        beliefs = load_beliefs(self.data_dir)
        evidence = load_evidence(self.data_dir, date)
        
        # Build the brief
        sections = []
        
        # Header
        sections.append(self._generate_header(date))
        
        # Section 1: What Actually Happened
        sections.append(generate_events_section(cluster_feed))
        
        # Section 2: What Is Changing
        sections.append(generate_trends_section(meta_signals, beliefs))
        
        # Section 3: What We Think Will Happen
        sections.append(generate_predictions_section(hypotheses, beliefs))
        
        # Section 4: What Changed Today (THE KILLER FEATURE)
        sections.append(generate_belief_updates_section(evidence, beliefs, hypotheses))
        
        # Section 5: Recommended Actions (Phase 2)
        sections.append(self._generate_actions_section(beliefs, hypotheses))
        
        # Section 6: System Calibration (Phase 3)
        sections.append(self._generate_calibration_section())
        
        # Footer
        sections.append(self._generate_footer(date))
        
        # Combine
        brief = "\n".join(sections)
        
        # Write to file
        output_path = self.output_dir / f"analyst_brief_{date}.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(brief)
        
        logger.info(f"Wrote analyst brief to {output_path}")
        
        return brief, output_path
    
    def _generate_header(self, date: str) -> str:
        """Generate brief header."""
        lines = []
        lines.append(f"# briefAI Analyst Brief")
        lines.append(f"**Date:** {date}")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)
    
    def _generate_actions_section(
        self,
        beliefs: Dict,
        hypotheses: Optional[Dict],
    ) -> str:
        """Generate recommended actions section."""
        try:
            from utils.decision_engine import DecisionEngine, generate_actions_section
            
            engine = DecisionEngine()
            
            # Flatten hypotheses for engine
            hyp_list = []
            if hypotheses:
                for bundle in hypotheses.get('bundles', []):
                    hyp_list.extend(bundle.get('hypotheses', []))
            
            recommendations = engine.generate_recommendations(beliefs, hyp_list)
            consolidated = engine.consolidate_recommendations(recommendations)
            
            return generate_actions_section(consolidated)
            
        except ImportError:
            return "## 5. Recommended Actions\n\n*Decision engine not available.*\n\n"
        except Exception as e:
            logger.warning(f"Failed to generate actions: {e}")
            return "## 5. Recommended Actions\n\n*Error generating recommendations.*\n\n"
    
    def _generate_calibration_section(self) -> str:
        """Generate calibration section."""
        try:
            from utils.forecast_calibration import (
                ForecastCalibrator,
                generate_calibration_section,
            )
            
            calibrator = ForecastCalibrator(self.data_dir)
            return generate_calibration_section(calibrator.state)
            
        except ImportError:
            return "## 6. System Calibration\n\n*Calibration engine not available.*\n\n"
        except Exception as e:
            logger.warning(f"Failed to generate calibration: {e}")
            return "## 6. System Calibration\n\n*Error loading calibration.*\n\n"
    
    def _generate_footer(self, date: str) -> str:
        """Generate brief footer."""
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("*This brief was generated by briefAI. Confidence scores are calibrated based on historical accuracy.*")
        lines.append("")
        lines.append(f"*Data as of {date}. Past performance does not guarantee future results.*")
        lines.append("")
        return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate daily analyst brief",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate today's brief
    python scripts/generate_analyst_brief.py
    
    # Generate for specific date
    python scripts/generate_analyst_brief.py --date 2026-02-10
    
    # Custom output
    python scripts/generate_analyst_brief.py --output my_brief.md
        """
    )
    
    parser.add_argument(
        '--date', '-d',
        type=str,
        default=None,
        help='Date for brief (YYYY-MM-DD), defaults to today',
    )
    
    parser.add_argument(
        '--output', '-o',
        type=Path,
        default=None,
        help='Custom output path',
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=None,
        help='Override data directory',
    )
    
    parser.add_argument(
        '--print',
        action='store_true',
        help='Print brief to stdout',
    )
    
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()
    
    generator = AnalystBriefGenerator(
        data_dir=args.data_dir,
        output_dir=args.output.parent if args.output else None,
    )
    
    brief, output_path = generator.generate(args.date)
    
    if args.print:
        print(brief)
    else:
        print(f"Generated: {output_path}")
        print(f"Size: {len(brief)} characters")


if __name__ == "__main__":
    main()
