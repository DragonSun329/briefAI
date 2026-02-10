# 中国AI生态简报

**报告日期**: {{ report_period }}
**生成时间**: {{ generation_time }}
**关注领域**: 国产大模型、AI监管、国产芯片、AI研究、行业动态

---

## 📊 今日要点

{{ executive_summary }}

---

## 🤖 国产大模型动态

{% for article in articles_by_category.get('llm_domestic', []) %}
### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }}

{% if article.key_takeaway %}
> 💡 **要点**: {{ article.key_takeaway }}
{% endif %}

---
{% endfor %}

{% if not articles_by_category.get('llm_domestic') %}
*今日暂无相关新闻*
{% endif %}

## 📜 AI监管政策

{% for article in articles_by_category.get('ai_regulation', []) %}
### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }}

{% if article.key_takeaway %}
> 💡 **要点**: {{ article.key_takeaway }}
{% endif %}

---
{% endfor %}

{% if not articles_by_category.get('ai_regulation') %}
*今日暂无相关新闻*
{% endif %}

## 💻 国产芯片

{% for article in articles_by_category.get('ai_chips', []) %}
### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }}

{% if article.key_takeaway %}
> 💡 **要点**: {{ article.key_takeaway }}
{% endif %}

---
{% endfor %}

{% if not articles_by_category.get('ai_chips') %}
*今日暂无相关新闻*
{% endif %}

## 🔬 研究进展

{% for article in articles_by_category.get('ai_research', []) %}
### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }}

{% if article.key_takeaway %}
> 💡 **要点**: {{ article.key_takeaway }}
{% endif %}

---
{% endfor %}

{% if not articles_by_category.get('ai_research') %}
*今日暂无相关新闻*
{% endif %}

## 📈 行业动态

{% for article in articles_by_category.get('industry_trends', []) %}
### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }}

{% if article.key_takeaway %}
> 💡 **要点**: {{ article.key_takeaway }}
{% endif %}

---
{% endfor %}

{% if not articles_by_category.get('industry_trends') %}
*今日暂无相关新闻*
{% endif %}

## 💰 AI投融资

{% for article in articles_by_category.get('ai_investment', []) %}
### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }}

{% if article.key_takeaway %}
> 💡 **要点**: {{ article.key_takeaway }}
{% endif %}

---
{% endfor %}

{% if not articles_by_category.get('ai_investment') %}
*今日暂无相关新闻*
{% endif %}

---

## 📊 数据来源

本简报数据来自以下中文AI媒体：
- 机器之心 (Synced)
- 量子位 (QbitAI)
- 36氪 AI频道
- 新智元
- 雷锋网 AI
- AI科技评论
- PaperWeekly
- 智源社区 (BAAI)

---

*本报告由 BriefAI 自动生成*
