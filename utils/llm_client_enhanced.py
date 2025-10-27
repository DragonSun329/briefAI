"""
Enhanced LLM Client with Automatic Provider Switching

Wraps the original LLMClient to add automatic fallback to OpenRouter
when Kimi hits rate limits. Maintains backward compatibility.
"""

import os
from typing import Optional, Dict, Any
from loguru import logger
from dotenv import load_dotenv

from utils.llm_client import LLMClient as OriginalLLMClient
from utils.provider_switcher import ProviderSwitcher
from utils.llm_provider import RateLimitError
from openai import APIError

load_dotenv()


class EnhancedLLMClient:
    """LLM Client with intelligent provider switching"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "moonshot-v1-8k",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        enable_caching: bool = True,
        cache_manager: Optional[Any] = None,
        enable_provider_switching: bool = True
    ):
        """
        Initialize Enhanced LLM Client

        Args:
            api_key: Moonshot API key
            model: Model to use
            max_tokens: Maximum tokens
            temperature: Temperature for generation
            enable_caching: Enable response caching
            cache_manager: Cache manager instance
            enable_provider_switching: Enable automatic provider fallback
        """
        self.enable_provider_switching = enable_provider_switching

        # Initialize original Kimi client
        self.kimi_client = OriginalLLMClient(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            enable_caching=enable_caching,
            cache_manager=cache_manager
        )

        # Initialize provider switcher if enabled
        self.switcher = None
        if enable_provider_switching:
            try:
                self.switcher = ProviderSwitcher()
                logger.info("Provider switching ENABLED - fallback available")
            except Exception as e:
                logger.warning(f"Provider switching initialization failed: {e}")
                logger.info("Continuing with Kimi only (no fallback)")

        self.stats = self.kimi_client.stats

    def get_current_provider_info(self) -> Dict[str, str]:
        """Get current provider and model information"""
        if self.switcher:
            provider_id = self.switcher.current_provider_id
            provider_name = self.switcher._get_provider_display_name(provider_id)

            # Get model name if it's OpenRouter
            if provider_id.startswith('openrouter.'):
                tier = provider_id.split('.')[1]
                current_idx = (self.switcher.tier_model_indices.get(tier, 0) - 1) % len(
                    self.switcher.config['providers'][1]['tiers'][tier]['models']
                )
                model = self.switcher.config['providers'][1]['tiers'][tier]['models'][current_idx]
                return {"provider": provider_name, "model": model}
            else:
                return {"provider": provider_name, "model": "moonshot-v1-8k"}
        else:
            return {"provider": "Kimi/Moonshot", "model": "moonshot-v1-8k"}

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> str:
        """
        Send a chat request with automatic provider fallback

        Args:
            system_prompt: System instruction
            user_message: User message
            temperature: Temperature override
            max_tokens: Max tokens override
            use_cache: Use cache if available

        Returns:
            Response text
        """
        # If provider switching disabled or not initialized, use Kimi directly
        if not self.switcher:
            logger.debug("[KIMI] Processing request")
            return self.kimi_client.chat(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )

        # Try with provider switching
        try:
            logger.debug("[KIMI] Attempting request with primary provider")
            return self.kimi_client.chat(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )

        except RateLimitError as e:
            logger.warning(f"[KIMI] Rate limited (429), switching to OpenRouter...")

            # Switch to next provider
            next_provider = self.switcher.switch_to_next_provider()
            if not next_provider:
                logger.error("All providers exhausted!")
                raise RuntimeError("All LLM providers exhausted")

            # Try with fallback provider
            try:
                provider_info = self.get_current_provider_info()
                provider_display = f"{provider_info['provider']} ({provider_info['model']})"
                logger.info(f"[FALLBACK] Attempting with {provider_display}...")

                response, usage = next_provider.chat(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    temperature=temperature or 0.3,
                    max_tokens=max_tokens or 4096
                )

                logger.info(f"[✓ SUCCESS] Completed with {provider_display}")
                return response

            except Exception as fallback_error:
                logger.error(f"[FALLBACK] Provider also failed: {fallback_error}")
                raise

        except Exception as e:
            logger.error(f"[ERROR] Unexpected error: {e}")
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
        Send a structured chat request (JSON) with automatic fallback

        Args:
            system_prompt: System instruction
            user_message: User message
            response_format: Expected format
            temperature: Temperature override
            max_tokens: Max tokens override
            use_cache: Use cache if available

        Returns:
            Parsed JSON response
        """
        try:
            logger.debug("[KIMI] Attempting structured request")
            return self.kimi_client.chat_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )

        except (RateLimitError, APIError) as e:
            # Handle both rate limits (429) and moderation blocks (403)
            error_code = getattr(e, 'status_code', None)
            if error_code == 403:
                logger.warning(f"[KIMI] Content flagged by moderation (403), switching to next model...")
            elif error_code == 429:
                logger.warning(f"[KIMI] Rate limited (429), switching to OpenRouter...")
            else:
                logger.warning(f"[KIMI] Error occurred, switching to fallback...")

            if not self.switcher:
                raise

            next_provider = self.switcher.switch_to_next_provider()
            if not next_provider:
                logger.error("All providers exhausted!")
                raise RuntimeError("All LLM providers exhausted")

            try:
                provider_info = self.get_current_provider_info()
                provider_display = f"{provider_info['provider']} ({provider_info['model']})"
                logger.info(f"[FALLBACK] Attempting structured request with {provider_display}...")

                # Get response from fallback
                response, usage = next_provider.chat(
                    system_prompt=system_prompt + "\n\nIMPORTANT: Return your response as valid JSON format.",
                    user_message=user_message,
                    temperature=temperature or 0.3,
                    max_tokens=max_tokens or 4096
                )

                # Parse JSON
                import json
                try:
                    if "```json" in response:
                        json_start = response.find("```json") + 7
                        json_end = response.find("```", json_start)
                        parsed = json.loads(response[json_start:json_end])
                    else:
                        parsed = json.loads(response)
                    logger.info(f"[✓ SUCCESS] Structured request completed with {provider_display}")
                    return parsed
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse JSON response: {response[:100]}")
                    raise

            except Exception as fallback_error:
                logger.error(f"[FALLBACK] Provider failed: {fallback_error}")
                raise

        except Exception as e:
            logger.error(f"[ERROR] Unexpected error: {e}")
            raise

    def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics from all providers"""
        if self.switcher:
            return self.switcher.get_provider_stats()
        return {"kimi": {"stats": self.kimi_client.stats}}

    def print_stats(self):
        """Print statistics to logger"""
        logger.info("=" * 60)
        logger.info("LLM CLIENT STATISTICS")
        logger.info("=" * 60)

        if self.switcher:
            self.switcher.print_stats()
        else:
            logger.info("Kimi Client (No fallback enabled):")
            logger.info(f"  Total calls: {self.stats['total_calls']}")
            logger.info(f"  Cache hits: {self.stats['cache_hits']}")
            logger.info(f"  Cache misses: {self.stats['cache_misses']}")
            logger.info(f"  Errors: {self.stats['errors']}")
            logger.info(
                f"  Tokens: {self.stats['total_input_tokens']} input, "
                f"{self.stats['total_output_tokens']} output"
            )
            logger.info(f"  Cost: ¥{self.stats['total_cost']:.4f}")

        logger.info("=" * 60)


# Backward compatibility: Create as alias to EnhancedLLMClient
# This allows existing code to work without changes
LLMClient = EnhancedLLMClient
