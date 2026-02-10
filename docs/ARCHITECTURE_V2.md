# briefAI Architecture v2 — News Intelligence, Not Stock Terminal

## The Problem

briefAI has been drifting toward becoming a ValueCell clone: real-time stock prices, technical indicators (RSI/MACD), 58-ticker AKShare scanning, Bloomberg Terminal UI, screener DSL. This plays to ValueCell's strengths and briefAI's weaknesses.

**What ValueCell does better:** Real-time market data, native TA, streaming prices, professional trading UI. They have dedicated infrastructure for this. Competing here is a losing game.

**What briefAI does that nobody else does:** AI-native news intelligence with 40+ alternative data sources, LLM-powered event extraction, adversarial multi-agent analysis, and Chinese AI ecosystem coverage.

## Design Principle

> **briefAI is an intelligence platform, not a trading terminal.**
> It answers "what's happening and why" — not "what's the RSI on 寒武纪."

Market data exists only as **context for news analysis**, never as a standalone feature.

---

## Core Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                         │
│  Chat (Orchestrator) │ Daily Brief │ Alert Feed │ Deep   │
│                      │             │            │ Dive   │
└───────────┬──────────┴──────┬──────┴─────┬──────┴────────┘
            │                 │            │
┌───────────▼─────────────────▼────────────▼───────────────┐
│                  INTELLIGENCE LAYER                       │
│                                                           │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐ │
│  │ Orchestrator │  │  News        │  │  Alert          │ │
│  │ (Chat Q&A)   │  │  Pipeline    │  │  Engine         │ │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘ │
│         │                 │                    │          │
│  ┌──────▼─────────────────▼────────────────────▼────────┐│
│  │              AGENT POOL                               ││
│  │  ┌────────────┐ ┌──────────┐ ┌──────────────────┐   ││
│  │  │ News       │ │ Hype-Man │ │ Trend Detector   │   ││
│  │  │ Sentiment  │ │ (Bull)   │ │ (Cross-Source)   │   ││
│  │  ├────────────┤ ├──────────┤ ├──────────────────┤   ││
│  │  │ Event      │ │ Skeptic  │ │ Narrative        │   ││
│  │  │ Extractor  │ │ (Bear)   │ │ Tracker          │   ││
│  │  ├────────────┤ ├──────────┤ ├──────────────────┤   ││
│  │  │ Sector     │ │ Arbiter  │ │ Prediction       │   ││
│  │  │ Context    │ │ (Judge)  │ │ Engine           │   ││
│  │  └────────────┘ └──────────┘ └──────────────────┘   ││
│  └──────────────────────────────────────────────────────┘│
└──────────────────────────┬───────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────┐
│                    DATA LAYER                             │
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Source Pool   │  │ Entity Store │  │ Market Context │ │
│  │ (40+ scraper) │  │ (SQLite)     │  │ (Lightweight)  │ │
│  ├──────────────┤  ├──────────────┤  ├────────────────┤ │
│  │ News DB      │  │ Event Store  │  │ Price Cache    │ │
│  │ (trend_radar)│  │ (events.db)  │  │ (daily only)   │ │
│  ├──────────────┤  ├──────────────┤  ├────────────────┤ │
│  │ Signal Store │  │ Prediction   │  │ Sector Map     │ │
│  │ (signals.db) │  │ Store        │  │ (static ref)   │ │
│  └──────────────┘  └──────────────┘  └────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

---

## Layer 1: Data Layer

### 1.1 Source Pool (KEEP — this is the moat)

The 40+ scrapers are briefAI's biggest competitive advantage. No reorganization needed, but tighten focus:

**Tier 1 — High Signal (run daily):**
| Source | Why |
|--------|-----|
| `tech_news_rss_scraper` | Core news flow |
| `china_tech_scraper` | Chinese AI ecosystem (unique) |
| `hackernews_scraper` | Developer sentiment leading indicator |
| `reddit_scraper` | Community pulse |
| `arxiv_scraper` | Research trend detection |
| `github_enhanced_scraper` | Adoption velocity (stars, forks, commits) |
| `huggingface_scraper` | Model adoption signals |
| `earnings_scraper` | Earnings events |
| `newsletter_scraper` | Curated expert signals |

