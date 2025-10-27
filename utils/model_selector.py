"""
Model Selector - Task-based model selection

Selects appropriate models from provider tiers based on the task type.
Implements quality-first strategy with intelligent fallback.
"""

import json
from typing import Optional, Dict, Any
from pathlib import Path
from enum import Enum
from loguru import logger


class TaskType(Enum):
    """Task type enumeration"""
    ENTITY_EXTRACTION = "entity_extraction"
    ARTICLE_EVALUATION = "article_evaluation"
    ARTICLE_PARAPHRASING = "article_paraphrasing"
    CATEGORY_SELECTION = "category_selection"
    GENERAL_CHAT = "general_chat"
    FALLBACK_EMERGENCY = "fallback_emergency"


class ModelSelector:
    """Selects optimal model based on task type"""

    def __init__(self, config_path: str = "./config/providers.json"):
        """
        Initialize model selector

        Args:
            config_path: Path to providers.json configuration
        """
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.task_mapping = self.config.get('task_model_mapping', {})

    def _load_config(self) -> Dict[str, Any]:
        """Load provider configuration"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Provider config not found: {self.config_path}")
            raise

    def get_preferred_tier(self, task_type: TaskType) -> str:
        """
        Get preferred tier for a task type

        Args:
            task_type: Type of task

        Returns:
            Tier name (tier1_quality, tier2_balanced, tier3_fast)
        """
        task_name = task_type.value
        if task_name in self.task_mapping:
            return self.task_mapping[task_name].get('preferred_tier', 'tier2_balanced')
        return 'tier2_balanced'

    def get_preferred_provider_spec(self, task_type: TaskType) -> str:
        """
        Get preferred provider specification for a task

        Args:
            task_type: Type of task

        Returns:
            Provider spec like 'kimi' or 'openrouter.tier1_quality'
        """
        # Quality-first strategy:
        # Try Kimi first for all critical tasks
        critical_tasks = [
            TaskType.ARTICLE_PARAPHRASING,
            TaskType.ARTICLE_EVALUATION,
            TaskType.ENTITY_EXTRACTION
        ]

        if task_type in critical_tasks:
            return 'kimi'  # Primary provider for quality
        else:
            tier = self.get_preferred_tier(task_type)
            return f'openrouter.{tier}'

    def select_model_for_task(
        self,
        task_type: TaskType,
        force_provider: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Select model configuration for a task

        Args:
            task_type: Type of task
            force_provider: Force specific provider (bypass recommendations)

        Returns:
            Dict with 'provider' and 'model' keys
        """
        if force_provider:
            provider_spec = force_provider
        else:
            provider_spec = self.get_preferred_provider_spec(task_type)

        # Get tier for OpenRouter
        if provider_spec.startswith('openrouter'):
            tier = provider_spec.split('.')[1] if '.' in provider_spec else 'tier2_balanced'
            openrouter_config = next(
                (p for p in self.config['providers'] if p['id'] == 'openrouter'),
                None
            )

            if openrouter_config and tier in openrouter_config['tiers']:
                models = openrouter_config['tiers'][tier]['models']
                model = models[0] if models else "meta-llama/llama-3.3-8b-instruct:free"
            else:
                model = "meta-llama/llama-3.3-8b-instruct:free"
        else:
            # Kimi
            model = "moonshot-v1-8k"

        return {
            "provider": provider_spec,
            "model": model,
            "task_type": task_type.value,
            "reason": self.task_mapping.get(task_type.value, {}).get('reason', 'Default selection')
        }

    def get_all_tier1_models(self) -> list:
        """Get all Tier 1 (quality) models"""
        openrouter_config = next(
            (p for p in self.config['providers'] if p['id'] == 'openrouter'),
            None
        )
        if openrouter_config:
            return openrouter_config['tiers']['tier1_quality']['models']
        return []

    def get_all_tier2_models(self) -> list:
        """Get all Tier 2 (balanced) models"""
        openrouter_config = next(
            (p for p in self.config['providers'] if p['id'] == 'openrouter'),
            None
        )
        if openrouter_config:
            return openrouter_config['tiers']['tier2_balanced']['models']
        return []

    def get_all_tier3_models(self) -> list:
        """Get all Tier 3 (fast) models"""
        openrouter_config = next(
            (p for p in self.config['providers'] if p['id'] == 'openrouter'),
            None
        )
        if openrouter_config:
            return openrouter_config['tiers']['tier3_fast']['models']
        return []

    def log_selection(self, task_type: TaskType, selection: Dict[str, str]):
        """Log model selection decision"""
        logger.debug(
            f"Model selection for {task_type.value}: "
            f"Provider={selection['provider']}, "
            f"Model={selection['model']}, "
            f"Reason: {selection['reason']}"
        )


# Singleton instance
_selector = None


def get_model_selector(config_path: str = "./config/providers.json") -> ModelSelector:
    """Get or create model selector singleton"""
    global _selector
    if _selector is None:
        _selector = ModelSelector(config_path)
    return _selector
