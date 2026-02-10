"""
Entity name normalization for deduplication.

This module provides utilities to normalize entity names into canonical forms,
enabling deduplication across different spellings and variations.
"""

from typing import Dict, List

__all__ = ['normalize_entity_name']


def normalize_entity_name(raw_name: str, entity_type: str) -> str:
    """
    Convert entity name to canonical form for deduplication.

    Args:
        raw_name: Original name from extraction (e.g., "Open AI", "GPT-4")
        entity_type: One of "company", "model", "topic", "person"

    Returns:
        Normalized entity_id (e.g., "openai", "gpt4")

    Examples:
        >>> normalize_entity_name("Open AI", "company")
        'openai'
        >>> normalize_entity_name("GPT-4", "model")
        'gpt4'
        >>> normalize_entity_name("Meta Platforms", "company")
        'meta'
        >>> normalize_entity_name("Claude 3.5", "model")
        'claude'
    """
    # Handle empty or None input
    if not raw_name or not isinstance(raw_name, str):
        return ""

    # Basic normalization: lowercase and strip whitespace
    normalized = raw_name.lower().strip()

    # Remove common punctuation and spaces
    normalized = normalized.replace('-', '').replace('.', '').replace(' ', '').replace('_', '')

    # Company-specific aliases
    company_aliases: Dict[str, List[str]] = {
        'openai': ['openai', 'open-ai', 'open.ai', 'openai'],
        'anthropic': ['anthropic', 'anthropicai'],
        'google': ['google', 'googlellc', 'alphabet', 'alphabetinc'],
        'microsoft': ['microsoft', 'msft', 'ms'],
        'meta': ['meta', 'facebook', 'metaplatforms', 'fb'],
        'amazon': ['amazon', 'aws', 'amazonwebservices'],
        'nvidia': ['nvidia', 'nvda'],
        'deepmind': ['deepmind', 'googledeep mind'],
        'huggingface': ['huggingface', 'hugging face', 'hf'],
        'cohere': ['cohere', 'cohereai'],
    }

    # Model-specific aliases
    model_aliases: Dict[str, List[str]] = {
        'gpt4': ['gpt4', 'gpt-4', 'gpt4o', 'gpt4turbo'],
        'gpt3': ['gpt3', 'gpt-3', 'gpt35', 'gpt3.5'],
        'claude': ['claude', 'claudeai', 'claude3', 'claude35', 'claude4'],
        'llama': ['llama', 'llama2', 'llama3', 'llama3.1', 'llama3.3'],
        'gemini': ['gemini', 'geminipro', 'geminiultra'],
        'palm': ['palm', 'palm2', 'palmapi'],
        'mistral': ['mistral', 'mistrallarge', 'mistralai'],
        'qwen': ['qwen', 'qwen2', 'qwen25', 'tongyi'],
        'deepseek': ['deepseek', 'deepseekcoder', 'deepseekv2'],
    }

    # Topic-specific aliases (optional, less critical)
    topic_aliases: Dict[str, List[str]] = {
        'llm': ['llm', 'largelanguagemodel', 'languagemodel'],
        'agi': ['agi', 'artificialgeneralintelligence'],
        'transformer': ['transformer', 'transformerarchitecture'],
        'rlhf': ['rlhf', 'reinforcementlearningfromhumanfeedback'],
    }

    # Apply aliases based on entity type
    if entity_type == "company":
        for canonical, aliases in company_aliases.items():
            if normalized in aliases:
                return canonical
    elif entity_type == "model":
        for canonical, aliases in model_aliases.items():
            if normalized in aliases:
                return canonical
    elif entity_type == "topic":
        for canonical, aliases in topic_aliases.items():
            if normalized in aliases:
                return canonical
    # For person type, use normalized form directly (less standardization needed)

    return normalized