**Tier 2 — Enrichment (run 2-3x/week):**
| Source | Why |
|--------|-----|
| `patent_scraper` | Strategic intent signals |
| `hiring_signals_scraper` | Resource allocation signals |
| `job_postings_scraper` | Expansion/contraction signals |
| `conference_papers_scraper` | Research direction |
| `policy_scraper` | Regulatory risk |
| `polymarket_scraper` / `metaculus_scraper` | Prediction market calibration |

**Tier 3 — Deprioritize:**
| Source | Reason |
|--------|--------|
| `glassdoor_scraper` | Low signal-to-noise |
| `salary_scraper` | Lagging indicator |
| `wayback_scraper` | Niche |
| `app_rankings_scraper` | Consumer, not AI-industry |

### 1.2 Entity Store (REFACTOR)

Current: Entities scattered across `trend_radar.db`, `signals.db`, etc.

**New: Unified entity graph**

```python
# utils/entity_store.py

class Entity:
    """Central entity record."""
    id: str                    # uuid
    canonical_name: str        # "OpenAI"
    aliases: list[str]         # ["openai", "Open AI", "OAI"]
    entity_type: EntityType    # COMPANY | PROJECT | MODEL | PERSON | SECTOR
    sector: str | None         # "LLM", "Robotics", "Chip", "Cloud"
    metadata: dict             # ticker, github_url, hf_id, etc.
    first_seen: datetime
    last_updated: datetime

class EntityMention:
    """Every time an entity appears in a source."""
    entity_id: str
    source_type: str           # "news", "github", "arxiv", "reddit"
    source_id: str             # article/repo/post ID
    mention_date: datetime
    sentiment: float | None    # -1.0 to 1.0
    context_snippet: str       # 200-char surrounding text
```

This is the **spine** everything else hangs off. Entity resolution (`entity_resolver.py`, `entity_matcher.py`) already exists — wire it into a single store.

### 1.3 Market Context (SLIM DOWN)

**Kill:** Real-time price streaming, AKShare 58-ticker scanning, bid/ask data, Fincept WebSocket integration.

**Keep:** Lightweight daily price context for entities that have tickers.

```python
# utils/market_context.py

class MarketContext:
    """Minimal market data — context for news, not a terminal."""

    async def get_price_context(self, ticker: str) -> dict:
        """Daily OHLCV + basic change%. Called on-demand, not streaming."""
        return {
            "ticker": ticker,
            "price": 142.50,
            "change_pct": -3.2,
            "volume_vs_avg": 2.1,  # 2.1x average volume
            "5d_trend": "down",
            "sector_change_pct": -1.8,  # for relative comparison
        }

    async def get_sector_snapshot(self, sector: str) -> dict:
        """Top movers in sector today. Max 5-10 tickers."""
        return {
            "sector": "半导体",
            "avg_change_pct": -2.1,
            "top_gainers": [...],
            "top_losers": [...],
        }
```

**Rules:**
- No real-time streaming. Daily close + intraday snapshot is enough.
- No TA indicators (RSI, MACD, Bollinger). If needed, link out to ValueCell/TradingView.
- Price data exists to answer "did the market react to this news?" — not "should I buy."
- Cache aggressively. One API call per ticker per day.

---

## Layer 2: Intelligence Layer (Agents)

### 2.1 Agent Redesign

**REMOVE these agents:**
- `technical_agent.py` — AKShare TA analysis. This is ValueCell's job.
- `fundamental_agent.py` — Financial statement analysis. Also ValueCell territory.

**KEEP and strengthen:**
- `news_sentiment_agent.py` → rename to **News Intelligence Agent**
- `hypeman.py` + `skeptic.py` + `arbiter.py` → **Adversarial Pipeline** (already good)
- `sector_agent.py` → slim down, keep only news-level sector context

**ADD these new agents:**

#### Trend Detector Agent (NEW — core differentiator)

