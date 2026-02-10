# briefAI Entity Coverage Analysis

**Generated:** 2026-01-26
**Total Entities:** 105

## Coverage Summary

### By Status
| Status | Count | Notes |
|--------|-------|-------|
| Public | 52 | Direct ticker trading |
| Private | 53 | Tracked via proxies or alternative signals |

### By Sector
| Sector | Count | Key Players |
|--------|-------|-------------|
| AI Foundation | 18 | OpenAI, Anthropic, Google, Meta, Mistral |
| AI Chips | 20 | NVIDIA, AMD, Intel, TSMC, Cerebras |
| AI Cloud/Infrastructure | 14 | AWS, CoreWeave, Together, Lambda |
| AI Coding | 8 | Cursor, Replit, Codeium, GitHub Copilot |
| AI Enterprise | 10 | Palantir, Salesforce, ServiceNow |
| Vision/Multimodal | 8 | Midjourney, Stability, Runway, Pika |
| Chinese AI | 15 | DeepSeek, Zhipu, Moonshot, SenseTime |
| Robotics | 7 | Figure, Boston Dynamics, 1X, Unitree |
| Other | 5 | Various specialized players |

## Coverage Gaps

### 1. Companies NOT Yet Tracked (Future Additions)
- **AI Safety/Alignment:** Redwood Research, ARC, MIRI
- **AI Hardware:** Etched, MatX, d-Matrix
- **Chinese Hardware:** Huawei HiSilicon, Enflame
- **Defense AI:** Anduril, Shield AI, Palantir (already tracked)
- **Biotech AI:** Recursion, Insitro, Isomorphic Labs
- **Robotics:** Apptronik, Sanctuary AI, Physical Intelligence

### 2. Ticker Mapping Challenges

#### Private Companies with No Good Proxy
| Company | Issue | Alternative Tracking |
|---------|-------|---------------------|
| ByteDance | Too large/diversified | Track via news sentiment |
| DeepSeek | No public investors | GitHub/HF activity |
| Groq | No strategic investors public | News coverage |
| SambaNova | Private enterprise focus | Partnership news |
| Poolside | Stealth mode | Funding announcements |

#### Proxy Quality Ratings
| Private Company | Proxy | Quality | Notes |
|-----------------|-------|---------|-------|
| OpenAI → MSFT | Good | High partnership revenue exposure |
| Anthropic → GOOGL/AMZN | Medium | Multiple investors dilutes signal |
| xAI → TSLA | Medium | Elon overlap, but separate companies |
| Mistral → MSFT | Low | Small partnership, limited exposure |
| Midjourney → ADBE | Low | Competitor, not investor |

### 3. Data Source Gaps

#### Missing Data Sources (Not Yet Integrated)
- **Crunchbase:** Funding rounds, valuations
- **LinkedIn:** Employee count, job postings
- **SimilarWeb:** Website traffic trends
- **Sensor Tower:** App downloads
- **arXiv API:** Research paper tracking
- **Twitter/X API:** Social sentiment

#### Available Data Sources
- ✅ GitHub API (stars, forks, commits)
- ✅ HuggingFace API (model downloads)
- ✅ Yahoo Finance (public tickers)
- ✅ News scraping (sentiment)

### 4. Chinese Entity Challenges

#### Accessible via HK/US Listings
- Alibaba (BABA, 9988.HK) ✅
- Tencent (0700.HK, TCEHY) ✅
- Baidu (BIDU, 9888.HK) ✅
- SenseTime (0020.HK) ✅
- Kuaishou (1024.HK) ✅

#### A-Share Access Issues
- Some tickers require specialized data providers
- Real-time data may need Wind/Bloomberg
- Recommend: Use ETFs (515980.SS) as sector proxies

#### Private Chinese Companies
Most major Chinese LLM companies are private:
- DeepSeek, Zhipu, Moonshot, MiniMax, Baichuan, 01.AI, StepFun

**Tracking Strategy:** 
- GitHub/HF activity for open-weight releases
- News monitoring for funding/partnerships
- Parent company proxies (Alibaba for Moonshot/Baichuan)

### 5. Crypto AI Token Tracking
Currently tracked:
- FET, AGIX, OCEAN, TAO, RNDR, WLD, ARKM, AKT, NOS, VIRTUAL, AI16Z

Potential additions:
- PRIME (Primordia)
- PAAL (PAAL AI)
- NFP (NFPrompt)
- RSS3

## Scoring Calibration Notes

### New Entity Calibration Required
Run `python -m briefai.calibration` after adding:
1. Ensure 30 days of price history available
2. Validate sentiment sources work
3. Check conviction scoring bounds

### Proxy Weighting
For private companies with multiple proxies, use:
```json
{
  "anthropic": {
    "GOOGL": 0.5,
    "AMZN": 0.5
  }
}
```

## Maintenance Schedule

### Weekly
- [ ] Check for IPO filings (private → public transitions)
- [ ] Monitor funding round announcements
- [ ] Update valuation estimates

### Monthly
- [ ] Full entity relationship audit
- [ ] Proxy quality review
- [ ] Add newly prominent companies

### Quarterly
- [ ] Major coverage expansion review
- [ ] Retire defunct companies
- [ ] Recalibrate scoring models
