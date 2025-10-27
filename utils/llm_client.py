"""
LLM API Client Wrapper (Kimi/Moonshot AI)

Provides a clean interface for interacting with Moonshot AI's Kimi API
with retry logic, error handling, response caching, and cost tracking.

Features:
- Automatic retry with exponential backoff
- Response caching to reduce API costs
- Token counting and cost estimation
- Structured JSON response parsing
- Comprehensive error handling
- Rate limiting support
"""

import os
import json
import time
import hashlib
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type
)
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class LLMClient:
    """Wrapper for Moonshot AI (Kimi) API with enhanced features"""

    # Pricing per million tokens (Kimi pricing as of Oct 2024)
    PRICING = {
        "moonshot-v1-8k": {"input": 12.00, "output": 12.00},
        "moonshot-v1-32k": {"input": 24.00, "output": 24.00},
        "moonshot-v1-128k": {"input": 60.00, "output": 60.00},
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "moonshot-v1-8k",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        enable_caching: bool = True,
        cache_manager: Optional[Any] = None,
        base_url: str = "https://api.moonshot.cn/v1"
    ):
        """
        Initialize LLM client for Kimi

        Args:
            api_key: Moonshot API key (defaults to env var MOONSHOT_API_KEY)
            model: Kimi model to use (moonshot-v1-8k, moonshot-v1-32k, moonshot-v1-128k)
            max_tokens: Maximum tokens in response
            temperature: Temperature for generation (0.0-1.0)
            enable_caching: Enable response caching
            cache_manager: Optional cache manager instance
            base_url: Moonshot API base URL
        """
        self.api_key = api_key or os.getenv("MOONSHOT_API_KEY")
        if not self.api_key:
            raise ValueError("MOONSHOT_API_KEY not found in environment")

        # Initialize OpenAI-compatible client for Kimi
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url
        )

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.enable_caching = enable_caching
        self.cache_manager = cache_manager

        # Statistics tracking
        self.stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
            "errors": 0
        }

        logger.info(f"Initialized Kimi LLM client with model: {model}")
        logger.info(f"Caching: {'enabled' if enable_caching else 'disabled'}")

    def _generate_cache_key(self, system_prompt: str, user_message: str, **kwargs) -> str:
        """Generate a cache key from request parameters"""
        key_data = f"{self.model}:{system_prompt}:{user_message}:{kwargs}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _update_stats(self, usage: Dict[str, int]):
        """Update usage statistics and cost"""
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        self.stats["total_input_tokens"] += input_tokens
        self.stats["total_output_tokens"] += output_tokens

        # Calculate cost
        pricing = self.PRICING.get(self.model, {"input": 12.00, "output": 12.00})
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        self.stats["total_cost"] += total_cost

        logger.debug(
            f"Token usage - Input: {input_tokens}, Output: {output_tokens}, "
            f"Cost: ${total_cost:.4f}"
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, APIConnectionError)),
        reraise=True
    )
    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> str:
        """
        Send a chat request to Kimi

        Args:
            system_prompt: System instruction
            user_message: User's message/query
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            use_cache: Use cached response if available

        Returns:
            Kimi's response as string
        """
        self.stats["total_calls"] += 1

        # Check cache first
        if self.enable_caching and use_cache and self.cache_manager:
            cache_key = self._generate_cache_key(
                system_prompt, user_message,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens
            )

            cached = self.cache_manager.get(f"kimi_{cache_key}", max_age_hours=24)
            if cached:
                self.stats["cache_hits"] += 1
                logger.debug(f"Cache hit for request")
                return cached

            self.stats["cache_misses"] += 1

        try:
            # Kimi uses OpenAI-compatible API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens or self.max_tokens,
                temperature=temperature or self.temperature
            )

            # Extract text from response
            content = response.choices[0].message.content

            # Update statistics
            if hasattr(response, 'usage'):
                self._update_stats(response.usage.__dict__)

            # Cache the response
            if self.enable_caching and use_cache and self.cache_manager:
                self.cache_manager.set(f"kimi_{cache_key}", content)

            logger.debug(f"Kimi response (length: {len(content)} chars)")
            return content

        except RateLimitError as e:
            logger.warning(f"Rate limit hit, retrying... {e}")
            self.stats["errors"] += 1
            raise
        except APIConnectionError as e:
            logger.warning(f"API connection error, retrying... {e}")
            self.stats["errors"] += 1
            raise
        except APIError as e:
            logger.error(f"Kimi API error: {e}")
            self.stats["errors"] += 1
            raise
        except Exception as e:
            logger.error(f"Unexpected error calling Kimi: {e}")
            self.stats["errors"] += 1
            raise

    def chat_structured(
        self,
        system_prompt: str,
        user_message: str,
        response_format: str = "json",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Send a chat request expecting structured output (JSON)

        Args:
            system_prompt: System instruction
            user_message: User's message/query
            response_format: Expected format (default: "json")
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            use_cache: Use cached response if available

        Returns:
            Parsed JSON response as dictionary
        """
        # Enhance system prompt to request JSON
        enhanced_system = f"{system_prompt}\n\nIMPORTANT: Return your response as valid JSON format."

        response_text = self.chat(
            system_prompt=enhanced_system,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens,
            use_cache=use_cache
        )

        # Try to extract JSON from response
        try:
            # Look for JSON in code blocks
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.find("```", json_start)
                json_text = response_text[json_start:json_end].strip()
            else:
                json_text = response_text.strip()

            return json.loads(json_text)

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.debug(f"Raw response: {response_text}")
            raise ValueError(f"Kimi did not return valid JSON: {e}")

    def batch_chat(
        self,
        requests: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        delay_between_calls: float = 0.5
    ) -> List[str]:
        """
        Process multiple chat requests in batch

        Args:
            requests: List of dicts with 'system_prompt' and 'user_message' keys
            temperature: Override default temperature
            max_tokens: Override default max_tokens
            delay_between_calls: Delay in seconds between API calls

        Returns:
            List of response strings
        """
        responses = []
        total = len(requests)

        logger.info(f"Processing {total} batch requests...")

        for i, request in enumerate(requests, 1):
            try:
                logger.debug(f"Processing request {i}/{total}")

                response = self.chat(
                    system_prompt=request['system_prompt'],
                    user_message=request['user_message'],
                    temperature=temperature,
                    max_tokens=max_tokens
                )

                responses.append(response)

                # Add delay to respect rate limits
                if i < total and delay_between_calls > 0:
                    time.sleep(delay_between_calls)

            except Exception as e:
                logger.error(f"Error processing request {i}: {e}")
                responses.append(None)

        logger.info(f"Batch processing complete: {len([r for r in responses if r])} succeeded")
        return responses

    def get_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics

        Returns:
            Dictionary with usage stats including tokens and cost
        """
        cache_hit_rate = 0.0
        if self.stats["total_calls"] > 0:
            cache_hit_rate = (self.stats["cache_hits"] / self.stats["total_calls"]) * 100

        return {
            **self.stats,
            "cache_hit_rate": f"{cache_hit_rate:.1f}%",
            "average_cost_per_call": (
                self.stats["total_cost"] / self.stats["total_calls"]
                if self.stats["total_calls"] > 0 else 0
            )
        }

    def print_stats(self):
        """Print usage statistics in a readable format"""
        stats = self.get_stats()

        print("\n" + "=" * 50)
        print("Kimi API Usage Statistics")
        print("=" * 50)
        print(f"Total API calls:       {stats['total_calls']}")
        print(f"Cache hits:            {stats['cache_hits']} ({stats['cache_hit_rate']})")
        print(f"Cache misses:          {stats['cache_misses']}")
        print(f"Errors:                {stats['errors']}")
        print(f"\nTotal input tokens:    {stats['total_input_tokens']:,}")
        print(f"Total output tokens:   {stats['total_output_tokens']:,}")
        print(f"Total tokens:          {stats['total_input_tokens'] + stats['total_output_tokens']:,}")
        print(f"\nTotal cost:            ${stats['total_cost']:.4f}")
        print(f"Avg cost per call:     ${stats['average_cost_per_call']:.4f}")
        print("=" * 50 + "\n")

    def reset_stats(self):
        """Reset usage statistics"""
        self.stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0,
            "errors": 0
        }
        logger.info("Statistics reset")


# Backwards compatibility alias
ClaudeClient = LLMClient


if __name__ == "__main__":
    # Test the Kimi client
    print("Testing Kimi LLM Client\n")

    # Test 1: Basic chat
    print("=" * 50)
    print("Test 1: Basic Chat")
    print("=" * 50)
    client = LLMClient(enable_caching=False)
    response = client.chat(
        system_prompt="你是一个有帮助的AI助手。",
        user_message="用中文说你好（简短回答）"
    )
    print(f"Response: {response}\n")

    # Test 2: Structured JSON response
    print("=" * 50)
    print("Test 2: Structured JSON Response")
    print("=" * 50)
    json_response = client.chat_structured(
        system_prompt="你是一个返回JSON的助手。",
        user_message='返回一个JSON对象，包含 "greeting"（中文问候）和 "language" 两个键'
    )
    print(f"JSON Response: {json.dumps(json_response, ensure_ascii=False, indent=2)}\n")

    # Print statistics
    client.print_stats()

    print("\n✅ All tests completed!")
