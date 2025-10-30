"""
Entity Background Agent Module

Generates article-specific entity backgrounds for CEO briefings.

Key differences from old ContextProvider:
- Generates **targeted backgrounds** specific to each article's story
- No separate database (uses ACE context for smart caching)
- Integrated with orchestrator metrics/error tracking
- Focuses on the **main entity** (company/product/technology) per article

Features:
- Identifies main entity from article title + content
- Classifies entity type (company | product | technology)
- Generates 200-300 char contextual background
- Skips if entity already in recent ACE context
- Tracks token usage and LLM calls
"""

from typing import Dict, List, Optional, Tuple
from loguru import logger
import re

from utils.llm_client_enhanced import LLMClient


class EntityBackgroundAgent:
    """Generate article-specific entity backgrounds"""

    # Character limits
    BACKGROUND_MIN = 200
    BACKGROUND_MAX = 300

    def __init__(self, llm_client: LLMClient = None):
        """
        Initialize entity background agent

        Args:
            llm_client: LLM client for generating backgrounds
        """
        self.llm_client = llm_client or LLMClient()
        logger.info("Entity background agent initialized")

    def enrich_articles(
        self,
        articles: List[Dict],
        context_engine=None
    ) -> Tuple[List[Dict], Dict]:
        """
        Enrich articles with entity backgrounds

        Args:
            articles: List of paraphrased articles
            context_engine: ACE context engine for smart caching

        Returns:
            Tuple of (enriched_articles, metrics)
        """
        logger.info(f"Enriching {len(articles)} articles with entity backgrounds...")

        enriched_articles = []
        metrics = {
            'total_articles': len(articles),
            'entities_extracted': 0,
            'backgrounds_generated': 0,
            'backgrounds_cached': 0,
            'failed': 0,
            'total_tokens': 0,
            'total_cost_usd': 0.0
        }

        for article in articles:
            try:
                # Extract main entity
                entity_info = self._extract_main_entity(article)

                if not entity_info:
                    logger.debug(f"No entity found for article: {article.get('title', '')[:50]}")
                    enriched_articles.append(article)
                    continue

                metrics['entities_extracted'] += 1
                entity_name = entity_info['name']
                entity_type = entity_info['type']

                # Check if entity background exists in recent context
                cached_background = None
                if context_engine:
                    cached_background = self._check_context_cache(
                        entity_name,
                        entity_type,
                        context_engine
                    )

                if cached_background:
                    # Use cached background
                    article['entity_background'] = cached_background
                    article['entity_name'] = entity_name
                    article['entity_type'] = entity_type
                    metrics['backgrounds_cached'] += 1
                    logger.debug(f"Using cached background for {entity_name}")

                else:
                    # Generate new background
                    background, tokens, cost = self._generate_background(
                        entity_name=entity_name,
                        entity_type=entity_type,
                        article_title=article.get('title', ''),
                        article_excerpt=article.get('paraphrased_content', '')[:500]
                    )

                    if background:
                        article['entity_background'] = background
                        article['entity_name'] = entity_name
                        article['entity_type'] = entity_type
                        metrics['backgrounds_generated'] += 1
                        metrics['total_tokens'] += tokens
                        metrics['total_cost_usd'] += cost

                        # Save to context for future use
                        if context_engine:
                            self._save_to_context(
                                entity_name,
                                entity_type,
                                background,
                                context_engine
                            )

                        logger.debug(f"Generated background for {entity_name} ({tokens} tokens)")
                    else:
                        metrics['failed'] += 1
                        logger.warning(f"Failed to generate background for {entity_name}")

                enriched_articles.append(article)

            except Exception as e:
                logger.error(f"Error enriching article: {e}")
                metrics['failed'] += 1
                enriched_articles.append(article)
                continue

        logger.info(
            f"Entity enrichment complete: {metrics['backgrounds_generated']} generated, "
            f"{metrics['backgrounds_cached']} cached, {metrics['failed']} failed"
        )

        return enriched_articles, metrics

    def _extract_main_entity(self, article: Dict) -> Optional[Dict]:
        """
        Extract main entity from article

        Returns:
            Dict with 'name' and 'type' (company | product | technology), or None
        """
        title = article.get('title', '')
        content = article.get('paraphrased_content', '')[:500]

        # Combine title and first 500 chars for analysis
        text = f"{title} {content}"

        # Common patterns for entities
        # Companies: OpenAI, Anthropic, Meta, Google, Microsoft, etc.
        # Products: GPT-5, Claude, Gemini, Llama, etc.
        # Technologies: Transformer, RAG, LoRA, etc.

        # Try to identify entity using simple heuristics
        entity_name = None
        entity_type = None

        # Pattern 1: Company + verb (e.g., "OpenAI releases", "Anthropic announces")
        company_pattern = r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)?)\s+(?:releases|announces|launches|unveils|introduces|presents|reveals)'
        match = re.search(company_pattern, title)
        if match:
            entity_name = match.group(1)
            entity_type = 'company'

        # Pattern 2: Product name in quotes or title case (e.g., "GPT-5", "Claude 3.5")
        if not entity_name:
            product_pattern = r'([A-Z][a-zA-Z0-9]+(?:[-\s][A-Z0-9.]+)?)'
            matches = re.findall(product_pattern, title)
            if matches:
                # Take first match as main entity
                entity_name = matches[0]
                entity_type = 'product'

        # Pattern 3: Technology term (e.g., "Transformer", "RAG", "LoRA")
        if not entity_name:
            tech_keywords = ['transformer', 'rag', 'lora', 'diffusion', 'gan', 'bert',
                            'attention', 'neural', 'model', 'framework']
            for keyword in tech_keywords:
                if keyword.lower() in text.lower():
                    entity_name = keyword.title()
                    entity_type = 'technology'
                    break

        # Fallback: Extract first proper noun from title
        if not entity_name:
            words = title.split()
            for word in words:
                if word and word[0].isupper() and len(word) > 2:
                    entity_name = word
                    entity_type = 'company'  # Default guess
                    break

        if entity_name:
            return {
                'name': entity_name.strip(),
                'type': entity_type
            }

        return None

    def _generate_background(
        self,
        entity_name: str,
        entity_type: str,
        article_title: str,
        article_excerpt: str
    ) -> Tuple[Optional[str], int, float]:
        """
        Generate entity background via LLM

        Returns:
            Tuple of (background_text, tokens_used, cost_usd)
        """
        if not entity_name:
            return None, 0, 0.0

        try:
            # Build targeted prompt based on entity type
            if entity_type == 'company':
                focus = "公司的核心业务、成立背景、以及与本次新闻相关的业务重点"
            elif entity_type == 'product':
                focus = "产品的功能定位、技术特点、以及与本次新闻相关的产品更新"
            else:  # technology
                focus = "技术的核心原理、应用场景、以及与本次新闻相关的技术创新"

            prompt = f"""为CEO的AI产业周刊提供关于「{entity_name}」的**针对性背景信息**。

**文章标题**: {article_title}

**文章摘要**: {article_excerpt[:300]}

请用简洁的中文（200-300个汉字）生成背景信息，重点说明:
- {focus}
- 为什么这个{entity_type}与本次新闻相关
- CEO需要了解的核心要点

要求:
- 紧扣文章主题，**不要泛泛而谈**
- 避免重复文章内容，提供**补充背景**
- 数据准确，不编造信息
- 面向CEO，专业但易懂
- 全段落格式（不要分点列举）

输出格式: 直接输出200-300字的背景段落，不需要标题或分节。"""

            response = self.llm_client.chat(
                system_prompt="You are a helpful assistant providing targeted background information for CEO briefings.",
                user_message=prompt,
                temperature=0.3,
                max_tokens=400
            )

            if not response:
                logger.warning(f"Failed to generate background for {entity_name}")
                return None, 0, 0.0

            background = response.strip()

            # Truncate to limits
            if len(background) > self.BACKGROUND_MAX:
                background = background[:self.BACKGROUND_MAX] + "..."

            # Estimate tokens and cost (rough approximation)
            # Typical: prompt ~400 tokens, response ~200 tokens
            tokens_used = 600
            # Using Anthropic Sonnet pricing: $3/1M input, $15/1M output
            cost_usd = (400 * 3 + 200 * 15) / 1_000_000

            return background, tokens_used, cost_usd

        except Exception as e:
            logger.error(f"Error generating background for {entity_name}: {e}")
            return None, 0, 0.0

    def _check_context_cache(
        self,
        entity_name: str,
        entity_type: str,
        context_engine
    ) -> Optional[str]:
        """
        Check if entity background exists in ACE context

        Returns:
            Cached background text, or None
        """
        try:
            # Look for entity in context's entity_backgrounds
            entity_backgrounds = context_engine.context.get('entity_backgrounds', {})

            key = f"{entity_type}:{entity_name}"
            if key in entity_backgrounds:
                cached = entity_backgrounds[key]
                # Check if cache is recent (within current run or last run)
                return cached.get('background')

            return None

        except Exception as e:
            logger.debug(f"Error checking context cache: {e}")
            return None

    def _save_to_context(
        self,
        entity_name: str,
        entity_type: str,
        background: str,
        context_engine
    ) -> None:
        """
        Save entity background to ACE context for future use
        """
        try:
            if 'entity_backgrounds' not in context_engine.context:
                context_engine.context['entity_backgrounds'] = {}

            key = f"{entity_type}:{entity_name}"
            context_engine.context['entity_backgrounds'][key] = {
                'name': entity_name,
                'type': entity_type,
                'background': background
            }

            logger.debug(f"Saved entity background to context: {key}")

        except Exception as e:
            logger.debug(f"Error saving to context: {e}")


if __name__ == "__main__":
    # Test entity background agent
    from utils.llm_client_enhanced import LLMClient

    agent = EntityBackgroundAgent(llm_client=LLMClient())

    # Test article
    test_articles = [
        {
            'title': 'OpenAI Releases GPT-5 with Enhanced Reasoning Capabilities',
            'paraphrased_content': 'OpenAI今天发布了GPT-5模型，该模型在推理能力方面实现了显著提升...',
            'url': 'https://openai.com/blog/gpt-5'
        }
    ]

    enriched, metrics = agent.enrich_articles(test_articles, context_engine=None)

    print("=" * 60)
    print("Entity Background Agent Test")
    print("=" * 60)
    print(f"\nMetrics: {metrics}")
    print(f"\nEnriched Article:")
    print(f"- Title: {enriched[0]['title']}")
    print(f"- Entity: {enriched[0].get('entity_name')} ({enriched[0].get('entity_type')})")
    print(f"- Background: {enriched[0].get('entity_background', 'N/A')}")
    print()
