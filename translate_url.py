#!/usr/bin/env python3
"""
URL Article Translator

Translates any article URL to Chinese using the article paraphraser module.
Can also fetch and extract content from web pages automatically.

Usage:
    python translate_url.py <URL>
    python translate_url.py <URL> --output translated_article.md
    python translate_url.py <URL> --format json
"""

import sys
import argparse
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger
import requests
from bs4 import BeautifulSoup

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.llm_client_enhanced import LLMClient
from utils.logger import setup_logger
from modules.article_paraphraser import ArticleParaphraser

# Load environment variables
load_dotenv()


class URLTranslator:
    """Translates articles from URLs to Chinese"""

    def __init__(self):
        """Initialize translator with LLM client"""
        self.llm_client = LLMClient()
        self.paraphraser = ArticleParaphraser(llm_client=self.llm_client)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })

    def fetch_article(self, url: str) -> dict:
        """
        Fetch article content from URL

        Args:
            url: Article URL to fetch

        Returns:
            Dictionary with article metadata and content
        """
        logger.info(f"Fetching article from: {url}")

        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            # Auto-detect encoding
            response.encoding = response.apparent_encoding

            soup = BeautifulSoup(response.text, 'html.parser')

            # Extract title
            title = None
            title_tags = ['h1', 'title', '.article-title', '.post-title']
            for tag in title_tags:
                elem = soup.select_one(tag) if tag.startswith('.') else soup.find(tag)
                if elem:
                    title = elem.get_text().strip()
                    break

            if not title:
                title = "Untitled Article"

            # Extract main content
            content = self._extract_content(soup)

            # Extract metadata
            published_date = self._extract_date(soup)
            source = self._extract_source(soup, url)

            article = {
                'title': title,
                'url': url,
                'content': content,
                'source': source,
                'published_date': published_date,
                'language': 'auto-detected'
            }

            logger.info(f"Successfully fetched: {title}")
            logger.info(f"Content length: {len(content)} characters")

            return article

        except Exception as e:
            logger.error(f"Failed to fetch article: {e}")
            raise

    def _extract_content(self, soup: BeautifulSoup) -> str:
        """Extract main article content from HTML"""

        # Remove unwanted elements
        for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'iframe']):
            tag.decompose()

        # Try common article content selectors
        content_selectors = [
            'article',
            '.article-content',
            '.post-content',
            '.entry-content',
            'main',
            '.content',
            '#content'
        ]

        content_elem = None
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                break

        # Fallback to body if no article content found
        if not content_elem:
            content_elem = soup.find('body')

        if not content_elem:
            return "Could not extract article content"

        # Extract all paragraph text
        paragraphs = content_elem.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'li'])
        content_parts = []

        for p in paragraphs:
            text = p.get_text().strip()
            if len(text) > 20:  # Filter out very short paragraphs
                content_parts.append(text)

        content = '\n\n'.join(content_parts)

        # Limit content length (to avoid token limits)
        if len(content) > 10000:
            content = content[:10000] + "...\n\n[Content truncated for processing]"

        return content

    def _extract_date(self, soup: BeautifulSoup) -> str:
        """Extract publication date from HTML"""

        # Try meta tags first
        date_metas = [
            ('property', 'article:published_time'),
            ('name', 'publication_date'),
            ('name', 'date'),
            ('itemprop', 'datePublished')
        ]

        for attr, value in date_metas:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                return meta['content']

        # Try common date selectors
        date_selectors = ['.publish-date', '.post-date', 'time', '.date']
        for selector in date_selectors:
            elem = soup.select_one(selector)
            if elem:
                return elem.get_text().strip()

        return datetime.now().strftime("%Y-%m-%d")

    def _extract_source(self, soup: BeautifulSoup, url: str) -> str:
        """Extract source/publication name"""

        # Try meta tags
        source_metas = [
            ('property', 'og:site_name'),
            ('name', 'author'),
            ('name', 'publisher')
        ]

        for attr, value in source_metas:
            meta = soup.find('meta', {attr: value})
            if meta and meta.get('content'):
                return meta['content']

        # Fallback to domain name
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        return domain.replace('www.', '')

    def translate(self, url: str) -> dict:
        """
        Translate article from URL to Chinese

        Args:
            url: Article URL

        Returns:
            Dictionary with original and translated content
        """
        # Fetch article
        article = self.fetch_article(url)

        # Translate using paraphraser
        logger.info("Translating article to Chinese...")
        translated_articles = self.paraphraser.paraphrase_articles([article])
        translated = translated_articles[0]

        result = {
            'original': {
                'title': article['title'],
                'url': article['url'],
                'source': article['source'],
                'published_date': article['published_date'],
                'content': article['content'][:500] + '...',  # Preview only
                'content_length': len(article['content'])
            },
            'translation': {
                'chinese_summary': translated['paraphrased_content'],
                'fact_check': translated.get('fact_check', 'passed'),
                'summary_length': len(translated['paraphrased_content'])
            },
            'metadata': {
                'translated_at': datetime.now().isoformat(),
                'model': 'moonshot-v1-8k'
            }
        }

        logger.info(f"✅ Translation complete!")
        return result

    def save_output(self, result: dict, output_path: str, format: str = 'markdown'):
        """Save translation result to file"""

        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        if format == 'json':
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved JSON to: {output_file}")

        else:  # markdown
            md_content = self._format_markdown(result)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(md_content)
            logger.info(f"Saved Markdown to: {output_file}")

    def _format_markdown(self, result: dict) -> str:
        """Format result as Markdown"""

        original = result['original']
        translation = result['translation']

        md = f"""# {original['title']}

**原文链接**: [{original['url']}]({original['url']})
**来源**: {original['source']}
**发布时间**: {original['published_date']}
**翻译时间**: {result['metadata']['translated_at']}

---

## 📝 中文摘要

{translation['chinese_summary']}

---

## 📄 原文预览

{original['content']}

---

*由 AI Briefing Agent 翻译 | 基于 Moonshot AI (Kimi)*
*原文长度: {original['content_length']} 字符 | 摘要长度: {translation['summary_length']} 字符*
*Fact Check: {translation['fact_check']}*
"""
        return md


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Translate article from URL to Chinese",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Translate and display
  python translate_url.py https://example.com/article

  # Save to file
  python translate_url.py https://example.com/article --output translated.md

  # Save as JSON
  python translate_url.py https://example.com/article --output result.json --format json

  # With debug logging
  python translate_url.py https://example.com/article --log-level DEBUG
        """
    )

    parser.add_argument(
        'url',
        type=str,
        help='URL of the article to translate'
    )

    parser.add_argument(
        '--output', '-o',
        type=str,
        help='Output file path (default: print to console)'
    )

    parser.add_argument(
        '--format', '-f',
        choices=['markdown', 'json'],
        default='markdown',
        help='Output format (default: markdown)'
    )

    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )

    args = parser.parse_args()

    # Setup logging
    setup_logger(log_level=args.log_level)

    # Validate URL
    if not args.url.startswith('http'):
        logger.error("URL must start with http:// or https://")
        sys.exit(1)

    try:
        # Translate article
        translator = URLTranslator()
        result = translator.translate(args.url)

        # Output result
        if args.output:
            translator.save_output(result, args.output, args.format)
        else:
            # Print to console
            if args.format == 'json':
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print("\n" + "=" * 70)
                print(f"📰 {result['original']['title']}")
                print("=" * 70)
                print(f"\n🔗 原文: {result['original']['url']}")
                print(f"📅 发布: {result['original']['published_date']}")
                print(f"📝 来源: {result['original']['source']}")
                print("\n" + "-" * 70)
                print("\n📝 中文摘要:\n")
                print(result['translation']['chinese_summary'])
                print("\n" + "-" * 70)
                print(f"\n✅ Fact Check: {result['translation']['fact_check']}")
                print(f"📊 原文长度: {result['original']['content_length']} 字符")
                print(f"📊 摘要长度: {result['translation']['summary_length']} 字符")
                print("\n" + "=" * 70)

        # Print cost stats
        print("\n💰 API Usage:")
        translator.llm_client.print_stats()

    except KeyboardInterrupt:
        logger.info("\nOperation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
