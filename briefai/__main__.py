"""
briefAI CLI entry point.

Usage:
    python -m briefai ask "question" [options]
    python -m briefai review --experiment v2_2_forward_test
    python -m briefai evolve --apply-patch data/reviews/config_patch_YYYY-MM-DD.json
    python -m briefai --help
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(
        description="briefAI - AI Industry Intelligence Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Ask command
    ask_parser = subparsers.add_parser(
        "ask",
        help="Interactive research queries (Dexter-style)",
        description="Run an agentic research loop to answer questions using local artifacts.",
    )
    ask_parser.add_argument(
        "question",
        nargs="?",
        help="Research question to answer",
    )
    ask_parser.add_argument(
        "--experiment", "-e",
        default="v2_2_forward_test",
        help="Experiment ID (default: v2_2_forward_test)",
    )
    ask_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    ask_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output result as JSON",
    )
    ask_parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools and exit",
    )
    ask_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum tool call iterations (default: 10)",
    )
    
    # Review command
    review_parser = subparsers.add_parser(
        "review",
        help="Prediction review and learning system",
        description="Analyze expired predictions to learn what the system is good and bad at predicting.",
    )
    review_parser.add_argument(
        "--experiment", "-e",
        default="v2_2_forward_test",
        help="Experiment ID to review (default: v2_2_forward_test)",
    )
    review_parser.add_argument(
        "--data-root",
        type=Path,
        help="Root data directory (default: ./data)",
    )
    review_parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        help="Output directory for reviews (default: data/reviews)",
    )
    review_parser.add_argument(
        "--as-of",
        type=str,
        help="Date to use as 'today' for expiration check (YYYY-MM-DD)",
    )
    review_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    review_parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output result summary as JSON",
    )
    
    # Evolve command
    evolve_parser = subparsers.add_parser(
        "evolve",
        help="Engine evolution system",
        description="Apply approved config patches to evolve the engine.",
    )
    evolve_parser.add_argument(
        "--validate",
        type=Path,
        metavar="PATCH_FILE",
        help="Validate a patch file without applying",
    )
    evolve_parser.add_argument(
        "--dry-run",
        type=Path,
        metavar="PATCH_FILE",
        help="Show what would be changed without applying",
    )
    evolve_parser.add_argument(
        "--apply-patch",
        type=Path,
        metavar="PATCH_FILE",
        help="Apply a patch file (creates git commit and tag)",
    )
    evolve_parser.add_argument(
        "--config-root",
        type=Path,
        help="Root directory of the project",
    )
    evolve_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    evolve_parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    
    args = parser.parse_args()
    
    if args.command == "ask":
        # Delegate to ask CLI
        from briefai.ask.cli import main as ask_main
        # Re-parse with ask parser
        sys.argv = ["briefai-ask"] + sys.argv[2:]  # Remove "briefai ask"
        return ask_main()
    elif args.command == "review":
        # Delegate to review CLI
        from briefai.review.cli import main as review_main
        # Re-parse with review parser
        sys.argv = ["briefai-review"] + sys.argv[2:]  # Remove "briefai review"
        return review_main()
    elif args.command == "evolve":
        # Delegate to evolve CLI
        from briefai.evolve.cli import main as evolve_main
        # Re-parse with evolve parser
        sys.argv = ["briefai-evolve"] + sys.argv[2:]  # Remove "briefai evolve"
        return evolve_main()
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
