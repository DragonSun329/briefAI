"""
Context Provider Module - Generate company and technology context for CEO briefings

Provides concise context (150-200 chars) for companies and technologies mentioned in articles:
- Company background (公司背景): Who they are, what they do
- Business model (业务模式): Their core business and focus
- Technology principles (技术原理): Simplified explanation of key technology

Context is cached in SQLite for efficient reuse across weekly reports.
"""

from typing import Dict, List, Optional, Tuple
import sqlite3
import json
from pathlib import Path
from datetime import datetime
from loguru import logger
import hashlib

from utils.llm_client_enhanced import LLMClient


class ContextProvider:
    """Generate and cache company/technology context for CEO briefings"""

    # Context database path
    CONTEXT_DB_PATH = "./data/context_cache.db"

    # Character limits for context sections
    CONTEXT_COMPANY_MAX = 200       # Company background: 150-200 chars
    CONTEXT_TECH_MAX = 200           # Technology principles: 150-200 chars

    # Cache validity: 30 days
    CACHE_VALIDITY_DAYS = 30

    def __init__(self, llm_client: LLMClient = None):
        """
        Initialize context provider

        Args:
            llm_client: LLM client for generating context via Claude
        """
        self.llm_client = llm_client or LLMClient()
        self.db_path = Path(self.CONTEXT_DB_PATH)

        # Initialize database
        self._init_database()
        logger.info("Context provider initialized")

    def _init_database(self) -> None:
        """Initialize SQLite database for context caching"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Create contexts table if not exists
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS company_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT UNIQUE NOT NULL,
            company_hash TEXT UNIQUE NOT NULL,
            company_background TEXT NOT NULL,
            business_model TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create technology contexts table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS technology_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tech_name TEXT UNIQUE NOT NULL,
            tech_hash TEXT UNIQUE NOT NULL,
            company_name TEXT,
            tech_principles TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create article context mapping (links article to company/tech contexts used)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS article_context_mapping (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            article_id TEXT NOT NULL,
            company_names TEXT,
            tech_names TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()
        conn.close()
        logger.debug("Context database initialized")

    def _get_hash(self, text: str) -> str:
        """Generate hash of text for unique identification"""
        return hashlib.md5(text.encode()).hexdigest()

    def _is_cache_valid(self, updated_at: str) -> bool:
        """Check if cached context is still valid (within 30 days)"""
        from datetime import datetime, timedelta

        try:
            updated_time = datetime.fromisoformat(updated_at)
            age_days = (datetime.now() - updated_time).days
            return age_days < self.CACHE_VALIDITY_DAYS
        except:
            return False

    def get_company_context(self, company_name: str, force_refresh: bool = False) -> Optional[Dict[str, str]]:
        """
        Get or generate company context

        Args:
            company_name: Name of the company
            force_refresh: If True, regenerate context even if cached

        Returns:
            Dictionary with 'background' and 'business_model' keys, or None

        Example:
            {
                'background': 'Anthropic是一家创立于2021年的AI安全公司...',
                'business_model': '通过API销售Claude模型，按token计费...'
            }
        """
        if not company_name or not isinstance(company_name, str):
            return None

        company_name = company_name.strip()

        # Check cache first
        if not force_refresh:
            cached = self._get_from_cache(table='company_contexts', name=company_name)
            if cached:
                return {
                    'background': cached.get('company_background', ''),
                    'business_model': cached.get('business_model', '')
                }

        # Generate new context via LLM
        context = self._generate_company_context(company_name)
        if context:
            # Cache it
            self._save_to_cache(
                table='company_contexts',
                data={
                    'company_name': company_name,
                    'company_hash': self._get_hash(company_name),
                    'company_background': context['background'],
                    'business_model': context.get('business_model', '')
                }
            )
            return context

        return None

    def get_technology_context(
        self,
        tech_name: str,
        company_name: Optional[str] = None,
        force_refresh: bool = False
    ) -> Optional[str]:
        """
        Get or generate technology context (principles explanation)

        Args:
            tech_name: Name of the technology
            company_name: Associated company (optional)
            force_refresh: If True, regenerate even if cached

        Returns:
            Simplified explanation of technology principles (150-200 chars), or None

        Example:
            "Constitutional AI通过预定义的安全准则让模型自我评估和改进，
             无需人工反复标注，大幅提高了训练效率和安全性。"
        """
        if not tech_name or not isinstance(tech_name, str):
            return None

        tech_name = tech_name.strip()

        # Check cache first
        if not force_refresh:
            cached = self._get_from_cache(table='technology_contexts', name=tech_name)
            if cached:
                return cached.get('tech_principles', '')

        # Generate new context via LLM
        principles = self._generate_tech_context(tech_name, company_name)
        if principles:
            # Cache it
            self._save_to_cache(
                table='technology_contexts',
                data={
                    'tech_name': tech_name,
                    'tech_hash': self._get_hash(tech_name),
                    'company_name': company_name or '',
                    'tech_principles': principles
                }
            )
            return principles

        return None

    def get_article_context(self, article: Dict) -> Dict[str, any]:
        """
        Get all context needed for an article (companies + technologies)

        Args:
            article: Article dictionary with 'title', 'content', 'entities'

        Returns:
            Dictionary with company and technology contexts

        Example:
            {
                'companies': {
                    'Anthropic': {...},
                    'OpenAI': {...}
                },
                'technologies': {
                    'Constitutional AI': '...',
                    'Large Language Model': '...'
                }
            }
        """
        article_id = article.get('id', '')
        result = {
            'companies': {},
            'technologies': {},
            'companies_list': [],  # Simple list for iteration
            'technologies_list': []
        }

        # Extract company names from entities
        entities = article.get('entities', {})
        company_entities = entities.get('companies', [])

        # Get context for each company
        for company_name in company_entities:
            context = self.get_company_context(company_name)
            if context:
                result['companies'][company_name] = context
                result['companies_list'].append({
                    'name': company_name,
                    'background': context['background'],
                    'business_model': context.get('business_model', '')
                })

        # Extract technology mentions from entities
        tech_entities = entities.get('technologies', [])

        for tech_name in tech_entities:
            # Find primary company for this tech
            company_name = None
            for comp in company_entities:
                if comp.lower() in tech_name.lower():
                    company_name = comp
                    break

            context = self.get_technology_context(tech_name, company_name)
            if context:
                result['technologies'][tech_name] = context
                result['technologies_list'].append({
                    'name': tech_name,
                    'company': company_name,
                    'principles': context
                })

        # Save mapping for tracking
        if company_entities or tech_entities:
            self._save_article_mapping(
                article_id,
                company_entities,
                tech_entities
            )

        return result

    def _generate_company_context(self, company_name: str) -> Optional[Dict[str, str]]:
        """Generate company context via LLM"""
        if not company_name:
            return None

        try:
            prompt = f"""为CEO的AI产业周刊提供关于{company_name}的背景信息。

