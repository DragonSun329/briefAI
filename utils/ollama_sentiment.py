"""
Ollama-Powered Sentiment Analyzer for briefAI

Replaces keyword-based sentiment scoring with LLM understanding.
Uses local Ollama models for:
- Nuanced sentiment analysis (bullish/bearish/neutral)
- Context-aware scoring (understands AI industry jargon)
- Bilingual support (English + Chinese)
- Free, unlimited, private inference

Expected improvement: 54% → 70%+ validation accuracy

Usage:
    from utils.ollama_sentiment import OllamaSentimentAnalyzer
    
    analyzer = OllamaSentimentAnalyzer()
    result = analyzer.analyze("NVIDIA announces record AI chip sales")
    print(result.sentiment)  # "bullish"
    print(result.score)      # 8.2
    print(result.confidence) # 0.85
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import requests
import concurrent.futures

logger = logging.getLogger(__name__)


@dataclass
class SentimentResult:
    """Result of sentiment analysis."""
    text: str
    sentiment: str  # "bullish", "bearish", "neutral"
    score: float    # 1-10 scale (1=very bearish, 10=very bullish)
    confidence: float  # 0-1
    reasoning: str
    entities: List[str] = field(default_factory=list)
    signals: List[str] = field(default_factory=list)  # extracted signals
    analyzed_at: datetime = field(default_factory=datetime.now)
    model: str = "qwen2.5:7b"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sentiment": self.sentiment,
            "score": self.score,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "entities": self.entities,
            "signals": self.signals,
            "model": self.model,
        }


class OllamaSentimentAnalyzer:
    """
    LLM-powered sentiment analyzer using local Ollama.
    
    Advantages over keyword-based:
    - Understands context ("sales declined" vs "declined to comment")
    - Handles negation properly
    - Recognizes AI industry jargon
    - Works with Chinese news
    
    Performance modes:
    - Fast mode: phi3:mini (~3s/batch) - good for high volume
    - Standard mode: qwen2.5:7b (~10s/batch) - best quality
    - Parallel batch: 3x throughput via concurrent requests
    """
    
    # Ollama API endpoint
    OLLAMA_URL = "http://localhost:11434"
    
    # Default model (bilingual, good quality/speed balance)
    DEFAULT_MODEL = "qwen2.5:7b"
    
    # Fast model for high-volume processing (~3x faster)
    FAST_MODEL = "phi3:mini"
    
    # Fallback models in order of preference
    FALLBACK_MODELS = ["phi3:mini", "mistral:7b", "llama3.1:8b", "llama2:7b"]
    
    # Sentiment prompt template
    SENTIMENT_PROMPT = """Analyze the sentiment of this AI industry news for investors/analysts.

TEXT: {text}

Respond in this exact JSON format:
{{
    "sentiment": "bullish" | "bearish" | "neutral",
    "score": <number 1-10, where 1=very bearish, 5=neutral, 10=very bullish>,
    "confidence": <number 0-1, your confidence in this assessment>,
    "reasoning": "<brief explanation>",
    "entities": ["<company/product names mentioned>"],
    "signals": ["<key signals extracted, e.g. 'revenue growth', 'layoffs', 'product launch'>"]
}}

Guidelines:
- "bullish" = positive for the company/sector (funding, growth, product launches, partnerships)
- "bearish" = negative (layoffs, losses, regulatory issues, competition threats)  
- "neutral" = informational, no clear positive/negative signal
- Consider AI industry context (e.g., "open source release" is usually bullish)
- For Chinese text, analyze in context of China AI ecosystem

Return ONLY valid JSON, no other text."""

    BATCH_PROMPT = """Analyze sentiment for these {count} AI industry headlines. Rate each 1-10 (1=bearish, 10=bullish).

HEADLINES:
{headlines}

Return JSON array with one object per headline:
[
    {{"index": 0, "sentiment": "bullish"|"bearish"|"neutral", "score": <1-10>, "confidence": <0-1>}},
    ...
]

