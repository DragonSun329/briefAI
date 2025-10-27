# URL Translator Guide

Translate any article from a URL to Chinese using AI-powered summarization.

## Overview

The URL Translator tool allows you to:
- Fetch any article from a URL
- Automatically extract the main content
- Translate/summarize it to professional Chinese (150-250 characters)
- Save the translation in Markdown or JSON format

Perfect for quickly understanding foreign articles or creating Chinese summaries of English content.

## Quick Start

### Basic Usage

```bash
# Translate and display in console
python translate_url.py https://example.com/article

# Save to Markdown file
python translate_url.py https://example.com/article --output translated.md

# Save as JSON
python translate_url.py https://example.com/article --output result.json --format json
```

### Example Output (Console)

```
======================================================================
📰 GPT-5 Released: Major Breakthrough in AI Reasoning
======================================================================

🔗 原文: https://example.com/article
📅 发布: 2024-10-25
📝 来源: example.com

----------------------------------------------------------------------

📝 中文摘要:

OpenAI发布了GPT-5模型，在推理能力和多模态理解方面实现了显著提升。新模型在数学、编程和科学推理等多个基准测试中超越了前代产品，同时支持更长的上下文窗口。这一突破可能会加速AI在专业领域的应用，特别是在需要复杂推理的场景中。该模型将通过API向企业客户开放，预计在未来几个月内逐步推广。

----------------------------------------------------------------------

✅ Fact Check: passed
📊 原文长度: 3542 字符
📊 摘要长度: 178 字符

======================================================================
```

## Features

### 🌐 Automatic Content Extraction

- **Smart Title Detection**: Automatically finds article title from multiple sources
- **Content Extraction**: Intelligently extracts main article content, ignoring navigation, ads, etc.
- **Metadata Parsing**: Extracts publication date, source, and author when available
- **Multi-Language Support**: Works with English, Chinese, and other languages

### 🤖 AI-Powered Translation

- **Executive Summary**: Generates 150-250 character professional Chinese summary
- **Paragraph Format**: Flowing paragraphs (not bullet points)
- **Fact Checking**: Validates content accuracy, prevents hallucinations
- **Context Aware**: Understands fintech/business context for better translations

### 💾 Flexible Output

- **Console Display**: Pretty-printed output for quick review
- **Markdown Export**: Formatted .md file with original and translation
- **JSON Export**: Structured data for programmatic use
- **Cost Tracking**: Shows API usage and estimated cost

## Usage Examples

### Example 1: Quick Translation

```bash
python translate_url.py https://techcrunch.com/2024/10/25/ai-breakthrough/
```

### Example 2: Save to File

```bash
python translate_url.py https://venturebeat.com/ai/article \
  --output translations/article_20241025.md
```

### Example 3: Batch Processing

```bash
# Create a script to translate multiple URLs
for url in $(cat urls.txt); do
  python translate_url.py "$url" --output "translations/$(basename $url).md"
done
```

### Example 4: JSON for Integration

```bash
python translate_url.py https://example.com/article \
  --output result.json \
  --format json

# Use in other scripts
python -c "import json; data = json.load(open('result.json')); print(data['translation']['chinese_summary'])"
```

## Command-Line Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `url` | - | Article URL to translate (required) | - |
| `--output` | `-o` | Output file path | Print to console |
| `--format` | `-f` | Output format: `markdown` or `json` | `markdown` |
| `--log-level` | - | Logging level: DEBUG/INFO/WARNING/ERROR | `INFO` |

## Output Formats

### Markdown Format

```markdown
# Article Title

**原文链接**: [https://...]
**来源**: Source Name
**发布时间**: 2024-10-25
**翻译时间**: 2024-10-25T10:30:00

---

## 📝 中文摘要

[Chinese summary here...]

---

## 📄 原文预览

[Original content preview...]

---

*由 AI Briefing Agent 翻译 | 基于 Moonshot AI (Kimi)*
```

### JSON Format

```json
{
  "original": {
    "title": "Article Title",
    "url": "https://...",
    "source": "Source Name",
    "published_date": "2024-10-25",
    "content": "Preview...",
    "content_length": 3542
  },
  "translation": {
    "chinese_summary": "中文摘要内容...",
    "fact_check": "passed",
    "summary_length": 178
  },
  "metadata": {
    "translated_at": "2024-10-25T10:30:00",
    "model": "moonshot-v1-8k"
  }
}
```

## How It Works

### 1. URL Fetching
- Sends HTTP request with proper headers
- Auto-detects character encoding
- Handles redirects and HTTPS

### 2. Content Extraction
- Parses HTML with BeautifulSoup
- Removes scripts, styles, navigation, ads
- Finds main article content using multiple strategies
- Extracts title, date, source metadata

### 3. Translation/Summarization
- Uses ArticleParaphraser module (same as weekly reports)
- Generates professional Chinese summary (150-250 chars)
- Paragraph format (not bullet points)
- Fact-checks against original content

### 4. Output Generation
- Formats result in Markdown or JSON
- Includes original URL for reference
- Tracks API usage and costs

## Supported Websites

Works with most news and blog websites:

✅ **Tested and Working:**
- TechCrunch
- VentureBeat
- Medium articles
- ArXiv papers (with text)
- Most news sites
- WordPress blogs
- Chinese tech media (36氪, 机器之心, etc.)

⚠️ **May Have Issues:**
- Paywalled content (WSJ, NYT premium)
- JavaScript-heavy sites
- Sites with aggressive bot protection

## Cost Estimation

Using Moonshot AI (Kimi) at ¥12/M tokens:

- **Short article** (< 1000 words): ~¥0.20 (~$0.03 USD)
- **Medium article** (1000-3000 words): ~¥0.40 (~$0.06 USD)
- **Long article** (3000+ words): ~¥0.60 (~$0.08 USD)

Very affordable for occasional translations!

## Tips and Best Practices

### 1. Check Content Quality

Not all websites extract cleanly. Review the output to ensure content was extracted properly.

### 2. Use Markdown for Archiving

Save translations as Markdown files for easy reading and version control:
```bash
python translate_url.py $URL --output "archive/$(date +%Y%m%d)_article.md"
```

### 3. Batch Processing

Create a `urls.txt` file with one URL per line, then:
```bash
while read url; do
  python translate_url.py "$url" --output "translations/$(echo $url | md5sum | cut -d' ' -f1).md"
  sleep 2  # Rate limiting
done < urls.txt
```

### 4. Integration with Workflows

Use JSON output to integrate with other tools:
```python
import json
import subprocess

result = subprocess.run(
    ['python', 'translate_url.py', url, '--format', 'json'],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
chinese_summary = data['translation']['chinese_summary']
```

## Troubleshooting

### Error: "Failed to fetch article"

**Causes:**
- Invalid URL
- Website is down
- Network connection issue
- Bot protection blocking access

**Solutions:**
- Verify URL is correct and accessible
- Try in a browser first
- Check internet connection
- Some sites may require manual content input

### Error: "Could not extract article content"

**Causes:**
- Non-standard HTML structure
- Content behind JavaScript
- Paywall or login required

**Solutions:**
- Try a different article
- Copy-paste content into a local file
- Some sites may not be compatible

### Poor Translation Quality

**Causes:**
- Content extraction captured wrong elements
- Very technical or specialized content
- Mixed languages in original

**Solutions:**
- Review extracted content in output
- Adjust prompts in `article_paraphraser.py`
- For critical translations, review manually

## Advanced Usage

### Custom Content Length

Edit `modules/article_paraphraser.py` to adjust summary length:

```python
paraphraser = ArticleParaphraser(
    min_length=200,  # Longer summaries
    max_length=350
)
```

### Adjust Translation Style

Modify prompts in `article_paraphraser.py` to change tone:
- More technical vs. business-friendly
- Formal vs. casual
- Detailed vs. high-level

### Integration with Weekly Reports

The URL translator uses the same ArticleParaphraser module as the weekly briefing system, ensuring consistent quality and style.

## Examples from Real Articles

### Example 1: Technical Article

**Input:** https://arxiv.org/abs/2024.xxxxx

**Output:**
```
研究团队提出了一种新的深度学习架构，在图像识别任务中实现了98.5%的准确率。该方法通过引入自适应注意力机制，显著降低了计算成本，同时保持了高精度。实验结果表明，该模型在资源受限的设备上也能高效运行，为边缘AI应用提供了新的可能性。
```

### Example 2: Business News

**Input:** https://techcrunch.com/ai-startup-funding/

**Output:**
```
人工智能初创公司XYZ完成了5000万美元B轮融资，由知名风投机构领投。该公司专注于企业级AI解决方案，其产品已被多家财富500强企业采用。新资金将用于扩大研发团队和拓展亚太市场，预计年内客户数量将增长三倍。这轮融资反映了投资者对企业AI市场的持续看好。
```

### Example 3: Tutorial/Guide

**Input:** https://towardsdatascience.com/guide-to-xyz/

**Output:**
```
本文介绍了如何使用Python构建高效的数据处理管道。作者详细阐述了从数据清洗、特征工程到模型训练的完整流程，并提供了可复用的代码示例。文中强调了模块化设计的重要性，建议使用Pandas和Scikit-learn等成熟库来提高开发效率。这套方法论已在实际项目中验证，适合中小型数据团队参考。
```

## Comparison with Weekly Briefing

| Feature | URL Translator | Weekly Briefing |
|---------|----------------|-----------------|
| Input | Single URL | Multiple RSS/Web sources |
| Output | One translation | 15 articles + insights |
| Use Case | Quick translation | Weekly digest |
| Processing | Instant | 15-20 minutes |
| Cost | ¥0.20-0.60 | ¥3.60 |

Both tools use the same translation engine for consistent quality.

## Future Enhancements

Potential improvements (not yet implemented):

- [ ] Support for PDF files
- [ ] Video transcript translation (YouTube)
- [ ] OCR for image-based articles
- [ ] Translation memory for consistency
- [ ] Custom glossary for technical terms

## See Also

- [SETUP.md](SETUP.md) - Main system setup
- [article_paraphraser.py](modules/article_paraphraser.py) - Translation engine
- [README.md](README.md) - Project overview

---

**Powered by Moonshot AI (Kimi)** 🤖 | **Built for Fintech** 💰