请用简洁的中文生成两个部分（每部分150-200个汉字）:

1. 【公司背景】: 公司是什么,成立时间,创始人背景,核心使命
2. 【业务模式】: 主要收入来源,客户群体,收费模式

格式要求:
- 简明扼要，避免冗长
- 数据准确，不编造数据
- 面向CEO，专业但易懂
- 不要列表格式，全段落格式

输出格式:
公司背景：[150-200字]

业务模式：[150-200字]"""

            response = self.llm_client.call_claude(
                prompt=prompt,
                temperature=0.3,
                max_tokens=400
            )

            if not response:
                logger.warning(f"Failed to generate context for {company_name}")
                return None

            # Parse response
            lines = response.strip().split('\n')
            background = ""
            business_model = ""

            for i, line in enumerate(lines):
                if '公司背景' in line or '背景' in line:
                    # Get text after the colon
                    parts = line.split('：')
                    if len(parts) > 1:
                        background = parts[1].strip()
                    # Continue collecting until next section
                    if i + 1 < len(lines) and '业务模式' not in lines[i + 1]:
                        background += lines[i + 1].strip()
                elif '业务模式' in line or '模式' in line:
                    parts = line.split('：')
                    if len(parts) > 1:
                        business_model = parts[1].strip()
                    if i + 1 < len(lines):
                        business_model += lines[i + 1].strip()

            if not background or not business_model:
                # Fallback: split response in half
                mid = len(response) // 2
                background = response[:mid]
                business_model = response[mid:]

            return {
                'background': background[:self.CONTEXT_COMPANY_MAX],
                'business_model': business_model[:self.CONTEXT_COMPANY_MAX]
            }

        except Exception as e:
            logger.error(f"Error generating company context for {company_name}: {e}")
            return None

    def _generate_tech_context(self, tech_name: str, company_name: Optional[str] = None) -> Optional[str]:
        """Generate technology context via LLM"""
        if not tech_name:
            return None

        try:
            company_context = f"(由{company_name}开发)" if company_name else ""

            prompt = f"""为CEO的AI产业周刊解释{tech_name}{company_context}的技术原理。

