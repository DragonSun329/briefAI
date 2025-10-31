# 🚀 AI产品评测周报

**报告日期**: {{ report_date }}
**精选产品**: {{ product_count }}款
**数据来源**: Product Hunt, Reddit, Hacker News等

---

## 📊 本周产品趋势概览

{{ weekly_trends }}

---

##  🔥 热门产品榜单

{% for product in products %}
### {{ loop.index }}. {{ product.name }}{% if product.trending_score >= 8.5 %} 🔥{% endif %}{% if product.trending_score >= 9.0 %} 💎{% endif %}

**综合评分**: {% if product.overall_score %}⭐ {{ "%.1f"|format(product.overall_score) }}/10{% else %}待评分{% endif %}
**产品分类**: {{ product.category_cn|default(product.category, true) }}
**热度指数**: {{ '🔥' * ((product.trending_score // 2)|int) }} ({{ "%.1f"|format(product.trending_score) }}/10)
**用户评论**: {{ product.review_count|default(0) }}条

---

#### 💡 产品简介

{{ product.deep_analysis }}

---

#### 👥 用户评价

{% if product.avg_rating %}
**平均评分**: {{ '⭐' * (product.avg_rating|int) }}{{ '☆' * (5 - (product.avg_rating|int)) }} ({{ "%.1f"|format(product.avg_rating) }}/5星)
**评论分布**: {{ product.review_distribution|default('待统计') }}
{% endif %}

{% if product.pros %}
**优点** ✅
{% for pro in product.pros[:5] %}
- {{ pro }}
{% endfor %}
{% endif %}

{% if product.cons %}
**缺点** ⚠️
{% for con in product.cons[:3] %}
- {{ con }}
{% endfor %}
{% endif %}

---

#### 💬 用户真实评论

{% if product.top_reviews %}
{% for review in product.top_reviews[:3] %}
> **{{ review.source }}用户** ({{ review.date }}):
> "{{ review.text }}"
{% if review.votes %} *[👍 {{ review.votes }}人赞同]*{% endif %}

{% endfor %}
{% else %}
> 暂无用户评论数据
{% endif %}

---

#### 📌 产品信息

{% if product.pricing %}
**价格**: {{ product.pricing }}
{% endif %}

{% if product.platform %}
**平台**: {{ product.platform }}
{% endif %}

{% if product.url %}
**官网**: [{{ product.url }}]({{ product.url }})
{% endif %}

{% if product.product_hunt_url %}
**Product Hunt**: [查看详情]({{ product.product_hunt_url }})
{% endif %}

---

{% endfor %}

## 📈 本周产品趋势洞察

{{ insights }}

---

## 🎯 CEO关键要点

{{ executive_summary }}

---

## 📊 统计数据

- **评测产品总数**: {{ total_products_analyzed }}款
- **来源数量**: {{ source_count }}个
- **总评论数**: {{ total_reviews }}条
- **平均产品评分**: {{ avg_product_score }}/5星

---

*本报告由 briefAI 自动生成 | 数据来源: Product Hunt API, Reddit PRAW, RSS聚合*
*报告生成时间: {{ generation_time }}*
