#!/usr/bin/env python3
"""
CLI Chatbox Interface for Article Q&A

Interactive command-line interface for asking questions about briefing articles.
Uses the ArticleQAAgent with ACE for multi-turn conversations.

Usage:
    python3 chatbox_cli.py [--week 43] [--articles-file path]
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from argparse import ArgumentParser
from typing import List, Dict, Any, Optional

from modules.article_qa_agent import ArticleQAAgent
from utils.logger import setup_logger
from loguru import logger


class ChatboxCLI:
    """Interactive CLI for article Q&A"""

    def __init__(self, articles: List[Dict[str, Any]]):
        """Initialize chatbox with articles"""
        self.agent = ArticleQAAgent(articles_db=articles)
        self.articles = articles
        logger.info(f"Chatbox initialized with {len(articles)} articles")

    def run(self):
        """Run interactive chatbox loop"""
        print("\n" + "="*70)
        print("📰 AI 行业周刊 - 文章智能问答系统 (Article Q&A Chatbox)")
        print("="*70)
        print("\n欢迎使用文章智能问答系统。您可以提出任何关于本周文章的问题。")
        print("输入 'quit' 或 'exit' 退出，'help' 获取帮助，'summary' 查看对话摘要。\n")

        # Show available topics
        self._show_available_topics()

        # Main loop
        turn_count = 0
        while True:
            try:
                # Get user input
                user_input = input("\n🤔 您的问题: ").strip()

                # Handle special commands
                if user_input.lower() in ['quit', 'exit', 'q']:
                    self._exit_chatbox()
                    break
                elif user_input.lower() == 'help':
                    self._show_help()
                    continue
                elif user_input.lower() == 'summary':
                    self._show_summary()
                    continue
                elif user_input.lower() == 'clear':
                    self.agent.clear_history()
                    print("✅ 对话历史已清除")
                    continue
                elif not user_input:
                    continue

                # Process question
                turn_count += 1
                print(f"\n⏳ 正在处理您的问题 (第{turn_count}轮)...\n")

                response = self.agent.answer_question(user_input)

                if response['success']:
                    self._display_response(response, turn_count)
                else:
                    print(f"❌ 错误: {response.get('error', '未知错误')}")
                    print(f"回复: {response['answer']}\n")

            except KeyboardInterrupt:
                self._exit_chatbox()
                break
            except Exception as e:
                logger.error(f"Chatbox error: {e}")
                print(f"\n❌ 处理错误: {e}\n")

    def _show_available_topics(self):
        """Display available article topics"""
        print("📚 本周可讨论的文章:")
        print("-" * 70)

        categories = {}
        for i, article in enumerate(self.articles, 1):
            cat = article.get('categories', ['未分类'])[0]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(f"{i}. {article.get('title', '未知')[:60]}")

        for category, articles in categories.items():
            print(f"\n🏷️  {category}:")
            for article in articles[:3]:  # Show first 3 per category
                print(f"   • {article}")
            if len(articles) > 3:
                print(f"   ... 以及 {len(articles) - 3} 篇更多文章")

        print("\n" + "-" * 70)
        print(f"总共: {len(self.articles)} 篇文章")

    def _display_response(self, response: Dict[str, Any], turn: int):
        """Display agent response"""
        print("📄 回复:")
        print("-" * 70)
        print(response['answer'])
        print("-" * 70)

        # Show referenced articles
        if response['referenced_articles']:
            print(f"\n📎 引用的文章 ({len(response['referenced_articles'])} 篇):")
            for article_title in response['referenced_articles']:
                # Find article URL
                for article in self.articles:
                    if article.get('title') == article_title:
                        url = article.get('url', 'N/A')
                        print(f"   • {article_title}")
                        print(f"     🔗 {url}\n")
                        break

        print(f"✅ 已处理 - 转数: {turn}, 文章数: {response['articles_count']}")

    def _show_summary(self):
        """Show conversation summary"""
        summary = self.agent.get_conversation_summary()
        print("\n" + "="*70)
        print("📊 对话摘要")
        print("="*70)
        print(f"总轮数: {summary['total_turns']}")
        print(f"总消息数: {summary['total_messages']}")
        print(f"涉及话题数: {summary['topics_discussed']}")
        if summary['articles_referenced']:
            print(f"\n引用的文章:")
            for article_title in summary['articles_referenced'][:10]:
                print(f"  • {article_title}")
        print("="*70)

    def _show_help(self):
        """Show help message"""
        print("\n" + "="*70)
        print("💡 使用帮助")
        print("="*70)
        print("""
可用命令:
  help        - 显示此帮助信息
  summary     - 显示对话摘要
  clear       - 清除对话历史
  quit/exit   - 退出聊天

问题示例:
  "第一篇文章讲的是什么?"
  "这些文章中最重要的发现是什么?"
  "GPT-5和Claude 3.5有什么区别?"
  "这些变化对我们的企业意味着什么?"
  "哪些文章涉及金融应用?"
  "请总结本周的关键趋势"

