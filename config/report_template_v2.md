# AI Intelligence Daily Brief

**{{ report_date }}** | Generated {{ generation_time }}{% if experiment_name %} | Experiment: `{{ experiment_name }}`{% endif %}

---

## 📊 Executive Summary

{{ executive_summary }}

---

{% if emerging_trends %}
## 🔥 Emerging Trends

{% for trend in emerging_trends %}
### {{ loop.index }}. {{ trend.name }}

**Emergence Score**: {{ trend.score }}/100 | **Velocity**: {{ trend.velocity }} | **Sources**: {{ trend.source_count }} types

{{ trend.narrative }}

{% if trend.evidence %}
Evidence chain:
{% for e in trend.evidence %}
{% if e is mapping %}
- **[{{ e.source_type }}]** {{ e.signal }} _({{ e.date }})_
{% else %}
- {{ e }}
{% endif %}
{% endfor %}
{% endif %}

{% if trend.prediction %}
> 🔮 **Prediction**: {{ trend.prediction }}
{% endif %}

---
{% endfor %}
{% endif %}

{% if action_predictions %}
## 🎯 Expected Company Actions

_Predicted actions based on incentive analysis — what companies are likely forced to do next._

{% for ap in action_predictions %}
- **{{ ap.entity | title }}** likely to announce **{{ ap.event_display_name }}**{% if ap.direction %} ({{ ap.direction }}){% endif %}{% if ap.counterparty_type %} with {{ ap.counterparty_type | replace('_', ' ') }}{% endif %} within {{ ap.timeframe_days }} days ({{ (ap.probability * 100) | int }}% confidence)
{% if ap.note %}  - _{{ ap.note }}_{% endif %}
{% endfor %}

---
{% endif %}

{% if stealth_signals %}
## 🕵️ Stealth Signals

_Non-news signals with zero media coverage — potential early alpha._

{% for signal in stealth_signals %}
- **{{ signal.entity }}**: {{ signal.description }}
{% endfor %}

---
{% endif %}

## 📰 Top Stories

{% for category_name, articles in articles_by_category.items() %}
### {{ category_name }}

{% for article in articles %}
**{{ loop.index }}. [{{ article.title }}]({{ article.url }})**

{{ article.paraphrased_content }}

{% if article.key_takeaway %}
> 💡 {{ article.key_takeaway }}
{% endif %}

_{{ article.source }}{% if article._source_type %} [{{ article._source_type }}]{% endif %} · {{ article.published_date or article.published_at or '' }}_

{% endfor %}
{% endfor %}

---

{% if narratives %}
## 📖 Active Narratives

{% for nar in narratives %}
### {{ nar.name }} — {{ nar.phase }}

**Momentum**: {{ nar.momentum }} | **Mentions**: {{ nar.mentions_7d }} (7d) / {{ nar.mentions_30d }} (30d)

{{ nar.summary }}

{% if nar.inflection_points %}
Key inflection points:
{% for ip in nar.inflection_points %}
- {{ ip }}
{% endfor %}
{% endif %}

{% if nar.outlook %}
> 📈 **Outlook**: {{ nar.outlook }}
{% endif %}

---
{% endfor %}
{% endif %}

{% if alerts %}
## ⚡ Alerts

{% for alert in alerts %}
- **{{ alert.severity | upper }}** — {{ alert.type }}: {{ alert.message }}
{% endfor %}

---
{% endif %}

{% if market_movers %}
## 📉 Market Movers & News Correlations

_AI stock price moves matched to today's news. Source: Finnhub + briefAI correlator._

{% if market_movers.sector_performance %}
**Sector Performance:**
{% for sector, avg in market_movers.sector_performance.items() %}
- **{{ sector }}**: {{ "%.2f"|format(avg) }}%
{% endfor %}
{% endif %}

{% for mover in market_movers.correlations[:10] %}
- **{{ mover.ticker }}** {{ mover.direction }} {{ "%.1f"|format(mover.price_change_pct|abs) }}% (${{ mover.current_price }}) — {% if mover.top_articles %}{{ mover.explanation_strength }}: _{{ mover.top_articles[0].title[:100] }}_{% else %}unexplained{% endif %}{% if mover.technical and mover.technical.rsi %} | RSI {{ mover.technical.rsi }}{% if mover.technical.ta_signals %} [{{ mover.technical.ta_signals | join(', ') }}]{% endif %}{% endif %}

{% endfor %}

---
{% endif %}

{% if podcast_insights %}
## 🎙️ Podcast Intelligence

_Key insights from this week's top AI/tech podcasts._

{% for ep in podcast_insights[:8] %}
### {{ ep.title[:80] }}
**{{ ep.podcast_channel }}** · {{ ep.duration_min }} min

{% if ep.summary %}{{ ep.summary[:300] }}{% endif %}

{% if ep.entities %}**Entities:** {{ ep.entities[:8] | join(', ') }}{% endif %}

{% endfor %}

---
{% endif %}

{% if deep_research %}
## 🧠 Deep Research (CellCog)

{% for report in deep_research %}
### {{ report.topic }}

{{ report.summary }}

{% if report.key_developments %}
**Key Developments:**
{% for dev in report.key_developments %}
- **[{{ dev.signal | upper }}]** {{ dev.event }} _({{ dev.entity }})_
{% endfor %}
{% endif %}

{% if report.investment_signals %}
**Investment Signals:**
{% for sig in report.investment_signals %}
- **{{ sig.entity }}** ({{ sig.direction }}): {{ sig.rationale[:100] }}...
{% endfor %}
{% endif %}

{% if report.analyst_outlook %}
> 📊 **Outlook**: {{ report.analyst_outlook[:300] }}...
{% endif %}

---
{% endfor %}
{% endif %}

{% if insider_trades %}
## 💰 Insider Trading Signals

_SEC Form 4 data from OpenInsider — executives buying their own stock._

{% for trade in insider_trades %}
- **{{ trade.entity }}**: {{ trade.insider_name }} ({{ trade.title }}) bought ${{ "{:,}".format(trade.value) }} @ ${{ "%.2f"|format(trade.price) }}
{% endfor %}

---
{% endif %}

{% if predictions %}
## 🔮 Active Predictions

| Prediction | Confidence | Check Date | Status |
|-----------|-----------|-----------|--------|
{% for pred in predictions %}
| {{ pred.statement }} | {{ pred.confidence }}% | {{ pred.check_date }} | {{ pred.status }} |
{% endfor %}

---
{% endif %}

## 📊 Signal Heatmap

| Entity | Composite | Media | Momentum 7d | Sources | Trend |
|--------|----------|-------|------------|---------|-------|
{% for entity in top_entities %}
| {{ entity.name }} | {{ entity.composite }} | {{ entity.media }} | {{ entity.momentum }} | {{ entity.source_count }} | {{ entity.trend }} |
{% endfor %}

---

_{{ total_articles_scraped }} articles scraped → {{ total_articles_included }} selected.{% if delta_stats and delta_stats.novel %} ({{ delta_stats.novel }} novel, {{ delta_stats.duplicates }} repeats){% endif %} Powered by briefAI._
