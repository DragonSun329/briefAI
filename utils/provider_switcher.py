"""
Provider Switcher - Intelligent fallback mechanism

Handles automatic switching between providers when rate limits are hit.
Implements quality-first strategy with graceful degradation.
"""

import json
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from loguru import logger

from utils.llm_provider import BaseLLMProvider, KimiProvider, OpenRouterProvider


class ProviderSwitcher:
    """Manages provider switching and fallback logic"""

    def __init__(self, config_path: str = "./config/providers.json"):
        """
        Initialize provider switcher

        Args:
            config_path: Path to providers.json configuration
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()

        # Initialize providers
        self.providers: Dict[str, BaseLLMProvider] = {}
        self.current_provider_id = "kimi"
        self.provider_queue = self._build_fallback_queue()

        # Track model usage per tier for rotation
        self.tier_model_indices: Dict[str, int] = {
            'tier1_quality': 0,
            'tier2_balanced': 0,
            'tier3_fast': 0
        }

        # Initialize primary provider
        self.current_provider = self._get_or_create_provider("kimi")

        logger.info("Provider Switcher initialized")
        logger.info(f"Fallback order: {' → '.join(self.provider_queue)}")

    def _load_config(self) -> Dict[str, Any]:
        """Load provider configuration"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Provider config not found: {self.config_path}")
            raise

    def _build_fallback_queue(self) -> List[str]:
        """Build provider fallback queue from configuration"""
        queue = []

        # Add Kimi first
        kimi_config = next(
            (p for p in self.config['providers'] if p['id'] == 'kimi'),
            None
        )
        if kimi_config and kimi_config.get('enabled'):
            queue.append('kimi')

        # Add OpenRouter with tiers
        openrouter_config = next(
            (p for p in self.config['providers'] if p['id'] == 'openrouter'),
            None
        )
        if openrouter_config and openrouter_config.get('enabled'):
            queue.append('openrouter.tier1_quality')
            queue.append('openrouter.tier2_balanced')
            queue.append('openrouter.tier3_fast')

        return queue

    def _get_or_create_provider(self, provider_spec: str) -> BaseLLMProvider:
        """
        Get or create a provider instance.
        For OpenRouter tiers, always creates a new instance with rotated model.

        Args:
            provider_spec: Provider ID or 'openrouter.tier1_quality' format

        Returns:
            Provider instance
        """
        # For Kimi, cache the provider (only one instance needed)
        if provider_spec == 'kimi':
            if provider_spec in self.providers:
                return self.providers[provider_spec]
            provider = KimiProvider()
            self.providers[provider_spec] = provider
            return provider

        # For OpenRouter, always create new instance (different model each time)
        elif provider_spec.startswith('openrouter'):
            # Extract tier if specified
            tier = None
            if '.' in provider_spec:
                tier = provider_spec.split('.')[1]

            # Select model from tier with rotation
            model = self._select_model_from_tier(tier)

            # Create new provider instance with rotated model
            # Use unique key with model name to avoid overwriting
            provider_key = f"openrouter.{tier}.{model}"

            # Create new provider (don't use cache for rotation)
            provider = OpenRouterProvider(model=model)

            # Store with unique key
            self.providers[provider_key] = provider

            return provider
        else:
            raise ValueError(f"Unknown provider spec: {provider_spec}")

    def _select_model_from_tier(self, tier: Optional[str] = None) -> str:
        """
        Select a model from the specified tier with rotation.
        Each time a rate limit is hit within a tier, rotate to the next model.
        """
        openrouter_config = next(
            (p for p in self.config['providers'] if p['id'] == 'openrouter'),
            None
        )

        if not openrouter_config:
            return "meta-llama/llama-3.3-8b-instruct:free"

        # Default to tier3 if not specified
        if tier is None:
            tier = 'tier3_fast'

        # Get models for this tier
        if tier not in openrouter_config['tiers']:
            logger.warning(f"Unknown tier: {tier}, using tier3_fast")
            tier = 'tier3_fast'

        models = openrouter_config['tiers'][tier]['models']

        if not models:
            return "meta-llama/llama-3.3-8b-instruct:free"

        # Get current index for this tier
        current_index = self.tier_model_indices.get(tier, 0)

        # Rotate to next model (wraparound if at end)
        next_index = (current_index + 1) % len(models)
        self.tier_model_indices[tier] = next_index

        selected_model = models[current_index]
        logger.debug(
            f"Selected model from {tier}: {selected_model} "
            f"(index {current_index}/{len(models)-1})"
        )

        return selected_model

    def get_current_provider(self) -> BaseLLMProvider:
        """Get current active provider"""
        return self.current_provider

    def get_current_provider_id(self) -> str:
        """Get current provider ID"""
        return self.current_provider_id

    def switch_provider(self, provider_spec: str) -> BaseLLMProvider:
        """
        Manually switch to a specific provider

        Args:
            provider_spec: Provider ID or 'openrouter.tier1_quality' format

        Returns:
            New provider instance
        """
        provider = self._get_or_create_provider(provider_spec)
        self.current_provider = provider
        self.current_provider_id = provider_spec

        logger.info(f"Switched provider to: {provider_spec}")
        return provider

    def switch_to_next_provider(self) -> Optional[BaseLLMProvider]:
        """
        Switch to next available provider/model in fallback queue.
        Within a tier, tries different models via rotation before moving to next tier.

        Returns:
            New provider instance or None if all providers exhausted
        """
        current_index = -1
        try:
            current_index = self.provider_queue.index(self.current_provider_id)
        except ValueError:
            current_index = -1

        # Try next providers in queue
        for i in range(current_index + 1, len(self.provider_queue)):
            provider_spec = self.provider_queue[i]

            # Extract tier name to show current model
            tier = None
            if provider_spec.startswith('openrouter.'):
                tier = provider_spec.split('.')[1]

            try:
                provider = self._get_or_create_provider(provider_spec)
                self.current_provider = provider
                self.current_provider_id = provider_spec

                # Determine provider name and current model for logging
                provider_name = self._get_provider_display_name(provider_spec)

                if tier and tier in self.tier_model_indices:
                    current_model_idx = (self.tier_model_indices[tier] - 1) % len(
                        self.config['providers'][1]['tiers'][tier]['models']
                    )
                    model_name = self.config['providers'][1]['tiers'][tier]['models'][
                        current_model_idx
                    ]
                    logger.info(
                        f"Switched to fallback provider: {provider_name} "
                        f"(using model: {model_name})"
                    )
                else:
                    logger.info(f"Switched to fallback provider: {provider_name}")

                return provider
            except Exception as e:
                logger.warning(f"Failed to create provider {provider_spec}: {e}")
                continue

        logger.error("All providers and models exhausted!")
        return None

    def _get_provider_display_name(self, provider_spec: str) -> str:
        """Get human-readable provider name"""
        if provider_spec == 'kimi':
            return 'Kimi/Moonshot (Primary)'
        elif provider_spec == 'openrouter.tier1_quality':
            return 'OpenRouter Tier 1 (Quality)'
        elif provider_spec == 'openrouter.tier2_balanced':
            return 'OpenRouter Tier 2 (Balanced)'
        elif provider_spec == 'openrouter.tier3_fast':
            return 'OpenRouter Tier 3 (Fast)'
        return provider_spec

    def retry_with_fallback(
        self,
        task_name: str,
        callback,
        *args,
        **kwargs
    ) -> Tuple[Any, str]:
        """
        Execute a task with automatic fallback on rate limits.
        On rate limit within a tier, tries different models in that tier first,
        then moves to next tier.

        Args:
            task_name: Name of the task for logging
            callback: Function to execute that accepts current provider as first arg
            *args: Positional arguments for callback
            **kwargs: Keyword arguments for callback

        Returns:
            Tuple of (result, provider_used)
        """
        max_retries = 5  # More retries to allow model rotation

        for attempt in range(max_retries):
            try:
                provider = self.current_provider
                provider_name = self._get_provider_display_name(
                    self.current_provider_id
                )

                logger.debug(f"[{task_name}] Attempt {attempt + 1} with {provider_name}")

                # Execute callback with current provider
                result = callback(provider, *args, **kwargs)

                logger.debug(f"[{task_name}] Success with {provider_name}")
                return result, self.current_provider_id

            except Exception as e:
                logger.warning(f"[{task_name}] {self.current_provider_id} error: {e}")

                # Check if it's a rate limit error
                if self.current_provider.detect_rate_limit(e):
                    # Extract current tier to see if we can rotate models within it
                    current_tier = None
                    if self.current_provider_id.startswith('openrouter.'):
                        current_tier = self.current_provider_id.split('.')[1]

                    logger.warning(
                        f"[{task_name}] Rate limit hit on "
                        f"{self._get_provider_display_name(self.current_provider_id)}, "
                        f"trying next model/provider..."
                    )

                    # If we're in an OpenRouter tier, try next model in same tier first
                    if current_tier and current_tier in self.tier_model_indices:
                        tier_models = self.config['providers'][1]['tiers'][current_tier]['models']
                        current_idx = (self.tier_model_indices[current_tier] - 1) % len(tier_models)
                        models_in_tier = len(tier_models)

                        # If we haven't tried all models in this tier, try next model
                        if models_in_tier > 1:
                            logger.debug(
                                f"[{task_name}] Trying next model in {current_tier}..."
                            )
                            # Create new provider with next model in same tier
                            provider = self._get_or_create_provider(
                                f"openrouter.{current_tier}"
                            )
                            self.current_provider = provider
                            continue

                    # Otherwise, move to next tier/provider
                    next_provider = self.switch_to_next_provider()
                    if next_provider:
                        continue
                    else:
                        logger.error(f"[{task_name}] All providers and models exhausted!")
                        raise RuntimeError("All LLM providers exhausted")
                else:
                    # Other errors - retry with same provider
                    if attempt < max_retries - 1:
                        logger.warning(f"[{task_name}] Retrying with same provider...")
                        continue
                    else:
                        logger.error(f"[{task_name}] Max retries exceeded")
                        raise

        raise RuntimeError(f"Failed to complete task: {task_name}")

    def get_provider_stats(self) -> Dict[str, Any]:
        """Get statistics for all providers"""
        stats = {}
        for provider_id, provider in self.providers.items():
            stats[provider_id] = {
                "provider_name": self._get_provider_display_name(provider_id),
                "stats": provider.stats,
                "is_available": provider.is_available,
                "last_error": str(provider.last_error) if provider.last_error else None
            }
        return stats

    def print_stats(self):
        """Print provider statistics to logger"""
        stats = self.get_provider_stats()

        logger.info("=" * 60)
        logger.info("PROVIDER STATISTICS")
        logger.info("=" * 60)

        for provider_id, provider_stats in stats.items():
            logger.info(f"\n{provider_stats['provider_name']}:")
            logger.info(f"  Total calls: {provider_stats['stats']['total_calls']}")
            logger.info(f"  Successful: {provider_stats['stats']['successful_calls']}")
            logger.info(f"  Failed: {provider_stats['stats']['failed_calls']}")
            logger.info(
                f"  Rate limit errors: {provider_stats['stats']['rate_limit_errors']}"
            )
            logger.info(
                f"  Tokens: "
                f"{provider_stats['stats']['total_input_tokens']} input, "
                f"{provider_stats['stats']['total_output_tokens']} output"
            )
            logger.info(f"  Cost: ¥{provider_stats['stats']['total_cost']:.4f}")

        # Print total
        total_calls = sum(
            p['stats']['total_calls']
            for p in stats.values()
        )
        total_cost = sum(
            p['stats']['total_cost']
            for p in stats.values()
        )

        logger.info("\n" + "=" * 60)
        logger.info(f"TOTAL: {total_calls} calls, Cost: ¥{total_cost:.4f}")
        logger.info("=" * 60)
