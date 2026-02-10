"""NotebookLM-style research chatbot for BriefAI.

Answers questions grounded in pipeline articles with citations.
Optionally uses Perplexity for web-augmented research.
"""

import os
import json
from typing import Dict, List, Any, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Citation:
    """A citation to a source."""
    source_id: str
    source_name: str
    title: str
    url: Optional[str]
    snippet: str
    relevance: float = 1.0


@dataclass
class ChatMessage:
    """A message in the chat history."""
    role: str  # "user" or "assistant"
    content: str
    citations: List[Citation] = None
    timestamp: str = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
        if self.citations is None:
            self.citations = []


class ResearchChatbot:
    """NotebookLM-style chatbot grounded in BriefAI articles."""

    def __init__(self, date: Optional[str] = None):
        self.date = date or datetime.now().strftime("%Y%m%d")
        self.history: List[ChatMessage] = []
        self.sources: Dict[str, Any] = {}
        self.context_loaded = False

        # API clients
        self.perplexity_key = os.environ.get("PERPLEXITY_API_KEY")
        self.openrouter_key = os.environ.get("OPENROUTER_API_KEY")

        # Paths
        self.cache_dir = Path("data/cache")
        self.reports_dir = Path("data/reports")

    def load_context(self, pipelines: List[str] = None) -> Dict[str, int]:
        """Load articles from pipelines as context sources."""
        pipelines = pipelines or ["news", "investing", "china_ai", "product"]
        loaded = {}

        for pipeline in pipelines:
            context_file = self.cache_dir / "pipeline_contexts" / f"{pipeline}_{self.date}.json"
            if context_file.exists():
                with open(context_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    articles = data.get("articles", [])
                    for article in articles:
                        source_id = f"{pipeline}_{article.get('id', '')}"
                        self.sources[source_id] = {
                            "pipeline": pipeline,
                            "title": article.get("title", ""),
                            "url": article.get("url", ""),
                            "source": article.get("source", ""),
                            "content": article.get("paraphrased_content") or article.get("content", ""),
                            "score": article.get("weighted_score", 0),
                        }
                    loaded[pipeline] = len(articles)

        self.context_loaded = True
        return loaded

    def _find_relevant_sources(self, query: str, top_k: int = 5) -> List[Dict]:
        """Find sources most relevant to the query using keyword matching."""
        if not self.sources:
            return []

        query_terms = set(query.lower().split())
        scored = []

        for source_id, source in self.sources.items():
            text = f"{source['title']} {source['content']}".lower()
            matches = sum(1 for term in query_terms if term in text)
            if matches > 0:
                scored.append({
                    "source_id": source_id,
                    "score": matches / len(query_terms),
                    **source
                })

        scored.sort(key=lambda x: (-x["score"], -x.get("weighted_score", 0)))
        return scored[:top_k]

    def _build_context_prompt(self, relevant_sources: List[Dict]) -> str:
        """Build context string from relevant sources."""
        if not relevant_sources:
            return ""

        context_parts = ["Here are relevant articles from today's briefings:\n"]
        for i, src in enumerate(relevant_sources, 1):
            context_parts.append(f"[Source {i}: {src['title']}]")
            context_parts.append(f"Pipeline: {src['pipeline']}")
            context_parts.append(f"Content: {src['content'][:500]}...")
            context_parts.append("")

        return "\n".join(context_parts)

    def _call_llm(self, messages: List[Dict], use_perplexity: bool = False) -> str:
        """Call LLM API (Perplexity for web search, OpenRouter for local)."""
        import requests

        if use_perplexity and self.perplexity_key:
            # Use Perplexity for web-grounded responses
            response = requests.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.perplexity_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "sonar",
                    "messages": messages,
                    "return_citations": True
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"], data.get("citations", [])

        elif self.openrouter_key:
            # Use OpenRouter (free tier)
            response = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.openrouter_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "google/gemini-2.0-flash-exp:free",
                    "messages": messages
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"], []

        else:
            return "Error: No API key configured (PERPLEXITY_API_KEY or OPENROUTER_API_KEY)", []

    def chat(
        self,
        query: str,
        use_web_search: bool = False,
        include_history: bool = True
    ) -> Dict[str, Any]:
        """
        Chat with the research assistant.

        Args:
            query: User's question
            use_web_search: Use Perplexity for web search (costs money)
            include_history: Include conversation history for context

        Returns:
            Dict with response, citations, and metadata
        """
        # Load context if not already loaded
        if not self.context_loaded:
            self.load_context()

        # Find relevant sources
        relevant_sources = self._find_relevant_sources(query)
        context = self._build_context_prompt(relevant_sources)

        # Build system prompt
        system_prompt = """You are a research assistant for an AI industry briefing system.
Answer questions based on the provided article context. When citing information:
- Reference sources by number [Source 1], [Source 2], etc.
- Be concise but thorough
- If the context doesn't contain enough information, say so
- For Chinese articles, you may respond in Chinese if appropriate

Always ground your answers in the provided sources when possible."""

        if use_web_search:
            system_prompt += "\n\nYou also have access to web search. Combine article context with web results for comprehensive answers."

        # Build messages
        messages = [{"role": "system", "content": system_prompt}]

        # Add history if requested
        if include_history and self.history:
            for msg in self.history[-6:]:  # Last 3 exchanges
                messages.append({"role": msg.role, "content": msg.content})

        # Add context and query
        if context:
            messages.append({
                "role": "user",
                "content": f"{context}\n\nQuestion: {query}"
            })
        else:
            messages.append({"role": "user", "content": query})

        # Get response
        try:
            response_text, web_citations = self._call_llm(messages, use_perplexity=use_web_search)
        except Exception as e:
            response_text = f"Error calling LLM: {str(e)}"
            web_citations = []

        # Build citations
        citations = []
        for i, src in enumerate(relevant_sources, 1):
            if f"[Source {i}]" in response_text or src["title"][:20] in response_text:
                citations.append(Citation(
                    source_id=src["source_id"],
                    source_name=src["source"],
                    title=src["title"],
                    url=src.get("url"),
                    snippet=src["content"][:200] + "...",
                    relevance=src["score"]
                ))

        # Add web citations if any
        for url in web_citations:
            citations.append(Citation(
                source_id=f"web_{hash(url) % 10000}",
                source_name="Web Search",
                title=url,
                url=url,
                snippet="Web search result",
                relevance=0.8
            ))

        # Save to history
        user_msg = ChatMessage(role="user", content=query)
        assistant_msg = ChatMessage(role="assistant", content=response_text, citations=citations)
        self.history.append(user_msg)
        self.history.append(assistant_msg)

        return {
            "response": response_text,
            "citations": [asdict(c) for c in citations],
            "sources_searched": len(self.sources),
            "relevant_sources": len(relevant_sources),
            "used_web_search": use_web_search,
            "timestamp": assistant_msg.timestamp
        }

    def get_history(self) -> List[Dict]:
        """Get conversation history."""
        return [
            {
                "role": msg.role,
                "content": msg.content,
                "citations": [asdict(c) for c in msg.citations] if msg.citations else [],
                "timestamp": msg.timestamp
            }
            for msg in self.history
        ]

    def clear_history(self):
        """Clear conversation history."""
        self.history = []

    def get_sources_summary(self) -> Dict[str, Any]:
        """Get summary of loaded sources."""
        by_pipeline = {}
        for source_id, source in self.sources.items():
            pipeline = source["pipeline"]
            if pipeline not in by_pipeline:
                by_pipeline[pipeline] = []
            by_pipeline[pipeline].append({
                "title": source["title"],
                "source": source["source"],
                "score": source.get("score", 0)
            })

        return {
            "date": self.date,
            "total_sources": len(self.sources),
            "by_pipeline": {k: len(v) for k, v in by_pipeline.items()},
            "top_articles": sorted(
                [{"title": s["title"], "pipeline": s["pipeline"], "score": s.get("score", 0)}
                 for s in self.sources.values()],
                key=lambda x: -x["score"]
            )[:5]
        }


# Singleton instance
_chatbot: Optional[ResearchChatbot] = None


def get_chatbot(date: Optional[str] = None) -> ResearchChatbot:
    """Get or create chatbot instance."""
    global _chatbot
    if _chatbot is None or (date and _chatbot.date != date):
        _chatbot = ResearchChatbot(date)
    return _chatbot


if __name__ == "__main__":
    # Demo
    print("BriefAI Research Chatbot")
    print("=" * 50)

    chatbot = get_chatbot()
    loaded = chatbot.load_context()
    print(f"Loaded sources: {loaded}")
    print(f"Sources summary: {chatbot.get_sources_summary()}")

    print("\n" + "=" * 50)
    print("Example queries (not making API calls):")
    print("- What are the main AI trends today?")
    print("- Tell me about vLLM funding")
    print("- Compare ToB vs ToC approaches for LLM companies")