请用简洁的中文（150-200个汉字）解释:
- 这项技术是什么
- 核心工作原理
- 相比传统方法的优势或创新点
- 实际应用场景

要求:
- 避免过度技术化，CEO能理解
- 不要列表，全段落格式
- 精准准确，不编造信息
- 突出对业务的实际意义"""

            response = self.llm_client.call_claude(
                prompt=prompt,
                temperature=0.3,
                max_tokens=300
            )

            if response:
                return response.strip()[:self.CONTEXT_TECH_MAX]

            logger.warning(f"Failed to generate context for {tech_name}")
            return None

        except Exception as e:
            logger.error(f"Error generating tech context for {tech_name}: {e}")
            return None

    def _get_from_cache(self, table: str, name: str) -> Optional[Dict]:
        """Get context from cache"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            name_col = 'company_name' if table == 'company_contexts' else 'tech_name'

            cursor.execute(f"""
            SELECT * FROM {table} WHERE {name_col} = ?
            """, (name,))

            row = cursor.fetchone()
            conn.close()

            if row:
                row_dict = dict(row)
                # Check if cache is still valid
                if self._is_cache_valid(row_dict.get('updated_at', '')):
                    logger.debug(f"Cache hit for {name}")
                    return row_dict
                else:
                    logger.debug(f"Cache expired for {name}")

            return None
        except Exception as e:
            logger.error(f"Error reading from cache: {e}")
            return None

    def _save_to_cache(self, table: str, data: Dict) -> bool:
        """Save context to cache"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            if table == 'company_contexts':
                cursor.execute("""
                INSERT OR REPLACE INTO company_contexts
                (company_name, company_hash, company_background, business_model, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    data.get('company_name'),
                    data.get('company_hash'),
                    data.get('company_background'),
                    data.get('business_model')
                ))

            elif table == 'technology_contexts':
                cursor.execute("""
                INSERT OR REPLACE INTO technology_contexts
                (tech_name, tech_hash, company_name, tech_principles, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (
                    data.get('tech_name'),
                    data.get('tech_hash'),
                    data.get('company_name'),
                    data.get('tech_principles')
                ))

            conn.commit()
            conn.close()

            logger.debug(f"Cached {data.get('company_name') or data.get('tech_name')}")
            return True

        except Exception as e:
            logger.error(f"Error saving to cache: {e}")
            return False

    def _save_article_mapping(
        self,
        article_id: str,
        companies: List[str],
        technologies: List[str]
    ) -> bool:
        """Track which contexts were used for an article"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cursor.execute("""
            INSERT INTO article_context_mapping (article_id, company_names, tech_names)
            VALUES (?, ?, ?)
            """, (
                article_id,
                json.dumps(companies),
                json.dumps(technologies)
            ))

            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error(f"Error saving article mapping: {e}")
            return False

    def get_cache_stats(self) -> Dict:
        """Get statistics about cached contexts"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            # Count companies
            cursor.execute("SELECT COUNT(*) FROM company_contexts")
            company_count = cursor.fetchone()[0]

            # Count technologies
            cursor.execute("SELECT COUNT(*) FROM technology_contexts")
            tech_count = cursor.fetchone()[0]

            # Count articles processed
            cursor.execute("SELECT COUNT(*) FROM article_context_mapping")
            article_count = cursor.fetchone()[0]

            conn.close()

            return {
                'cached_companies': company_count,
                'cached_technologies': tech_count,
                'articles_processed': article_count,
                'cache_path': str(self.db_path)
            }
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {}

    def clear_cache(self, older_than_days: int = 30) -> bool:
        """Clear old cached contexts"""
        try:
            conn = sqlite3.connect(str(self.db_path))
            cursor = conn.cursor()

            cutoff_date = f"datetime('now', '-{older_than_days} days')"

            cursor.execute(f"""
            DELETE FROM company_contexts WHERE updated_at < {cutoff_date}
            """)
            deleted_companies = cursor.rowcount

            cursor.execute(f"""
            DELETE FROM technology_contexts WHERE updated_at < {cutoff_date}
            """)
            deleted_techs = cursor.rowcount

            conn.commit()
            conn.close()

            logger.info(f"Cleared {deleted_companies} companies, {deleted_techs} technologies")
            return True
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return False
