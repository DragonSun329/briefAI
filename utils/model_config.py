"""
Model Configuration Manager

Provides YAML-based model selection per pipeline/task.
Supports environment variable overrides and fallback chains.

Usage:
    from utils.model_config import get_model_config, ModelConfig
    
    # Get config for a pipeline
    config = get_model_config(pipeline="news")
    
    # Get config for a specific task
    config = get_model_config(task="deep_research")
    
    # Use with LLM client
    client = LLMClient(
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens
    )
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import yaml
from loguru import logger


@dataclass
class ModelConfig:
    """Configuration for a single model."""
    provider: str
    model: str
    temperature: float = 0.3
    max_tokens: int = 4096
    
    @property
    def display_name(self) -> str:
        return f"{self.provider}/{self.model}" if '/' not in self.model else self.model


class ModelConfigManager:
    """Manages model configurations from YAML with env var overrides."""
    
    _instance = None
    _config = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._config is None:
            self._load_config()
    
    def _load_config(self):
        config_path = Path(__file__).parent.parent / "config" / "models.yaml"
        try:
            with open(config_path, 'r') as f:
                self._config = yaml.safe_load(f)
            logger.info(f"Loaded model config from {config_path}")
        except FileNotFoundError:
            logger.warning(f"Model config not found at {config_path}, using defaults")
            self._config = {"defaults": {"provider": "openrouter", "temperature": 0.3, "max_tokens": 4096}}
    
    def get_config(
        self,
        pipeline: Optional[str] = None,
        task: Optional[str] = None,
        tier: str = "primary"
    ) -> ModelConfig:
        """Get model config for a pipeline or task.
        
        Priority: env vars > task config > pipeline config > defaults
        """
        defaults = self._config.get("defaults", {})
        
        # Start with defaults
        config = {
            "provider": defaults.get("provider", "openrouter"),
            "model": defaults.get("model", "anthropic/claude-haiku-4.5"),
            "temperature": defaults.get("temperature", 0.3),
            "max_tokens": defaults.get("max_tokens", 4096),
        }
        
        # Layer pipeline config
        if pipeline:
            pipeline_cfg = self._config.get("pipelines", {}).get(pipeline, {}).get(tier, {})
            config.update({k: v for k, v in pipeline_cfg.items() if v is not None})
        
        # Layer task config (takes priority over pipeline)
        if task:
            task_cfg = self._config.get("tasks", {}).get(task, {}).get(tier, {})
            config.update({k: v for k, v in task_cfg.items() if v is not None})
        
        # Environment variable overrides
        prefix = f"BRIEFAI_{(task or pipeline or 'DEFAULT').upper()}"
        env_model = os.getenv(f"{prefix}_MODEL")
        env_provider = os.getenv(f"{prefix}_PROVIDER")
        env_temp = os.getenv(f"{prefix}_TEMPERATURE")
        env_tokens = os.getenv(f"{prefix}_MAX_TOKENS")
        
        if env_model:
            config["model"] = env_model
        if env_provider:
            config["provider"] = env_provider
        if env_temp:
            config["temperature"] = float(env_temp)
        if env_tokens:
            config["max_tokens"] = int(env_tokens)
        
        return ModelConfig(**config)
    
    def get_fallback(
        self,
        pipeline: Optional[str] = None,
        task: Optional[str] = None
    ) -> Optional[ModelConfig]:
        """Get fallback model config, or None if no fallback defined."""
        try:
            return self.get_config(pipeline=pipeline, task=task, tier="fallback")
        except Exception:
            return None
    
    def reload(self):
        """Reload config from disk."""
        self._config = None
        self._load_config()


# Module-level convenience functions
_manager = None

def get_model_config(
    pipeline: Optional[str] = None,
    task: Optional[str] = None,
    tier: str = "primary"
) -> ModelConfig:
    """Get model config for a pipeline or task."""
    global _manager
    if _manager is None:
        _manager = ModelConfigManager()
    return _manager.get_config(pipeline=pipeline, task=task, tier=tier)

def get_fallback_config(
    pipeline: Optional[str] = None,
    task: Optional[str] = None
) -> Optional[ModelConfig]:
    """Get fallback model config."""
    global _manager
    if _manager is None:
        _manager = ModelConfigManager()
    return _manager.get_fallback(pipeline=pipeline, task=task)