提示:
  • 您可以问一个问题多次,每次会获得基于之前对话的上下文的回复
  • 系统会自动找到相关文章并引用源材料
  • 使用清晰、具体的语言提出问题以获得最佳结果
""")
        print("="*70)

    def _exit_chatbox(self):
        """Exit chatbox"""
        summary = self.agent.get_conversation_summary()
        print("\n" + "="*70)
        print("👋 再见!")
        print("="*70)
        print(f"您进行了 {summary['total_turns']} 轮对话,讨论了 {summary['topics_discussed']} 个话题。")
        print("感谢使用 AI 行业周刊智能问答系统!\n")


def load_articles(articles_file: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load articles from cache or file"""
    if articles_file and Path(articles_file).exists():
        logger.info(f"Loading articles from {articles_file}")
        with open(articles_file, encoding='utf-8') as f:
            data = json.load(f)
            return data.get('articles', [])

    # Try to load from default cache location
    cache_dir = Path("./data/cache/article_contexts")
    if cache_dir.exists():
        # Get most recent cache file
        cache_files = sorted(cache_dir.glob("*.json"), reverse=True)
        if cache_files:
            latest_file = cache_files[0]
            logger.info(f"Loading articles from {latest_file}")
            with open(latest_file, encoding='utf-8') as f:
                data = json.load(f)
                articles = data.get('articles', [])
                if articles:
                    return articles

    # Fallback: create sample articles for testing
    logger.warning("No cached articles found, creating sample articles for testing")
    return create_sample_articles()


def create_sample_articles() -> List[Dict[str, Any]]:
    """Create sample articles for testing"""
    return [
        {
            "title": "AI PB: A Grounded Generative Agent for Personalized Investment Insight",
            "source": "ArXiv",
            "url": "https://arxiv.org/abs/2510.20099",
            "categories": ["金融AI应用"],
            "paraphrased_content": """一项新研究介绍了AI PB系统,这是一个为个人投资者提供个性化投资洞察的生成式AI代理。该系统结合了大语言模型和金融数据分析能力,能够根据投资者的个人情况提供定制化的投资建议。

系统通过分析市场数据、经济指标和历史趋势,为投资者生成具体的投资决策建议。这项研究表明,AI在个性化金融建议领域的应用已经达到了可实用的阶段。

该研究对金融科技行业具有重要意义,表明AI可以显著提升个人投资者的决策质量和效率。""",
            "published_date": "2025-10-20"
        },
        {
            "title": "Agentic AI in Finance: Opportunities and Challenges for Indonesia",
            "source": "Towards Data Science",
            "url": "https://towardsdatascience.com/agentic-ai-in-finance-opportunities-and-challenges-for-indonesia/",
            "categories": ["金融AI应用", "新兴市场"],
            "paraphrased_content": """该文章探讨了代理AI在金融领域的应用机遇和挑战,特别是对于印尼这样的发展中市场。代理AI系统能够自主执行复杂的金融任务,包括投资组合管理、风险评估和客户服务。

印尼作为东南亚第一大经济体,在金融科技创新上具有巨大潜力。该文章指出,代理AI可以帮助印尼建立现代化的金融体系,特别是为无银行账户人群提供金融服务。

该分析对亚洲市场的金融AI发展具有参考意义,表明不同地区的金融AI应用会有不同的优先级和挑战。""",
            "published_date": "2025-10-21"
        },
        {
            "title": "The Hidden Curriculum of Data Science Interviews",
            "source": "KDnuggets",
            "url": "https://www.kdnuggets.com/the-hidden-curriculum-of-data-science-interviews-what-companies-really-test",
            "categories": ["数据科学职业"],
            "paraphrased_content": """这篇文章深入探讨了数据科学面试背后的真实需求。企业在数据科学面试中究竟在测试什么?不仅仅是算法知识和编程能力,更重要的是候选人解决实际业务问题的能力、沟通能力和产品思维。

文章指出,顶级科技公司的数据科学面试越来越关注与业务对齐的能力,包括如何设计实验、解释结果和推动组织变革。这反映了数据科学角色的演变,从纯技术走向更多的战略参与。

对求职者来说,这提示了在准备数据科学面试时应该关注的方向,以及行业对数据科学专业人才的实际期望。""",
            "published_date": "2025-10-22"
        }
    ]


def main():
    """Main entry point"""
    parser = ArgumentParser(description="CLI Chatbox for Article Q&A")
    parser.add_argument("--articles-file", help="Path to articles JSON file")
    parser.add_argument("--week", help="Week to load (for future use)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Setup logging
    setup_logger(level="DEBUG" if args.debug else "INFO")

    # Load articles
    articles = load_articles(args.articles_file)

    if not articles:
        print("❌ 无法加载文章,程序退出。")
        sys.exit(1)

    print(f"✅ 成功加载 {len(articles)} 篇文章\n")

    # Run chatbox
    chatbox = ChatboxCLI(articles)
    chatbox.run()


if __name__ == "__main__":
    main()
