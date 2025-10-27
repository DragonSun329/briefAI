# Interactive Mode Guide

Complete guide to using the interactive category selection menu.

## Overview

The interactive mode now features a **menu-based category selection** system that makes it easy to choose which topics you want to focus on without typing natural language queries.

## How to Use

### Start Interactive Mode

```bash
python main.py --interactive
```

### Step-by-Step Walkthrough

#### 1. Welcome Screen

```
============================================================
AI Industry Weekly Briefing Agent
============================================================
```

#### 2. Category Selection Menu

```
请选择您想关注的AI领域:

可选分类:
  1. 金融科技AI应用
  2. 数据分析
  3. 智能营销与广告
  4. 风险管理与反欺诈
  5. 信贷与支付创新
  6. 客户体验优化
  7. 新兴产品与工具
  8. 行业案例与最佳实践
  9. 使用默认分类 (金融科技AI应用, 数据分析, 智能营销与广告)
  10. 自定义输入

请输入选项编号，多个选项用逗号分隔 (例如: 1,2,3)
或直接按Enter使用默认分类

>
```

#### 3. Time Range Selection

```
查看过去几天的新闻？(默认: 7天)
> 7
```

#### 4. Article Count Selection

```
报告中包含多少篇文章？(默认: 15篇)
> 15
```

#### 5. Report Generation

```
开始生成报告...

[1/5] Selecting categories...
[2/5] Scraping articles...
[3/5] Evaluating articles...
[4/5] Paraphrasing articles...
[5/5] Generating final report...

✅ 报告已生成: ./data/reports/ai_briefing_20241025.md
```

## Selection Options

### Option 1: Use Default Categories (Press Enter)

Simply press Enter without typing anything to use the pre-configured default categories.

**Example:**
```
> [Press Enter]
```

**Result:** Uses default categories (金融科技AI应用, 数据分析, 智能营销与广告)

---

### Option 2: Select Single Category

Enter a single number to focus on one category.

**Example:**
```
> 1
```

**Result:** Only includes "金融科技AI应用" articles

---

### Option 3: Select Multiple Categories

Enter multiple numbers separated by commas.

**Example:**
```
> 1,2,4
```

**Result:** Includes articles from:
- 金融科技AI应用
- 数据分析
- 风险管理与反欺诈

---

### Option 4: Use Default Categories (Select Option 9)

**Example:**
```
> 9
```

**Result:** Uses default categories (same as pressing Enter)

---

### Option 5: Custom Input (Select Option 10)

Choose option 10 to enter a custom natural language query.

**Example:**
```
> 10

请输入您想关注的领域 (自然语言):
(例如: 我想了解智能风控和数据分析)

> 我想了解AI在信贷领域的最新应用
```

**Result:** LLM interprets your natural language input and maps to relevant categories

---

## Complete Examples

### Example 1: Default Categories

```bash
$ python main.py --interactive

============================================================
AI Industry Weekly Briefing Agent
============================================================

请选择您想关注的AI领域:

可选分类:
  1. 金融科技AI应用
  2. 数据分析
  3. 智能营销与广告
  4. 风险管理与反欺诈
  5. 信贷与支付创新
  6. 客户体验优化
  7. 新兴产品与工具
  8. 行业案例与最佳实践
  9. 使用默认分类 (金融科技AI应用, 数据分析, 智能营销与广告)
  10. 自定义输入

请输入选项编号，多个选项用逗号分隔 (例如: 1,2,3)
或直接按Enter使用默认分类

> [Press Enter]

查看过去几天的新闻？(默认: 7天)
> [Press Enter]

报告中包含多少篇文章？(默认: 15篇)
> [Press Enter]

开始生成报告...
```

**Result:** Quick start with all defaults

---

### Example 2: Risk Management Focus

```bash
> 4

查看过去几天的新闻？(默认: 7天)
> 3

报告中包含多少篇文章？(默认: 15篇)
> 10

开始生成报告...
```

**Result:**
- Focus: Risk management & anti-fraud
- Time range: Last 3 days
- Articles: Top 10

---

### Example 3: Multiple Categories

```bash
> 1,2,5

查看过去几天的新闻？(默认: 7天)
> 7

报告中包含多少篇文章？(默认: 15篇)
> 20

开始生成报告...
```

**Result:**
- Focus: Fintech AI, Data Analytics, Credit & Payment Innovation
- Time range: Last 7 days
- Articles: Top 20

---

### Example 4: Custom Natural Language

```bash
> 10

请输入您想关注的领域 (自然语言):
(例如: 我想了解智能风控和数据分析)

> 我想了解AI在客户服务和用户体验方面的创新

查看过去几天的新闻？(默认: 7天)
> 5

报告中包含多少篇文章？(默认: 15篇)
> 12

开始生成报告...
```

**Result:**
- Focus: Customer service & UX innovations (LLM-interpreted)
- Time range: Last 5 days
- Articles: Top 12

---

## Error Handling

### Invalid Input

If you enter invalid input, the system will use default categories:

```
> abc

⚠️  输入格式错误，使用默认分类

查看过去几天的新闻？(默认: 7天)
```

### Out of Range Selection

```
> 99

⚠️  无效选择，使用默认分类

查看过去几天的新闻？(默认: 7天)
```

### Mixed Valid and Invalid

```
> 1,2,99

[Only valid selections (1, 2) are used]

查看过去几天的新闻？(默认: 7天)
```

