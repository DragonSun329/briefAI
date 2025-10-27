"""
News Evaluator Module

Evaluates and ranks articles based on Impact, Relevance, Recency, and Credibility.
Uses Claude to score articles and select the most important ones.
Includes multi-stage deduplication: fuzzy matching + semantic similarity.
"""

import json
from typing import List, Dict, Any, Optional
from datetime import datetime
from loguru import logger

from utils.llm_client_enhanced import LLMClient
from utils.entity_extractor import EntityExtractor
from utils.semantic_deduplication import SemanticDeduplicator
from pathlib import Path


class NewsEvaluator:
    """Evaluates and ranks news articles"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        min_score: float = 6.0,
        company_context: Optional[Dict[str, Any]] = None,
        enable_deduplication: bool = True
    ):
        """
        Initialize news evaluator

        Args:
            llm_client: LLM client instance (creates new if None)
            min_score: Minimum average score to include article
            company_context: Company context for relevancy evaluation
            enable_deduplication: Enable entity-based deduplication
        """
        self.llm_client = llm_client or LLMClient()
        self.min_score = min_score
        self.company_context = company_context or {}
        self.enable_deduplication = enable_deduplication

        # Initialize deduplication components
        if self.enable_deduplication:
            # Entity-based deduplication (existing)
            self.entity_extractor = EntityExtractor(llm_client=self.llm_client)
            logger.info("Entity-based deduplication enabled")

            # Semantic deduplication (new)
            self.semantic_dedup = SemanticDeduplicator(strict_mode=True)
            if self.semantic_dedup.available:
                logger.info("Semantic deduplication enabled (vector-based)")
            else:
                logger.warning("Semantic deduplication unavailable - missing dependencies")
                self.semantic_dedup = None

        # Load company context from categories config if not provided
        if not self.company_context:
            try:
                config_path = Path("./config/categories.json")
                if config_path.exists():
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                        self.company_context = config.get('company_context', {})
            except Exception as e:
                logger.warning(f"Could not load company context: {e}")

    def evaluate_articles(
        self,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]],
        top_n: int = 10,
        top_by_score: int = 7,
        top_by_novelty: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Evaluate and rank articles with novelty scoring

        Args:
            articles: List of scraped articles
            categories: User's selected categories
            top_n: Total number of articles to return (default: 10)
            top_by_score: Number of articles to select by quality score (default: 7)
            top_by_novelty: Number of articles to select by novelty score (default: 3)

        Returns:
            List of evaluated and ranked articles (top_by_score + top_by_novelty)
        """
        logger.info(f"Evaluating {len(articles)} articles (top {top_by_score} by score + {top_by_novelty} by novelty)...")

        # Step 1: Extract entities and deduplicate if enabled
        if self.enable_deduplication and len(articles) > 1:
            articles = self._deduplicate_articles(articles)
            logger.info(f"After deduplication: {len(articles)} unique articles")

        evaluated_articles = []

        for i, article in enumerate(articles):
            try:
                logger.debug(f"Evaluating article {i+1}/{len(articles)}: {article['title']}")

                evaluation = self._evaluate_single_article(article, categories)

                # Add evaluation to article
                article['evaluation'] = evaluation
                article['avg_score'] = evaluation['average_score']
                article['5d_score_breakdown'] = evaluation.get('scores', {})

                # Use the 5D weighted score from evaluation
                base_weighted_score = evaluation.get('weighted_score', evaluation['average_score'])

                # Apply source weighting if available (additional boost on top of 5D score)
                relevance_weight = article.get('relevance_weight', 1)
                if relevance_weight > 1:
                    # Boost score based on source relevance weight (1-10 scale)
                    weight_multiplier = 1 + ((relevance_weight - 1) / 9) * 0.3  # Max 30% boost
                    article['weighted_score'] = base_weighted_score * weight_multiplier
                    article['source_weight'] = relevance_weight
                    logger.debug(f"Applied source weight {relevance_weight} → score boost: {base_weighted_score:.2f} → {article['weighted_score']:.2f}")
                else:
                    article['weighted_score'] = base_weighted_score
                    article['source_weight'] = 1.0

                # Only keep articles above threshold (use weighted score)
                if article['weighted_score'] >= self.min_score:
                    evaluated_articles.append(article)

            except Exception as e:
                logger.error(f"Failed to evaluate article '{article['title']}': {e}")
                continue

        # Sort by weighted score (descending)
        evaluated_articles.sort(key=lambda x: x['weighted_score'], reverse=True)

        # Step 2: Calculate novelty scores for remaining articles
        logger.info(f"Calculating novelty scores for {len(evaluated_articles)} articles...")
        evaluated_articles = self._calculate_novelty_scores(evaluated_articles)

        # Step 3: Select top articles
        # - Top N by weighted score
        # - Top M by novelty score (from remaining articles)
        top_by_quality = evaluated_articles[:top_by_score]
        remaining_articles = evaluated_articles[top_by_score:]
        remaining_articles.sort(key=lambda x: x.get('novelty_score', 0), reverse=True)
        top_by_novelty = remaining_articles[:top_by_novelty]

        # Combine and sort by original order (quality first, then novelty)
        final_articles = top_by_quality + top_by_novelty

        logger.info(
            f"Selected {len(final_articles)} articles: "
            f"{len(top_by_quality)} by quality (scores: {[round(a['weighted_score'], 2) for a in top_by_quality[:3]]}...), "
            f"{len(top_by_novelty)} by novelty (scores: {[round(a.get('novelty_score', 0), 2) for a in top_by_novelty[:3]]}...)"
        )

        return final_articles

    def _evaluate_single_article(
        self,
        article: Dict[str, Any],
        categories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Evaluate a single article using Claude

        Returns evaluation dictionary with scores and rationale
        """
        system_prompt = self._build_evaluation_prompt()
        user_message = self._build_article_message(article, categories)

        response = self.llm_client.chat_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.3
        )

        # Calculate weighted score using 5D scoring system
        scores = response.get('scores', {})

        # 5D weights: market_impact (25%), competitive_impact (20%), strategic_relevance (20%),
        #             operational_relevance (15%), credibility (10%)
        weights = {
            'market_impact': 0.25,
            'competitive_impact': 0.20,
            'strategic_relevance': 0.20,
            'operational_relevance': 0.15,
            'credibility': 0.10
        }

        # Calculate weighted score
        weighted_score = sum(scores.get(key, 0) * weight for key, weight in weights.items())
        response['weighted_score'] = round(weighted_score, 2)

        # Also calculate average for backward compatibility
        avg_score = sum(scores.values()) / len(scores) if scores else 0
        response['average_score'] = round(avg_score, 2)

        return response

    def _build_evaluation_prompt(self) -> str:
        """Build system prompt for article evaluation with 5D scoring"""
        context_info = ""
        if self.company_context:
            business = self.company_context.get('business', '')
            industry = self.company_context.get('industry', '')
            focus_areas = self.company_context.get('focus_areas', [])
            context_info = f"""
**公司背景**:
- 业务: {business}
- 行业: {industry}
- 关注领域: {', '.join(focus_areas)}

评估相关性和影响时,请特别考虑与上述业务和关注领域的关联度。
"""

        return f"""你是一位专业分析师,为CEO评估AI行业新闻。
{context_info}
**任务**: 对每篇文章在5个维度上评分 (1-10分):

1. **Market Impact** (市场影响力 - 25%权重): 这条新闻对整个市场和行业的影响有多大?
   - 9-10: 行业重大突破,改变市场格局
   - 7-8: 重要市场动向,显著影响
   - 5-6: 中等市场关注度,有一定影响
   - 1-4: 次要市场新闻,影响有限

2. **Competitive Impact** (竞争影响力 - 20%权重): 这条新闻对竞争格局和竞争对手的影响如何?
   - 9-10: 直接影响竞争态势,竞争对手重大动向
   - 7-8: 竞争格局有明显变化,值得关注
   - 5-6: 有一定竞争影响,需要了解
   - 1-4: 竞争影响有限

3. **Strategic Relevance** (战略相关性 - 20%权重): 与公司业务战略和长期规划的相关度?
   - 9-10: 直接影响公司战略方向和决策
   - 7-8: 对战略规划很重要,需要深入了解
   - 5-6: 值得了解,对战略有辅助意义
   - 1-4: 战略相关度较低

4. **Operational Relevance** (运营相关性 - 15%权重): 与日常运营、产品开发、客户体验的相关度?
   - 9-10: 直接影响日常运营或产品策略
   - 7-8: 对运营有重要参考价值
   - 5-6: 值得了解,可用于优化运营
   - 1-4: 运营相关度有限

5. **Credibility** (可信度 - 10%权重): 来源和内容的可信度如何?
   - 9-10: 顶级来源,充分证实,事实严谨
   - 7-8: 信誉良好,基本核实,可信
   - 5-6: 一般来源,需要适度验证
   - 1-4: 来源或声明可疑,需要谨慎

**返回JSON格式**:
{{
  "scores": {{
    "market_impact": 8,
    "competitive_impact": 7,
    "strategic_relevance": 9,
    "operational_relevance": 6,
    "credibility": 8
  }},
  "weighted_score": 7.85,
  "rationale": "简要说明 (2-3句中文)",
  "key_takeaway": "一句话总结 (中文)",
  "recommended_category": "最匹配的分类"
}}

权重计算: weighted_score = (market_impact × 0.25) + (competitive_impact × 0.20) + (strategic_relevance × 0.20) + (operational_relevance × 0.15) + (credibility × 0.10)

请保持客观和批判性。大多数文章在各维度应该得5-7分。只有真正卓越的内容才应得8-10分。"""

    def _build_article_message(
        self,
        article: Dict[str, Any],
        categories: List[Dict[str, Any]]
    ) -> str:
        """Build user message with article details"""
        category_names = ", ".join([cat['name'] for cat in categories])

        focus_tags = article.get('focus_tags', [])
        focus_info = f"\n**Source focus tags**: {', '.join(focus_tags)}" if focus_tags else ""

        return f"""请评估这篇文章:

**标题**: {article['title']}
**来源**: {article['source']} (可信度: {article.get('credibility_score', 'N/A')}/10)
**发布时间**: {article.get('published_date', 'Unknown')}
**语言**: {article.get('language', 'Unknown')}{focus_info}

**内容**: {article['content'][:1000]}...

**用户关注的分类**: {category_names}

请以JSON格式提供评估。"""

    def _deduplicate_articles(self, articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Deduplicate articles using multi-stage approach:
        1. Entity-based clustering (existing articles in this batch)
        2. Semantic similarity (against recent articles in vector DB)

        Args:
            articles: List of articles to deduplicate

        Returns:
            Deduplicated list of articles
        """
        logger.info("Starting multi-stage deduplication...")

        # Stage 1: Entity-based clustering (within batch)
        logger.info("Stage 1: Extracting entities for batch deduplication...")
        articles = self.entity_extractor.extract_entities_batch(articles)

        # Build similarity matrix and cluster
        clusters = []
        used_indices = set()

        for i, article1 in enumerate(articles):
            if i in used_indices:
                continue

            # Start a new cluster
            cluster = [i]
            used_indices.add(i)

            # Find similar articles
            for j in range(i + 1, len(articles)):
                if j in used_indices:
                    continue

                article2 = articles[j]

                # Calculate entity similarity
                similarity = self.entity_extractor.calculate_similarity(
                    article1.get('entities', {}),
                    article2.get('entities', {})
                )

                # If similarity > threshold, add to cluster
                if similarity >= 0.6:  # 60% similarity threshold
                    cluster.append(j)
                    used_indices.add(j)
                    logger.debug(f"Clustering similar articles: '{article1['title'][:50]}' ~ '{article2['title'][:50]}' (similarity: {similarity:.2f})")

            clusters.append(cluster)

        # Keep best article from each cluster
        deduplicated = []
        for cluster in clusters:
            if len(cluster) == 1:
                # No duplicates, keep the article
                deduplicated.append(articles[cluster[0]])
            else:
                # Multiple similar articles, keep the one from highest credibility source
                cluster_articles = [articles[idx] for idx in cluster]
                best_article = max(cluster_articles, key=lambda x: x.get('credibility_score', 5))
                deduplicated.append(best_article)
                logger.debug(f"Removed {len(cluster) - 1} duplicate(s), kept: '{best_article['title'][:50]}'")

        logger.info(f"Stage 1 complete: {len(articles)} → {len(deduplicated)} articles ({len(articles) - len(deduplicated)} batch duplicates removed)")

        # Stage 2: Semantic deduplication (against 7-day history)
        if self.semantic_dedup and self.semantic_dedup.available:
            logger.info("Stage 2: Checking for semantic duplicates against recent history...")
            final_articles = []
            semantic_dups_count = 0

            for article in deduplicated:
                # Check if article is semantically similar to recent articles
                is_duplicate, dup_id, score = self.semantic_dedup.check_duplicate(article)

                if is_duplicate:
                    logger.info(f"Semantic duplicate detected: '{article['title'][:50]}' (match score: {score:.3f})")
                    semantic_dups_count += 1
                else:
                    # Not a duplicate - add to vector DB and final list
                    final_articles.append(article)
                    self.semantic_dedup.add_article(article)

            logger.info(f"Stage 2 complete: Removed {semantic_dups_count} semantic duplicates")

            # Cleanup old articles from vector DB (>7 days)
            if semantic_dups_count > 0:
                cleanup_count = self.semantic_dedup.cleanup_old_articles(days=7)
                if cleanup_count > 0:
                    logger.debug(f"Cleaned up {cleanup_count} old articles from semantic index")

            deduplicated = final_articles

        logger.info(f"Deduplication complete: {len(articles)} → {len(deduplicated)} unique articles")

        return deduplicated

    def _calculate_novelty_scores(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Calculate novelty scores for articles based on entity overlap

        Novelty = how different an article is from others
        Calculated as: 1 - (entity_overlap / max_entity_count)

        Args:
            articles: List of evaluated articles with searchable_entities

        Returns:
            Articles with 'novelty_score' field added
        """
        logger.debug(f"Calculating novelty scores for {len(articles)} articles...")

        # Extract entities from all articles (or use existing searchable_entities)
        entity_extractor = EntityExtractor(llm_client=self.llm_client)

        for i, article in enumerate(articles):
            try:
                # Get or extract entities
                if 'searchable_entities' not in article:
                    paraphrased = article.get('paraphrased_content', '')
                    if paraphrased:
                        entities = entity_extractor.extract_entities(paraphrased)
                        article['searchable_entities'] = entities
                    else:
                        article['searchable_entities'] = entity_extractor._empty_entities()

                # Calculate novelty based on entity overlap with higher-ranked articles
                article_entities = article.get('searchable_entities', {})

                # Compare with previous articles (higher-ranked ones)
                entity_overlaps = []
                for prev_article in articles[:i]:
                    prev_entities = prev_article.get('searchable_entities', {})

                    # Calculate overlap (simple: how many entities are shared)
                    overlap = self._calculate_entity_overlap(article_entities, prev_entities)
                    entity_overlaps.append(overlap)

                # Novelty = inverse of average overlap with previous articles
                if entity_overlaps:
                    avg_overlap = sum(entity_overlaps) / len(entity_overlaps)
                    novelty_score = 1.0 - avg_overlap  # High overlap = low novelty
                else:
                    novelty_score = 1.0  # First article = maximum novelty

                article['novelty_score'] = round(novelty_score, 2)
                logger.debug(
                    f"Article {i+1}: novelty={novelty_score:.2f} "
                    f"(entities: {sum(len(v) for v in article_entities.values())})"
                )

            except Exception as e:
                logger.error(f"Failed to calculate novelty for article {i+1}: {e}")
                article['novelty_score'] = 0.5  # Default middle value

        return articles

    def _calculate_entity_overlap(
        self,
        entities1: Dict[str, List[str]],
        entities2: Dict[str, List[str]]
    ) -> float:
        """
        Calculate entity overlap between two articles

        Returns score between 0 (no overlap) and 1 (complete overlap)

        Args:
            entities1: First entity dictionary
            entities2: Second entity dictionary

        Returns:
            Overlap score (0-1)
        """
        # Combine all entity types
        set1 = set()
        set2 = set()

        for entity_type in entities1.keys():
            for entity in entities1.get(entity_type, []):
                set1.add(entity.lower().strip())
            for entity in entities2.get(entity_type, []):
                set2.add(entity.lower().strip())

        if not set1 and not set2:
            return 0.0

        # Jaccard similarity: intersection / union
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        overlap = intersection / union if union > 0 else 0.0
        return overlap


if __name__ == "__main__":
    # Test news evaluator
    evaluator = NewsEvaluator()

    # Sample article
    sample_article = {
        'title': 'OpenAI发布GPT-5，性能提升显著',
        'source': '机器之心',
        'content': 'OpenAI今日发布了GPT-5大语言模型，在多项基准测试中性能大幅提升...',
        'published_date': datetime.now().isoformat(),
        'language': 'zh-CN',
        'credibility_score': 9
    }

    sample_categories = [
        {'id': 'llm', 'name': '大模型'}
    ]

    result = evaluator.evaluate_articles([sample_article], sample_categories, top_n=1)
    print(json.dumps(result, ensure_ascii=False, indent=2))