```python
class TrendDetectorAgent(BaseAgent):
    """
    Detects emerging trends BEFORE they're obvious.

    Cross-references signals across multiple sources to find patterns:
    - GitHub repos gaining stars + HN discussion + arxiv papers = emerging tech
    - Hiring surge + patent filings + no news yet = stealth buildup
    - News volume spike + prediction market shift + Reddit buzz = breakout

    This is what Bloomberg CANNOT do.
    """

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="trend_detector",
            name="Trend Detector",
            description="Cross-source pattern detection for emerging AI trends",
            capabilities=[
                "cross_source_correlation",
                "early_signal_detection",
                "trend_velocity_tracking",
            ],
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        """
        Inputs: time window, optional sector/entity filter
        Process:
          1. Pull recent signals from all source types
          2. Cluster by entity (using entity_resolver)
          3. For each entity cluster, compute:
             - Source diversity score (how many different source types mention it)
             - Velocity (acceleration of mentions over time)
             - Sentiment divergence (are different sources disagreeing?)
             - Novelty (is this entity new to our radar?)
          4. Rank by composite "emergence score"
          5. LLM generates narrative for top-N emerging trends
        Output: Ranked list of emerging trends with evidence chains
        """
```

**Key insight:** The value isn't any single scraper — it's the **cross-referencing**. A GitHub repo trending alone means nothing. A GitHub repo trending + arxiv paper + 3 news articles + hiring signals = something real is happening.

#### Narrative Tracker Agent (NEW)

```python
class NarrativeTrackerAgent(BaseAgent):
    """
    Tracks evolving narratives over time.

    Examples:
    - "AI bubble" narrative: tracks mentions, sentiment shifts, key events
    - "China chip independence" narrative: policy changes, company moves
    - "OpenAI vs open-source" narrative: competitive dynamics

    Uses the event store + entity mentions to build narrative timelines.
    """

    @property
    def card(self) -> AgentCard:
        return AgentCard(
            agent_id="narrative_tracker",
            name="Narrative Tracker",
            description="Tracks how stories evolve over weeks/months",
            capabilities=[
                "narrative_detection",
                "timeline_construction",
                "sentiment_evolution",
                "narrative_momentum",
            ],
        )

    async def run(self, input: AgentInput) -> AgentOutput:
        """
        Inputs: narrative topic or auto-detect
        Process:
          1. Cluster recent events by theme (using cluster_engine)
          2. For each cluster, build timeline:
             - First mention date
             - Key inflection points
             - Current momentum (growing/fading/stable)
             - Sentiment arc (how opinion has shifted)
          3. LLM generates narrative summary with predictions
        Output: Active narratives with timelines and momentum scores
        """
```

#### Prediction Engine Agent (REFACTOR from existing)

```python
class PredictionEngineAgent(BaseAgent):
    """
    Makes explicit, falsifiable predictions based on signal patterns.

    NOT price predictions. Event predictions:
    - "OpenAI will announce GPT-5 within 30 days" (confidence: 0.7)
    - "NVIDIA earnings will beat consensus" (based on hiring + patent signals)
    - "This startup will raise Series B within 90 days" (hiring surge + job posts)

    Tracks accuracy over time for calibration.
    """

    async def run(self, input: AgentInput) -> AgentOutput:
        """
        Process:
          1. Gather all signals for entity/topic
          2. Pattern match against historical events (outcome_tracker)
          3. Generate prediction with confidence interval
          4. Store in prediction_store for later verification
          5. Periodically auto-verify and update calibration
        """
```

### 2.2 Revised Agent Registry

```
AGENT POOL (v2)
├── News Intelligence Agent    — "What's being said?" (sentiment, volume, key articles)
├── Trend Detector Agent       — "What's emerging?" (cross-source pattern detection)  ← NEW
├── Narrative Tracker Agent    — "How is the story evolving?" (timeline, momentum)    ← NEW
├── Prediction Engine Agent    — "What happens next?" (falsifiable event predictions) ← REFACTORED
├── Sector Context Agent       — "What's the industry backdrop?" (news-based, not TA)← SLIMMED
├── Hype-Man (Bull)            — "Why this is exciting" (adoption velocity)           ← KEEP
├── Skeptic (Bear)             — "Why this is risky" (risk factors, red flags)        ← KEEP
└── Arbiter (Judge)            — "What's the verdict?" (synthesis)                    ← KEEP
```

**Removed:** `technical_agent`, `fundamental_agent`

### 2.3 Orchestrator Updates

