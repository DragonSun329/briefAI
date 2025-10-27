"""
Checkpoint Manager - Save and resume article processing progress

Saves processed articles to disk as they're completed, allowing resumable workflows.
Supports both single-batch and weekly collection modes.

Each batch of articles is saved with status: extracted, evaluated, paraphrased.
For weekly collection, articles from each day are accumulated and deduplicated at week end.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from loguru import logger


class CheckpointManager:
    """Manages checkpoints for resumable article processing"""

    def __init__(self, cache_dir: str = "./data/cache"):
        """
        Initialize checkpoint manager

        Args:
            cache_dir: Directory to store checkpoint files
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.checkpoint_file = None
        self.processed_articles: Dict[str, Dict[str, Any]] = {}
        self.weekly_checkpoint_file = None
        self.week_id = None

        logger.info(f"Checkpoint manager initialized: {self.cache_dir}")

    def create_checkpoint(self, batch_id: str) -> None:
        """
        Create a new checkpoint file for a batch of articles

        Args:
            batch_id: Unique batch identifier (e.g., 'batch_2025_10_25_13_28')
        """
        self.checkpoint_file = self.cache_dir / f"checkpoint_{batch_id}.json"
        self.processed_articles = {}

        logger.info(f"Created checkpoint: {self.checkpoint_file}")

    def load_checkpoint(self, batch_id: str) -> bool:
        """
        Load checkpoint if it exists

        Args:
            batch_id: Batch identifier to load

        Returns:
            True if checkpoint loaded, False if not found
        """
        checkpoint_file = self.cache_dir / f"checkpoint_{batch_id}.json"

        if not checkpoint_file.exists():
            logger.debug(f"No checkpoint found: {checkpoint_file}")
            return False

        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.processed_articles = data.get('articles', {})
                self.checkpoint_file = checkpoint_file

                logger.info(
                    f"Loaded checkpoint with {len(self.processed_articles)} articles: "
                    f"{checkpoint_file}"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return False

    def save_article_entities(
        self,
        article_id: str,
        article_data: Dict[str, Any],
        entities: Dict[str, List[str]],
        provider_used: str
    ) -> None:
        """
        Save extracted entities for an article

        Args:
            article_id: Unique article identifier
            article_data: Original article data (title, url, content, etc.)
            entities: Extracted entities
            provider_used: Which provider/model extracted the entities
        """
        if article_id not in self.processed_articles:
            self.processed_articles[article_id] = {
                "article": article_data,
                "timestamp_created": datetime.now().isoformat()
            }

        self.processed_articles[article_id].update({
            "entities": entities,
            "entities_provider": provider_used,
            "entities_timestamp": datetime.now().isoformat(),
            "status": "extracted"
        })

        self._save_checkpoint()
        logger.debug(f"Saved entities for article {article_id}")

    def save_article_evaluation(
        self,
        article_id: str,
        scores: Dict[str, float],
        takeaway: str,
        provider_used: str
    ) -> None:
        """
        Save evaluation scores for an article

        Args:
            article_id: Unique article identifier
            scores: Evaluation scores (impact, relevance, recency, credibility, overall)
            takeaway: Key takeaway in Mandarin Chinese
            provider_used: Which provider evaluated the article
        """
        if article_id not in self.processed_articles:
            logger.warning(f"Article {article_id} not in checkpoint, creating new entry")
            self.processed_articles[article_id] = {
                "timestamp_created": datetime.now().isoformat()
            }

        self.processed_articles[article_id].update({
            "scores": scores,
            "takeaway": takeaway,
            "evaluation_provider": provider_used,
            "evaluation_timestamp": datetime.now().isoformat(),
            "status": "evaluated"
        })

        self._save_checkpoint()
        logger.debug(f"Saved evaluation for article {article_id}")

    def save_article_paraphrase(
        self,
        article_id: str,
        paraphrased_content: str,
        length_characters: int,
        provider_used: str
    ) -> None:
        """
        Save paraphrased content for an article

        Args:
            article_id: Unique article identifier
            paraphrased_content: Paraphrased content in Mandarin Chinese
            length_characters: Length of paraphrased content in characters
            provider_used: Which provider paraphrased the article
        """
        if article_id not in self.processed_articles:
            logger.warning(f"Article {article_id} not in checkpoint, creating new entry")
            self.processed_articles[article_id] = {
                "timestamp_created": datetime.now().isoformat()
            }

        self.processed_articles[article_id].update({
            "paraphrased_content": paraphrased_content,
            "paraphrased_length": length_characters,
            "paraphrase_provider": provider_used,
            "paraphrase_timestamp": datetime.now().isoformat(),
            "status": "paraphrased"
        })

        self._save_checkpoint()
        logger.debug(f"Saved paraphrase for article {article_id}")

    def get_processed_article_ids(self) -> List[str]:
        """
        Get list of article IDs already processed

        Returns:
            List of article IDs
        """
        return list(self.processed_articles.keys())

    def get_article_status(self, article_id: str) -> Optional[str]:
        """
        Get processing status of an article

        Args:
            article_id: Article identifier

        Returns:
            Status ('extracted', 'evaluated', 'paraphrased') or None if not found
        """
        if article_id in self.processed_articles:
            return self.processed_articles[article_id].get('status')
        return None

    def get_checkpoint_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current checkpoint

        Returns:
            Statistics about processed articles
        """
        total = len(self.processed_articles)
        extracted = sum(1 for a in self.processed_articles.values() if a.get('status') == 'extracted')
        evaluated = sum(1 for a in self.processed_articles.values() if a.get('status') == 'evaluated')
        paraphrased = sum(1 for a in self.processed_articles.values() if a.get('status') == 'paraphrased')

        return {
            "total_articles": total,
            "extracted": extracted,
            "evaluated": evaluated,
            "paraphrased": paraphrased,
            "checkpoint_file": str(self.checkpoint_file) if self.checkpoint_file else None
        }

    def _save_checkpoint(self) -> None:
        """Save current state to checkpoint file"""
        if not self.checkpoint_file:
            logger.warning("No checkpoint file set, cannot save")
            return

        try:
            checkpoint_data = {
                "checkpoint_version": "1.0",
                "last_updated": datetime.now().isoformat(),
                "articles": self.processed_articles
            }

            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")

    def export_processed_articles(self) -> Dict[str, Any]:
        """
        Export all processed articles in checkpoint

        Returns:
            Dictionary of processed articles
        """
        return self.processed_articles.copy()

    # Weekly Collection Methods

    def create_weekly_checkpoint(self, week_id: str) -> None:
        """
        Create a new weekly checkpoint for daily collection mode

        Args:
            week_id: Unique week identifier (e.g., 'week_2025_43')
        """
        self.weekly_checkpoint_file = self.cache_dir / f"weekly_{week_id}.json"
        self.week_id = week_id
        self.processed_articles = {}

        logger.info(f"Created weekly checkpoint: {self.weekly_checkpoint_file}")

    def load_weekly_checkpoint(self, week_id: str) -> bool:
        """
        Load weekly checkpoint if it exists

        Args:
            week_id: Week identifier to load

        Returns:
            True if checkpoint loaded, False if not found
        """
        weekly_checkpoint_file = self.cache_dir / f"weekly_{week_id}.json"

        if not weekly_checkpoint_file.exists():
            logger.debug(f"No weekly checkpoint found: {weekly_checkpoint_file}")
            return False

        try:
            with open(weekly_checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.processed_articles = data.get('articles', {})
                self.weekly_checkpoint_file = weekly_checkpoint_file
                self.week_id = week_id

                logger.info(
                    f"Loaded weekly checkpoint with {len(self.processed_articles)} articles: "
                    f"{weekly_checkpoint_file}"
                )
                return True

        except Exception as e:
            logger.error(f"Failed to load weekly checkpoint: {e}")
            return False

    def save_article_tier2_score(
        self,
        article_id: str,
        article_data: Dict[str, Any],
        tier2_score: float,
        tier2_reasoning: str,
        tier1_score: Optional[float] = None,
        day: Optional[int] = None
    ) -> None:
        """
        Save Tier 2 batch evaluation score for an article (weekly collection mode)

        Args:
            article_id: Unique article identifier
            article_data: Original article data
            tier2_score: Tier 2 batch evaluation score (0-10)
            tier2_reasoning: Brief reasoning from Tier 2 evaluation
            tier1_score: Optional Tier 1 pre-filter score
            day: Optional day of week (1-7) for tracking collection day
        """
        if article_id not in self.processed_articles:
            self.processed_articles[article_id] = {
                "article": article_data,
                "timestamp_created": datetime.now().isoformat()
            }

        self.processed_articles[article_id].update({
            "tier1_score": tier1_score,
            "tier2_score": tier2_score,
            "tier2_reasoning": tier2_reasoning,
            "collection_day": day or self._get_current_day(),
            "tier2_timestamp": datetime.now().isoformat(),
            "status": "tier2_evaluated"
        })

        self._save_checkpoint()
        logger.debug(f"Saved Tier 2 score for article {article_id}")

    def save_article_tier3_score(
        self,
        article_id: str,
        scores: Dict[str, float],
        takeaway: str,
        provider_used: str
    ) -> None:
        """
        Save Tier 3 full evaluation scores for an article (weekly finalization)

        Args:
            article_id: Unique article identifier
            scores: Evaluation scores (impact, relevance, recency, credibility, overall)
            takeaway: Key takeaway in Mandarin Chinese
            provider_used: Which provider evaluated the article
        """
        if article_id not in self.processed_articles:
            logger.warning(f"Article {article_id} not in checkpoint, creating new entry")
            self.processed_articles[article_id] = {
                "timestamp_created": datetime.now().isoformat()
            }

        self.processed_articles[article_id].update({
            "tier3_scores": scores,
            "takeaway": takeaway,
            "tier3_provider": provider_used,
            "tier3_timestamp": datetime.now().isoformat(),
            "status": "tier3_evaluated"
        })

        self._save_checkpoint()
        logger.debug(f"Saved Tier 3 score for article {article_id}")

    def get_articles_by_status(self, status: str) -> Dict[str, Dict[str, Any]]:
        """
        Get all articles with a specific status

        Args:
            status: Status to filter by ('tier2_evaluated', 'tier3_evaluated', etc.)

        Returns:
            Dictionary of articles matching the status
        """
        return {
            article_id: article
            for article_id, article in self.processed_articles.items()
            if article.get('status') == status
        }

    def get_weekly_stats(self) -> Dict[str, Any]:
        """
        Get statistics about current weekly checkpoint

        Returns:
            Statistics about collected articles
        """
        total = len(self.processed_articles)
        tier2_evaluated = sum(
            1 for a in self.processed_articles.values()
            if a.get('status') == 'tier2_evaluated'
        )
        tier3_evaluated = sum(
            1 for a in self.processed_articles.values()
            if a.get('status') == 'tier3_evaluated'
        )

        return {
            "week_id": self.week_id,
            "total_articles": total,
            "tier2_evaluated": tier2_evaluated,
            "tier3_evaluated": tier3_evaluated,
            "checkpoint_file": str(self.weekly_checkpoint_file) if self.weekly_checkpoint_file else None
        }

    def merge_articles_from_checkpoint(self, other_checkpoint_file: str) -> int:
        """
        Merge articles from another checkpoint file into current checkpoint

        Args:
            other_checkpoint_file: Path to checkpoint file to merge from

        Returns:
            Number of articles merged
        """
        try:
            with open(other_checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                other_articles = data.get('articles', {})

                # Merge articles, preferring articles with higher tier status
                merged_count = 0
                for article_id, article_data in other_articles.items():
                    if article_id not in self.processed_articles:
                        self.processed_articles[article_id] = article_data
                        merged_count += 1
                    else:
                        # If incoming article has higher evaluation status, update it
                        current_status = self.processed_articles[article_id].get('status')
                        incoming_status = article_data.get('status')
                        if self._status_rank(incoming_status) > self._status_rank(current_status):
                            self.processed_articles[article_id] = article_data

                logger.info(f"Merged {merged_count} new articles from {other_checkpoint_file}")
                self._save_checkpoint()
                return merged_count

        except Exception as e:
            logger.error(f"Failed to merge checkpoint: {e}")
            return 0

    def _get_current_day(self) -> int:
        """Get current day of week (1-7, Monday-Sunday)"""
        return datetime.now().isoweekday()

    @staticmethod
    def _status_rank(status: Optional[str]) -> int:
        """Get ranking of status (higher = more complete)"""
        status_ranks = {
            'extracted': 1,
            'tier1_filtered': 2,
            'tier2_evaluated': 3,
            'evaluated': 4,
            'tier3_evaluated': 4,
            'paraphrased': 5
        }
        return status_ranks.get(status, 0)
