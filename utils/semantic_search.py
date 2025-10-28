"""
Semantic Search Module - Embedding-based similarity search for articles

Provides semantic search capabilities using sentence transformers and cosine similarity.
Includes embedding caching and efficient similarity computation.
"""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
import json
import hashlib
from datetime import datetime

try:
    from sentence_transformers import SentenceTransformer
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

from utils.cache_manager import CacheManager


class SemanticSearch:
    """
    Semantic search engine using embeddings and cosine similarity.

    Features:
    - Generate embeddings from text using sentence transformers
    - Cache embeddings for performance
    - Compute semantic similarity between query and documents
    - Rerank results by semantic relevance
    - Support for hybrid search (keyword + semantic)
    """

    def __init__(
        self,
        model_name: str = "all-MiniLM-L6-v2",
        cache_manager: Optional[CacheManager] = None,
        similarity_threshold: float = 0.3
    ):
        """
        Initialize semantic search engine.

        Args:
            model_name: Sentence transformer model name
            cache_manager: Optional cache manager for embedding caching
            similarity_threshold: Minimum similarity score for results (0.0-1.0)
        """
        self.model_name = model_name
        self.cache_manager = cache_manager or CacheManager()
        self.similarity_threshold = similarity_threshold
        self.model = None
        self._initialized = False

        if HAS_TRANSFORMERS:
            try:
                self.model = SentenceTransformer(model_name)
                self._initialized = True
            except Exception as e:
                print(f"⚠ Failed to load semantic model: {e}")
                self._initialized = False

    def get_embedding(self, text: str) -> Optional[np.ndarray]:
        """
        Get embedding for text, using cache if available.

        Args:
            text: Text to embed

        Returns:
            Embedding vector as numpy array, or None if model not available
        """
        if not self._initialized:
            return None

        # Create cache key from text hash
        text_hash = hashlib.md5(text.encode()).hexdigest()
        cache_key = f"embedding_{self.model_name}_{text_hash}"

        # Try to get from cache
        cached = self.cache_manager.get(cache_key)
        if cached is not None:
            try:
                return np.array(json.loads(cached))
            except:
                pass

        # Generate new embedding
        try:
            embedding = self.model.encode(text, convert_to_numpy=True)

            # Cache the embedding
            self.cache_manager.set(cache_key, json.dumps(embedding.tolist()), ttl=86400)

            return embedding
        except Exception as e:
            return None

    def get_embeddings_batch(self, texts: List[str]) -> Optional[np.ndarray]:
        """
        Get embeddings for multiple texts efficiently.

        Args:
            texts: List of texts to embed

        Returns:
            Array of embeddings or None if model not available
        """
        if not self._initialized or not texts:
            return None

        embeddings = []
        for text in texts:
            emb = self.get_embedding(text)
            if emb is not None:
                embeddings.append(emb)

        if embeddings:
            return np.array(embeddings)
        return None

    def cosine_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0.0-1.0)
        """
        dot_product = np.dot(embedding1, embedding2)
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def search_similar(
        self,
        query: str,
        articles: List[Dict[str, Any]],
        search_fields: Optional[List[str]] = None,
        top_k: int = 10,
        return_scores: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Search articles by semantic similarity to query.

        Args:
            query: Search query text
            articles: List of articles to search
            search_fields: Fields to use for similarity (default: title, paraphrased_content)
            top_k: Return top K results
            return_scores: Include similarity scores in results

        Returns:
            List of articles sorted by semantic similarity
        """
        if not self._initialized or not articles:
            return []

        if search_fields is None:
            search_fields = ["title", "paraphrased_content"]

        # Get query embedding
        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return []

        # Compute similarities
        results_with_scores = []
        for article in articles:
            # Combine search fields
            text_parts = []
            for field in search_fields:
                if field in article and article[field]:
                    text_parts.append(str(article[field]))

            if not text_parts:
                continue

            combined_text = " ".join(text_parts)
            article_embedding = self.get_embedding(combined_text)

            if article_embedding is None:
                continue

            similarity = self.cosine_similarity(query_embedding, article_embedding)

            if similarity >= self.similarity_threshold:
                article_with_score = article.copy()
                article_with_score['semantic_similarity'] = similarity
                results_with_scores.append(article_with_score)

        # Sort by similarity
        results_with_scores.sort(key=lambda x: x['semantic_similarity'], reverse=True)

        # Return top K
        return results_with_scores[:top_k]

    def rerank_results(
        self,
        query: str,
        articles: List[Dict[str, Any]],
        search_fields: Optional[List[str]] = None,
        diversity_boost: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Rerank articles by semantic similarity to query.

        Args:
            query: Search query text
            articles: Articles to rerank (may come from keyword search)
            search_fields: Fields to use for similarity
            diversity_boost: Boost diverse results (0.0-1.0). Higher = more diversity

        Returns:
            Reranked articles with semantic_similarity scores
        """
        if not self._initialized or not articles:
            return articles

        if search_fields is None:
            search_fields = ["title", "paraphrased_content"]

        # Get query embedding
        query_embedding = self.get_embedding(query)
        if query_embedding is None:
            return articles

        # Add semantic similarity scores
        for article in articles:
            text_parts = []
            for field in search_fields:
                if field in article and article[field]:
                    text_parts.append(str(article[field]))

            if text_parts:
                combined_text = " ".join(text_parts)
                article_embedding = self.get_embedding(combined_text)

                if article_embedding is not None:
                    similarity = self.cosine_similarity(query_embedding, article_embedding)
                    article['semantic_similarity'] = similarity
                else:
                    article['semantic_similarity'] = 0.0
            else:
                article['semantic_similarity'] = 0.0

        # If diversity boost requested, diversify selection
        if diversity_boost > 0 and len(articles) > 1:
            articles = self._apply_diversity_boost(articles, query_embedding, diversity_boost)
        else:
            # Simple reranking by similarity
            articles.sort(key=lambda x: x['semantic_similarity'], reverse=True)

        return articles

    def _apply_diversity_boost(
        self,
        articles: List[Dict[str, Any]],
        query_embedding: np.ndarray,
        boost_factor: float
    ) -> List[Dict[str, Any]]:
        """
        Apply diversity boosting to avoid similar results.

        Args:
            articles: Articles with semantic_similarity scores
            query_embedding: Query embedding
            boost_factor: Diversity boost factor (0.0-1.0)

        Returns:
            Diversified ranking
        """
        if not articles:
            return articles

        # Sort by similarity first
        articles = sorted(articles, key=lambda x: x.get('semantic_similarity', 0), reverse=True)

        selected = [articles[0]]
        article_embeddings = {0: self.get_embedding(
            " ".join([str(articles[0].get(f, '')) for f in ['title', 'paraphrased_content']])
        )}

        for i in range(1, len(articles)):
            article = articles[i]

            # Get embedding for this article
            text = " ".join([str(article.get(f, '')) for f in ['title', 'paraphrased_content']])
            current_emb = self.get_embedding(text)

            if current_emb is None:
                continue

            # Calculate diversity score (min distance to already selected)
            min_similarity_to_selected = min(
                self.cosine_similarity(current_emb, article_embeddings[j])
                for j in range(len(selected))
            )

            # Adjusted score: similarity to query - diversity penalty
            adjusted_score = (
                article.get('semantic_similarity', 0) -
                (boost_factor * (1 - min_similarity_to_selected))
            )

            # Add back to selected if score still good
            if adjusted_score > 0:
                selected.append(article)
                article_embeddings[len(selected) - 1] = current_emb

        return selected

    def cluster_by_similarity(
        self,
        articles: List[Dict[str, Any]],
        search_fields: Optional[List[str]] = None,
        similarity_threshold: float = 0.7
    ) -> List[List[Dict[str, Any]]]:
        """
        Cluster articles by semantic similarity.

        Args:
            articles: Articles to cluster
            search_fields: Fields to use for similarity
            similarity_threshold: Threshold for same cluster (0.7-0.95)

        Returns:
            List of clusters, each containing similar articles
        """
        if not self._initialized or not articles:
            return [[article] for article in articles]

        if search_fields is None:
            search_fields = ["title", "paraphrased_content"]

        # Get embeddings for all articles
        embeddings = {}
        for i, article in enumerate(articles):
            text_parts = []
            for field in search_fields:
                if field in article and article[field]:
                    text_parts.append(str(article[field]))

            if text_parts:
                combined_text = " ".join(text_parts)
                emb = self.get_embedding(combined_text)
                if emb is not None:
                    embeddings[i] = emb

        # Simple clustering: greedy approach
        clusters = []
        assigned = set()

        for i in sorted(embeddings.keys()):
            if i in assigned:
                continue

            cluster = [articles[i]]
            assigned.add(i)

            # Find similar articles
            for j in sorted(embeddings.keys()):
                if j in assigned or j <= i:
                    continue

                similarity = self.cosine_similarity(embeddings[i], embeddings[j])
                if similarity >= similarity_threshold:
                    cluster.append(articles[j])
                    assigned.add(j)

            clusters.append(cluster)

        # Add articles without embeddings to nearest cluster
        for i, article in enumerate(articles):
            if i not in assigned:
                if clusters:
                    clusters[0].append(article)
                else:
                    clusters.append([article])

        return clusters

    def is_available(self) -> bool:
        """Check if semantic search is available."""
        return self._initialized
