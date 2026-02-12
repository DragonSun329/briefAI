"""
CLI for Ask Mode.

Usage:
    python -m briefai ask "What signals suggest OpenAI pricing changes?" --experiment v2_2_forward_test
    python -m briefai ask "Is LangChain adoption accelerating?" --verbose
    python -m briefai ask --list-tools
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from loguru import logger


def main():
    parser = argparse.ArgumentParser(
        description="briefAI Ask Mode - Interactive research queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Basic question
    python -m briefai ask "What signals suggest OpenAI pricing changes?"
    
    # With specific experiment
    python -m briefai ask "Is demand for AI chips increasing?" --experiment v2_2_forward_test
    
    # Verbose mode (shows tool calls)
    python -m briefai ask "What's happening with LangChain?" --verbose
    
    # List available tools
    python -m briefai ask --list-tools
    
    # Output as JSON
    python -m briefai ask "Question" --json
        """,
    )
    
    parser.add_argument(
        "question",
        nargs="?",
        help="Research question to answer",
    )
    
    parser.add_argument(
        "--experiment", "-e",
        default="v2_2_forward_test",
        help="Experiment ID (default: v2_2_forward_test)",
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress",
    )
    
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output result as JSON",
    )
    
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="List available tools and exit",
    )
    
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum tool call iterations (default: 10)",
    )
    
    args = parser.parse_args()
    
    # Handle list-tools
    if args.list_tools:
        from briefai.ask.tools import ToolRegistry
        registry = ToolRegistry()
        print(registry.get_tool_docs())
        return 0
    
    # Require question for normal operation
    if not args.question:
        parser.error("Question is required (or use --list-tools)")
        return 1
    
    # Configure logging
    if args.verbose:
        logger.enable("briefai")
    else:
        logger.disable("briefai")
    
    # Run ask
    try:
        from briefai.ask.engine import AskEngine, EngineConfig
        
        config = EngineConfig(
            experiment_id=args.experiment,
            max_iterations=args.max_iterations,
            verbose=args.verbose,
        )
        
        engine = AskEngine(experiment_id=args.experiment, config=config)
        
        if args.verbose:
            print(f"\n🔍 Researching: {args.question}")
            print(f"📁 Experiment: {args.experiment}\n")
        
        result = engine.ask(args.question)
        
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            # Pretty print
            print("\n" + "=" * 60)
            print("📋 ANSWER")
            print("=" * 60)
            print(result.final_answer)
            
            print("\n" + "-" * 60)
            print("📊 QUALITY ASSESSMENT")
            print("-" * 60)
            print(f"Confidence: {result.confidence_level}")
            print(f"Review Required: {result.review_required}")
            
            if result.quality_notes:
                print("\nNotes:")
                for note in result.quality_notes:
                    print(f"  • {note}")
            
            if result.measurable_checks:
                print("\n" + "-" * 60)
                print("📈 MEASURABLE PREDICTIONS")
                print("-" * 60)
                for check in result.measurable_checks:
                    print(f"  • {check.entity or '?'} {check.metric} → {check.direction} (within {check.window_days}d)")
            
            print("\n" + "-" * 60)
            print("📝 METADATA")
            print("-" * 60)
            print(f"Tool Calls: {len(result.tool_calls)}")
            print(f"Evidence Sources: {len(result.evidence_links)}")
            print(f"Loop Iterations: {result.loop_iterations}")
            print(f"Duration: {result.duration_ms}ms")
            print(f"Commit: {result.commit_hash[:8]}")
            
            if result.loop_warnings:
                print("\n⚠️ Loop Warnings:")
                for warning in result.loop_warnings:
                    print(f"  {warning}")
        
        return 0
        
    except Exception as e:
        logger.exception(f"Ask mode error: {e}")
        if args.verbose:
            raise
        print(f"\n❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
