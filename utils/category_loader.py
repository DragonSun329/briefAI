"""
Category Loader Utility

Handles loading and structuring category data from configuration for use in evaluation pipelines.
Categories are used by ArticleFilter and NewsEvaluator to contextualize article evaluation.
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from loguru import logger


def load_categories(
    category_ids: Optional[List[str]] = None,
    categories_file: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Load categories from configuration file.

    Args:
        category_ids: List of specific category IDs to load (e.g., ["fintech_ai", "data_analytics"])
                     If None, loads default categories from config
        categories_file: Optional path to categories file (defaults to ./config/categories.json)

    Returns:
        List of category dictionaries with structure:
        {
            "id": "fintech_ai",
            "name": "Fintech AI Applications",
            "aliases": ["fintech", "finance", ...],
            "priority": 10,
            "description": "..."
        }

    Raises:
        FileNotFoundError: If config/categories.json not found
        ValueError: If invalid category_ids specified
    """
    # Load config
    config_path = Path(categories_file or "./config/categories.json")
    if not config_path.exists():
        logger.error(f"Category config not found at {config_path}")
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    all_categories = config.get('categories', [])

    # If no category_ids specified, use defaults
    if category_ids is None:
        default_ids = config.get('default_categories', [])
        category_ids = default_ids

    # Validate that all requested category_ids exist
    all_ids = {cat['id'] for cat in all_categories}
    invalid_ids = set(category_ids) - all_ids
    if invalid_ids:
        logger.warning(f"Invalid category IDs requested: {invalid_ids}")
        valid_ids = set(category_ids) & all_ids
        if not valid_ids:
            raise ValueError(f"No valid categories found. Invalid IDs: {invalid_ids}")
        category_ids = list(valid_ids)
        logger.warning(f"Using only valid categories: {category_ids}")

    # Return matching categories in order
    selected_categories = [
        cat for cat in all_categories
        if cat['id'] in category_ids
    ]

    logger.info(f"Loaded {len(selected_categories)}/{len(category_ids)} categories: {[c['id'] for c in selected_categories]}")
    return selected_categories


def get_all_categories() -> List[Dict[str, Any]]:
    """
    Get all available categories from configuration.

    Returns:
        List of all 9+ category dictionaries
    """
    config_path = Path("./config/categories.json")
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    categories = config.get('categories', [])
    logger.info(f"Loaded all {len(categories)} categories")
    return categories


def get_default_categories() -> List[Dict[str, Any]]:
    """
    Get the default categories configured for this company/use case.

    Returns:
        List of default category dictionaries
    """
    return load_categories(category_ids=None)


def get_category_by_id(category_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a single category by ID.

    Args:
        category_id: Category ID (e.g., "fintech_ai")

    Returns:
        Category dictionary or None if not found
    """
    config_path = Path("./config/categories.json")
    if not config_path.exists():
        return None

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    all_categories = config.get('categories', [])
    for cat in all_categories:
        if cat['id'] == category_id:
            logger.debug(f"Found category: {category_id}")
            return cat

    logger.warning(f"Category not found: {category_id}")
    return None


def list_all_category_ids() -> List[str]:
    """
    Get list of all available category IDs.

    Returns:
        List of category IDs like ["fintech_ai", "data_analytics", ...]
    """
    config_path = Path("./config/categories.json")
    if not config_path.exists():
        return []

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    categories = config.get('categories', [])
    ids = [cat['id'] for cat in categories]
    logger.debug(f"Available categories: {ids}")
    return ids


def get_company_context() -> Dict[str, Any]:
    """
    Get company context from configuration (used for evaluation context).

    Returns:
        Company context dictionary with keys like business, industry, focus_areas
    """
    config_path = Path("./config/categories.json")
    if not config_path.exists():
        logger.warning("Config file not found, returning empty company context")
        return {}

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    company_context = config.get('company_context', {})
    logger.debug(f"Company context: {company_context.get('business', 'N/A')}")
    return company_context


if __name__ == "__main__":
    # Test the loader
    print("\n" + "=" * 60)
    print("Testing Category Loader")
    print("=" * 60)

    # Test 1: Load default categories
    print("\n[Test 1] Load default categories:")
    try:
        defaults = get_default_categories()
        print(f"✓ Loaded {len(defaults)} default categories:")
        for cat in defaults:
            print(f"  - {cat['id']}: {cat['name']}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 2: Load all categories
    print("\n[Test 2] Load all categories:")
    try:
        all_cats = get_all_categories()
        print(f"✓ Loaded all {len(all_cats)} categories")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 3: Load specific categories
    print("\n[Test 3] Load specific categories (fintech_ai, llm_tech):")
    try:
        specific = load_categories(["fintech_ai", "llm_tech"])
        print(f"✓ Loaded {len(specific)} categories:")
        for cat in specific:
            print(f"  - {cat['id']}: {cat['name']}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 4: Get company context
    print("\n[Test 4] Get company context:")
    try:
        context = get_company_context()
        print(f"✓ Company: {context.get('business', 'N/A')}")
        print(f"  Industry: {context.get('industry', 'N/A')}")
        print(f"  Focus: {', '.join(context.get('focus_areas', []))}")
    except Exception as e:
        print(f"✗ Error: {e}")

    # Test 5: List all IDs
    print("\n[Test 5] List all category IDs:")
    try:
        ids = list_all_category_ids()
        print(f"✓ Available IDs ({len(ids)}):")
        for cid in ids:
            print(f"  - {cid}")
    except Exception as e:
        print(f"✗ Error: {e}")

    print("\n" + "=" * 60)
    print("Category Loader Tests Complete")
    print("=" * 60)
