"""
ACE-Planner Module

Decomposes user intent into structured query plans with sub-themes,
keywords, and entity lists for improved search targeting.

ACE = Agentic Content Explorer
"""

import json
from typing import List, Dict, Any, Optional
from loguru import logger

from utils.llm_client_enhanced import LLMClient


class ACEPlanner:
    """Plans and structures queries for content retrieval"""

    def __init__(
        self,
        llm_client: LLMClient = None,
        company_context: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize ACE-Planner

        Args:
            llm_client: LLM client instance (creates new if None)
            company_context: Company context for tailored planning
        """
        self.llm_client = llm_client or LLMClient()
        self.company_context = company_context or {}

        logger.info("ACE-Planner initialized")

    def plan_queries(
        self,
        user_input: str,
        categories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Decompose user intent into structured query plan

        Args:
            user_input: User's natural language input
            categories: Selected categories

        Returns:
            Dictionary with themes, keywords, and entities
        """
        logger.info("Planning queries for user input...")

        # Build planning prompt
        system_prompt = self._build_planning_prompt()
        user_message = self._build_planning_message(user_input, categories)

        try:
            # Get structured plan from LLM
            response = self.llm_client.chat_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.3
            )

            # Validate and enhance plan
            plan = self._validate_plan(response)

            logger.info(f"Generated plan with {len(plan['themes'])} themes")
            logger.debug(f"Plan: {json.dumps(plan, ensure_ascii=False, indent=2)}")

            return plan

        except Exception as e:
            logger.error(f"Failed to generate query plan: {e}")
            # Return fallback plan
            return self._create_fallback_plan(categories)

    def _build_planning_prompt(self) -> str:
        """Build system prompt for query planning"""

        context_info = ""
        if self.company_context:
            business = self.company_context.get('business', '')
            focus_areas = self.company_context.get('focus_areas', [])
            context_info = f"""
**公司背景**:
- 业务: {business}
- 关注领域: {', '.join(focus_areas)}

在规划查询时,请特别考虑与公司业务的相关性。
"""

        return f"""你是一位专业的信息检索规划专家,负责将用户需求分解为结构化的查询计划。
{context_info}
**任务**: 将用户关注的领域分解为2-4个具体的子主题(themes),并为每个主题生成:

1. **Must Keywords** (必须包含): 核心关键词,文章必须包含至少一个
2. **Should Keywords** (应该包含): 相关关键词,有助于提高相关性
3. **Not Keywords** (不应包含): 排除关键词,帮助过滤无关内容
4. **Entities** (实体列表): 相关的公司、产品、人物、机构名称

**关键词生成原则**:
- Must keywords: 高度特定,直接相关 (3-5个)
- Should keywords: 相关但不强制 (5-8个)
- Not keywords: 明确无关的主题 (2-4个)
- Entities: 具体名称,包括中英文 (5-10个)

**输出JSON格式**:
{{
  "themes": [
    {{
      "name": "主题名称",
      "description": "简短描述",
      "must_keywords": ["关键词1", "关键词2"],
      "should_keywords": ["相关词1", "相关词2"],
      "not_keywords": ["排除词1", "排除词2"],
      "entities": ["公司名", "产品名", "人名"]
    }}
  ],
  "global_entities": ["通用实体1", "通用实体2"],
  "time_priority": "recent"
}}

**示例** (输入: "我想了解智能风控和反欺诈"):
{{
  "themes": [
    {{
      "name": "智能风控技术",
      "description": "AI驱动的风险控制技术和方法",
      "must_keywords": ["风控", "风险控制", "信用评分", "风险评估"],
      "should_keywords": ["机器学习", "深度学习", "AI", "人工智能", "模型"],
      "not_keywords": ["股票", "投资", "理财"],
      "entities": ["蚂蚁集团", "微众银行", "京东数科", "FICO"]
    }},
    {{
      "name": "反欺诈技术",
      "description": "欺诈检测和防范技术",
      "must_keywords": ["反欺诈", "欺诈检测", "反作弊", "风险识别"],
      "should_keywords": ["异常检测", "行为分析", "图谱", "知识图谱"],
      "not_keywords": ["广告", "营销"],
      "entities": ["同盾科技", "DataVisor", "Feedzai"]
    }}
  ],
  "global_entities": ["央行", "PBOC", "银保监会", "金融科技"],
  "time_priority": "recent"
}}

请基于用户输入和选定的分类,生成合理的查询计划。"""

    def _build_planning_message(
        self,
        user_input: str,
        categories: List[Dict[str, Any]]
    ) -> str:
        """Build user message for planning"""

        category_info = []
        for cat in categories:
            aliases = cat.get('aliases', [])
            category_info.append(f"- {cat['name']}: {', '.join(aliases[:5])}")

        category_text = "\n".join(category_info)

        return f"""请为以下用户需求生成查询计划:

**用户输入**: {user_input}

**选定的分类**:
{category_text}

请生成2-4个具体的子主题,每个主题包含must/should/not关键词和相关实体。以JSON格式返回。"""

    def _validate_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and normalize query plan"""

        # Ensure required fields exist
        if 'themes' not in plan:
            raise ValueError("Plan missing 'themes' field")

        # Normalize themes
        validated_themes = []
        for theme in plan.get('themes', []):
            validated_theme = {
                'name': theme.get('name', '未命名主题'),
                'description': theme.get('description', ''),
                'must_keywords': theme.get('must_keywords', []),
                'should_keywords': theme.get('should_keywords', []),
                'not_keywords': theme.get('not_keywords', []),
                'entities': theme.get('entities', [])
            }

            # Ensure all keyword lists are actually lists
            for key in ['must_keywords', 'should_keywords', 'not_keywords', 'entities']:
                if not isinstance(validated_theme[key], list):
                    validated_theme[key] = []

            validated_themes.append(validated_theme)

        # Build validated plan
        validated_plan = {
            'themes': validated_themes,
            'global_entities': plan.get('global_entities', []),
            'time_priority': plan.get('time_priority', 'recent')
        }

        return validated_plan

    def _create_fallback_plan(
        self,
        categories: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create fallback plan if LLM planning fails"""

        logger.warning("Creating fallback query plan from categories")

        themes = []
        global_entities = []

        for cat in categories:
            theme = {
                'name': cat['name'],
                'description': f"基于{cat['name']}分类的文章",
                'must_keywords': cat.get('aliases', [])[:3],  # Use first 3 aliases as must keywords
                'should_keywords': cat.get('aliases', [])[3:8],  # Next 5 as should keywords
                'not_keywords': [],
                'entities': []
            }
            themes.append(theme)

        fallback_plan = {
            'themes': themes,
            'global_entities': global_entities,
            'time_priority': 'recent'
        }

        return fallback_plan

    def summarize_plan(self, plan: Dict[str, Any]) -> str:
        """Generate human-readable summary of query plan"""

        summary_lines = []
        summary_lines.append(f"查询计划包含 {len(plan['themes'])} 个主题:\n")

        for i, theme in enumerate(plan['themes'], 1):
            summary_lines.append(f"{i}. {theme['name']}")
            summary_lines.append(f"   描述: {theme['description']}")
            summary_lines.append(f"   必须关键词: {', '.join(theme['must_keywords'][:5])}")
            if theme['entities']:
                summary_lines.append(f"   相关实体: {', '.join(theme['entities'][:5])}")
            summary_lines.append("")

        if plan['global_entities']:
            summary_lines.append(f"全局实体: {', '.join(plan['global_entities'][:10])}")

        return "\n".join(summary_lines)


if __name__ == "__main__":
    # Test ACE-Planner
    from pathlib import Path

    planner = ACEPlanner()

    # Sample categories
    sample_categories = [
        {
            'id': 'fintech_ai',
            'name': '金融科技AI应用',
            'aliases': ['金融AI', 'fintech', '智能风控', '信贷', '反欺诈']
        },
        {
            'id': 'data_analytics',
            'name': '数据分析',
            'aliases': ['数据', '分析', '大数据', '数据挖掘', '预测分析']
        }
    ]

    # Test planning
    user_input = "我想了解智能风控和反欺诈技术的最新进展"
    plan = planner.plan_queries(user_input, sample_categories)

    print("\n" + "=" * 60)
    print("Query Plan Generated")
    print("=" * 60)
    print(planner.summarize_plan(plan))
    print("\n" + "=" * 60)
    print("Full Plan (JSON):")
    print("=" * 60)
    print(json.dumps(plan, ensure_ascii=False, indent=2))
