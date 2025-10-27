"""
Batch Evaluator Module (Tier 2)

Performs lightweight batch evaluation of pre-filtered articles using LLM.
Scores 10 articles in one LLM call instead of individual calls.

Reduces token usage by:
1. Evaluating only pre-filtered articles (60-70% fewer articles)
2. Using lightweight evaluation (2 dimensions instead of 4)
3. Batch processing (10 articles per LLM call)

Articles scoring >= 6 pass to Tier 3 for full evaluation.
"""

import json
from typing import List, Dict, Any, Optional
from loguru import logger

from utils.llm_client_enhanced import LLMClient


class BatchEvaluator:
    """Lightweight batch evaluation of articles"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        batch_size: int = 15,
        pass_score: float = 6.0,
        enable_checkpoint: bool = False,
        checkpoint_manager: Optional[Any] = None
    ):
        """
        Initialize batch evaluator

        Args:
            llm_client: LLM client instance (creates new if None)
            batch_size: Number of articles to evaluate per LLM call (increased from 10 to 15 for speed)
            pass_score: Minimum score to pass to Tier 3 (0-10 scale)
            enable_checkpoint: Save results to checkpoint
            checkpoint_manager: Checkpoint manager instance
        """
        self.llm_client = llm_client or LLMClient()
        self.batch_size = batch_size
        self.pass_score = pass_score
        self.enable_checkpoint = enable_checkpoint
        self.checkpoint_manager = checkpoint_manager

        logger.info(
            f"Batch evaluator initialized "
            f"(batch_size: {batch_size}, pass_score: {pass_score})"
        )

    def evaluate_batch(
        self,
        articles: List[Dict[str, Any]],
        categories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Batch evaluate articles with lightweight criteria

        Args:
            articles: Pre-filtered articles from Tier 1
            categories: User's selected categories

        Returns:
            Articles that passed batch evaluation (score >= pass_score)
        """
        logger.info(f"[TIER 2] Batch evaluating {len(articles)} articles...")

        if not articles:
            logger.warning("[TIER 2] No articles to evaluate")
            return []

        passed_articles = []
        batches = [articles[i:i + self.batch_size] for i in range(0, len(articles), self.batch_size)]

        logger.info(f"[TIER 2] Processing {len(batches)} batches of {self.batch_size} articles")

        for batch_num, batch in enumerate(batches, 1):
            try:
                logger.debug(f"[TIER 2] Evaluating batch {batch_num}/{len(batches)}")

                # Evaluate this batch
                batch_results = self._evaluate_batch_call(batch, categories)

                # Process results
                for article, result in zip(batch, batch_results):
                    article['batch_eval_score'] = result['score']
                    article['batch_eval_reasoning'] = result['reasoning']

                    if result['score'] >= self.pass_score:
                        passed_articles.append(article)
                        logger.debug(
                            f"PASS  [{result['score']:.1f}] {article['title'][:60]}"
                        )
                    else:
                        logger.debug(
                            f"FAIL  [{result['score']:.1f}] {article['title'][:60]}"
                        )

            except Exception as e:
                logger.error(f"[TIER 2] Batch {batch_num} evaluation failed: {e}")
                # On error, pass articles through to be safe
                passed_articles.extend(batch)
                continue

        logger.info(
            f"[TIER 2] Results: {len(passed_articles)}/{len(articles)} articles passed "
            f"(threshold: {self.pass_score})"
        )

        return passed_articles

    def _evaluate_batch_call(
        self,
        batch: List[Dict[str, Any]],
        categories: List[Dict[str, Any]]
    ) -> List[Dict[str, float]]:
        """
        Make single LLM call to evaluate batch of articles

        Args:
            batch: List of articles to evaluate (up to batch_size)
            categories: User's selected categories

        Returns:
            List of evaluation results with scores and reasoning
        """
        # Build article summaries for batch
        articles_text = self._build_articles_text(batch, categories)

        system_prompt = self._build_system_prompt(categories)
        user_message = f"""请评估以下{len(batch)}篇文章的重要性和相关性。

{articles_text}

对每篇文章进行快速评分(1-10分):
- 1-3分: 不相关或重要性低
- 4-5分: 相关但不够重要
- 6-7分: 重要且相关 ✓ 通过第二层
- 8-10分: 高度重要且相关

以JSON格式返回每篇文章的评分。"""

        try:
            response = self.llm_client.chat_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.3,
                max_tokens=1500
            )

            # Parse response
            results = self._parse_batch_response(response, len(batch))
            return results

        except Exception as e:
            logger.error(f"Batch evaluation API call failed: {e}")
            # Return neutral scores on error (so articles pass through)
            return [
                {"score": 6.0, "reasoning": "评估失败，通过"}
                for _ in batch
            ]

    def _build_articles_text(
        self,
        batch: List[Dict[str, Any]],
        categories: List[Dict[str, Any]]
    ) -> str:
        """Build text representation of articles for batch evaluation"""
        articles_text = ""

        for i, article in enumerate(batch, 1):
            title = article.get('title', 'N/A')
            description = article.get('description', '')[:200]
            source = article.get('source', 'Unknown')
            tier1_score = article.get('tier1_score', 0)

            articles_text += f"""【文章{i}】
标题: {title}
来源: {source}
摘要: {description}
初选评分: {tier1_score:.1f}/10

"""

        return articles_text

    def _build_system_prompt(self, categories: List[Dict[str, Any]]) -> str:
        """Build system prompt for batch evaluation"""
        category_names = ", ".join([cat['name'] for cat in categories])

        return f"""你是一位新闻分类专家，需要快速评估多篇AI行业新闻的重要性和相关性。

**用户关注领域**: {category_names}

**评分标准** (1-10分):

**相关性** (占60%权重):
- 与用户关注领域的直接相关性
- 是否涉及关键技术、公司或发展趋势

**重要性** (占40%权重):
- 是否代表重大突破或行业动向
- 是否影响行业发展方向
- 是否具有新闻价值

**快速评分指南**:
- 6-7分: 值得CEO了解的内容，通过筛选 ✓
- 5分及以下: 重要性不足，无需详细分析
- 8分及以上: 高度重要，一定会被详细分析

请给出简要推理（1-2句），专注于快速决策。"""

    def _parse_batch_response(
        self,
        response: Dict[str, Any],
        expected_count: int
    ) -> List[Dict[str, float]]:
        """
        Parse batch evaluation response from LLM

        Expected format:
        {
          "evaluations": [
            {"score": 7.5, "reasoning": "相关且重要"},
            {"score": 4.0, "reasoning": "不够重要"},
            ...
          ]
        }
        """
        try:
            evaluations = response.get('evaluations', [])

            # Ensure we have correct number of results
            if len(evaluations) != expected_count:
                logger.warning(
                    f"Expected {expected_count} evaluations, got {len(evaluations)}. "
                    f"Using defaults for missing results."
                )

                # Pad with neutral scores if needed
                while len(evaluations) < expected_count:
                    evaluations.append({"score": 6.0, "reasoning": "默认通过"})

            # Validate and normalize scores
            results = []
            for eval_item in evaluations[:expected_count]:
                score = float(eval_item.get('score', 6.0))
                score = max(1.0, min(10.0, score))  # Clamp to 1-10

                results.append({
                    "score": score,
                    "reasoning": eval_item.get('reasoning', '无')
                })

            return results

        except Exception as e:
            logger.error(f"Failed to parse batch response: {e}")
            # Return neutral scores on parsing error
            return [
                {"score": 6.0, "reasoning": "解析失败"}
                for _ in range(expected_count)
            ]
