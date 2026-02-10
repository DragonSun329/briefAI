"""
Content Enricher - Fetch and summarize article bodies from URLs.

Techmeme gives us headlines + links, not content.
This module enriches articles with:
- body_text: extracted article content
- tldr: short summary (1-2 sentences)
- key_points: bullet points (optional)

Uses trafilatura for extraction (fast, good baseline).
"""

import asyncio
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from loguru import logger

try:
    import trafilatura
    from trafilatura.settings import use_config
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logger.warning("Content enrichment requires: pip install trafilatura")

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    # Fall back to requests
    try:
        import requests
        REQUESTS_AVAILABLE = True
    except ImportError:
        REQUESTS_AVAILABLE = False


class ContentEnricher:
    """
    Enrich articles with body text and summaries.
    
    Usage:
        enricher = ContentEnricher()
        articles = enricher.enrich_batch(articles)
        # Each article now has: body_text, tldr, enriched=True
    """
    
    # Limits
    MAX_BODY_LENGTH = 5000  # Truncate body to this
    TLDR_LENGTH = 300       # Target TLDR length
    TIMEOUT = 15            # HTTP timeout per URL
    MAX_WORKERS = 5         # Parallel fetch workers
    
    def __init__(self, llm_client=None, use_llm_summary: bool = False):
        """
        Initialize content enricher.
        
        Args:
            llm_client: Optional LLM client for summarization
            use_llm_summary: Use LLM for TLDR (vs trafilatura's built-in)
        """
        self.available = TRAFILATURA_AVAILABLE
        self.llm_client = llm_client
        self.use_llm_summary = use_llm_summary and llm_client is not None
        
        if not self.available:
            logger.warning("ContentEnricher unavailable - install trafilatura")
            return
        
        # Configure trafilatura
        self.config = use_config()
        self.config.set("DEFAULT", "EXTRACTION_TIMEOUT", "10")
        
        logger.info(f"ContentEnricher initialized (llm_summary={self.use_llm_summary})")
    
    def _fetch_url(self, url: str) -> Optional[str]:
        """Fetch HTML content from URL."""
        try:
            if HTTPX_AVAILABLE:
                with httpx.Client(timeout=self.TIMEOUT, follow_redirects=True) as client:
                    resp = client.get(url, headers={
                        'User-Agent': 'Mozilla/5.0 (compatible; briefAI/1.0)'
                    })
                    resp.raise_for_status()
                    return resp.text
            elif REQUESTS_AVAILABLE:
                import requests
                resp = requests.get(url, timeout=self.TIMEOUT, headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; briefAI/1.0)'
                })
                resp.raise_for_status()
                return resp.text
            else:
                # Use trafilatura's built-in fetcher
                return trafilatura.fetch_url(url)
        except Exception as e:
            logger.debug(f"Failed to fetch {url}: {e}")
            return None
    
    def _extract_content(self, html: str, url: str) -> Dict[str, Any]:
        """Extract content from HTML using trafilatura."""
        if not html:
            return {'body_text': '', 'tldr': '', 'success': False}
        
        try:
            # Extract main content
            body = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=True,
                config=self.config
            )
            
            if not body or len(body) < 100:
                return {'body_text': '', 'tldr': '', 'success': False}
            
            # Truncate if too long
            body_text = body[:self.MAX_BODY_LENGTH]
            
            # Generate TLDR (first paragraph or trafilatura summary)
            tldr = self._generate_tldr(body_text, html)
            
            return {
                'body_text': body_text,
                'tldr': tldr,
                'success': True
            }
            
        except Exception as e:
            logger.debug(f"Extraction failed for {url}: {e}")
            return {'body_text': '', 'tldr': '', 'success': False}
    
    def _generate_tldr(self, body_text: str, html: str = None) -> str:
        """Generate a TLDR summary."""
        if self.use_llm_summary and self.llm_client:
            return self._llm_summary(body_text)
        
        # Simple extraction: first 2-3 sentences
        sentences = body_text.replace('\n', ' ').split('. ')
        tldr_sentences = []
        char_count = 0
        
        for sent in sentences:
            if char_count + len(sent) > self.TLDR_LENGTH:
                break
            tldr_sentences.append(sent.strip())
            char_count += len(sent)
        
        return '. '.join(tldr_sentences) + ('.' if tldr_sentences else '')
    
    def _llm_summary(self, body_text: str) -> str:
        """Generate TLDR using LLM."""
        try:
            response = self.llm_client.chat(
                system_prompt="Summarize this article in 1-2 sentences. Be factual and concise.",
                user_message=body_text[:2000],
                temperature=0.3
            )
            return response[:self.TLDR_LENGTH] if response else ''
        except Exception as e:
            logger.debug(f"LLM summary failed: {e}")
            return ''
    
    def enrich_article(self, article: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich a single article with body text and TLDR.
        
        Modifies article in-place and returns it.
        """
        if not self.available:
            article['enriched'] = False
            return article
        
        url = article.get('url', '')
        if not url:
            article['enriched'] = False
            return article
        
        # Skip if already enriched
        if article.get('enriched') and article.get('body_text'):
            return article
        
        # Fetch and extract
        html = self._fetch_url(url)
        content = self._extract_content(html, url)
        
        article['body_text'] = content.get('body_text', '')
        article['tldr'] = content.get('tldr', '')
        article['enriched'] = content.get('success', False)
        
        return article
    
    def enrich_batch(
        self,
        articles: List[Dict[str, Any]],
        max_workers: int = None
    ) -> List[Dict[str, Any]]:
        """
        Enrich a batch of articles in parallel.
        
        Args:
            articles: List of article dicts with 'url' field
            max_workers: Override default parallelism
        
        Returns:
            Same list with enrichment fields added
        """
        if not self.available:
            for article in articles:
                article['enriched'] = False
            return articles
        
        workers = max_workers or self.MAX_WORKERS
        logger.info(f"Enriching {len(articles)} articles (workers={workers})...")
        
        enriched_count = 0
        failed_count = 0
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # Submit all tasks
            future_to_idx = {
                executor.submit(self.enrich_article, article): i
                for i, article in enumerate(articles)
            }
            
            # Collect results
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    if result.get('enriched'):
                        enriched_count += 1
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.debug(f"Enrichment failed for article {idx}: {e}")
                    articles[idx]['enriched'] = False
                    failed_count += 1
        
        logger.info(f"Enrichment complete: {enriched_count} success, {failed_count} failed")
        
        return articles
    
    def get_embedding_text(self, article: Dict[str, Any], max_chars: int = 1500) -> str:
        """
        Get the best text for embedding from an article.
        
        Priority:
        1. tldr + title (if enriched)
        2. body_text excerpt (if enriched)
        3. title + content (fallback)
        """
        title = article.get('title', '')
        
        if article.get('enriched') and article.get('tldr'):
            # Best case: title + TLDR
            text = f"{title}. {article['tldr']}"
            if len(text) < max_chars and article.get('body_text'):
                # Add body excerpt if room
                remaining = max_chars - len(text)
                text += f" {article['body_text'][:remaining]}"
            return text[:max_chars]
        
        if article.get('enriched') and article.get('body_text'):
            # Have body but no TLDR
            return f"{title}. {article['body_text'][:max_chars - len(title) - 2]}"
        
        # Fallback: title + whatever content we have
        content = article.get('content', article.get('summary', ''))
        if content and content != title:
            return f"{title}. {content}"[:max_chars]
        
        return title


# Debug helper
def diagnose_enrichment(articles: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Diagnose enrichment coverage for a batch of articles.
    
    Returns stats useful for debugging clustering issues.
    """
    total = len(articles)
    enriched = sum(1 for a in articles if a.get('enriched'))
    has_body = sum(1 for a in articles if len(a.get('body_text', '')) > 200)
    has_tldr = sum(1 for a in articles if len(a.get('tldr', '')) > 50)
    
    body_lengths = [len(a.get('body_text', '')) for a in articles]
    avg_body = sum(body_lengths) / total if total else 0
    
    return {
        'total': total,
        'enriched': enriched,
        'enriched_pct': round(100 * enriched / total, 1) if total else 0,
        'has_body_200': has_body,
        'has_tldr_50': has_tldr,
        'avg_body_length': round(avg_body),
        'min_body_length': min(body_lengths) if body_lengths else 0,
        'max_body_length': max(body_lengths) if body_lengths else 0,
    }


if __name__ == "__main__":
    # Quick test
    enricher = ContentEnricher()
    
    test_article = {
        'title': 'Test Article',
        'url': 'https://simonwillison.net/2026/Feb/7/claude-fast-mode/',
        'source': 'Test'
    }
    
    result = enricher.enrich_article(test_article)
    print(f"Enriched: {result.get('enriched')}")
    print(f"TLDR: {result.get('tldr', '')[:200]}...")
    print(f"Body length: {len(result.get('body_text', ''))}")
