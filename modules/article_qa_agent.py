"""
Article Q&A Agent with ACE Integration

Single-agent system for answering questions about articles in the briefing.
Uses Adaptive Context Engineering (ACE) for multi-turn conversation management.
"""

import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger

from utils.llm_client_enhanced import LLMClient
from utils.semantic_deduplication import SemanticDeduplicator, SEMANTIC_AVAILABLE


class ArticleQAAgent:
    """Single agent for answering questions about briefing articles using ACE"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        articles_db: Optional[List[Dict[str, Any]]] = None,
        max_context_turns: int = 10,
        enable_semantic_search: bool = True
    ):
        """
        Initialize Article QA Agent

        Args:
            llm_client: LLM client instance (creates new if None)
            articles_db: List of articles to search from
            max_context_turns: Number of conversation turns to maintain in context
            enable_semantic_search: Use semantic similarity for article retrieval
        """
        self.llm_client = llm_client or LLMClient()
        self.articles_db = articles_db or []
        self.max_context_turns = max_context_turns
        self.enable_semantic_search = enable_semantic_search and SEMANTIC_AVAILABLE

        # Initialize semantic search if available
        if self.enable_semantic_search:
            try:
                self.semantic_dedup = SemanticDeduplicator(strict_mode=True)
                logger.info("Semantic search enabled for article retrieval")
            except Exception as e:
                logger.warning(f"Failed to initialize semantic search: {e}")
                self.enable_semantic_search = False

        # Conversation history for ACE context
        self.conversation_history: List[Dict[str, str]] = []
        self.retrieved_articles: Dict[int, Dict[str, Any]] = {}  # Cache of retrieved articles

        logger.info(f"Article QA Agent initialized with {len(self.articles_db)} articles")

    def update_articles(self, articles: List[Dict[str, Any]]):
        """Update the articles database"""
        self.articles_db = articles
        self.retrieved_articles.clear()
        logger.info(f"Updated articles database: {len(articles)} articles")

    def answer_question(self, user_query: str) -> Dict[str, Any]:
        """
        Answer a user question about articles using ACE for context

        Args:
            user_query: User's question or request

        Returns:
            Dictionary with response, referenced articles, and metadata
        """
        try:
            # Add user query to conversation history (ACE context)
            self.conversation_history.append({
                "role": "user",
                "content": user_query
            })

            # Trim conversation history if too long
            if len(self.conversation_history) > self.max_context_turns * 2:
                # Keep first 2 turns and last max_context_turns turns
                self.conversation_history = (
                    self.conversation_history[:4] +
                    self.conversation_history[-(self.max_context_turns * 2 - 4):]
                )

            # Step 1: Retrieve relevant articles
            retrieved = self._retrieve_relevant_articles(user_query)
            logger.debug(f"Retrieved {len(retrieved)} articles for query: {user_query[:60]}...")

            # Step 2: Build ACE context from conversation history
            ace_context = self._build_ace_context()

            # Step 3: Generate response using LLM
            response = self._generate_response(user_query, retrieved, ace_context)

            # Add assistant response to history
            self.conversation_history.append({
                "role": "assistant",
                "content": response['answer']
            })

            return {
                "success": True,
                "answer": response['answer'],
                "referenced_articles": response['referenced_articles'],
                "articles_count": len(retrieved),
                "turn_number": len(self.conversation_history) // 2,
                "generation_time": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Failed to answer question: {e}")
            return {
                "success": False,
                "error": str(e),
                "answer": "抱歉,我在处理您的问题时遇到了错误。请稍后重试。"
            }

    def _retrieve_relevant_articles(self, query: str) -> List[Dict[str, Any]]:
        """
        Retrieve articles relevant to the user's query

        Uses semantic search if available, falls back to keyword matching
        """
        if not self.articles_db:
            return []

        retrieved = []

        # Semantic search (if available and enabled)
        if self.enable_semantic_search:
            try:
                semantic_results = self._semantic_search(query)
                retrieved.extend(semantic_results[:5])  # Top 5 by similarity
            except Exception as e:
                logger.warning(f"Semantic search failed, falling back to keyword matching: {e}")

        # Keyword-based search (always available as fallback)
        keyword_results = self._keyword_search(query)

        # Merge results (prefer semantic, add keyword-only results)
        retrieved_ids = {id(r) for r in retrieved}
        for result in keyword_results[:5]:
            if id(result) not in retrieved_ids and result not in retrieved:
                retrieved.append(result)

        # Limit to top 8 articles
        return retrieved[:8]

    def _semantic_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Search articles using semantic similarity

        Returns articles ordered by relevance
        """
        if not self.enable_semantic_search:
            return []

        try:
            query_embedding = self.semantic_dedup.model.encode(query)
            scores = []

            for i, article in enumerate(self.articles_db):
                # Create searchable text from article
                article_text = f"{article.get('title', '')} {article.get('paraphrased_content', '')}"
                article_embedding = self.semantic_dedup.model.encode(article_text)

                # Calculate cosine similarity
                similarity = float(
                    (query_embedding @ article_embedding) /
                    (np.linalg.norm(query_embedding) * np.linalg.norm(article_embedding) + 1e-8)
                )
                scores.append((i, article, similarity))

            # Sort by similarity and return top results
            scores.sort(key=lambda x: x[2], reverse=True)
            return [item[1] for item in scores if item[2] > 0.3][:10]

        except Exception as e:
            logger.warning(f"Semantic search error: {e}")
            return []

    def _keyword_search(self, query: str) -> List[Dict[str, Any]]:
        """
        Keyword-based search through articles

        Looks for matches in title, content, and categories
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_articles = []

        for article in self.articles_db:
            score = 0

            # Title matches (high weight)
            title_lower = article.get('title', '').lower()
            title_matches = sum(1 for word in query_words if word in title_lower)
            score += title_matches * 3

            # Content matches (medium weight)
            content_lower = article.get('paraphrased_content', '').lower()
            content_matches = sum(1 for word in query_words if word in content_lower)
            score += content_matches * 1.5

            # Category matches (medium weight)
            categories = article.get('categories', [])
            category_str = ' '.join(categories).lower()
            category_matches = sum(1 for word in query_words if word in category_str)
            score += category_matches * 2

            if score > 0:
                scored_articles.append((article, score))

        # Sort by score
        scored_articles.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored_articles]

    def _build_ace_context(self) -> str:
        """
        Build Adaptive Context Engineering (ACE) context from conversation history

        Summarizes previous turns to maintain conversation coherence
        """
        if not self.conversation_history:
            return "这是一次新的对话。"

        # For now, include last few turns as context
        # In advanced version, could summarize key entities and topics
        recent_turns = self.conversation_history[-6:]  # Last 3 turns

        context_parts = ["对话历史:"]
        for turn in recent_turns:
            role = "用户" if turn['role'] == 'user' else "助手"
            content = turn['content'][:100] + "..." if len(turn['content']) > 100 else turn['content']
            context_parts.append(f"\n{role}: {content}")

        return "\n".join(context_parts)

    def _generate_response(
        self,
        query: str,
        retrieved_articles: List[Dict[str, Any]],
        ace_context: str
    ) -> Dict[str, Any]:
        """
        Generate response using LLM with retrieved articles and ACE context

        Returns response and referenced articles
        """
        # Build article context
        articles_context = self._format_articles_context(retrieved_articles)

        # Build prompt
        system_prompt = self._build_qa_system_prompt()
        user_message = self._build_qa_user_message(query, articles_context, ace_context)

        # Call LLM
        response = self.llm_client.chat_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.5
        )

        answer = response.get('answer', '无法生成回复')
        referenced_articles = response.get('referenced_articles', [])

        return {
            "answer": answer,
            "referenced_articles": referenced_articles
        }

    def _format_articles_context(self, articles: List[Dict[str, Any]]) -> str:
        """Format articles for context in prompt"""
        if not articles:
            return "未找到相关文章。"

        formatted = []
        for i, article in enumerate(articles, 1):
            formatted.append(f"""