The orchestrator is already well-designed (triage → plan → execute → synthesize). Minimal changes:

```python
# Update the planner's available agents
AGENT_DESCRIPTIONS = """
Available agents for task planning:

1. sentiment — News & social media analysis. Use when the query involves
   recent news, public opinion, media coverage, or social buzz about an entity.

2. trend_detector — Cross-source emerging trend detection. Use when the query
   asks about emerging trends, "what's hot", or pattern detection across sources.

3. narrative_tracker — Story evolution tracking. Use when the query asks about
   how a situation has developed over time, or narrative/theme analysis.

4. prediction — Event prediction engine. Use when the query asks "what will
   happen", "will X do Y", or requests forward-looking analysis.

5. sector — Industry/sector context. Use when the query needs sector-level
   backdrop or peer comparison context.

6. adversarial — Bull vs Bear analysis (runs hypeman + skeptic + arbiter).
   Use for balanced investment-style analysis of any entity.
"""
```

---

## Layer 3: Intelligence Products (Outputs)

### 3.1 Daily Brief (STRENGTHEN)

The Streamlit weekly briefing is a good start. Upgrade to daily:

```
DAILY AI INTELLIGENCE BRIEF
────────────────────────────
📊 Executive Summary (3-5 bullets, LLM-generated)

🔥 Top Stories (5-10 articles, ranked by composite score)
   Each with: headline, source, impact score, 2-line summary

📈 Emerging Trends (from Trend Detector)
   - New this week: [entity] gaining traction across [N] sources
   - Accelerating: [narrative] mentions up 3x week-over-week

⚡ Alerts (from Alert Engine)
   - Anomaly: [entity] mentioned in 5 sources in 24h (normal: 1/week)
   - Prediction: [event] confidence crossed 80% threshold

📖 Narrative Updates (from Narrative Tracker)
   - "AI regulation in China": new policy draft published, sentiment shifting
   - "Open-source vs closed-source": Meta's latest move changes dynamics
```

### 3.2 Chat Interface (KEEP orchestrator)

Already works well. The orchestrator handles:
- Simple questions → direct answer
- Complex analysis → multi-agent plan → parallel execution → synthesis

No changes needed. Just update agent pool.

### 3.3 Alert System (REFOCUS)

**Kill:** Price alerts, technical indicator alerts, screener-based alerts.

**Keep and add:**

```python
class AlertType(Enum):
    # Existing
    ANOMALY_SPIKE      = "anomaly_spike"       # Unusual mention volume
    SENTIMENT_SHIFT    = "sentiment_shift"      # Sudden sentiment change

    # New
    TREND_EMERGENCE    = "trend_emergence"      # New cross-source pattern detected
    NARRATIVE_INFLECT  = "narrative_inflection"  # Narrative momentum changed direction
    PREDICTION_TRIGGER = "prediction_trigger"    # Prediction confidence crossed threshold
    SOURCE_DIVERGENCE  = "source_divergence"     # Sources disagree (news positive, Reddit negative)
    STEALTH_SIGNAL     = "stealth_signal"        # Non-news signals (hiring, patents) without news coverage
```

The **stealth signal** alert is the killer feature: "Company X has filed 3 patents and posted 12 AI engineering jobs this month, but there's been zero news coverage." That's alpha.

### 3.4 Deep Dive (NEW)

On-demand deep research for any entity/topic:

```
User: "Deep dive on 寒武纪"

→ Orchestrator dispatches ALL agents in parallel:
  - News Intelligence: recent coverage, sentiment arc
  - Trend Detector: cross-source signal strength
  - Narrative Tracker: what narratives is it part of?
  - Sector Context: how does 半导体 sector look?
  - Adversarial: bull case vs bear case → verdict

→ Synthesized into a structured report:
  ┌──────────────────────────────────────┐
  │ 寒武纪 (688256) — Deep Intelligence │
  ├──────────────────────────────────────┤
  │ Signal Strength: ████████░░ 8/10    │
  │ Source Diversity: 7 source types     │
  │ Sentiment: 62 (cautiously positive) │
  │ Narrative: "国产AI芯片突破"          │
  ├──────────────────────────────────────┤
  │ 🐂 Bull Case                        │
  │ ...                                 │
  │ 🐻 Bear Case                        │
  │ ...                                 │
  │ ⚖️ Verdict                          │
  │ ...                                 │
  ├──────────────────────────────────────┤
  │ 📰 Key Recent Articles (5)         │
  │ 📊 Signal Timeline (30d chart)     │
  │ 🔗 Related Entities                │
  └──────────────────────────────────────┘
```

