# AI行业周报

**报告周期**: {{ report_period }}
**生成时间**: {{ generation_time }}
**关注领域**: {{ focus_categories }}

---

## 📊 本周概览

{{ executive_summary }}

---

## 📰 重点资讯

{% for category_name, articles in articles_by_category.items() %}
### {{ category_name }}

{% for article in articles %}
#### {{ loop.index }}. [{{ article.title }}]({{ article.url }})

{{ article.paraphrased_content }}

**来源**: {{ article.source }} | **发布时间**: {{ article.published_date }} | **[阅读原文]({{ article.url }})**

{% if article.key_takeaway %}
> 💡 **关键要点**: {{ article.key_takeaway }}
{% endif %}

---

{% endfor %}
{% endfor %}

## 🔍 关键洞察

{{ key_insights }}

---

## 📚 延伸阅读

本周共筛选 {{ total_articles_scraped }} 篇文章，精选以上 {{ total_articles_included }} 篇呈现。

{% if additional_readings %}
其他值得关注的文章：
{% for item in additional_readings %}
- [{{ item.title }}]({{ item.url }}) - {{ item.source }}
{% endfor %}
{% endif %}

---

*本报告由 AI Briefing Agent 自动生成，基于 Moonshot AI (Kimi)*
