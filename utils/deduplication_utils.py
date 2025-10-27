"""
Deduplication Utilities - Detect and merge duplicate articles

Uses fast string similarity (RapidFuzz) and entity-based matching to identify
duplicate or near-duplicate articles collected during the week.
"""

from typing import List, Dict, Any, Tuple, Set
from rapidfuzz import fuzz
from loguru import logger


class DeduplicationUtils:
    """Utilities for detecting and merging duplicate articles"""

    # Similarity threshold for considering articles as duplicates
    # Range: 0.0-1.0, where 1.0 is identical
    # These thresholds are deliberately HIGH (conservative) to preserve article diversity
    # while still removing obvious duplicates from identical news coverage
    #
    # Reasoning:
    # - 0.75 (old) caught too many variations: "Claude 3.5 released" vs "Claude 3.5 announcement"
    # - 0.85+ ensures only truly duplicate articles are merged
    # - Articles about same event but different angles/sources should remain separate
    TITLE_SIMILARITY_THRESHOLD = 0.88  # 88% title similarity = near-identical titles
    CONTENT_SIMILARITY_THRESHOLD = 0.80  # 80% content similarity = substantial overlap
    ENTITY_OVERLAP_THRESHOLD = 0.75  # 75% shared entities = very high topic overlap

    @staticmethod
    def find_duplicate_articles(
        articles: List[Dict[str, Any]],
        strategy: str = "combined"
    ) -> List[Tuple[str, str, float]]:
        """
        Find potential duplicate articles using multiple strategies

        Args:
            articles: List of article dictionaries
            strategy: Detection strategy:
                - 'title': Only title matching (most conservative)
                - 'content': Only content matching
                - 'entities': Only entity overlap
                - 'combined_strict': All 3 must match above threshold (very conservative)
                - 'combined': Any of 3 strategies finds match (default, balanced)

        Returns:
            List of (article_id_1, article_id_2, similarity_score) tuples
        """
        duplicates = []

        if strategy == 'combined_strict':
            # Require ALL three strategies to find duplicates (most conservative)
            # This means only truly identical articles from multiple sources are merged
            title_dups = set(DeduplicationUtils._find_title_duplicates(articles))
            content_dups = set(DeduplicationUtils._find_content_duplicates(articles))
            entity_dups = set(DeduplicationUtils._find_entity_duplicates(articles))

            # Find intersection - pairs that match on ALL three dimensions
            for pair in title_dups & content_dups & entity_dups:
                # Re-fetch the score (use title similarity as primary)
                id1, id2, score = pair
                duplicates.append(pair)

            logger.info(
                f"Found {len(title_dups)} title matches, {len(content_dups)} content matches, "
                f"{len(entity_dups)} entity matches. Using intersection: {len(duplicates)} pairs"
            )
        else:
            # Default 'combined' strategy: OR logic (any match counts)
            if strategy in ['title', 'combined']:
                title_duplicates = DeduplicationUtils._find_title_duplicates(articles)
                duplicates.extend(title_duplicates)

            if strategy in ['content', 'combined']:
                content_duplicates = DeduplicationUtils._find_content_duplicates(articles)
                duplicates.extend(content_duplicates)

            if strategy in ['entities', 'combined']:
                entity_duplicates = DeduplicationUtils._find_entity_duplicates(articles)
                duplicates.extend(entity_duplicates)

        # Remove duplicate pairs (A,B and B,A)
        unique_duplicates = []
        seen = set()
        for id1, id2, score in duplicates:
            pair = tuple(sorted([id1, id2]))
            if pair not in seen:
                unique_duplicates.append((id1, id2, score))
                seen.add(pair)

        logger.info(
            f"Found {len(unique_duplicates)} potential duplicate pairs using '{strategy}' strategy "
            f"(thresholds: title={DeduplicationUtils.TITLE_SIMILARITY_THRESHOLD}, "
            f"content={DeduplicationUtils.CONTENT_SIMILARITY_THRESHOLD}, "
            f"entity={DeduplicationUtils.ENTITY_OVERLAP_THRESHOLD})"
        )
        return unique_duplicates

    @staticmethod
    def _find_title_duplicates(
        articles: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, float]]:
        """Find duplicates based on title similarity"""
        duplicates = []

        for i, article1 in enumerate(articles):
            for article2 in articles[i + 1:]:
                similarity = DeduplicationUtils.string_similarity(
                    article1.get('title', ''),
                    article2.get('title', '')
                )

                if similarity >= DeduplicationUtils.TITLE_SIMILARITY_THRESHOLD:
                    duplicates.append((
                        article1.get('id'),
                        article2.get('id'),
                        similarity
                    ))

        return duplicates

    @staticmethod
    def _find_content_duplicates(
        articles: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, float]]:
        """Find duplicates based on content similarity (first 500 chars)"""
        duplicates = []

        for i, article1 in enumerate(articles):
            for article2 in articles[i + 1:]:
                # Use first 500 characters of content for comparison
                content1 = article1.get('content', '')[:500].lower()
                content2 = article2.get('content', '')[:500].lower()

                similarity = DeduplicationUtils.string_similarity(content1, content2)

                if similarity >= DeduplicationUtils.CONTENT_SIMILARITY_THRESHOLD:
                    duplicates.append((
                        article1.get('id'),
                        article2.get('id'),
                        similarity
                    ))

        return duplicates

    @staticmethod
    def _find_entity_duplicates(
        articles: List[Dict[str, Any]]
    ) -> List[Tuple[str, str, float]]:
        """Find duplicates based on shared entity overlap"""
        duplicates = []

        for i, article1 in enumerate(articles):
            entities1 = DeduplicationUtils._extract_entity_set(article1)
            if not entities1:
                continue

            for article2 in articles[i + 1:]:
                entities2 = DeduplicationUtils._extract_entity_set(article2)
                if not entities2:
                    continue

                overlap = DeduplicationUtils.entity_overlap(entities1, entities2)

                if overlap >= DeduplicationUtils.ENTITY_OVERLAP_THRESHOLD:
                    duplicates.append((
                        article1.get('id'),
                        article2.get('id'),
                        overlap
                    ))

        return duplicates

    @staticmethod
    def string_similarity(str1: str, str2: str) -> float:
        """
        Calculate string similarity using RapidFuzz token_sort_ratio

        RapidFuzz is 5-10x faster than SequenceMatcher and better at:
        - Word-order independent matching: "A B C" vs "C B A"
        - Title variations: "GPT-5 OpenAI pushes" vs "OpenAI pushes GPT-5"
        - Minor spacing/punctuation differences

        Args:
            str1: First string
            str2: Second string

        Returns:
            Similarity score (0.0-1.0)
        """
        if not str1 or not str2:
            return 0.0

        # token_sort_ratio: splits into words, sorts, then compares
        # This handles "A B C" == "C B A" scenarios
        # Returns 0-100, normalize to 0-1
        similarity = fuzz.token_sort_ratio(str1.lower(), str2.lower()) / 100.0
        return similarity

    @staticmethod
    def entity_overlap(entities1: Set[str], entities2: Set[str]) -> float:
        """
        Calculate overlap between two entity sets (Jaccard index)

        Args:
            entities1: First entity set
            entities2: Second entity set

        Returns:
            Overlap score (0.0-1.0)
        """
        if not entities1 or not entities2:
            return 0.0

        intersection = len(entities1 & entities2)
        union = len(entities1 | entities2)

        if union == 0:
            return 0.0

        return intersection / union

    @staticmethod
    def _extract_entity_set(article: Dict[str, Any]) -> Set[str]:
        """Extract entity set from article"""
        entities = set()

        # Get entities from checkpoint if available
        if 'entities' in article:
            article_entities = article.get('entities', {})
            for entity_type, entity_list in article_entities.items():
                if isinstance(entity_list, list):
                    entities.update([e.lower() for e in entity_list])

        # Also extract key words from title
        title = article.get('title', '').lower()
        title_words = [w for w in title.split() if len(w) > 2]
        entities.update(title_words)

        return entities

    @staticmethod
    def merge_duplicate_articles(
        article1: Dict[str, Any],
        article2: Dict[str, Any],
        strategy: str = "prefer_higher_score"
    ) -> Dict[str, Any]:
        """
        Merge two duplicate articles into one

        Args:
            article1: First article
            article2: Second article
            strategy: Merge strategy ('prefer_higher_score', 'prefer_recent', 'combine', 'smart_merge')

        Returns:
            Merged article dictionary
        """
        if strategy == "prefer_higher_score":
            # Keep the article with higher tier2_score
            score1 = article1.get('tier2_score', 0)
            score2 = article2.get('tier2_score', 0)
            primary = article1 if score1 >= score2 else article2
            secondary = article2 if score1 >= score2 else article1

        elif strategy == "prefer_recent":
            # Keep the more recently collected article
            time1 = article1.get('timestamp_created', '')
            time2 = article2.get('timestamp_created', '')
            primary = article1 if time1 >= time2 else article2
            secondary = article2 if time1 >= time2 else article1

        elif strategy == "smart_merge":
            # For smart merge: use the higher-scoring article but combine metadata
            score1 = article1.get('tier2_score', 0)
            score2 = article2.get('tier2_score', 0)
            primary = article1 if score1 >= score2 else article2
            secondary = article2 if score1 >= score2 else article1

            # Create merged article with higher score
            merged = primary.copy()
            merged['tier2_score'] = max(score1, score2)  # Keep the higher score
            merged['merged_with'] = [secondary.get('id')]
            merged['merge_strategy'] = 'smart_merge'
            merged['sources'] = [primary.get('source'), secondary.get('source')]

            return merged

        else:  # "combine"
            # Average scores and combine data
            primary = article1.copy()
            score1 = article1.get('tier2_score', 0)
            score2 = article2.get('tier2_score', 0)
            primary['tier2_score'] = (score1 + score2) / 2
            primary['merged_from'] = [article1.get('id'), article2.get('id')]
            return primary

        # For prefer strategies: copy primary and add merge metadata
        merged = primary.copy()
        merged['merged_with'] = secondary.get('id')
        merged['merge_strategy'] = strategy

        return merged

    @staticmethod
    def deduplicate_articles(
        articles: Dict[str, Dict[str, Any]],
        strategy: str = "combined",
        preserve_high_scorers: bool = True,
        min_score_to_preserve: float = 6.0
    ) -> Tuple[Dict[str, Dict[str, Any]], int]:
        """
        Deduplicate a collection of articles with smart preservation of high-impact articles

        Args:
            articles: Dictionary of article_id -> article_data
            strategy: Detection strategy for finding duplicates ('combined', 'title', 'content', 'entities')
            preserve_high_scorers: If True, preserve high-scoring articles even if similar to others
            min_score_to_preserve: Minimum tier2_score (0-10) to preserve despite similarity (default: 6.0)

        Returns:
            Tuple of (deduplicated_articles, removed_count)
        """
        articles_list = [
            {**data, 'id': article_id}
            for article_id, data in articles.items()
        ]

        # Find duplicates
        duplicates = DeduplicationUtils.find_duplicate_articles(
            articles_list,
            strategy=strategy
        )

        # Track which articles to remove
        removed_ids = set()
        merged_articles = {}
        preserved_high_scorers = set()

        for id1, id2, similarity in duplicates:
            if id1 in removed_ids or id2 in removed_ids:
                continue

            article1 = next(a for a in articles_list if a['id'] == id1)
            article2 = next(a for a in articles_list if a['id'] == id2)

            score1 = article1.get('tier2_score', 0)
            score2 = article2.get('tier2_score', 0)
            max_score = max(score1, score2)
            min_score = min(score1, score2)

            # Decision: whether to deduplicate or preserve both
            if preserve_high_scorers and max_score >= min_score_to_preserve:
                # High-impact articles: preserve both or merge without removing
                merged = DeduplicationUtils.merge_duplicate_articles(
                    article1,
                    article2,
                    strategy="smart_merge"
                )
                merged_articles[id1] = {k: v for k, v in merged.items() if k != 'id'}
                removed_ids.add(id2)
                preserved_high_scorers.add(id1)

                logger.info(
                    f"Merged (HIGH IMPACT) {id1} + {id2} (similarity: {similarity:.2f}, scores: {score1:.1f}/{score2:.1f})"
                )
            else:
                # Low-impact duplicates: merge and only keep higher-scoring one
                merged = DeduplicationUtils.merge_duplicate_articles(
                    article1,
                    article2,
                    strategy="prefer_higher_score"
                )
                merged_articles[id1] = {k: v for k, v in merged.items() if k != 'id'}
                removed_ids.add(id2)

                logger.info(
                    f"Merged (LOW IMPACT) {id1} + {id2} (similarity: {similarity:.2f}, scores: {score1:.1f}/{score2:.1f})"
                )

        # Build final deduped dictionary
        deduped = {}
        for article_id, article_data in articles.items():
            if article_id not in removed_ids:
                if article_id in merged_articles:
                    # Include the merged article with combined metadata
                    deduped[article_id] = merged_articles[article_id]
                else:
                    deduped[article_id] = article_data

        logger.info(
            f"Deduplication complete: {len(articles)} → {len(deduped)} articles "
            f"(removed {len(removed_ids)} duplicates, preserved {len(preserved_high_scorers)} high-impact merged articles)"
        )

        return deduped, len(removed_ids)

    @staticmethod
    def rank_by_combined_score(
        articles: Dict[str, Dict[str, Any]]
    ) -> List[Tuple[str, Dict[str, Any], float]]:
        """
        Rank articles by combined score from all collection days

        Combined score: tier2_score × 0.4 + recency_boost × 0.4 + trending_boost × 0.2

        Args:
            articles: Dictionary of articles from weekly collection

        Returns:
            List of (article_id, article_data, combined_score) sorted by score descending
        """
        ranked = []

        for article_id, article_data in articles.items():
            tier2_score = article_data.get('tier2_score', 0) / 10.0  # Normalize to 0-1
            trending_boost = 1.0 if article_data.get('tier1_score', 0) >= 6 else 0.5

            # Recency boost: articles from more recent days get higher boost
            collection_day = article_data.get('collection_day', 0)
            recency_boost = collection_day / 7.0  # Day 7 (latest) = 1.0, Day 1 = 0.14

            combined_score = (tier2_score * 0.4) + (recency_boost * 0.4) + (trending_boost * 0.2)

            ranked.append((article_id, article_data, combined_score))

        # Sort by combined score descending
        ranked.sort(key=lambda x: x[2], reverse=True)

        logger.info(f"Ranked {len(ranked)} articles by combined score")

        return ranked