---

## Tips and Best Practices

### 1. Quick Start

For first-time users, press Enter three times to use all defaults:
```
> [Enter]   # Categories
> [Enter]   # Days
> [Enter]   # Articles
```

### 2. Weekly Digest

For a comprehensive weekly digest:
```
> 9         # Use defaults (covers fintech, data, marketing)
> 7         # Last 7 days
> 15        # 15 articles
```

### 3. Daily Brief

For a quick daily update:
```
> 1,2       # Focus on fintech AI and data analytics
> 1         # Last day only
> 5         # Top 5 articles
```

### 4. Deep Dive

For in-depth research on specific topics:
```
> 4         # Risk management only
> 30        # Last 30 days
> 30        # Top 30 articles
```

### 5. Custom Topics

Use option 10 when:
- You want to explore adjacent topics not in the menu
- You have very specific requirements
- You want to combine topics in a unique way

**Example queries:**
- "我想了解AI在反欺诈和风险预测方面的应用"
- "关注金融科技的监管政策和合规要求"
- "数据隐私和安全相关的最新进展"

---

## Category Descriptions

| # | Category | Focus |
|---|----------|-------|
| 1 | 金融科技AI应用 | AI in fintech, smart risk control, credit scoring |
| 2 | 数据分析 | Data analytics, big data, predictive analysis |
| 3 | 智能营销与广告 | Smart marketing, ad targeting, user profiling |
| 4 | 风险管理与反欺诈 | Risk management, fraud detection, security |
| 5 | 信贷与支付创新 | Credit innovations, payment systems, lending |
| 6 | 客户体验优化 | Customer experience, UX, personalization |
| 7 | 新兴产品与工具 | New products, tools, platforms |
| 8 | 行业案例与最佳实践 | Case studies, best practices, implementations |
| 9 | 使用默认分类 | Pre-selected top 3 categories |
| 10 | 自定义输入 | Natural language custom query |

---

## Comparison: Menu vs Command-Line

### Interactive Mode (Menu)
```bash
python main.py --interactive
```

**Pros:**
- ✅ Visual menu, easy to see all options
- ✅ No need to remember category names
- ✅ Guided experience
- ✅ Error handling with fallback
- ✅ Good for occasional users

**Cons:**
- ❌ Requires user interaction (not scriptable)
- ❌ Slower for expert users

### Command-Line Mode
```bash
python main.py --input "金融科技AI和数据分析" --days 7 --top 15
```

**Pros:**
- ✅ Scriptable and automatable
- ✅ Fast for expert users
- ✅ Can be used in cron jobs
- ✅ No interaction needed

**Cons:**
- ❌ Need to know category names
- ❌ Less discoverable
- ❌ No visual guidance

### Default Mode
```bash
python main.py --defaults --days 7 --top 15
```

**Pros:**
- ✅ Fastest option
- ✅ Scriptable
- ✅ Consistent results

**Cons:**
- ❌ No customization
- ❌ Fixed categories

---

## Advanced Usage

### Combining with Other Options

You can't combine `--interactive` with other flags, but you can use non-interactive modes:

```bash
# Use defaults with custom time range
python main.py --defaults --days 3 --top 10

# Custom input via command line
python main.py --input "我想了解智能风控" --days 7 --top 15

# Force fresh scraping
python main.py --defaults --no-cache

# Debug mode
python main.py --defaults --log-level DEBUG
```

### Scripting the Interactive Mode

For automation, use command-line mode instead:

```bash
#!/bin/bash
# weekly_report.sh

python main.py --defaults --days 7 --top 15
```

---

## Troubleshooting

### Issue: Categories not loading

**Error:**
```
Failed to load categories: [Errno 2] No such file or directory
```

**Solution:**
- Ensure you're running from the project root directory
- Check that `config/categories.json` exists

### Issue: Input not recognized

**Symptom:**
```
⚠️  输入格式错误，使用默认分类
```

**Solution:**
- Enter numbers only (e.g., `1,2,3`)
- Don't use spaces between numbers (use `1,2,3` not `1, 2, 3`)
- Use commas as separators

### Issue: Custom input not working

**Solution:**
- Make sure you selected option 10 first
- Enter natural language in Chinese
- Include context (e.g., "我想了解..." works better than just "风控")

---

## FAQ

### Q: Can I save my preferences?

**A:** Not currently. Each run asks for preferences. For repeated use with same preferences, use command-line mode:
```bash
python main.py --input "我想了解金融科技AI和数据分析" --days 7 --top 15
```

### Q: Can I select all categories?

**A:** Use option 9 for defaults, or enter all numbers: `1,2,3,4,5,6,7,8`

### Q: What's the difference between option 9 and option 10?

**A:**
- **Option 9**: Uses pre-configured defaults from `config/categories.json`
- **Option 10**: You write a custom natural language query that LLM interprets

### Q: Can I add my own categories?

**A:** Yes! Edit `config/categories.json` to add/modify categories. They'll appear in the menu automatically.

### Q: What happens if I select incompatible categories?

**A:** All selected categories are included. The system finds articles matching any of the selected categories.

---

## See Also

- [SETUP.md](SETUP.md) - Installation and setup
- [README.md](README.md) - Project overview
- [config/categories.json](config/categories.json) - Category definitions

---

**Last Updated**: 2025-10-25
**Feature**: Interactive Category Selection Menu