---

## What Gets Deleted

| File/Module | Action | Reason |
|-------------|--------|--------|
| `agents/technical_agent.py` | DELETE | ValueCell territory. AKShare TA is flaky and not our strength. |
| `agents/fundamental_agent.py` | DELETE | Financial statement analysis = ValueCell's job. |
| `integrations/fincept_bridge.py` | DELETE | Real-time market data integration we don't need. |
| `integrations/realtime_feed.py` | DELETE | Streaming prices. Not our game. |
| `integrations/price_alerts.py` | DELETE | Price-based alerts. Keep signal-based alerts only. |
| `modules/bloomberg_terminal.py` | DELETE | Bloomberg Terminal UI. We're not building Bloomberg. |
| `modules/screener_ui.py` | DELETE | Stock screener UI. |
| `utils/screener_engine.py` | DELETE | Stock screener engine. |
| `utils/screener_dsl.py` | DELETE | Screener query DSL. |
| `utils/sentiment_technicals.py` | REVIEW | Keep if it does news-based sentiment. Delete if it's TA indicators on sentiment data. |
| `utils/financial_signals.py` | SLIM | Keep basic "has this stock moved?" context. Remove TA calculations. |
| `utils/financial_signals_cn.py` | SLIM | Same — keep price context, remove TA. |
| `docs/BLOOMBERG_ROADMAP.md` | DELETE | We're not building Bloomberg. |
| `docs/SCREENER.md` | DELETE | Screener is gone. |
| `docs/REALTIME_*.md` | DELETE | Real-time infrastructure docs for features we're removing. |

## What Gets Created

| File/Module | Purpose |
|-------------|---------|
| `agents/trend_detector.py` | Cross-source emerging trend detection |
| `agents/narrative_tracker.py` | Narrative/story evolution tracking |
| `agents/prediction_engine.py` | Falsifiable event predictions with calibration |
| `utils/entity_store.py` | Unified entity graph (spine of the system) |
| `utils/market_context.py` | Lightweight daily price context (replaces all market data infra) |
| `utils/emergence_scorer.py` | Cross-source signal scoring for trend detection |
| `docs/ARCHITECTURE_V2.md` | This document |

---

## Migration Order

### Phase 1: Clean House (1-2 days)
1. Delete ValueCell-territory files (technical_agent, fundamental_agent, bloomberg_terminal, screener, fincept, realtime)
2. Create `utils/market_context.py` — lightweight replacement
3. Update orchestrator to remove deleted agents from registry
4. Run tests, fix any imports that break

### Phase 2: Entity Spine (2-3 days)
1. Build `utils/entity_store.py` with unified entity model
2. Wire existing `entity_resolver.py` and `entity_matcher.py` into it
3. Migrate `trend_radar.db` entity data into new store
4. Update `news_sentiment_agent` to use entity store

### Phase 3: New Agents (3-5 days)
1. Build `trend_detector.py` — cross-source pattern detection
2. Build `narrative_tracker.py` — story evolution
3. Refactor prediction engine into proper agent
4. Update orchestrator planner with new agent descriptions
5. Wire alerts to new agent outputs

### Phase 4: Daily Brief Upgrade (2-3 days)
1. Redesign daily brief template with new sections (trends, narratives, predictions)
2. Add alert feed view
3. Deep dive report template

---

## Success Metrics

**briefAI is succeeding when:**
- It surfaces a trend 2-3 days before mainstream news covers it
- Its cross-source signals correctly predict events (>60% accuracy)
- Dragon asks "what's happening in AI?" and gets a better answer than Bloomberg
- The stealth signal alerts find things that news hasn't covered yet

**briefAI is failing when:**
- It's being used to check stock prices (that's TradingView)
- Its "analysis" is just regurgitating RSI numbers
- The daily brief looks like a stock screener output
- Dragon has to go elsewhere for the "why" behind market moves
