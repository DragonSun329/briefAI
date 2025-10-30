"""
LLM Provider Abstraction Layer

Provides a unified interface for multiple LLM providers (Kimi, OpenRouter, etc.)
with automatic fallback and rate limit handling.
"""

import os
import json
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from openai import OpenAI, RateLimitError, APIConnectionError, APIError
from loguru import logger


class BaseLLMProvider(ABC):
    """Abstract base class for LLM providers"""

    def __init__(
        self,
        provider_id: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = None
    ):
        """
        Initialize provider

        Args:
            provider_id: Unique provider identifier (kimi, openrouter, etc.)
            api_key: API key for the provider
            base_url: API base URL
            model: Default model to use
        """
        self.provider_id = provider_id
        self.api_key = api_key
        self.base_url = base_url
        self.current_model = model
        self.is_available = True
        self.last_error = None

        # Initialize OpenAI-compatible client
        if api_key and base_url:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            self.client = None

        # Statistics
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "rate_limit_errors": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_cost": 0.0
        }

    @abstractmethod
    def get_pricing(self, model: str) -> Dict[str, float]:
        """
        Get pricing for a model

        Returns:
            Dict with 'input' and 'output' keys (cost per million tokens)
        """
        pass

    @abstractmethod
    def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> tuple[str, Dict[str, int]]:
        """
        Send a chat request

        Args:
            system_prompt: System instruction
            user_message: User message
            model: Model to use (overrides default)
            temperature: Temperature for generation
            max_tokens: Maximum tokens in response

        Returns:
            Tuple of (response_text, usage_dict)
        """
        pass

    def detect_rate_limit(self, error: Exception) -> bool:
        """
        Detect if error is a rate limit or fallback-triggering error.
        Treats 403 moderation blocks, 404 no endpoints, and 429 rate limits the same way - triggers fallback.
        """
        # Direct rate limit errors
        if isinstance(error, RateLimitError):
            return True

        # HTTP 429 (rate limit)
        if hasattr(error, 'status_code') and error.status_code == 429:
            return True

        # HTTP 404 (no endpoints available - common with free tier)
        # "no endpoints found matching your data policy" means model unavailable
        if hasattr(error, 'status_code') and error.status_code == 404:
            error_str = str(error).lower()
            if 'no endpoints' in error_str or 'not found' in error_str:
                logger.warning(f"Model endpoint not available, will try next model")
                return True

        # HTTP 403 (moderation blocked, content blocked, etc.)
        # This should trigger fallback to next model
        if hasattr(error, 'status_code') and error.status_code == 403:
            if hasattr(error, 'message') and 'flagged' in str(error.message).lower():
                logger.warning(f"Model flagged content, will try next model")
                return True
            # Check in error body for moderation messages
            error_str = str(error).lower()
            if 'moderation' in error_str or 'flagged' in error_str or 'blocked' in error_str:
                return True

        return False

    def is_rate_limited(self) -> bool:
        """Check if provider is currently rate limited"""
        return isinstance(self.last_error, RateLimitError)