Return ONLY the JSON array, no other text."""

    def __init__(
        self,
        model: str = None,
        ollama_url: str = None,
        timeout: int = 30,
        temperature: float = 0.1,  # Low temp for consistent scoring
        fast_mode: bool = False,   # Use lighter model for speed
    ):
        """
        Initialize Ollama sentiment analyzer.
        
        Args:
            model: Ollama model name (default: qwen2.5:7b)
            ollama_url: Ollama API URL (default: http://localhost:11434)
            timeout: Request timeout in seconds
            temperature: LLM temperature (lower = more consistent)
            fast_mode: Use phi3:mini for ~3x faster processing
        """
        if fast_mode and model is None:
            self.model = self.FAST_MODEL
        else:
            self.model = model or self.DEFAULT_MODEL
        self.ollama_url = ollama_url or self.OLLAMA_URL
        self.timeout = timeout
        self.temperature = temperature
        self.fast_mode = fast_mode
        
        # Check if Ollama is running
        self._verify_ollama()
    
    def _verify_ollama(self) -> bool:
        """Verify Ollama is running and model is available."""
        try:
            # Check Ollama is running
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=5)
            if response.status_code != 200:
                logger.warning("Ollama not responding")
                return False
            
            # Check if model is available
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            if self.model not in model_names and f"{self.model}:latest" not in model_names:
                # Try to find a fallback
                for fallback in self.FALLBACK_MODELS:
                    if fallback in model_names or f"{fallback}:latest" in model_names:
                        logger.info(f"Model {self.model} not found, using {fallback}")
                        self.model = fallback
                        return True
                
                logger.warning(f"Model {self.model} not available. Available: {model_names}")
                return False
            
            logger.info(f"Ollama ready with model: {self.model}")
            return True
            
        except requests.exceptions.ConnectionError:
            logger.warning("Cannot connect to Ollama. Is it running?")
            return False
        except Exception as e:
            logger.warning(f"Ollama verification failed: {e}")
            return False
    
    def _call_ollama(self, prompt: str) -> Optional[str]:
        """Make a request to Ollama API."""
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": self.temperature,
                        "num_predict": 500,  # Limit output length
                    }
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json().get("response", "")
            else:
                logger.error(f"Ollama error: {response.status_code} - {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning("Ollama request timed out")
            return None
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            return None
    
    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Extract JSON from LLM response."""
        if not response:
            return None
        
        # Try to find JSON in response
        response = response.strip()
        
        # Try direct parse
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find JSON object/array
        json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        logger.warning(f"Could not parse JSON from response: {response[:200]}")
        return None
    
    def analyze(self, text: str) -> SentimentResult:
        """
        Analyze sentiment of a single text.
        
        Args:
            text: News headline or article text
            
        Returns:
            SentimentResult with sentiment, score, confidence, reasoning
        """
        # Truncate very long text
        if len(text) > 2000:
            text = text[:2000] + "..."
        
        prompt = self.SENTIMENT_PROMPT.format(text=text)
        response = self._call_ollama(prompt)
        
        if not response:
            # Fallback to neutral
            return SentimentResult(
                text=text,
                sentiment="neutral",
                score=5.0,
                confidence=0.0,
                reasoning="Analysis failed - Ollama not available",
                model=self.model,
            )
        
        parsed = self._parse_json_response(response)
        
        if not parsed:
            # Fallback to neutral
            return SentimentResult(
                text=text,
                sentiment="neutral",
                score=5.0,
                confidence=0.0,
                reasoning=f"Could not parse response: {response[:100]}",
                model=self.model,
            )
        
        # Extract and validate fields
        sentiment = parsed.get("sentiment", "neutral").lower()
        if sentiment not in ["bullish", "bearish", "neutral"]:
            sentiment = "neutral"
        
        score = float(parsed.get("score", 5.0))
        score = max(1.0, min(10.0, score))  # Clamp to 1-10
        
        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))  # Clamp to 0-1
        
        return SentimentResult(
            text=text,
            sentiment=sentiment,
            score=score,
            confidence=confidence,
            reasoning=parsed.get("reasoning", ""),
            entities=parsed.get("entities", []),
            signals=parsed.get("signals", []),
            model=self.model,
        )
    
    def analyze_batch(
        self, 
        texts: List[str],
        batch_size: int = 10
    ) -> List[SentimentResult]:
        """
        Analyze sentiment for multiple texts efficiently.
        
        Uses batch prompts to reduce API calls.
        
        Args:
            texts: List of news headlines/articles
            batch_size: Number of texts per batch
            
        Returns:
            List of SentimentResult for each text
        """
        results = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            # Format headlines for batch prompt
            headlines = "\n".join(
                f"{j}. {text[:200]}" 
                for j, text in enumerate(batch)
            )
            
            prompt = self.BATCH_PROMPT.format(
                count=len(batch),
                headlines=headlines
            )
            
            response = self._call_ollama(prompt)
            parsed = self._parse_json_response(response)
            
            if parsed and isinstance(parsed, list):
                # Match results to texts
                for j, text in enumerate(batch):
                    result_data = next(
                        (r for r in parsed if r.get("index") == j),
                        {"sentiment": "neutral", "score": 5.0, "confidence": 0.3}
                    )
                    
                    results.append(SentimentResult(
                        text=text,
                        sentiment=result_data.get("sentiment", "neutral"),
                        score=float(result_data.get("score", 5.0)),
                        confidence=float(result_data.get("confidence", 0.3)),
                        reasoning="Batch analysis",
                        model=self.model,
                    ))
            else:
                # Fallback: analyze individually
                for text in batch:
                    results.append(self.analyze(text))
        
        return results

    def analyze_batch_parallel(
        self,
        texts: List[str],
        batch_size: int = 10,
        max_workers: int = 3
    ) -> List[SentimentResult]:
        """
        Analyze sentiment for multiple texts in parallel.
        
        Splits into batches and processes concurrently for ~3x speedup.
        
        Args:
            texts: List of news headlines/articles
            batch_size: Number of texts per batch (sent as single prompt)
            max_workers: Number of parallel requests
            
        Returns:
            List of SentimentResult for each text
        """
        import concurrent.futures
        
        if len(texts) <= batch_size:
            return self.analyze_batch(texts, batch_size)
        
        # Split into chunks for parallel processing
        chunks = []
        for i in range(0, len(texts), batch_size):
            chunks.append(texts[i:i + batch_size])
        
        results_by_chunk = [None] * len(chunks)
        
        def process_chunk(chunk_idx: int, chunk: List[str]) -> Tuple[int, List[SentimentResult]]:
            return chunk_idx, self.analyze_batch(chunk, batch_size=len(chunk))
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(process_chunk, idx, chunk)
                for idx, chunk in enumerate(chunks)
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    chunk_idx, chunk_results = future.result()
                    results_by_chunk[chunk_idx] = chunk_results
                except Exception as e:
                    logger.error(f"Parallel batch failed: {e}")
        
        # Flatten results in order
        results = []
        for chunk_results in results_by_chunk:
            if chunk_results:
                results.extend(chunk_results)
            else:
                # Add neutral fallbacks for failed chunks
                results.extend([
                    SentimentResult(
                        text="",
                        sentiment="neutral",
                        score=5.0,
                        confidence=0.0,
                        reasoning="Batch processing failed",
                        model=self.model,
                    )
                    for _ in range(batch_size)
                ])
        
        return results[:len(texts)]  # Trim to original length
    
    def score_for_briefai(self, text: str) -> Tuple[float, float, str]:
        """
        Get sentiment score in briefAI format.
        
        Returns:
            Tuple of (score, confidence, sentiment_label)
            - score: 1-10 (compatible with existing signals)
            - confidence: 0-1
            - sentiment_label: "bullish"/"bearish"/"neutral"
        """
        result = self.analyze(text)
        return result.score, result.confidence, result.sentiment


