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
                openrouter_config = self.switcher._get_openrouter_config()
                if openrouter_config and 'tiers' in openrouter_config and tier in openrouter_config['tiers']:
                    current_idx = (self.switcher.tier_model_indices.get(tier, 0) - 1) % len(
                        openrouter_config['tiers'][tier]['models']
                    )
                    model = openrouter_config['tiers'][tier]['models'][current_idx]
                    return {"provider": provider_name, "model": model}
                else:
                    return {"provider": provider_name, "model": "unknown"}
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

        # Use switcher's current provider (may be OpenRouter if Kimi disabled)
        max_attempts = 10
        last_error = None
        
        for attempt in range(max_attempts):
            current_provider = self.switcher.get_current_provider()
            provider_info = self.get_current_provider_info()
            provider_display = f"{provider_info['provider']} ({provider_info['model']})"
            
            try:
                logger.debug(f"[{provider_info['provider']}] Attempting request...")
                
                response, usage = current_provider.chat(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    temperature=temperature or 0.3,
                    max_tokens=max_tokens or 4096
                )

                logger.debug(f"[✓ SUCCESS] Completed with {provider_display}")
                return response

            except Exception as e:
                last_error = e
                logger.warning(f"[{provider_info['provider']}] Failed: {e}, trying next...")

                # Switch to next provider
                next_provider = self.switcher.switch_to_next_provider()
                if not next_provider:
                    logger.error("All providers exhausted!")
                    raise RuntimeError("All LLM providers exhausted") from last_error
                continue

        raise RuntimeError("All LLM providers exhausted") from last_error

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
        import json as json_module
        
        # If no switcher, use Kimi directly
        if not self.switcher:
            logger.debug("[KIMI] Attempting structured request (no switcher)")
            return self.kimi_client.chat_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                response_format=response_format,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )

        # Use switcher's current provider with retry loop
        max_attempts = 10
        last_error = None
        
        for attempt in range(max_attempts):
            current_provider = self.switcher.get_current_provider()
            provider_info = self.get_current_provider_info()
            provider_display = f"{provider_info['provider']} ({provider_info['model']})"
            
            try:
                logger.debug(f"[{provider_info['provider']}] Attempting structured request...")

                # Get response from current provider
                response, usage = current_provider.chat(
                    system_prompt=system_prompt + "\n\nIMPORTANT: Return your response as valid JSON format only. No markdown, no explanation, just the JSON object.",
                    user_message=user_message,
                    temperature=temperature or 0.3,
                    max_tokens=max_tokens or 4096
                )

                # Parse JSON
                try:
                    # Handle markdown code blocks
                    if "```json" in response:
                        json_start = response.find("```json") + 7
                        json_end = response.find("```", json_start)
                        parsed = json_module.loads(response[json_start:json_end].strip())
                    elif "```" in response:
                        json_start = response.find("```") + 3
                        json_end = response.find("```", json_start)
                        parsed = json_module.loads(response[json_start:json_end].strip())
                    else:
                        # Try to find JSON object/array in response
                        response_stripped = response.strip()
                        if response_stripped.startswith('{') or response_stripped.startswith('['):
                            parsed = json_module.loads(response_stripped)
                        else:
                            # Try to extract JSON from response
                            start = response.find('{')
                            if start == -1:
                                start = response.find('[')
                            if start != -1:
                                parsed = json_module.loads(response[start:])
                            else:
                                raise json_module.JSONDecodeError("No JSON found", response, 0)
                    
                    logger.debug(f"[✓ SUCCESS] Structured request completed with {provider_display}")
                    return parsed
                    
                except json_module.JSONDecodeError as je:
                    logger.error(f"Failed to parse JSON response: {response[:200] if response else '(empty)'}")
                    last_error = je
                    # Try next provider
                    next_provider = self.switcher.switch_to_next_provider()
                    if not next_provider:
                        raise RuntimeError("All LLM providers exhausted") from last_error
                    continue

            except Exception as e:
                last_error = e
                logger.warning(f"[{provider_info['provider']}] Failed: {e}, trying next...")

                # Switch to next provider
                next_provider = self.switcher.switch_to_next_provider()
                if not next_provider:
                    logger.error("All providers exhausted!")
                    raise RuntimeError("All LLM providers exhausted") from last_error
                continue

        raise RuntimeError("All LLM providers exhausted") from last_error

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
