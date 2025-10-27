"""
Semantic Deduplication Utilities - Detect semantically similar articles

Uses sentence embeddings (Sentence-Transformers) and vector database (Chroma)
to detect paraphrased or reworded duplicate articles.

Example duplicates caught:
- "GPT-5发布" vs "OpenAI推出新一代语言模型"
- "华为发布新AI芯片" vs "Huawei launches cutting-edge AI processor"
- Different phrasings of same news from multiple sources
"""

from typing import Dict, Any, Tuple, Optional
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

try:
    from sentence_transformers import SentenceTransformer
    import chromadb
    from chromadb.utils import embedding_functions
    SEMANTIC_AVAILABLE = True
except ImportError:
    SEMANTIC_AVAILABLE = False
    logger.warning("Semantic deduplication disabled - install sentence-transformers and chromadb")


class SemanticDeduplicator:
    """
    Detects semantically similar articles using embeddings and vector search.

    Uses:
    - all-MiniLM-L6-v2: Fast English embeddings (22M params, 384 dims)
    - Chroma: Persistent vector database (SQLite backend)
    - 7-day rolling window: Only checks recent articles
    """

    # Similarity threshold for strict mode (prefer missing duplicates)
    SEMANTIC_SIMILARITY_THRESHOLD = 0.85  # cosine similarity >= 0.85

    def __init__(
        self,
        db_path: str = "./data/chroma_db",
        model_name: str = "all-MiniLM-L6-v2",
        strict_mode: bool = True
    ):
        """
        Initialize semantic deduplicator

        Args:
            db_path: Path to Chroma database directory
            model_name: Sentence-Transformers model name
            strict_mode: If True, use higher threshold (fewer false positives)
        """
        if not SEMANTIC_AVAILABLE:
            logger.error("Semantic deduplication not available - missing dependencies")
            self.available = False
            return

        self.db_path = Path(db_path)
        self.db_path.mkdir(parents=True, exist_ok=True)
        self.strict_mode = strict_mode
        self.threshold = self.SEMANTIC_SIMILARITY_THRESHOLD if strict_mode else 0.80

        try:
            # Load sentence embedding model (cached after first download)
            logger.info(f"Loading embedding model: {model_name}")
            self.model = SentenceTransformer(model_name)

            # Initialize Chroma persistent client
            self.client = chromadb.PersistentClient(path=str(self.db_path))

            # Get or create collection with cosine distance metric
            self.collection = self.client.get_or_create_collection(
                name="news_articles_semantic",
                metadata={"hnsw:space": "cosine"}
            )

            self.available = True
            logger.info(f"Semantic deduplicator initialized (threshold: {self.threshold:.2f})")

        except Exception as e:
            logger.error(f"Failed to initialize semantic deduplicator: {e}")
            self.available = False

    def check_duplicate(
        self,
        article: Dict[str, Any],
        check_window_days: int = 7
    ) -> Tuple[bool, Optional[str], float]:
        """
        Check if article is semantically similar to recent articles.

        Args:
            article: Article dictionary with 'id' and 'title' fields
            check_window_days: Only check against articles from last N days

        Returns:
            Tuple of (is_duplicate, duplicate_article_id, similarity_score)
            - is_duplicate: True if semantic duplicate found
            - duplicate_article_id: ID of the original article (or None)
            - similarity_score: Cosine similarity (0.0-1.0)
        """
        if not self.available:
            return False, None, 0.0

        try:
            # Extract text for embedding (title is most discriminative)
            text = article.get('title', '')
            if not text:
                logger.warning(f"Article {article.get('id')} has no title")
                return False, None, 0.0

            # Generate embedding
            embedding = self.model.encode([text])[0].tolist()

            # Calculate cutoff date
            cutoff_date = (datetime.now() - timedelta(days=check_window_days)).strftime('%Y-%m-%d')

            # Query vector database for similar articles
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=1,
                where={"date": {"$gte": cutoff_date}}
            )

            # Check results
            if not results['ids'] or not results['ids'][0]:
                return False, None, 0.0

            # In Chroma, distances are typically L2 distances
            # For cosine metric (0-2 scale), convert to similarity (0-1)
            # distance 0 = identical (similarity 1.0)
            # distance 2 = opposite (similarity -1.0)
            # Formula: similarity = 1 - (distance / 2)
            distance = results['distances'][0][0]
            similarity = 1.0 - (distance / 2.0)

            # Log and return result
            duplicate_id = results['ids'][0][0]

            if similarity >= self.threshold:
                logger.info(
                    f"Semantic duplicate detected: '{article.get('title')}' "
                    f"matches '{results['metadatas'][0][0].get('title')}' "
                    f"(similarity: {similarity:.3f})"
                )
                return True, duplicate_id, similarity

            # Not a duplicate (similarity below threshold)
            return False, None, similarity

        except Exception as e:
            logger.error(f"Error checking duplicate for {article.get('id')}: {e}")
            return False, None, 0.0

    def add_article(self, article: Dict[str, Any]) -> bool:
        """
        Add article to semantic deduplication index.

        Args:
            article: Article dictionary with 'id', 'title', 'date' fields

        Returns:
            True if successfully added, False otherwise
        """
        if not self.available:
            return False

        try:
            article_id = article.get('id')
            text = article.get('title', '')

            if not article_id or not text:
                logger.warning(f"Cannot index article - missing id or title")
                return False

            # Generate embedding
            embedding = self.model.encode([text])[0].tolist()

            # Add to vector database
            self.collection.add(
                embeddings=[embedding],
                metadatas=[{
                    'title': text,
                    'date': article.get('date', ''),
                    'source': article.get('source', ''),
                    'url': article.get('url', '')
                }],
                ids=[article_id]
            )

            return True

        except Exception as e:
            logger.error(f"Error adding article {article.get('id')} to index: {e}")
            return False

    def cleanup_old_articles(self, days: int = 7) -> int:
        """
        Remove articles older than N days from the index.

        This keeps the database size manageable and focuses on recent deduplication.

        Args:
            days: Remove articles older than this many days

        Returns:
            Number of articles removed
        """
        if not self.available:
            return 0

        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

            # Get all articles older than cutoff
            old_articles = self.collection.get(
                where={"date": {"$lt": cutoff_date}}
            )

            if not old_articles['ids']:
                logger.info(f"No articles older than {days} days to remove")
                return 0

            # Delete old articles
            self.collection.delete(ids=old_articles['ids'])

            removed_count = len(old_articles['ids'])
            logger.info(f"Removed {removed_count} articles older than {days} days")

            return removed_count

        except Exception as e:
            logger.error(f"Error cleaning up old articles: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the semantic index.

        Returns:
            Dictionary with index statistics
        """
        if not self.available:
            return {"available": False}

        try:
            count = self.collection.count()
            return {
                "available": True,
                "total_articles": count,
                "threshold": self.threshold,
                "strict_mode": self.strict_mode,
                "model": self.model.get_sentence_embedding_dimension(),
                "db_path": str(self.db_path)
            }
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {"available": False, "error": str(e)}