class OllamaSentimentScorer:
    """
    Drop-in replacement for keyword-based sentiment scoring in briefAI scrapers.
    
    Usage in scraper:
        from utils.ollama_sentiment import OllamaSentimentScorer
        
        scorer = OllamaSentimentScorer()
        
        for article in articles:
            sentiment_score = scorer.score(article['title'] + " " + article['summary'])
            article['sentiment_score'] = sentiment_score
    """
    
    def __init__(self, model: str = None):
        self.analyzer = OllamaSentimentAnalyzer(model=model)
        self._cache: Dict[str, float] = {}
    
    def score(self, text: str) -> float:
        """
        Get sentiment score for text.
        
        Args:
            text: News text to analyze
            
        Returns:
            Score 1-10 (1=bearish, 5=neutral, 10=bullish)
        """
        # Check cache
        cache_key = text[:100]
        if cache_key in self._cache:
            return self._cache[cache_key]
        
        score, _, _ = self.analyzer.score_for_briefai(text)
        
        # Cache result
        self._cache[cache_key] = score
        return score
    
    def score_batch(self, texts: List[str]) -> List[float]:
        """Score multiple texts efficiently."""
        results = self.analyzer.analyze_batch(texts)
        return [r.score for r in results]
    
    def clear_cache(self):
        """Clear the score cache."""
        self._cache = {}