[文章{i}]
标题: {article.get('title', '未知')}
来源: {article.get('source', '未知')}
URL: {article.get('url', 'N/A')}
摘要: {article.get('paraphrased_content', article.get('content', '无内容'))[:300]}
""")

        return "\n".join(formatted)

    def _build_qa_system_prompt(self) -> str:
        """Build system prompt for Q&A"""
        return """你是一个专业的AI行业分析师,为CEO提供深度的文章分析和建议。

**你的角色**:
1. 根据提供的文章内容准确回答用户的问题
2. 引用具体的文章、数据和事实来支持你的观点
3. 提供战略洞察和商业implications
4. 对比分析多篇文章中的相关观点
5. 在对话中保持上下文一致性

**回复要求**:
- 使用专业、客观的语言
- 始终引用原文信息,不进行无根据的推测
- 如果没有足够信息回答,明确说明
- 中文回复,技术术语可保留英文
- 提供具体的参考和链接

**返回JSON格式**:
{
  "answer": "你的详细回复(中文)",
  "referenced_articles": ["引用的文章标题1", "引用的文章标题2"],
  "confidence": 0.95,
  "requires_more_info": false,
  "follow_up_questions": ["建议的后续问题1", "建议的后续问题2"]
}"""

    def _build_qa_user_message(self, query: str, articles_context: str, ace_context: str) -> str:
        """Build user message for Q&A"""
        return f"""请根据以下文章内容回答我的问题。

{ace_context}

**当前问题**: {query}

**相关文章**:
{articles_context}

请提供基于这些文章的深度分析和建议。使用JSON格式返回你的回复。"""

    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history.clear()
        self.retrieved_articles.clear()
        logger.info("Conversation history cleared")

    def get_conversation_summary(self) -> Dict[str, Any]:
        """Get summary of current conversation"""
        return {
            "total_turns": len(self.conversation_history) // 2,
            "total_messages": len(self.conversation_history),
            "topics_discussed": len(self.retrieved_articles),
            "articles_referenced": list(set(
                article.get('title', 'Unknown')
                for article in self.retrieved_articles.values()
            ))
        }


# Placeholder for numpy import (will be imported when semantic search is used)
try:
    import numpy as np
except ImportError:
    np = None  # Will fail gracefully if semantic search is attempted
