#!/usr/bin/env python3
"""
Artifact Manager - Save and load pipeline artifacts for resumption

Each pipeline phase produces artifacts that are saved to disk immediately.
If the pipeline fails, it can resume from the last successful phase.

Architecture:
  data/artifacts/
  ├── run_20251030_175101/
  │   ├── phase1_initialization.json
  │   ├── phase2_scraping.json
  │   ├── phase3_tier1_filter.json
  │   ├── phase4_tier2_batch.json
  │   ├── phase5_tier3_5d.json
  │   ├── phase6_ranking.json
  │   ├── phase7_paraphrasing.json
  │   ├── phase8_enrichment.json
  │   ├── phase9_validation.json
  │   └── phase10_final_report.md
  └── latest -> run_20251030_175101/  # Symlink to latest run
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
from loguru import logger


class ArtifactManager:
    """Manages pipeline artifacts for resumption and inspection"""

    def __init__(self, run_id: Optional[str] = None, base_dir: str = "data/artifacts"):
        """
        Initialize ArtifactManager

        Args:
            run_id: Unique run identifier (e.g., "20251030_175101")
                   If None, generates timestamp-based ID
            base_dir: Base directory for all artifacts
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

        # Generate run_id if not provided
        if run_id is None:
            run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        self.run_id = run_id
        self.artifact_dir = self.base_dir / run_id
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"ArtifactManager initialized for run: {run_id}")
        logger.info(f"Artifact directory: {self.artifact_dir}")

    def save_artifact(
        self,
        phase_name: str,
        phase_number: int,
        data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Save phase output as artifact

        Args:
            phase_name: Name of the phase (e.g., "scraping", "tier1_filter")
            phase_number: Phase number (1-10)
            data: Phase output data
            metadata: Optional metadata (duration, cost, etc.)

        Returns:
            Path to saved artifact file
        """
        # Build artifact filename
        artifact_filename = f"phase{phase_number}_{phase_name}.json"
        artifact_path = self.artifact_dir / artifact_filename

        # Build metadata
        if metadata is None:
            metadata = {}

        metadata.update({
            "run_id": self.run_id,
            "phase_name": phase_name,
            "phase_number": phase_number,
            "timestamp": datetime.now().isoformat(),
            "status": "completed"
        })

        # Add input/output counts if data contains articles
        if "articles" in data:
            metadata["output_count"] = len(data["articles"])

        # Build artifact structure
        artifact = {
            "metadata": metadata,
            "data": data
        }

        # Save to disk
        with open(artifact_path, 'w', encoding='utf-8') as f:
            json.dump(artifact, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ Saved artifact: {artifact_filename}")
        logger.info(f"   Location: {artifact_path}")

        if "articles" in data:
            logger.info(f"   Articles: {len(data['articles'])}")

        # Update 'latest' symlink
        self._update_latest_symlink()

        return artifact_path

    def load_artifact(self, phase_name: str) -> Dict[str, Any]:
        """
        Load phase artifact by name

        Args:
            phase_name: Name of the phase (e.g., "scraping", "tier1_filter")
                       Can also specify full filename (e.g., "phase2_scraping.json")

        Returns:
            Artifact data (without metadata wrapper)

        Raises:
            FileNotFoundError: If artifact doesn't exist
        """
        # Handle both phase name and full filename
        if phase_name.endswith('.json'):
            artifact_filename = phase_name
        else:
            # Find artifact by phase name (glob pattern)
            matches = list(self.artifact_dir.glob(f"phase*_{phase_name}.json"))
            if not matches:
                raise FileNotFoundError(
                    f"Artifact not found for phase '{phase_name}' in run {self.run_id}"
                )
            artifact_filename = matches[0].name

        artifact_path = self.artifact_dir / artifact_filename

        if not artifact_path.exists():
            raise FileNotFoundError(
                f"Artifact not found: {artifact_path}"
            )

        with open(artifact_path, 'r', encoding='utf-8') as f:
            artifact = json.load(f)

        logger.info(f"📂 Loaded artifact: {artifact_filename}")

        # Return just the data portion (metadata is for inspection tools)
        return artifact.get("data", artifact)

    def list_artifacts(self) -> List[Dict[str, Any]]:
        """
        List all artifacts for this run

        Returns:
            List of artifact metadata dictionaries
        """
        artifacts = []

        for artifact_file in sorted(self.artifact_dir.glob("phase*.json")):
            with open(artifact_file, 'r', encoding='utf-8') as f:
                artifact = json.load(f)

            artifacts.append({
                "filename": artifact_file.name,
                "phase_name": artifact["metadata"]["phase_name"],
                "phase_number": artifact["metadata"]["phase_number"],
                "timestamp": artifact["metadata"]["timestamp"],
                "output_count": artifact["metadata"].get("output_count", 0)
            })

        return artifacts

    def get_latest_artifact(self) -> Optional[Dict[str, Any]]:
        """
        Get the latest (highest phase number) artifact

        Returns:
            Artifact metadata dict, or None if no artifacts exist
        """
        artifacts = self.list_artifacts()

        if not artifacts:
            return None

        # Sort by phase number (descending)
        artifacts.sort(key=lambda x: x["phase_number"], reverse=True)

        return artifacts[0]

    def get_latest_phase_number(self) -> int:
        """
        Get the phase number of the latest artifact

        Returns:
            Phase number (1-10), or 0 if no artifacts exist
        """
        latest = self.get_latest_artifact()
        return latest["phase_number"] if latest else 0

    def artifact_exists(self, phase_name: str) -> bool:
        """
        Check if artifact exists for a given phase

        Args:
            phase_name: Name of the phase

        Returns:
            True if artifact exists, False otherwise
        """
        try:
            self.load_artifact(phase_name)
            return True
        except FileNotFoundError:
            return False

    def _update_latest_symlink(self):
        """Update 'latest' symlink to point to current run"""
        latest_link = self.base_dir / "latest"

        # Remove existing symlink if it exists
        if latest_link.is_symlink() or latest_link.exists():
            latest_link.unlink()

        # Create new symlink
        try:
            os.symlink(self.run_id, latest_link)
            logger.debug(f"Updated 'latest' symlink → {self.run_id}")
        except OSError as e:
            logger.warning(f"Failed to create 'latest' symlink: {e}")

    @classmethod
    def list_all_runs(cls, base_dir: str = "data/artifacts") -> List[str]:
        """
        List all run IDs

        Args:
            base_dir: Base directory for artifacts

        Returns:
            List of run IDs, sorted by timestamp (newest first)
        """
        base_path = Path(base_dir)

        if not base_path.exists():
            return []

        runs = [
            d.name for d in base_path.iterdir()
            if d.is_dir() and d.name != "latest"
        ]

        # Sort by timestamp (newest first)
        runs.sort(reverse=True)

        return runs

    @classmethod
    def get_latest_run_id(cls, base_dir: str = "data/artifacts") -> Optional[str]:
        """
        Get the latest run ID

        Args:
            base_dir: Base directory for artifacts

        Returns:
            Latest run ID, or None if no runs exist
        """
        runs = cls.list_all_runs(base_dir)
        return runs[0] if runs else None


# Convenience functions for CLI usage

def load_latest_artifact(phase_name: str) -> Dict[str, Any]:
    """
    Load artifact from latest run

    Args:
        phase_name: Name of the phase

    Returns:
        Artifact data
    """
    latest_run = ArtifactManager.get_latest_run_id()

    if latest_run is None:
        raise ValueError("No runs found")

    manager = ArtifactManager(run_id=latest_run)
    return manager.load_artifact(phase_name)


def print_run_summary(run_id: Optional[str] = None):
    """
    Print summary of a run's artifacts

    Args:
        run_id: Run ID to inspect (or latest if None)
    """
    if run_id is None:
        run_id = ArtifactManager.get_latest_run_id()

        if run_id is None:
            print("No runs found")
            return

    manager = ArtifactManager(run_id=run_id)
    artifacts = manager.list_artifacts()

    print(f"\n{'='*70}")
    print(f"Run: {run_id}")
    print(f"{'='*70}\n")

    for artifact in artifacts:
        status_icon = "✓" if artifact["output_count"] > 0 else "✗"
        print(
            f"Phase {artifact['phase_number']:2d}: {artifact['phase_name']:20s} "
            f"[{status_icon}] {artifact['output_count']:3d} articles"
        )

    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) > 1:
        if sys.argv[1] == "list":
            runs = ArtifactManager.list_all_runs()
            print("\nAvailable runs:")
            for run in runs:
                print(f"  - {run}")
            print()

        elif sys.argv[1] == "summary":
            run_id = sys.argv[2] if len(sys.argv) > 2 else None
            print_run_summary(run_id)

        else:
            print("Usage:")
            print("  python artifact_manager.py list              # List all runs")
            print("  python artifact_manager.py summary [run_id]  # Show run summary")

    else:
        print("Usage:")
        print("  python artifact_manager.py list              # List all runs")
        print("  python artifact_manager.py summary [run_id]  # Show run summary")
