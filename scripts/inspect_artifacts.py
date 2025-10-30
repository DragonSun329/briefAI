#!/usr/bin/env python3
"""
Artifact Inspector - CLI tool for browsing pipeline artifacts

Usage:
  python scripts/inspect_artifacts.py list              # List all runs
  python scripts/inspect_artifacts.py summary [run_id]  # Show run summary
  python scripts/inspect_artifacts.py view <run_id> <phase_name>  # View artifact content
  python scripts/inspect_artifacts.py compare <run1> <run2>  # Compare two runs
"""

import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.artifact_manager import ArtifactManager

try:
    from tabulate import tabulate as tabulate_func
except ImportError:
    tabulate_func = None


def list_runs():
    """List all available runs"""
    runs = ArtifactManager.list_all_runs()

    if not runs:
        print("No runs found")
        return

    print(f"\nAvailable runs ({len(runs)} total):\n")

    rows = []
    for run in runs[:20]:  # Show last 20 runs
        manager = ArtifactManager(run_id=run)
        artifacts = manager.list_artifacts()
        latest = manager.get_latest_artifact()

        rows.append([
            run,
            len(artifacts),
            latest['phase_name'] if latest else 'N/A',
            f"Phase {latest['phase_number']}" if latest else 'N/A'
        ])

    print(tabulate_func(rows, headers=['Run ID', '# Artifacts', 'Latest Phase', 'Progress'], tablefmt='simple'))
    print()


def show_summary(run_id=None):
    """Show detailed summary of a run"""
    if run_id is None:
        run_id = ArtifactManager.get_latest_run_id()

        if run_id is None:
            print("No runs found")
            return

    try:
        manager = ArtifactManager(run_id=run_id)
    except Exception as e:
        print(f"Error: Run '{run_id}' not found: {e}")
        return

    artifacts = manager.list_artifacts()

    print(f"\n{'='*80}")
    print(f"Run: {run_id}")
    print(f"{'='*80}\n")

    if not artifacts:
        print("No artifacts found for this run")
        return

    rows = []
    for artifact in artifacts:
        status_icon = "✓" if artifact["output_count"] > 0 else "✗"

        rows.append([
            f"Phase {artifact['phase_number']:2d}",
            artifact['phase_name'],
            f"[{status_icon}]",
            artifact['output_count'],
            artifact['timestamp']
        ])

    print(tabulate_func(rows, headers=['Phase', 'Name', 'Status', '# Items', 'Timestamp'], tablefmt='simple'))
    print(f"\n{'='*80}\n")


def view_artifact(run_id, phase_name):
    """View detailed artifact content"""
    try:
        manager = ArtifactManager(run_id=run_id)
        artifact_file = manager.artifact_dir / f"phase*_{phase_name}.json"

        # Find artifact file
        matches = list(manager.artifact_dir.glob(f"phase*_{phase_name}.json"))
        if not matches:
            print(f"Error: Artifact not found for phase '{phase_name}'")
            return

        artifact_path = matches[0]

        # Load full artifact (with metadata)
        with open(artifact_path, 'r', encoding='utf-8') as f:
            artifact = json.load(f)

        # Display metadata
        print(f"\n{'='*80}")
        print(f"Artifact: {artifact_path.name}")
        print(f"{'='*80}\n")

        print("Metadata:")
        metadata = artifact.get('metadata', {})
        for key, value in metadata.items():
            print(f"  {key:20s}: {value}")

        # Display data summary
        print("\nData:")
        data = artifact.get('data', {})

        if 'articles' in data:
            articles = data['articles']
            print(f"  Articles: {len(articles)}")

            if articles:
                print("\n  Sample articles:")
                for i, article in enumerate(articles[:3], 1):
                    title = article.get('title', article.get('Title', 'No title'))
                    score = article.get('weighted_score', article.get('tier1_score', 'N/A'))
                    print(f"    {i}. {title[:60]}... (score: {score})")

        elif 'report_path' in data:
            print(f"  Report path: {data['report_path']}")

        else:
            print(f"  Keys: {', '.join(data.keys())}")

        print(f"\n{'='*80}\n")

    except Exception as e:
        print(f"Error viewing artifact: {e}")


def compare_runs(run1, run2):
    """Compare two runs side by side"""
    try:
        manager1 = ArtifactManager(run_id=run1)
        manager2 = ArtifactManager(run_id=run2)

        artifacts1 = {a['phase_name']: a for a in manager1.list_artifacts()}
        artifacts2 = {a['phase_name']: a for a in manager2.list_artifacts()}

        all_phases = sorted(set(artifacts1.keys()) | set(artifacts2.keys()))

        print(f"\n{'='*80}")
        print(f"Comparing: {run1} vs {run2}")
        print(f"{'='*80}\n")

        rows = []
        for phase in all_phases:
            a1 = artifacts1.get(phase)
            a2 = artifacts2.get(phase)

            count1 = a1['output_count'] if a1 else '-'
            count2 = a2['output_count'] if a2 else '-'

            diff = ''
            if a1 and a2:
                diff_val = a2['output_count'] - a1['output_count']
                if diff_val > 0:
                    diff = f"+{diff_val}"
                elif diff_val < 0:
                    diff = str(diff_val)

            rows.append([phase, count1, count2, diff])

        print(tabulate_func(rows, headers=['Phase', run1[:15], run2[:15], 'Diff'], tablefmt='simple'))
        print(f"\n{'='*80}\n")

    except Exception as e:
        print(f"Error comparing runs: {e}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1]

    if command == 'list':
        list_runs()

    elif command == 'summary':
        run_id = sys.argv[2] if len(sys.argv) > 2 else None
        show_summary(run_id)

    elif command == 'view':
        if len(sys.argv) < 4:
            print("Usage: inspect_artifacts.py view <run_id> <phase_name>")
            return
        view_artifact(sys.argv[2], sys.argv[3])

    elif command == 'compare':
        if len(sys.argv) < 4:
            print("Usage: inspect_artifacts.py compare <run1> <run2>")
            return
        compare_runs(sys.argv[2], sys.argv[3])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    # Check if tabulate is installed
    if tabulate_func is None:
        print("Error: tabulate not installed")
        print("Install with: pip install tabulate")
        sys.exit(1)

    main()