class KimiProvider(BaseLLMProvider):
    """Kimi/Moonshot AI provider implementation"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "moonshot-v1-8k"
    ):
        """
        Initialize Kimi provider

        Args:
            api_key: Moonshot API key (defaults to env var)
            model: Default model to use
        """
        api_key = api_key or os.getenv("MOONSHOT_API_KEY")
        if not api_key:
            raise ValueError("MOONSHOT_API_KEY not found in environment")

        super().__init__(
            provider_id="kimi",
            api_key=api_key,
            base_url="https://api.moonshot.cn/v1",
            model=model
        )

        logger.info(f"Initialized Kimi provider with model: {model}")

    def get_pricing(self, model: str) -> Dict[str, float]:
        """Get Kimi pricing"""
        pricing_map = {
            "moonshot-v1-8k": {"input": 12.00, "output": 12.00},
            "moonshot-v1-32k": {"input": 24.00, "output": 24.00},
            "moonshot-v1-128k": {"input": 60.00, "output": 60.00},
        }
        return pricing_map.get(model, {"input": 12.00, "output": 12.00})

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> tuple[str, Dict[str, int]]:
        """Send a chat request to Kimi"""
        model = model or self.current_model

        try:
            self.stats["total_calls"] += 1

            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )

            content = response.choices[0].message.content
            usage = response.usage.__dict__ if hasattr(response, 'usage') else {}

            self.stats["successful_calls"] += 1
            self._update_stats(usage, model)

            self.last_error = None
            self.is_available = True

            return content, usage

        except RateLimitError as e:
            self.stats["rate_limit_errors"] += 1
            self.stats["failed_calls"] += 1
            self.last_error = e
            logger.warning(f"Kimi rate limit hit: {e}")
            raise

        except Exception as e:
            self.stats["failed_calls"] += 1
            self.last_error = e
            logger.error(f"Kimi API error: {e}")
            raise

    def _update_stats(self, usage: Dict[str, int], model: str):
        """Update usage statistics"""
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        self.stats["total_input_tokens"] += input_tokens
        self.stats["total_output_tokens"] += output_tokens

        pricing = self.get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        self.stats["total_cost"] += input_cost + output_cost


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter provider with support for 50+ free models"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "meta-llama/llama-3.3-8b-instruct:free"
    ):
        """
        Initialize OpenRouter provider

        Args:
            api_key: OpenRouter API key (defaults to env vars with fallback)
            model: Default model to use
        """
        # Try multiple API keys in order: explicit, primary, secondary
        if not api_key:
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                api_key = os.getenv("OPENROUTER_API_KEY_2")

        if not api_key:
            raise ValueError("No OPENROUTER_API_KEY found in environment")

        super().__init__(
            provider_id="openrouter",
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model
        )

        # Store all available API keys for fallback
        self.api_keys = [
            k for k in [
                os.getenv("OPENROUTER_API_KEY"),
                os.getenv("OPENROUTER_API_KEY_2")
            ] if k
        ]
        self.current_key_index = 0

        logger.info(f"Initialized OpenRouter provider with model: {model} ({len(self.api_keys)} API keys available)")

    def get_pricing(self, model: str) -> Dict[str, float]:
        """
        Get pricing for OpenRouter models
        Most free models have $0 pricing
        """
        # Free tier pricing
        if ":free" in model:
            return {"input": 0.0, "output": 0.0}

        # Default free pricing
        return {"input": 0.0, "output": 0.0}

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 4096
    ) -> tuple[str, Dict[str, int]]:
        """Send a chat request to OpenRouter"""
        model = model or self.current_model

        try:
            self.stats["total_calls"] += 1

            # Add OpenRouter headers
            headers = {
                "HTTP-Referer": "https://github.com/dragonsun/briefAI",
                "X-Title": "AI Industry Weekly Briefing Agent"
            }

            # Create request with headers
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                max_tokens=max_tokens,
                temperature=temperature,
                extra_headers=headers
            )

            content = response.choices[0].message.content
            usage = response.usage.__dict__ if hasattr(response, 'usage') else {}

            self.stats["successful_calls"] += 1
            self._update_stats(usage, model)

            self.last_error = None
            self.is_available = True

            return content, usage

        except RateLimitError as e:
            self.stats["rate_limit_errors"] += 1
            self.stats["failed_calls"] += 1
            self.last_error = e

            # Check if it's a daily limit error and we have backup API keys
            error_str = str(e).lower()
            if ('free-models-per-day' in error_str or 'daily' in error_str) and len(self.api_keys) > 1:
                # Try switching to next API key
                next_index = (self.current_key_index + 1) % len(self.api_keys)
                if next_index != self.current_key_index:  # Haven't tried all keys yet
                    next_key = self.api_keys[next_index]
                    logger.warning(f"OpenRouter daily limit hit on key {self.current_key_index + 1}, switching to key {next_index + 1}")

                    # Recreate client with new API key
                    from openai import OpenAI
                    self.api_key = next_key
                    self.client = OpenAI(api_key=next_key, base_url=self.base_url)
                    self.current_key_index = next_index

                    # Retry with new API key
                    return self.chat(system_prompt, user_message, model, temperature, max_tokens)

            logger.warning(f"OpenRouter rate limit hit: {e}")
            raise

        except Exception as e:
            self.stats["failed_calls"] += 1
            self.last_error = e
            logger.error(f"OpenRouter API error: {e}")
            raise

    def _update_stats(self, usage: Dict[str, int], model: str):
        """Update usage statistics"""
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        self.stats["total_input_tokens"] += input_tokens
        self.stats["total_output_tokens"] += output_tokens

        # OpenRouter free models are $0
        pricing = self.get_pricing(model)
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        self.stats["total_cost"] += input_cost + output_cost


def create_provider(
    provider_id: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None
) -> BaseLLMProvider:
    """
    Factory function to create provider instances

    Args:
        provider_id: 'kimi' or 'openrouter'
        api_key: API key (optional, uses env vars if not provided)
        model: Model to use

    Returns:
        Provider instance
    """
    if provider_id == "kimi":
        return KimiProvider(api_key=api_key, model=model or "moonshot-v1-8k")
    elif provider_id == "openrouter":
        return OpenRouterProvider(
            api_key=api_key,
            model=model or "meta-llama/llama-3.3-8b-instruct:free"
        )
    else:
        raise ValueError(f"Unknown provider: {provider_id}")
