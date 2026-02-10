#!/usr/bin/env python
"""
Demo: Generate a sample analyst brief with synthetic data.

This demonstrates the full pipeline:
1. Create sample cluster data
2. Create sample meta-signals
3. Create sample hypotheses
4. Create sample beliefs with evidence
5. Generate the analyst brief

Run:
    python scripts/demo_analyst_brief.py
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_analyst_brief import AnalystBriefGenerator


def create_sample_data(data_dir: Path, date: str):
    """Create sample data for demo."""
    
    # Ensure directories exist
    (data_dir / "clusters").mkdir(parents=True, exist_ok=True)
    (data_dir / "meta_signals").mkdir(parents=True, exist_ok=True)
    (data_dir / "hypotheses").mkdir(parents=True, exist_ok=True)
    (data_dir / "predictions").mkdir(parents=True, exist_ok=True)
    
    # Sample cluster feed
    clusters = {
        "date": date,
        "clusters": [
            {
                "title": "NVIDIA Blackwell Production Ramp",
                "confidence": 0.89,
                "signal_count": 12,
                "summary": "Multiple sources report NVIDIA's next-gen Blackwell architecture entering mass production at TSMC, with datacenter shipments expected Q2 2026.",
                "sources": ["Reuters", "DigiTimes", "SemiAnalysis"],
            },
            {
                "title": "OpenAI Enterprise Expansion",
                "confidence": 0.82,
                "signal_count": 8,
                "summary": "OpenAI announces expanded enterprise tier with dedicated compute, SOC2 compliance, and custom model fine-tuning for Fortune 500 clients.",
                "sources": ["TechCrunch", "The Information", "OpenAI Blog"],
            },
            {
                "title": "Cloud GPU Shortage Easing",
                "confidence": 0.75,
                "signal_count": 6,
                "summary": "AWS, Azure, and GCP all report improved H100 availability. Wait times for GPU instances down 60% from December peak.",
                "sources": ["AWS Blog", "The Information", "SemiAnalysis"],
            },
            {
                "title": "Anthropic Series D Closing",
                "confidence": 0.71,
                "signal_count": 5,
                "summary": "Anthropic reportedly closing $2B Series D at $60B valuation, led by Google and Spark Capital.",
                "sources": ["Bloomberg", "The Information"],
            },
            {
                "title": "Meta AI Research Restructure",
                "confidence": 0.68,
                "signal_count": 4,
                "summary": "Meta consolidating FAIR and GenAI teams under single leadership, signaling increased focus on product integration.",
                "sources": ["The Verge", "Bloomberg"],
            },
        ],
    }
    
    with open(data_dir / "clusters" / f"cluster_feed_{date}.json", "w") as f:
        json.dump(clusters, f, indent=2)
    
    # Sample meta-signals
    meta_signals = {
        "date": date,
        "meta_signals": [
            {
                "meta_id": "meta_nvidia_compute_demand",
                "concept_name": "NVIDIA Compute Demand Acceleration",
                "confidence": 0.87,
                "velocity": 1.3,
                "independence_score": 0.82,
                "categories": ["financial", "technical", "infrastructure"],
                "key_evidence": ["Blackwell ramp ahead of schedule", "H100 allocation still constrained"],
            },
            {
                "meta_id": "meta_enterprise_ai_adoption",
                "concept_name": "Enterprise AI Adoption Accelerating",
                "confidence": 0.79,
                "velocity": 1.1,
                "independence_score": 0.75,
                "categories": ["enterprise", "financial", "technical"],
                "key_evidence": ["Fortune 500 AI budgets up 40% YoY", "Enterprise API usage growing 25% MoM"],
            },
            {
                "meta_id": "meta_model_commoditization",
                "concept_name": "Foundation Model Commoditization",
                "confidence": 0.72,
                "velocity": 0.9,
                "independence_score": 0.68,
                "categories": ["competitive", "pricing", "technical"],
                "key_evidence": ["Open-weight models closing capability gap", "API pricing down 60% in 12 months"],
            },
            {
                "meta_id": "meta_datacenter_capex",
                "concept_name": "Hyperscaler Datacenter CapEx Surge",
                "confidence": 0.85,
                "velocity": 1.2,
                "independence_score": 0.80,
                "categories": ["financial", "infrastructure"],
                "key_evidence": ["$150B combined 2026 capex guidance", "Power infrastructure bottleneck emerging"],
            },
        ],
    }
    
    with open(data_dir / "meta_signals" / f"meta_signals_{date}.json", "w") as f:
        json.dump(meta_signals, f, indent=2)
    
    # Sample hypotheses
    hypotheses = {
        "date": date,
        "bundles": [
            {
                "meta_id": "meta_nvidia_compute_demand",
                "concept_name": "NVIDIA Compute Demand Acceleration",
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp_nvidia_infra_001",
                        "title": "Infrastructure Scaling Continues",
                        "mechanism": "infra_scaling",
                        "confidence": 0.84,
                        "predicted_next_signals": [
                            {
                                "category": "financial",
                                "description": "NVIDIA datacenter revenue beats estimates",
                                "expected_timeframe_days": 45,
                                "measurable": True,
                                "canonical_metric": "earnings_mentions",
                            },
                            {
                                "category": "technical",
                                "description": "Blackwell benchmark results published",
                                "expected_timeframe_days": 30,
                                "measurable": True,
                                "canonical_metric": "repo_activity",
                            },
                        ],
                        "falsifiers": [
                            {"description": "H100 inventory builds at channel partners"},
                            {"description": "Cloud GPU pricing drops >30% in 30 days"},
                        ],
                    },
                ],
            },
            {
                "meta_id": "meta_enterprise_ai_adoption",
                "concept_name": "Enterprise AI Adoption Accelerating",
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp_enterprise_001",
                        "title": "Enterprise Deployment Acceleration",
                        "mechanism": "enterprise_adoption",
                        "confidence": 0.76,
                        "predicted_next_signals": [
                            {
                                "category": "technical",
                                "description": "Enterprise SDK downloads increase",
                                "expected_timeframe_days": 14,
                                "measurable": True,
                                "canonical_metric": "repo_activity",
                            },
                            {
                                "category": "financial",
                                "description": "AI-related job postings increase",
                                "expected_timeframe_days": 30,
                                "measurable": True,
                                "canonical_metric": "job_postings_count",
                            },
                        ],
                        "falsifiers": [
                            {"description": "Enterprise API usage flattens"},
                            {"description": "AI budget cuts announced at major enterprises"},
                        ],
                    },
                ],
            },
            {
                "meta_id": "meta_datacenter_capex",
                "concept_name": "Hyperscaler Datacenter CapEx Surge",
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp_capex_001",
                        "title": "CapEx Beneficiary Rally",
                        "mechanism": "capex_acceleration",
                        "confidence": 0.81,
                        "predicted_next_signals": [
                            {
                                "category": "financial",
                                "description": "Datacenter REIT occupancy increases",
                                "expected_timeframe_days": 60,
                                "measurable": True,
                                "canonical_metric": "filing_mentions",
                            },
                            {
                                "category": "technical",
                                "description": "Power infrastructure orders increase",
                                "expected_timeframe_days": 45,
                                "measurable": True,
                                "canonical_metric": "contract_count",
                            },
                        ],
                        "falsifiers": [
                            {"description": "Hyperscaler capex guidance reduced"},
                        ],
                    },
                ],
            },
        ],
    }
    
    with open(data_dir / "hypotheses" / f"hypotheses_{date}.json", "w") as f:
        json.dump(hypotheses, f, indent=2)
    
    # Sample beliefs
    beliefs = {
        "hyp_nvidia_infra_001": {
            "hypothesis_id": "hyp_nvidia_infra_001",
            "meta_id": "meta_nvidia_compute_demand",
            "prior_confidence": 0.75,
            "posterior_confidence": 0.88,
            "support_count": 4,
            "contradict_count": 1,
            "evidence_sum": 2.1,
            "weight_sum": 3.2,
        },
        "hyp_enterprise_001": {
            "hypothesis_id": "hyp_enterprise_001",
            "meta_id": "meta_enterprise_ai_adoption",
            "prior_confidence": 0.68,
            "posterior_confidence": 0.79,
            "support_count": 3,
            "contradict_count": 0,
            "evidence_sum": 1.4,
            "weight_sum": 2.0,
        },
        "hyp_capex_001": {
            "hypothesis_id": "hyp_capex_001",
            "meta_id": "meta_datacenter_capex",
            "prior_confidence": 0.72,
            "posterior_confidence": 0.81,
            "support_count": 2,
            "contradict_count": 0,
            "evidence_sum": 1.1,
            "weight_sum": 1.5,
        },
    }
    
    with open(data_dir / "predictions" / "beliefs.json", "w") as f:
        json.dump(beliefs, f, indent=2)
    
    # Sample evidence
    evidence = [
        {
            "prediction_id": "pred_001",
            "hypothesis_id": "hyp_nvidia_infra_001",
            "meta_id": "meta_nvidia_compute_demand",
            "entity": "nvidia",
            "canonical_metric": "repo_activity",
            "category": "technical",
            "expected_direction": "up",
            "direction": "support",
            "evidence_score": 0.85,
            "effect_size": 0.42,
            "weight": 0.75,
            "percent_change": 0.42,
            "notes": "GitHub CUDA SDK activity up 42%",
        },
        {
            "prediction_id": "pred_002",
            "hypothesis_id": "hyp_nvidia_infra_001",
            "meta_id": "meta_nvidia_compute_demand",
            "entity": "nvidia",
            "canonical_metric": "filing_mentions",
            "category": "financial",
            "expected_direction": "up",
            "direction": "support",
            "evidence_score": 0.72,
            "effect_size": 0.28,
            "weight": 0.90,
            "percent_change": 0.28,
            "notes": "SEC filings mention datacenter revenue growth",
        },
        {
            "prediction_id": "pred_003",
            "hypothesis_id": "hyp_enterprise_001",
            "meta_id": "meta_enterprise_ai_adoption",
            "entity": "openai",
            "canonical_metric": "job_postings_count",
            "category": "technical",
            "expected_direction": "up",
            "direction": "support",
            "evidence_score": 0.65,
            "effect_size": 0.35,
            "weight": 0.65,
            "percent_change": 0.35,
            "notes": "Enterprise AI job postings up 35%",
        },
        {
            "prediction_id": "pred_004",
            "hypothesis_id": "hyp_nvidia_infra_001",
            "meta_id": "meta_nvidia_compute_demand",
            "entity": "amd",
            "canonical_metric": "article_count",
            "category": "media",
            "expected_direction": "up",
            "direction": "contradict",
            "evidence_score": -0.45,
            "effect_size": 0.18,
            "weight": 0.45,
            "percent_change": -0.18,
            "notes": "AMD competitor coverage increasing",
        },
    ]
    
    with open(data_dir / "predictions" / f"evidence_{date}.jsonl", "w") as f:
        for e in evidence:
            f.write(json.dumps(e) + "\n")
    
    print(f"Created sample data for {date}")


def main():
    """Generate demo analyst brief."""
    data_dir = Path(__file__).parent.parent / "data"
    date = datetime.now().strftime("%Y-%m-%d")
    
    print("=" * 60)
    print("ANALYST BRIEF DEMO")
    print("=" * 60)
    print()
    
    # Create sample data
    print("[1] Creating sample data...")
    create_sample_data(data_dir, date)
    print()
    
    # Generate brief
    print("[2] Generating analyst brief...")
    generator = AnalystBriefGenerator(data_dir)
    brief, output_path = generator.generate(date)
    print()
    
    # Show brief
    print("[3] Generated Brief:")
    print("=" * 60)
    print()
    print(brief)
    
    print()
    print("=" * 60)
    print(f"Brief saved to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
