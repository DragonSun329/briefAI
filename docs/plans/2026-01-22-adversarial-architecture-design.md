# Plan: Adversarial Intelligence Architecture (Devil's Advocate)

## Overview

To move BriefAI from a "news collector" to a "risk rating agency," we are implementing a three-agent adversarial workflow. This system calibrates confidence by pitting a "Hype-Man" (Growth) against a "Skeptic" (Risk), with an "Arbiter" synthesizing the final conviction score.

**Goal:** Assign conviction scores (0-100) to trending AI entities based on how well they survive adversarial scrutiny.

**Key Innovation:** Classification-aware scoring - OSS projects aren't penalized for "missing pricing."

## Architecture Components

### 1. Hype-Man Agent (The Bull)

**Role:** Identify breakout velocity and adoption signals.

**Input Data Sources:**
| Signal | Source | Metric |
|--------|--------|--------|
| GitHub stars | `github_enhanced_scraper` | Count + velocity (stars/week) |
| GitHub forks | `github_enhanced_scraper` | Fork count |
| HuggingFace downloads | `huggingface_scraper` | Download count |
| HuggingFace likes | `huggingface_scraper` | Like count |
| News volume | `news` pipeline | Article count |
| Social buzz | `reddit/hackernews_scraper` | Upvotes, comments |
| Product Hunt | `product_review_scraper` | Upvotes, ranking |

**Output Schema:**
```json
{
  "entity": "DeepSeek",
  "bull_thesis": "Fastest open-source LLM adoption in history: 50K GitHub stars in 3 weeks, #1 on HuggingFace, outperforming GPT-4 on MMLU.",
  "momentum_signals": [
    {"signal": "GitHub stars", "value": 52000, "velocity": "+8000/week"},
    {"signal": "HF downloads", "value": 2400000, "trend": "exponential"},
    {"signal": "News mentions", "value": 147, "sentiment": "positive"}
  ],
  "technical_velocity_score": 95
}
```

**System Prompt:**
```
You are a "Growth Analyst" identifying breakout trends in AI. Your job is to make the strongest possible BULL CASE for why this entity is gaining traction.

Focus on ADOPTION VELOCITY - not quality, not fundamentals. Your metrics:
- Raw popularity (stars, downloads, mentions)
- Growth rate (week-over-week acceleration)
- Community engagement (forks, issues, discussions)

Output a technical_velocity_score (0-100) where:
- 90-100: Viral (exponential growth, top trending)
- 70-89: Strong momentum (consistent growth)
- 50-69: Moderate interest (steady but not breakout)
- 0-49: Low signal (limited adoption)
```

---

### 2. Skeptic Agent (The Bear)

**Role:** Forensic analysis of commercial maturity, code health, and risk factors.

**Input Data Sources:**
| Signal | Source | Risk Type |
|--------|--------|-----------|
| Funding data | `funding_enricher`, `cn_ai_funding_lookup` | Financial substance |
| SEC filings | `financial_scorer` | Regulatory/IPO signals |
| G2/Capterra reviews | `product_review_scraper` | Enterprise PMF |
| Investor quality | `openbook_vc_scraper` | Smart money signal |
| Last commit date | `github_scraper` | Abandonment risk |
| Issue closure ratio | `github_scraper` | Maintenance debt |
| News sentiment | `news` pipeline | Reputation risk |

**System Prompt:**
```
You are the "Risk Officer" for an AI intelligence engine. Your goal is to identify **Structural Risks**, **Vaporware**, and **Commercial Weaknesses** in trending AI entities.

You act as the counterbalance to "Hype" (Twitter buzz/GitHub stars). You do not "hate" trends; you "stress-test" them.

## PHASE 1: CLASSIFICATION (Crucial)
Before scoring, determine what you are analyzing. This sets the grading curve.

1. **Open Source Project (OSS):** A library, framework, or model (e.g., AutoGPT, Llama-3).
   * *Success Metric:* Maintainer activity, community health, documentation.
   * *Forgivable:* No revenue, no pricing, no sales team.

2. **Commercial Product (SaaS):** A platform, API, or app (e.g., Jasper, Perplexity).
   * *Success Metric:* Revenue, enterprise logos, pricing tiers, compliance.
   * *Unforgivable:* No pricing, broken links, anonymous team.

## PHASE 2: FORENSIC ANALYSIS

### 1. The "Vaporware" Test (Code & Product)
* **OSS Risk:** Is the `last_commit_date` > 90 days? Is the README just a manifesto with no install instructions? Are issues piling up without answers?
* **SaaS Risk:** Is the "Get Started" button just a waitlist form? Is there a documentation portal, or just a landing page?

### 2. The "Sustainability" Test (Financial)
* **Burn Rate Risk:** If they raised funding >12 months ago with no new announcements, flag as "Zombie Unicorn" risk.
* **Business Model Risk:** If SaaS, is the pricing purely "Contact Sales" (Enterprise only) or is there Self-Serve? (Total opacity = high risk).
* **Audit Trail:** Do the founders have a track record, or are they anonymous avatars?

### 3. "Silence as Signal" (Context-Aware)
Interpret *missing* data based on the Classification:
* *Missing Pricing:* Fatal for SaaS. Irrelevant for OSS.
* *Missing Team Page:* Suspicious for SaaS (Scam risk). Acceptable for niche OSS.
* *Missing Case Studies:* High risk for "Enterprise" tools. Normal for "Developer" tools.

## PHASE 3: SCORING RUBRIC (0-100)

**Commercial Maturity Score:**
* 0-20: Hype only. No product, no company, just a repo/landing page.
* 21-50: Early Beta. Product exists, but unproven (no customers/revenue).
* 51-80: Growth. Verified funding, active users, some logos.
* 81-100: Established. Public pricing, case studies, compliance certifications (SOC2).

**Brand Safety Score:**
* Deduct points for: Security breaches (-30), Lawsuits (-20), Layoffs (-15), Founder drama (-10).
```

