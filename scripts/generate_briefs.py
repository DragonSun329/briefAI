#!/usr/bin/env python
"""
Generate Split Briefs - Strategy Intelligence vs Market Intelligence.

Two products from the same engine:

Product A — Strategy Intelligence (Companies)
    Audience: corporate strategy, product managers, startup founders
    They care about: trends, technology direction, adoption curves
    They read: What is changing

Product B — Market Intelligence (Investors)
    Audience: hedge funds, VCs, public equities analysts
    They care about: timing, lead indicators, capital flows
    They read: What to do

Outputs:
    data/briefs/strategy_brief_YYYY-MM-DD.md
    data/briefs/investor_brief_YYYY-MM-DD.md

Usage:
    python scripts/generate_briefs.py
    python scripts/generate_briefs.py --type strategy
    python scripts/generate_briefs.py --type investor
    python scripts/generate_briefs.py --date 2026-02-10
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

# Import existing modules
from scripts.generate_analyst_brief import (
    load_cluster_feed,
    load_meta_signals,
    load_hypotheses,
    load_beliefs,
    load_evidence,
    generate_events_section,
    generate_trends_section,
    generate_predictions_section,
)

from utils.evidence_ledger import (
    LedgerGenerator,
    generate_evidence_ledger_section,
)

from utils.forecast_scoreboard import (
    ScoreboardGenerator,
    generate_scoreboard_section,
)

from utils.lead_time_tracker import (
    LeadTimeTracker,
    generate_lead_time_section,
)

from utils.decision_engine import (
    DecisionEngine,
    generate_actions_section,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_BRIEFS_DIR = DEFAULT_DATA_DIR / "briefs"


# =============================================================================
# STRATEGY BRIEF GENERATOR
# =============================================================================

class StrategyBriefGenerator:
    """
    Generate Strategy Intelligence Brief.
    
    Audience: corporate strategy, PMs, founders
    Focus: trends, technology direction, adoption curves
    """
    
    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.output_dir = self.data_dir / "briefs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate(self, date: str = None) -> Tuple[str, Path]:
        """Generate strategy brief."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Generating strategy brief for {date}")
        
        # Load data
        cluster_feed = load_cluster_feed(self.data_dir, date)
        meta_signals = load_meta_signals(self.data_dir, date)
        hypotheses = load_hypotheses(self.data_dir, date)
        beliefs = load_beliefs(self.data_dir)
        evidence = load_evidence(self.data_dir, date)
        
        # Build sections
        sections = []
        
        # Header
        sections.append(self._header(date))
        
        # Executive Summary
        sections.append(self._executive_summary(meta_signals, beliefs))
        
        # Section 1: Technology Landscape
        sections.append(self._technology_landscape(cluster_feed))
        
        # Section 2: Trend Analysis (the main focus)
        sections.append(self._trend_analysis(meta_signals, beliefs))
        
        # Section 3: Adoption Signals
        sections.append(self._adoption_signals(hypotheses, beliefs))
        
        # Section 4: Competitive Dynamics
        sections.append(self._competitive_dynamics(meta_signals, cluster_feed))
        
        # Section 5: Strategic Implications
        sections.append(self._strategic_implications(hypotheses, beliefs))
        
        # Footer
        sections.append(self._footer(date))
        
        brief = "\n".join(sections)
        
        output_path = self.output_dir / f"strategy_brief_{date}.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(brief)
        
        logger.info(f"Wrote strategy brief to {output_path}")
        
        return brief, output_path
    
    def _header(self, date: str) -> str:
        lines = []
        lines.append("# Strategy Intelligence Brief")
        lines.append("")
        lines.append(f"**Date:** {date}")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("*For: Corporate Strategy, Product Leadership, Founders*")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)
    
    def _executive_summary(self, meta_signals: Dict, beliefs: Dict) -> str:
        lines = []
        lines.append("## Executive Summary")
        lines.append("")
        
        if not meta_signals:
            lines.append("*No significant trends detected today.*")
            lines.append("")
            return "\n".join(lines)
        
        metas = meta_signals.get("meta_signals", [])[:3]
        
        lines.append("**Key trends to watch:**")
        lines.append("")
        
        for meta in metas:
            concept = meta.get("concept_name", "")
            conf = meta.get("confidence", 0)
            lines.append(f"- {concept} ({conf:.0%} confidence)")
        
        lines.append("")
        return "\n".join(lines)
    
    def _technology_landscape(self, cluster_feed: Dict) -> str:
        lines = []
        lines.append("## 1. Technology Landscape")
        lines.append("")
        lines.append("*What's happening in the market right now*")
        lines.append("")
        
        if not cluster_feed:
            lines.append("*No cluster data available.*")
            lines.append("")
            return "\n".join(lines)
        
        clusters = cluster_feed.get("clusters", [])[:5]
        
        for cluster in clusters:
            title = cluster.get("title", "")
            summary = cluster.get("summary", "")[:150]
            if len(cluster.get("summary", "")) > 150:
                summary += "..."
            
            lines.append(f"**{title}**")
            lines.append(f"> {summary}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _trend_analysis(self, meta_signals: Dict, beliefs: Dict) -> str:
        lines = []
        lines.append("## 2. Trend Analysis")
        lines.append("")
        lines.append("*Where the market is heading*")
        lines.append("")
        
        if not meta_signals:
            lines.append("*No trend data available.*")
            lines.append("")
            return "\n".join(lines)
        
        metas = meta_signals.get("meta_signals", [])
        
        for meta in metas[:7]:
            concept = meta.get("concept_name", "")
            meta_id = meta.get("meta_id", "")
            
            belief = beliefs.get(meta_id, {})
            prior = belief.get("prior_confidence", meta.get("confidence", 0.5))
            posterior = belief.get("posterior_confidence", prior)
            
            # Direction indicator
            change = posterior - prior
            if change > 0.03:
                trend = "Accelerating"
                icon = "↗️"
            elif change < -0.03:
                trend = "Decelerating"
                icon = "↘️"
            else:
                trend = "Stable"
                icon = "➡️"
            
            categories = ", ".join(meta.get("categories", [])[:3])
            
            lines.append(f"### {icon} {concept}")
            lines.append(f"**Trend:** {trend} | **Confidence:** {posterior:.0%}")
            lines.append(f"**Categories:** {categories}")
            lines.append("")
            
            # Key evidence
            evidence = meta.get("key_evidence", [])
            if evidence:
                lines.append("**Evidence:**")
                for e in evidence[:2]:
                    lines.append(f"- {e}")
                lines.append("")
        
        return "\n".join(lines)
    
    def _adoption_signals(self, hypotheses: Dict, beliefs: Dict) -> str:
        lines = []
        lines.append("## 3. Adoption Signals")
        lines.append("")
        lines.append("*Early indicators of market adoption*")
        lines.append("")
        
        if not hypotheses:
            lines.append("*No adoption data available.*")
            lines.append("")
            return "\n".join(lines)
        
        # Focus on enterprise and developer adoption mechanisms
        adoption_mechanisms = ["enterprise_adoption", "developer_adoption", "consumer_adoption"]
        
        for bundle in hypotheses.get("bundles", [])[:5]:
            for hyp in bundle.get("hypotheses", []):
                mechanism = hyp.get("mechanism", "")
                
                if mechanism not in adoption_mechanisms:
                    continue
                
                title = hyp.get("title", "")
                hyp_id = hyp.get("hypothesis_id", "")
                
                belief = beliefs.get(hyp_id, {})
                conf = belief.get("posterior_confidence", hyp.get("confidence", 0.5))
                
                lines.append(f"**{title}** ({conf:.0%})")
                
                predictions = hyp.get("predicted_next_signals", [])
                if predictions:
                    lines.append("Watch for:")
                    for pred in predictions[:2]:
                        desc = pred.get("description", "")
                        timeframe = pred.get("expected_timeframe_days", "?")
                        lines.append(f"- {desc} ({timeframe}d)")
                
                lines.append("")
        
        return "\n".join(lines)
    
    def _competitive_dynamics(self, meta_signals: Dict, cluster_feed: Dict) -> str:
        lines = []
        lines.append("## 4. Competitive Dynamics")
        lines.append("")
        lines.append("*Shifts in competitive positioning*")
        lines.append("")
        
        # Look for competitive-related signals
        competitive_keywords = ["competition", "pricing", "market share", "moat", "differentiation"]
        
        found_any = False
        
        if cluster_feed:
            for cluster in cluster_feed.get("clusters", []):
                title = cluster.get("title", "").lower()
                summary = cluster.get("summary", "").lower()
                
                if any(kw in title or kw in summary for kw in competitive_keywords):
                    found_any = True
                    lines.append(f"- {cluster.get('title', '')}")
        
        if not found_any:
            lines.append("*No significant competitive shifts detected.*")
        
        lines.append("")
        return "\n".join(lines)
    
    def _strategic_implications(self, hypotheses: Dict, beliefs: Dict) -> str:
        lines = []
        lines.append("## 5. Strategic Implications")
        lines.append("")
        lines.append("*What this means for your strategy*")
        lines.append("")
        
        if not hypotheses:
            lines.append("*No strategic implications available.*")
            lines.append("")
            return "\n".join(lines)
        
        # High confidence hypotheses
        high_conf = []
        
        for bundle in hypotheses.get("bundles", []):
            for hyp in bundle.get("hypotheses", []):
                hyp_id = hyp.get("hypothesis_id", "")
                belief = beliefs.get(hyp_id, {})
                conf = belief.get("posterior_confidence", hyp.get("confidence", 0.5))
                
                if conf >= 0.75:
                    high_conf.append({
                        "title": hyp.get("title", ""),
                        "mechanism": hyp.get("mechanism", ""),
                        "confidence": conf,
                    })
        
        if high_conf:
            lines.append("**High-conviction trends:**")
            for h in sorted(high_conf, key=lambda x: x["confidence"], reverse=True)[:5]:
                lines.append(f"- {h['title']} ({h['confidence']:.0%})")
            lines.append("")
        else:
            lines.append("*No high-conviction trends currently.*")
            lines.append("")
        
        return "\n".join(lines)
    
    def _footer(self, date: str) -> str:
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("*This Strategy Intelligence Brief is generated by briefAI.*")
        lines.append("")
        lines.append(f"*Data as of {date}. For strategic planning purposes.*")
        lines.append("")
        return "\n".join(lines)


# =============================================================================
# INVESTOR BRIEF GENERATOR
# =============================================================================

class InvestorBriefGenerator:
    """
    Generate Market Intelligence Brief.
    
    Audience: hedge funds, VCs, public equities analysts
    Focus: timing, lead indicators, capital flows, actions
    """
    
    def __init__(self, data_dir: Path = None):
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.output_dir = self.data_dir / "briefs"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize sub-generators
        self.ledger_generator = LedgerGenerator()
        self.scoreboard_generator = ScoreboardGenerator(data_dir)
        self.lead_time_tracker = LeadTimeTracker(data_dir)
        self.decision_engine = DecisionEngine()
    
    def generate(self, date: str = None) -> Tuple[str, Path]:
        """Generate investor brief."""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        logger.info(f"Generating investor brief for {date}")
        
        # Load data
        cluster_feed = load_cluster_feed(self.data_dir, date)
        meta_signals = load_meta_signals(self.data_dir, date)
        hypotheses = load_hypotheses(self.data_dir, date)
        beliefs = load_beliefs(self.data_dir)
        evidence = load_evidence(self.data_dir, date)
        
        # Build sections
        sections = []
        
        # Header
        sections.append(self._header(date))
        
        # Section 1: Market Signals (quick hits)
        sections.append(self._market_signals(cluster_feed))
        
        # Section 2: Evidence Ledger (THE KILLER FEATURE - auditable updates)
        ledgers = self.ledger_generator.generate_ledgers_from_data(
            evidence, beliefs, hypotheses, date
        )
        sections.append(generate_evidence_ledger_section(ledgers))
        
        # Section 3: Recommended Actions (what to do)
        hyp_list = []
        if hypotheses:
            for bundle in hypotheses.get("bundles", []):
                hyp_list.extend(bundle.get("hypotheses", []))
        
        recommendations = self.decision_engine.generate_recommendations(beliefs, hyp_list)
        consolidated = self.decision_engine.consolidate_recommendations(recommendations)
        sections.append(generate_actions_section(consolidated))
        
        # Section 4: Forecast Scoreboard (proving reliability)
        scoreboard = self.scoreboard_generator.load_and_generate(30)
        sections.append(generate_scoreboard_section(scoreboard))
        
        # Section 5: Lead Time Performance (proving earliness)
        lead_time_summary = self.lead_time_tracker.generate_summary()
        sections.append(generate_lead_time_section(lead_time_summary))
        
        # Section 6: Mechanism Reliability
        sections.append(self._mechanism_reliability(scoreboard))
        
        # Footer
        sections.append(self._footer(date))
        
        brief = "\n".join(sections)
        
        output_path = self.output_dir / f"investor_brief_{date}.md"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(brief)
        
        logger.info(f"Wrote investor brief to {output_path}")
        
        return brief, output_path
    
    def _header(self, date: str) -> str:
        lines = []
        lines.append("# Market Intelligence Brief")
        lines.append("")
        lines.append(f"**Date:** {date}")
        lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append("")
        lines.append("*For: Investment Professionals, VCs, Analysts*")
        lines.append("")
        lines.append("---")
        lines.append("")
        return "\n".join(lines)
    
    def _market_signals(self, cluster_feed: Dict) -> str:
        lines = []
        lines.append("## 1. Today's Market Signals")
        lines.append("")
        
        if not cluster_feed:
            lines.append("*No signals available.*")
            lines.append("")
            return "\n".join(lines)
        
        clusters = cluster_feed.get("clusters", [])[:5]
        
        for cluster in clusters:
            title = cluster.get("title", "")
            confidence = cluster.get("confidence", 0)
            sources = ", ".join(cluster.get("sources", [])[:3])
            
            lines.append(f"- **{title}** ({confidence:.0%}) — {sources}")
        
        lines.append("")
        return "\n".join(lines)
    
    def _mechanism_reliability(self, scoreboard) -> str:
        lines = []
        lines.append("## Mechanism Reliability")
        lines.append("")
        lines.append("*Accuracy by prediction type*")
        lines.append("")
        
        if scoreboard is None or not scoreboard.mechanism_scores:
            lines.append("*Not enough data to calculate mechanism reliability.*")
            lines.append("")
            return "\n".join(lines)
        
        lines.append("| Mechanism | Accuracy | Reliability | Recommendation |")
        lines.append("|-----------|----------|-------------|----------------|")
        
        for score in scoreboard.mechanism_scores:
            mechanism = score.mechanism.replace("_", " ")
            
            # Recommendation based on accuracy
            if score.accuracy >= 0.75:
                rec = "Weight heavily"
            elif score.accuracy >= 0.60:
                rec = "Use with caution"
            else:
                rec = "Discount or ignore"
            
            lines.append(
                f"| {mechanism} | {score.accuracy:.0%} | {score.reliability} | {rec} |"
            )
        
        lines.append("")
        lines.append("*System automatically adjusts confidence based on mechanism reliability.*")
        lines.append("")
        
        return "\n".join(lines)
    
    def _footer(self, date: str) -> str:
        lines = []
        lines.append("---")
        lines.append("")
        lines.append("*This Market Intelligence Brief is generated by briefAI.*")
        lines.append("*Accuracy metrics updated daily. Historical performance auditable.*")
        lines.append("")
        lines.append(f"*Data as of {date}. Not investment advice.*")
        lines.append("")
        return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate split briefs (strategy vs investor)",
    )
    
    parser.add_argument(
        '--type', '-t',
        choices=['strategy', 'investor', 'both'],
        default='both',
        help='Type of brief to generate',
    )
    
    parser.add_argument(
        '--date', '-d',
        type=str,
        default=None,
        help='Date for brief (YYYY-MM-DD)',
    )
    
    parser.add_argument(
        '--data-dir',
        type=Path,
        default=None,
        help='Override data directory',
    )
    
    return parser.parse_args()


def main():
    args = parse_args()
    
    data_dir = args.data_dir or DEFAULT_DATA_DIR
    date = args.date or datetime.now().strftime("%Y-%m-%d")
    
    print("=" * 60)
    print("BRIEF GENERATION")
    print("=" * 60)
    print()
    
    if args.type in ['strategy', 'both']:
        print("Generating Strategy Brief...")
        gen = StrategyBriefGenerator(data_dir)
        _, path = gen.generate(date)
        print(f"  -> {path}")
        print()
    
    if args.type in ['investor', 'both']:
        print("Generating Investor Brief...")
        gen = InvestorBriefGenerator(data_dir)
        _, path = gen.generate(date)
        print(f"  -> {path}")
        print()
    
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
