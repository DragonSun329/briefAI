#!/usr/bin/env python3
"""
Orchestrated Pipeline Entry Point

Runs the complete AI briefing pipeline using the ACE Orchestrator (Agentic Context Engineering).

Features:
- 9-phase managed pipeline
- Adaptive context management
- Comprehensive error tracking
- Detailed token usage metrics
- Fail-fast error handling
- Execution summaries and bug reports

Usage:
    python3 run_orchestrated_pipeline.py --top-n 12
    python3 run_orchestrated_pipeline.py --mode product --top-n 15
    python3 run_orchestrated_pipeline.py --categories fintech_ai llm_tech
    python3 run_orchestrated_pipeline.py --resume
"""

import sys
import argparse
from pathlib import Path
from loguru import logger

# Ensure imports work
sys.path.insert(0, str(Path(__file__).parent))

from orchestrator.ace_orchestrator import ACEOrchestrator


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run orchestrated AI briefing pipeline with ACE (Agentic Context Engineering)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with defaults (12 articles, 7 days back)
  python3 run_orchestrated_pipeline.py

  # Specify number of articles
  python3 run_orchestrated_pipeline.py --top-n 15

  # Use specific categories
  python3 run_orchestrated_pipeline.py --categories fintech_ai data_analytics

  # Resume from checkpoint
  python3 run_orchestrated_pipeline.py --resume

  # Force restart (ignore checkpoint)
  python3 run_orchestrated_pipeline.py --force-restart

  # Look back 14 days
  python3 run_orchestrated_pipeline.py --days-back 14
        """
    )

    parser.add_argument(
        '--categories',
        nargs='+',
        default=None,
        help='Specific category IDs (e.g., fintech_ai llm_tech). If not specified, uses defaults.'
    )
    parser.add_argument(
        '--top-n',
        type=int,
        default=12,
        help='Number of final articles to select (default: 12)'
    )
    parser.add_argument(
        '--days-back',
        type=int,
        default=7,
        help='Number of days to look back for articles (default: 7)'
    )
    parser.add_argument(
        '--resume',
        action='store_true',
        help='Resume from checkpoint if available (skips completed sources)'
    )
    parser.add_argument(
        '--force-restart',
        action='store_true',
        help='Force restart (ignore any existing checkpoint and start fresh)'
    )
    parser.add_argument(
        '--mode',
        type=str,
        choices=['news', 'product'],
        default=None,
        help='Pipeline mode: news (general AI news) or product (AI product reviews). Default from env or "news".'
    )

    args = parser.parse_args()

    # Print banner
    print("\n" + "=" * 80)
    print("ACE ORCHESTRATOR - AI Briefing Pipeline")
    print("Agentic Context Engineering (ACE) with Error Tracking & Metrics")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Mode: {args.mode or 'default (news)'}")
    print(f"  Categories: {args.categories or 'default'}")
    print(f"  Top N Articles: {args.top_n}")
    print(f"  Days Back: {args.days_back}")
    print(f"  Resume: {args.resume}")
    print(f"  Force Restart: {args.force_restart}")
    print("=" * 80 + "\n")

    try:
        # Initialize orchestrator with mode
        orchestrator = ACEOrchestrator(mode=args.mode)

        # Run pipeline
        report_path = orchestrator.run_pipeline(
            category_ids=args.categories,
            top_n=args.top_n,
            days_back=args.days_back,
            resume=args.resume,
            force_restart=args.force_restart
        )

        # Success
        print("\n" + "=" * 80)
        print("✅ PIPELINE COMPLETED SUCCESSFULLY")
        print("=" * 80)
        print(f"\n📄 Final Report: {report_path}")
        print(f"📊 Execution Summary: data/reports/execution_summary_{orchestrator.run_id}.md")
        print(f"🐛 Error Log: data/logs/errors_{orchestrator.run_id}.json")
        print(f"📈 Metrics: data/metrics/metrics_{orchestrator.run_id}.json")
        print(f"🧠 Context: data/context/context_{orchestrator.run_id}.json")
        print("\n" + "=" * 80 + "\n")

        return 0

    except Exception as e:
        # Failure
        print("\n" + "=" * 80)
        print("❌ PIPELINE FAILED")
        print("=" * 80)
        print(f"\nError: {e}")
        print("\nCheck error logs for details:")
        print(f"  data/logs/errors_*.json")
        print(f"  data/reports/bug_report_*.md")
        print("\n" + "=" * 80 + "\n")

        logger.exception("Pipeline execution failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