**Output Schema:**
```json
{
  "entity_type": "OSS_PROJECT",
  "risk_assessment": {
    "commercial_maturity_score": 40,
    "brand_safety_score": 80
  },
  "skeptic_verdict": {
    "bear_thesis": "Technically impressive demo, but high abandonment risk. The repo has 10k stars but hasn't been updated in 4 months.",
    "primary_risk_factor": "MAINTENANCE_DEBT",
    "red_flags": [
      {"signal": "Last commit > 120 days ago", "severity": "HIGH"},
      {"signal": "No documentation beyond README", "severity": "MEDIUM"},
      {"signal": "Issue tracker disabled", "severity": "MEDIUM"}
    ]
  },
  "missing_critical_signals": [
    "No contribution guidelines",
    "No license file"
  ],
  "confidence_in_assessment": "HIGH"
}
```

---

### 3. Arbiter Agent (The Judge)

**Role:** Synthesize conflicting Bull/Bear data into a single conviction score.

**Weighted Scoring Logic (OSS Defense):**

```python
def calculate_conviction(entity_type, technical_score, commercial_score, risk_penalty):
    """
    Dynamic weighting based on entity type.
    OSS projects get more credit for technical adoption.
    SaaS products must prove commercial viability.
    """
    if entity_type == "OSS_PROJECT":
        base_score = (technical_score * 0.7) + (commercial_score * 0.3)
    else:  # COMMERCIAL_SAAS
        base_score = (technical_score * 0.5) + (commercial_score * 0.5)

    # Momentum bonus for viral growth
    momentum_bonus = 10 if velocity == "exponential" else 0

    # Apply risk penalties
    conviction = base_score + momentum_bonus + risk_penalty

    return max(0, min(100, conviction))
```

**Conflict Intensity Calculation:**
```python
def calculate_conflict(technical_score, commercial_score):
    """
    Measures disagreement between Hype-Man and Skeptic.
    High conflict = interesting trend (viral but unproven).
    """
    gap = abs(technical_score - commercial_score)

    if gap > 40:
        return "HIGH"    # Big spread - needs human review
    elif gap > 20:
        return "MEDIUM"  # Moderate uncertainty
    else:
        return "LOW"     # Consensus (both agree)
```

**Recommendation States:**
| State | Trigger | Action |
|-------|---------|--------|
| `ALERT` | Conviction > 80 | Push notification. High confidence breakout. |
| `INVESTIGATE` | Conflict = HIGH | Needs human review. Big hype/substance gap. |
| `MONITOR` | Conviction 40-79 | Add to watchlist. Check back in 2 weeks. |
| `IGNORE` | Conviction < 40 OR risk_penalty > -30 | Filter out. Too early or too risky. |

**Output Schema:**
```json
{
  "entity": "DeepSeek",
  "entity_type": "OSS_PROJECT",
  "conviction_score": 72,
  "conflict_intensity": "HIGH",
  "verdict": {
    "bull_thesis": "Fastest open-source LLM adoption in history...",
    "bear_thesis": "Commercial viability unproven; regulatory cloud...",
    "synthesis": "Strong technical signal with unproven commercial path. Watch for enterprise adoption in next 90 days.",
    "key_uncertainty": "Will major cloud providers offer hosted DeepSeek?"
  },
  "signal_breakdown": {
    "technical_velocity": 95,
    "commercial_maturity": 40,
    "brand_safety": 80
  },
  "recommendation": "INVESTIGATE"
}
```

---

## Data Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Trend Radar (Input)                         │
│  Entity: "DeepSeek" | Rising Score: 85 | Mentions: 147          │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┴───────────────┐
          ▼                               ▼
