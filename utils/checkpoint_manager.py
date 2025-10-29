"""
Checkpoint Manager

Manages pipeline checkpoints to enable resume functionality after interruptions.
Tracks completed sources and allows resuming from last position.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any
from loguru import logger


class CheckpointManager:
    """Manages pipeline checkpoints for resume functionality"""

    def __init__(self, checkpoint_file: str = "./data/cache/pipeline_checkpoint.json"):
        """
        Initialize checkpoint manager

        Args:
            checkpoint_file: Path to checkpoint file
        """
        self.checkpoint_file = Path(checkpoint_file)
        self.checkpoint_file.parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Checkpoint file: {self.checkpoint_file}")

    def save_checkpoint(
        self,
        phase: str,
        completed_sources: List[str],
        total_sources: int,
        articles_count: int,
        run_id: str,
        additional_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Save pipeline checkpoint

        Args:
            phase: Current pipeline phase ('scraping', 'filtering', 'evaluating', etc.)
            completed_sources: List of source IDs that completed successfully
            total_sources: Total number of sources
            articles_count: Number of articles scraped so far
            run_id: Unique run identifier (timestamp-based)
            additional_data: Optional additional data to store

        Returns:
            True if checkpoint saved successfully
        """
        try:
            checkpoint_data = {
                'timestamp': datetime.now().isoformat(),
                'phase': phase,
                'completed_sources': completed_sources,
                'total_sources': total_sources,
                'articles_count': articles_count,
                'run_id': run_id,
                'progress_percent': round(len(completed_sources) / total_sources * 100, 1) if total_sources > 0 else 0
            }

            if additional_data:
                checkpoint_data.update(additional_data)

            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, indent=2, ensure_ascii=False)

            logger.debug(
                f"Checkpoint saved: {phase} - {len(completed_sources)}/{total_sources} sources "
                f"({checkpoint_data['progress_percent']}%)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            return False

    def load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """
        Load pipeline checkpoint

        Returns:
            Checkpoint data dict or None if not found/invalid
        """
        if not self.checkpoint_file.exists():
            logger.debug("No checkpoint file found")
            return None

        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                checkpoint_data = json.load(f)

            logger.info(
                f"Checkpoint loaded: {checkpoint_data.get('phase', 'unknown')} - "
                f"{len(checkpoint_data.get('completed_sources', []))}/{checkpoint_data.get('total_sources', 0)} sources "
                f"({checkpoint_data.get('progress_percent', 0)}%)"
            )
            return checkpoint_data

        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")
            return None

    def should_resume(self, max_age_hours: int = 2) -> bool:
        """
        Check if checkpoint is valid for resuming

        Args:
            max_age_hours: Maximum age of checkpoint in hours (default: 2)

        Returns:
            True if checkpoint exists and is not expired
        """
        checkpoint = self.load_checkpoint()

        if not checkpoint:
            return False

        # Check age
        try:
            checkpoint_time = datetime.fromisoformat(checkpoint['timestamp'])
            age = datetime.now() - checkpoint_time

            if age > timedelta(hours=max_age_hours):
                logger.info(f"Checkpoint expired (age: {age}). Starting fresh.")
                return False

            logger.info(f"Valid checkpoint found (age: {age}). Resume available.")
            return True

        except Exception as e:
            logger.warning(f"Failed to check checkpoint age: {e}")
            return False

    def get_remaining_sources(self, all_sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Get list of sources that haven't been scraped yet

        Args:
            all_sources: Complete list of sources

        Returns:
            List of sources not in checkpoint (or all sources if no checkpoint)
        """
        checkpoint = self.load_checkpoint()

        if not checkpoint:
            return all_sources

        completed_source_ids = set(checkpoint.get('completed_sources', []))
        remaining = [s for s in all_sources if s['id'] not in completed_source_ids]

        logger.info(
            f"Resume mode: {len(completed_source_ids)} sources already completed, "
            f"{len(remaining)} remaining"
        )

        return remaining

    def get_completed_sources(self) -> List[str]:
        """
        Get list of source IDs that have been completed

        Returns:
            List of completed source IDs (empty list if no checkpoint)
        """
        checkpoint = self.load_checkpoint()

        if not checkpoint:
            return []

        return checkpoint.get('completed_sources', [])

    def clear_checkpoint(self) -> bool:
        """
        Clear checkpoint file (called on successful pipeline completion)

        Returns:
            True if checkpoint cleared successfully
        """
        try:
            if self.checkpoint_file.exists():
                self.checkpoint_file.unlink()
                logger.info("Checkpoint cleared (pipeline completed successfully)")
            return True

        except Exception as e:
            logger.error(f"Failed to clear checkpoint: {e}")
            return False

    def get_run_id(self) -> str:
        """
        Get run ID from checkpoint, or generate new one

        Returns:
            Run ID string (timestamp-based)
        """
        checkpoint = self.load_checkpoint()

        if checkpoint and 'run_id' in checkpoint:
            return checkpoint['run_id']

        # Generate new run ID
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def get_checkpoint_info(self) -> Optional[Dict[str, Any]]:
        """
        Get human-readable checkpoint information

        Returns:
            Dict with checkpoint summary or None
        """
        checkpoint = self.load_checkpoint()

        if not checkpoint:
            return None

        try:
            checkpoint_time = datetime.fromisoformat(checkpoint['timestamp'])
            age = datetime.now() - checkpoint_time

            return {
                'exists': True,
                'phase': checkpoint.get('phase', 'unknown'),
                'progress': f"{len(checkpoint.get('completed_sources', []))}/{checkpoint.get('total_sources', 0)}",
                'progress_percent': checkpoint.get('progress_percent', 0),
                'articles_count': checkpoint.get('articles_count', 0),
                'age': str(age).split('.')[0],  # Remove microseconds
                'age_hours': age.total_seconds() / 3600,
                'run_id': checkpoint.get('run_id', 'unknown')
            }

        except Exception as e:
            logger.warning(f"Failed to get checkpoint info: {e}")
            return None
