"""
Category Selector Module

Interprets user preferences and maps them to structured categories.
Uses Claude to understand natural language input like "我想了解大模型和AI应用".

Features:
- Natural language understanding in Chinese and English
- Smart category matching with aliases
- Priority weighting for matched categories
- Keyword extraction for focused filtering
- Graceful fallback to defaults on errors
"""

import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from loguru import logger

from utils.llm_client_enhanced import LLMClient
from utils.cache_manager import CacheManager


class CategorySelector:
    """Selects and prioritizes news categories based on user input"""

    def __init__(
        self,
        categories_config: str = "./config/categories.json",
        llm_client: LLMClient = None,
        cache_manager: CacheManager = None,
        enable_caching: bool = True,
        enable_ace_planner: bool = True
    ):
        """
        Initialize category selector

        Args:
            categories_config: Path to categories configuration file
            llm_client: LLM client instance (creates new if None)
            cache_manager: Cache manager for caching selections
            enable_caching: Enable caching of category selections
            enable_ace_planner: Enable ACE-Planner for query decomposition
        """
        self.categories_config = Path(categories_config)
        self.cache_manager = cache_manager
        self.enable_caching = enable_caching
        self.enable_ace_planner = enable_ace_planner

        # Initialize LLM client with caching if available
        if llm_client:
            self.llm_client = llm_client
        else:
            self.llm_client = LLMClient(
                enable_caching=enable_caching,
                cache_manager=cache_manager
            )

        # Load categories
        with open(self.categories_config, 'r', encoding='utf-8') as f:
            config = json.load(f)
            self.categories = config['categories']
            self.default_categories = config['default_categories']
            self.company_context = config.get('company_context', {})

        # Initialize ACE-Planner if enabled
        self.ace_planner = None
        if self.enable_ace_planner:
            from modules.ace_planner import ACEPlanner
            self.ace_planner = ACEPlanner(
                llm_client=self.llm_client,
                company_context=self.company_context
            )
            logger.info("ACE-Planner enabled for enhanced query planning")

        # Build category lookup maps for faster matching
        self._build_lookup_maps()

        logger.info(f"Loaded {len(self.categories)} categories")

    def _build_lookup_maps(self):
        """Build lookup maps for efficient category matching"""
        # Map category IDs to full category objects
        self.id_to_category = {cat['id']: cat for cat in self.categories}

        # Map aliases to category IDs
        self.alias_to_id = {}
        for cat in self.categories:
            # Add category name
            self.alias_to_id[cat['name'].lower()] = cat['id']
            # Add all aliases
            for alias in cat['aliases']:
                self.alias_to_id[alias.lower()] = cat['id']

    def select_categories(
        self,
        user_input: str = None,
        use_defaults: bool = False,
        max_categories: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Select categories based on user input

        Args:
            user_input: Natural language input (e.g., "我想了解大模型和AI应用")
            use_defaults: Use default categories if True
            max_categories: Maximum number of categories to select (default: 5)

        Returns:
            List of selected category dictionaries with enriched information:
            - All original category fields (id, name, aliases, priority, description)
            - 'selection_priority': Priority for this selection (1-10)
            - 'keywords': Specific keywords for filtering
            - 'rationale': Why this category was selected
        """
        if use_defaults or not user_input:
            logger.info("Using default categories")
            return self._get_default_categories()

        # Strip and validate input
        user_input = user_input.strip()
        if not user_input:
            logger.info("Empty input, using defaults")
            return self._get_default_categories()

        logger.info(f"Selecting categories from input: '{user_input}'")

        # Try simple matching first (faster, no API call)
        simple_match = self._try_simple_match(user_input)
        if simple_match:
            logger.info(f"Simple match found: {[c['name'] for c in simple_match]}")
            return simple_match[:max_categories]

        # Use Claude for complex/ambiguous input
        try:
            response = self._select_with_claude(user_input, max_categories)

            if not response or not response.get('categories'):
                logger.warning("Claude returned empty categories, using defaults")
                return self._get_default_categories()

            # Enrich category data
            selected_categories = self._enrich_categories(response['categories'])

            # Use ACE-Planner to generate detailed query plan
            if self.ace_planner and selected_categories:
                try:
                    logger.info("Generating query plan with ACE-Planner...")
                    query_plan = self.ace_planner.plan_queries(user_input, selected_categories)

                    # Attach query plan to each category
                    for cat in selected_categories:
                        cat['query_plan'] = query_plan

                    logger.info(f"Query plan generated with {len(query_plan['themes'])} themes")
                except Exception as e:
                    logger.warning(f"ACE-Planner failed, continuing without query plan: {e}")

            logger.info(
                f"Selected {len(selected_categories)} categories: "
                f"{[c['name'] for c in selected_categories]}"
            )

            return selected_categories[:max_categories]

        except Exception as e:
            logger.error(f"Failed to select categories: {e}")
            logger.info("Falling back to default categories")
            return self._get_default_categories()

    def _try_simple_match(self, user_input: str) -> Optional[List[Dict[str, Any]]]:
        """
        Try to match categories using simple keyword matching

        Returns:
            List of matched categories or None if no clear match
        """
        input_lower = user_input.lower()
        matched_ids = set()

        # Check each alias
        for alias, cat_id in self.alias_to_id.items():
            if alias in input_lower:
                matched_ids.add(cat_id)

        # Only return if we have clear matches
        if matched_ids:
            categories = [self.id_to_category[cat_id].copy() for cat_id in matched_ids]
            # Add default priority
            for cat in categories:
                cat['selection_priority'] = cat.get('priority', 5)
                cat['keywords'] = []
                cat['rationale'] = f"直接匹配关键词"

            # Sort by original priority
            categories.sort(key=lambda x: x['priority'], reverse=True)
            return categories

        return None

    def _select_with_claude(
        self,
        user_input: str,
        max_categories: int
    ) -> Dict[str, Any]:
        """
        Use Claude to select categories from user input

        Returns:
            Response dictionary with categories and metadata
        """
        system_prompt = self._build_system_prompt()
        user_message = self._build_user_message(user_input, max_categories)

        response = self.llm_client.chat_structured(
            system_prompt=system_prompt,
            user_message=user_message,
            temperature=0.2
        )

        return response

    def _enrich_categories(
        self,
        claude_categories: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich Claude's category selection with full category data

        Args:
            claude_categories: Categories from Claude response

        Returns:
            Enriched category dictionaries
        """
        enriched = []

        for claude_cat in claude_categories:
            cat_id = claude_cat.get('id')
            if cat_id not in self.id_to_category:
                logger.warning(f"Unknown category ID: {cat_id}")
                continue

            # Get full category data
            full_cat = self.id_to_category[cat_id].copy()

            # Add Claude's enrichments
            full_cat['selection_priority'] = claude_cat.get('priority', 5)
            full_cat['keywords'] = claude_cat.get('keywords', [])
            full_cat['rationale'] = claude_cat.get('rationale', '')

            enriched.append(full_cat)

        # Sort by selection priority
        enriched.sort(key=lambda x: x['selection_priority'], reverse=True)

        return enriched

    def _get_default_categories(self) -> List[Dict[str, Any]]:
        """Get default categories with enriched data"""
        defaults = []
        for cat in self.categories:
            if cat['id'] in self.default_categories:
                enriched = cat.copy()
                enriched['selection_priority'] = cat.get('priority', 5)
                enriched['keywords'] = []
                enriched['rationale'] = "默认类别"
                defaults.append(enriched)

        # Sort by priority
        defaults.sort(key=lambda x: x['priority'], reverse=True)
        return defaults

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Get all available categories"""
        return self.categories

    def get_category_by_id(self, category_id: str) -> Optional[Dict[str, Any]]:
        """Get a category by its ID"""
        return self.id_to_category.get(category_id)

    def _build_system_prompt(self) -> str:
        """Build system prompt for Claude based on PROMPTS.md template"""
        # Build category descriptions
        categories_list = []
        for i, cat in enumerate(self.categories, 1):
            aliases_str = ", ".join(cat['aliases'])
            categories_list.append(
                f"{i}. {cat['name']} (ID: {cat['id']}) - {aliases_str}\n"
                f"   {cat['description']}"
            )

        categories_desc = "\n".join(categories_list)

        return f"""You are a category classification expert for AI industry news. Your task is to interpret user preferences and map them to specific AI news categories.

Available categories:
{categories_desc}

Your task:
1. Analyze the user's input (may be in Chinese or English)
2. Identify which categories match their interests
3. Assign priority weights (1-10, where 10 is highest)
4. Extract specific keywords or topics to focus on

Return a JSON structure with selected categories and priority weights.

IMPORTANT: Return ONLY valid JSON in this exact format:
{{
  "categories": [
    {{
      "id": "category_id",
      "name": "分类名称",
      "priority": 8,
      "keywords": ["关键词1", "关键词2"],
      "rationale": "为什么选择这个类别（用中文）"
    }}
  ],
  "focus_areas": ["具体主题1", "具体主题2"]
}}

Rules:
- Match user input to category names, IDs, and aliases
- Select 1-3 categories (at most 5 for very broad requests)
- Prioritize exact matches and user-mentioned keywords
- If input is vague, select 2-3 most generally important categories
- Always include rationale in Chinese
- Extract specific keywords mentioned by the user"""

    def _build_user_message(self, user_input: str, max_categories: int) -> str:
        """Build user message for Claude"""
        return f"""User preference: {user_input}

Based on this input, determine:
1. Which 1-{max_categories} categories are most relevant
2. Priority weight for each (1-10 scale, where 10 is highest priority)
3. Specific keywords or topics to focus on within each category

Return the JSON response following the format specified in the system prompt."""


if __name__ == "__main__":
    """Test category selector with various inputs"""
    import sys

    print("=" * 60)
    print("Testing Category Selector Module")
    print("=" * 60)

    selector = CategorySelector(enable_caching=False)

    # Test scenarios
    test_cases = [
        ("我想了解大模型和AI应用的最新动态", "Chinese - clear intent"),
        ("LLM developments and policy changes", "English - clear intent"),
        ("最近AI有什么新闻", "Chinese - vague"),
        ("tell me about AI", "English - vague"),
        ("大模型", "Single keyword"),
        ("GPT, Claude, 政策", "Mixed keywords"),
        ("", "Empty input"),
    ]

    for i, (user_input, description) in enumerate(test_cases, 1):
        print(f"\n{'─' * 60}")
        print(f"Test {i}: {description}")
        print(f"Input: '{user_input}'")
        print(f"{'─' * 60}")

        try:
            result = selector.select_categories(user_input) if user_input else selector.select_categories(use_defaults=True)

            print(f"✓ Selected {len(result)} categories:")
            for cat in result:
                print(f"  • {cat['name']} (ID: {cat['id']})")
                print(f"    Priority: {cat.get('selection_priority', 'N/A')}")
                if cat.get('keywords'):
                    print(f"    Keywords: {', '.join(cat['keywords'])}")
                if cat.get('rationale'):
                    print(f"    Rationale: {cat['rationale']}")

        except Exception as e:
            print(f"✗ Error: {e}")
            import traceback
            traceback.print_exc()

    # Test defaults
    print(f"\n{'═' * 60}")
    print("Test: Default Categories")
    print(f"{'═' * 60}")
    defaults = selector.select_categories(use_defaults=True)
    print(f"Default categories ({len(defaults)}):")
    for cat in defaults:
        print(f"  • {cat['name']} (priority: {cat['priority']})")

    # Print all available categories
    print(f"\n{'═' * 60}")
    print("All Available Categories")
    print(f"{'═' * 60}")
    all_cats = selector.get_all_categories()
    for cat in all_cats:
        aliases = ", ".join(cat['aliases'][:3])
        print(f"  • {cat['name']} (ID: {cat['id']})")
        print(f"    Aliases: {aliases}...")
        print(f"    Priority: {cat['priority']}")

    print(f"\n{'═' * 60}")
    print("✅ Testing Complete")
    print(f"{'═' * 60}\n")