┌─────────────────────┐         ┌─────────────────────┐
│    Hype-Man Agent   │         │   Skeptic Agent     │
│                     │         │                     │
│ Input: GitHub,      │         │ Input: Funding,     │
│   HF, News, Social  │         │   G2, SEC, Code age │
│                     │         │                     │
│ Output:             │         │ Output:             │
│  technical_velocity │         │  commercial_maturity│
│  bull_thesis        │         │  bear_thesis        │
│                     │         │  entity_type        │
└─────────┬───────────┘         └─────────┬───────────┘
          │                               │
          └───────────────┬───────────────┘
                          ▼
              ┌─────────────────────┐
              │   Arbiter Agent     │
              │                     │
              │ • Weighted scoring  │
              │ • Conflict calc     │
              │ • Recommendation    │
              └─────────┬───────────┘
                        ▼
              ┌─────────────────────┐
              │  Dashboard / API    │
              │                     │
              │ • Sort by conviction│
              │ • Filter by conflict│
              │ • Alert on ALERT    │
              └─────────────────────┘
```

---

## Database Schema

Add to `trend_radar.db`:

```sql
CREATE TABLE IF NOT EXISTS conviction_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- OSS_PROJECT | COMMERCIAL_SAAS

    -- Scores
    technical_velocity_score REAL,
    commercial_maturity_score REAL,
    brand_safety_score REAL,
    conviction_score REAL,

    -- Conflict
    conflict_intensity TEXT,  -- HIGH | MEDIUM | LOW
    recommendation TEXT,       -- ALERT | INVESTIGATE | MONITOR | IGNORE

    -- Theses
    bull_thesis TEXT,
    bear_thesis TEXT,
    synthesis TEXT,
    key_uncertainty TEXT,

    -- Red flags (JSON array)
    red_flags TEXT,
    missing_signals TEXT,

    -- Metadata
    analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    llm_model TEXT,
    prompt_version TEXT,

    UNIQUE(entity_name, analyzed_at)
);

CREATE INDEX idx_conviction_score ON conviction_scores(conviction_score DESC);
CREATE INDEX idx_conflict ON conviction_scores(conflict_intensity);
CREATE INDEX idx_recommendation ON conviction_scores(recommendation);
```

---

## API Endpoints

```python
# New endpoints for api/routers/conviction.py

GET /api/conviction/scores
# Returns all conviction scores, sortable by conviction_score, conflict_intensity
# Query params: min_conviction, max_conviction, conflict, recommendation, entity_type

GET /api/conviction/{entity_name}
# Returns full conviction analysis for a specific entity

POST /api/conviction/analyze
# Trigger adversarial analysis for a specific entity
# Body: {"entity_name": "DeepSeek", "force_refresh": false}

GET /api/conviction/alerts
# Returns entities with recommendation = "ALERT" or "INVESTIGATE"
```

---

## Implementation Roadmap

### Phase 1: Data Foundation
- [ ] Add `last_commit_date` to GitHub scraper
- [ ] Add pricing page detection to web scraper
- [ ] Ensure funding data is enriched for all trending entities

### Phase 2: Agent Implementation
- [ ] Create `agents/hypeman.py` with prompt template
- [ ] Create `agents/skeptic.py` with classification logic
- [ ] Create `agents/arbiter.py` with weighted scoring

### Phase 3: Orchestration
- [ ] Create `AdversarialPipeline` class
- [ ] Run Hype-Man and Skeptic in parallel
- [ ] Store results in `conviction_scores` table

### Phase 4: Integration
- [ ] Add `/api/conviction/*` endpoints
- [ ] Add conviction column to dashboard
- [ ] Add conflict filter to trend radar view

---

## Success Criteria

1. **Accuracy:** Conviction scores correlate with 90-day outcomes (backtestable)
2. **Coverage:** Can analyze any entity in trend_radar.db
3. **Speed:** Full analysis completes in < 10 seconds
4. **Explainability:** Bull/bear theses are human-readable and cite data

---

## Example Output

**Entity:** DeepSeek (OSS_PROJECT)

| Metric | Score | Weight | Contribution |
|--------|-------|--------|--------------|
| Technical Velocity | 95 | 0.70 | 66.5 |
| Commercial Maturity | 40 | 0.30 | 12.0 |
| Momentum Bonus | +10 | - | 10.0 |
| Risk Penalty | -7 | - | -7.0 |
| **Conviction** | **81.5** | - | - |

**Conflict:** HIGH (95 - 40 = 55 point gap)

**Recommendation:** ALERT (Conviction > 80)

**Verdict:** "Viral open-source LLM with unprecedented adoption velocity. Commercial path unclear but irrelevant for OSS. Watch for: (1) Major cloud provider partnerships, (2) Enterprise fine-tuning services, (3) Regulatory clarity on China-origin models."
