#!/usr/bin/env python3
"""
Review Summarizer - LLM-based review analysis and summarization

Analyzes user reviews to extract:
- Sentiment distribution (positive/negative/mixed)
- Key pros (3-5 points)
- Key cons (2-3 points)
- Best user quotes (2-3)
- Overall rating (1-5 stars)
- Common themes and patterns
"""

import json
from typing import List, Dict, Any, Optional
from loguru import logger


class ReviewSummarizer:
    """Summarize user reviews using LLM"""

    def __init__(self, llm_client):
        """
        Initialize review summarizer

        Args:
            llm_client: LLM client instance (LLMClient or enhanced)
        """
        self.llm_client = llm_client
        logger.info("Review summarizer initialized")

    def summarize_reviews(
        self,
        product_name: str,
        reviews: List[Dict[str, Any]],
        max_reviews: int = 20
    ) -> Dict[str, Any]:
        """
        Summarize reviews for a product

        Args:
            product_name: Name of the product
            reviews: List of review dictionaries
            max_reviews: Maximum reviews to analyze

        Returns:
            Summary dictionary with sentiment, pros, cons, quotes, rating
        """
        if not reviews:
            return self._empty_summary()

        # Select top reviews by credibility
        top_reviews = self._select_top_reviews(reviews, max_reviews)

        # Build prompt
        prompt = self._build_summary_prompt(product_name, top_reviews)

        try:
            # Query LLM
            response = self.llm_client.query(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.3  # Low temperature for consistent analysis
            )

            # Parse response
            summary = self._parse_summary_response(response, reviews)

            logger.info(f"Summarized {len(reviews)} reviews for {product_name}")

            return summary

        except Exception as e:
            logger.error(f"Error summarizing reviews for {product_name}: {e}")
            return self._empty_summary()

    def _select_top_reviews(
        self,
        reviews: List[Dict[str, Any]],
        max_reviews: int
    ) -> List[Dict[str, Any]]:
        """
        Select top reviews by credibility score

        Args:
            reviews: All reviews
            max_reviews: Maximum to select

        Returns:
            Top reviews sorted by credibility
        """
        # Sort by credibility score (descending)
        sorted_reviews = sorted(
            reviews,
            key=lambda r: r.get('credibility_score', 0),
            reverse=True
        )

        return sorted_reviews[:max_reviews]

    def _build_summary_prompt(
        self,
        product_name: str,
        reviews: List[Dict[str, Any]]
    ) -> str:
        """
        Build LLM prompt for review summarization

        Args:
            product_name: Product name
            reviews: Reviews to analyze

        Returns:
            Prompt string
        """
        # Format reviews for prompt
        reviews_text = ""
        for i, review in enumerate(reviews, 1):
            source = review.get('source', 'Unknown')
            text = review.get('text', '')
            votes = review.get('votes', 0)

            reviews_text += f"{i}. [{source}] ({votes}👍) {text}\n\n"

        prompt = f"""分析以下关于"{product_name}"的用户评论,提取关键信息。

用户评论:
{reviews_text}

请提供JSON格式的分析结果,包含:

1. **sentiment_distribution**: 情感分布对象
   - positive: 正面评论百分比 (0-100)
   - negative: 负面评论百分比 (0-100)
   - neutral: 中立评论百分比 (0-100)

2. **pros**: 优点列表 (3-5个关键优点,每个10-20字)

3. **cons**: 缺点列表 (2-3个常见问题,每个10-20字)

4. **top_quotes**: 最佳用户评论列表 (2-3条代表性评论,保留原文,每条不超过80字)

5. **overall_rating**: 综合评分 (1-5星,保留1位小数)

6. **key_themes**: 关键主题列表 (2-3个主要讨论点,每个5-10字)

**输出格式示例:**
```json
{{
  "sentiment_distribution": {{
    "positive": 70,
    "negative": 20,
    "neutral": 10
  }},
  "pros": [
    "代码补全速度快,比Copilot快3倍",
    "AI理解上下文能力强,生成代码准确",
    "界面简洁直观,易于上手"
  ],
  "cons": [
    "价格较贵,月费$20偏高",
    "偶尔出现bug导致卡顿"
  ],
  "top_quotes": [
    "这是我用过最好的AI编程工具,提升效率明显",
    "Love the features but it's a bit expensive at $20/month"
  ],
  "overall_rating": 4.3,
  "key_themes": ["代码补全", "价格争议", "效率提升"]
}}
```

请仅返回JSON,不要其他文字。"""

        return prompt

    def _parse_summary_response(
        self,
        response: str,
        reviews: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Parse LLM response into structured summary

        Args:
            response: LLM response text
            reviews: Original reviews (for fallback)

        Returns:
            Structured summary dict
        """
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1

            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                summary = json.loads(json_str)

                # Validate required fields
                if not all(k in summary for k in ['sentiment_distribution', 'pros', 'cons', 'overall_rating']):
                    logger.warning("LLM response missing required fields, using fallback")
                    return self._fallback_summary(reviews)

                return summary
            else:
                logger.warning("No JSON found in LLM response, using fallback")
                return self._fallback_summary(reviews)

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON: {e}, using fallback")
            return self._fallback_summary(reviews)
        except Exception as e:
            logger.error(f"Error parsing summary response: {e}")
            return self._fallback_summary(reviews)

    def _fallback_summary(self, reviews: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate basic summary without LLM

        Args:
            reviews: Reviews to analyze

        Returns:
            Basic summary dict
        """
        # Count sentiment indicators
        positive_count = sum(
            1 for r in reviews
            if any(word in r.get('text', '').lower()
                   for word in ['love', 'great', 'amazing', 'excellent', 'best'])
        )

        negative_count = sum(
            1 for r in reviews
            if any(word in r.get('text', '').lower()
                   for word in ['bad', 'terrible', 'worst', 'hate', 'poor', 'expensive'])
        )

        total = len(reviews)
        positive_pct = int((positive_count / total) * 100) if total > 0 else 0
        negative_pct = int((negative_count / total) * 100) if total > 0 else 0
        neutral_pct = 100 - positive_pct - negative_pct

        # Get top quotes by votes
        top_quotes = [
            r.get('text', '')[:80]
            for r in sorted(reviews, key=lambda r: r.get('votes', 0), reverse=True)[:2]
        ]

        return {
            'sentiment_distribution': {
                'positive': positive_pct,
                'negative': negative_pct,
                'neutral': neutral_pct
            },
            'pros': ['用户反馈正面', '功能实用'],
            'cons': ['部分用户提及价格问题'],
            'top_quotes': top_quotes,
            'overall_rating': 4.0,
            'key_themes': ['用户体验', '功能评价']
        }

    def _empty_summary(self) -> Dict[str, Any]:
        """
        Return empty summary when no reviews available

        Returns:
            Empty summary dict
        """
        return {
            'sentiment_distribution': {
                'positive': 0,
                'negative': 0,
                'neutral': 100
            },
            'pros': [],
            'cons': [],
            'top_quotes': [],
            'overall_rating': 0.0,
            'key_themes': []
        }

    def add_summaries_to_articles(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Add review summaries to all articles

        Args:
            articles: Articles with reviews

        Returns:
            Articles with review_summary field added
        """
        for article in articles:
            reviews = article.get('reviews', [])

            if reviews:
                product_name = (
                    article.get('ph_product_name') or
                    article.get('title', 'Unknown Product')
                )

                summary = self.summarize_reviews(product_name, reviews)
                article['review_summary'] = summary

                # Add summary metrics to article
                article['avg_rating'] = summary.get('overall_rating', 0.0)
                article['pros'] = summary.get('pros', [])
                article['cons'] = summary.get('cons', [])
                article['top_reviews'] = [
                    {
                        'text': quote,
                        'source': 'User Review',
                        'date': article.get('date', ''),
                        'votes': 0
                    }
                    for quote in summary.get('top_quotes', [])
                ]
            else:
                article['review_summary'] = self._empty_summary()
                article['avg_rating'] = 0.0
                article['pros'] = []
                article['cons'] = []
                article['top_reviews'] = []

        logger.info(f"Added summaries to {len(articles)} articles")

        return articles


if __name__ == "__main__":
    # Test review summarizer
    print("Testing ReviewSummarizer...\n")

    # Note: Requires LLM client
    print("⚠️  This module requires an LLM client instance")
    print("Example usage:\n")

    code = """
from utils.llm_client_enhanced import LLMClient
from modules.review_summarizer import ReviewSummarizer

# Initialize
llm_client = LLMClient()
summarizer = ReviewSummarizer(llm_client)

# Sample reviews
reviews = [
    {
        'text': "I've been using Cursor for 2 weeks and it's a game changer. Code completion is 3x faster than Copilot.",
        'author': 'john_dev',
        'votes': 15,
        'credibility_score': 0.8
    },
    {
        'text': "Love the features but it's a bit expensive at $20/month. Would be great if there was a free tier.",
        'author': 'jane_coder',
        'votes': 8,
        'credibility_score': 0.7
    }
]

# Summarize
summary = summarizer.summarize_reviews('Cursor IDE', reviews)

print("Summary:")
print(f"  Rating: {summary['overall_rating']}/5")
print(f"  Sentiment: {summary['sentiment_distribution']}")
print(f"  Pros: {summary['pros']}")
print(f"  Cons: {summary['cons']}")
"""

    print(code)