# =============================================================================
# Integration with briefAI Signal Pipeline
# =============================================================================

def upgrade_scraper_sentiment(scraper_module_path: str) -> None:
    """
    Instructions for upgrading a scraper to use Ollama sentiment.
    
    Replace keyword-based scoring:
    
    OLD:
        sentiment_score = self._keyword_sentiment(title, content)
    
    NEW:
        from utils.ollama_sentiment import OllamaSentimentScorer
        scorer = OllamaSentimentScorer()
        sentiment_score = scorer.score(f"{title} {content}")
    """
    print(f"""
To upgrade {scraper_module_path} to use Ollama sentiment:

1. Add import at top:
   from utils.ollama_sentiment import OllamaSentimentScorer

2. Initialize scorer in __init__:
   self.sentiment_scorer = OllamaSentimentScorer()

3. Replace sentiment calculation:
   # OLD: sentiment_score = self._keyword_sentiment(title, content)
   sentiment_score = self.sentiment_scorer.score(f"{{title}} {{content}}")

4. For batch processing, use:
   scores = self.sentiment_scorer.score_batch(texts)
""")


# =============================================================================
# CLI for testing
# =============================================================================

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("Ollama Sentiment Analyzer Test")
    print("=" * 60)
    
    analyzer = OllamaSentimentAnalyzer()
    
    # Test cases
    test_texts = [
        "NVIDIA reports record quarterly revenue of $26 billion, beating expectations",
        "OpenAI faces major lawsuit over copyright infringement",
        "Google announces new AI research partnership with university",
        "Meta lays off 10,000 employees in restructuring",
        "Anthropic raises $4 billion from Amazon, valuation soars",
        "DeepSeek releases open source model rivaling GPT-4",
        "百度发布文心一言4.0，性能超越GPT-4",
        "阿里云宣布通义千问全面降价，最高降幅85%",
    ]
    
    print("\nAnalyzing test headlines...\n")
    
    for text in test_texts:
        result = analyzer.analyze(text)
        emoji = "🟢" if result.sentiment == "bullish" else "🔴" if result.sentiment == "bearish" else "⚪"
        print(f"{emoji} [{result.score:.1f}] {result.sentiment.upper():8s} | {text[:60]}")
        if result.reasoning:
            print(f"   └─ {result.reasoning[:80]}")
        print()
    
    print("=" * 60)
    print("Test complete!")
