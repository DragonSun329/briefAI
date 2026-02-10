# React Dashboard Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace Streamlit dashboard with React + FastAPI for proper sorting, filtering, and UX control.

**Architecture:** FastAPI backend wraps existing Python modules, serves JSON. React frontend handles all UI, sorting, filtering client-side.

**Tech Stack:** FastAPI, React + Vite, Recharts, TanStack Table, Tailwind CSS

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     React Frontend (port 5173)              │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐           │
│  │ 洞察    │ │ 文章    │ │ AI速查  │ │ 雷达    │           │
│  │Insights │ │Articles │ │Shortlist│ │ Radar   │           │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘           │
│       └───────────┴───────────┴───────────┘                 │
│                        │ fetch()                            │
└────────────────────────┼────────────────────────────────────┘
                         │
┌────────────────────────┼────────────────────────────────────┐
│                   FastAPI Backend (port 8000)               │
│  /api/insights  /api/articles  /api/companies  /api/signals │
│       │              │              │              │        │
│  ┌────┴──────────────┴──────────────┴──────────────┴────┐   │
│  │           Existing Python modules                     │   │
│  │  CrossPipelineAnalyzer, SignalStore, generate_shortlist│  │
│  └───────────────────────────────────────────────────────┘   │
│                          │                                   │
│  ┌───────────────────────┴───────────────────────────────┐   │
│  │  Data: SQLite DBs + JSON cache files                  │   │
│  └───────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

```
GET /api/dates                    → Available dates for date picker
GET /api/insights?date=YYYYMMDD   → Summary stats + bubble chart + hot entities

GET /api/articles/{pipeline}?date=YYYYMMDD
    pipeline = news | product | investing

GET /api/entities/cross?date=YYYYMMDD&min_pipelines=2
GET /api/entities/hot?date=YYYYMMDD&limit=10

GET /api/companies                → All companies (frontend sorts/paginates)
GET /api/companies/filters        → Available categories and stages

GET /api/signals/entities?limit=50
GET /api/signals/divergence

GET /api/buckets
GET /api/buckets/{bucket_id}
GET /api/buckets/alerts
```

---

## Frontend Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── Layout.jsx          # Nav tabs, header, date picker
│   │   ├── ArticleCard.jsx     # Reusable article display
│   │   ├── CompanyTable.jsx    # TanStack Table for shortlist
│   │   ├── BubbleChart.jsx     # Recharts scatter for entities
│   │   ├── RadarChart.jsx      # Signal radar visualization
│   │   ├── HeatmapChart.jsx    # Bucket timeline
│   │   └── StatCard.jsx        # Metric display cards
│   │
│   ├── pages/
│   │   ├── Insights.jsx        # Summary + bubble + hot entities
│   │   ├── Articles.jsx        # News/Product/Investing (shared)
│   │   ├── Shortlist.jsx       # Company table with tabs
│   │   ├── SignalRadar.jsx     # Entity signals + divergence
│   │   └── BucketRadar.jsx     # Bucket quad chart + alerts
│   │
│   ├── hooks/
│   │   └── useApi.js           # fetch wrapper with loading/error
│   │
│   ├── App.jsx                 # Router + tab navigation
│   └── main.jsx                # Entry point
│
├── index.html
├── tailwind.config.js
├── vite.config.js
└── package.json
```

---

## Backend Structure

```
api/
├── main.py                 # FastAPI app, CORS, mount routers
├── routers/
│   ├── insights.py         # /api/insights, /api/dates
│   ├── articles.py         # /api/articles/{pipeline}
│   ├── companies.py        # /api/companies, /api/companies/filters
│   ├── signals.py          # /api/signals/*
│   └── buckets.py          # /api/buckets/*
└── requirements.txt        # fastapi, uvicorn
```

---

## Pages (Feature Parity)

### 1. 洞察 (Insights)
- 4 stat cards: News count, Product count, Investing count, Cross-pipeline entities
- Bubble chart: Entity mentions across pipelines (Recharts ScatterChart)
- Hot entities table: Top 10 by total mentions
- Cross-pipeline section: Expandable entity details

### 2. AI新闻 / 产品 / 投资 (Articles)
- Single page component, pipeline passed as prop
- Article cards with score badge, source, expandable summary
- Client-side search/filter

### 3. AI速查 (Shortlist)
- Sub-tabs: 全部, 巨头, 新兴, 最热, 类别
- TanStack Table with:
  - Sortable columns (click header to sort ALL data)
  - Filter dropdowns (category, stage, min sources)
  - Client-side pagination
- Columns: Company, Category, Stage, Funding $M, Revenue $M, Founded, CB Rank

### 4. 信号雷达 (Signal Radar)
- Top entities by composite score
- Divergence grid: Opportunities vs Risks
- Radar chart per entity (5 dimensions)

### 5. 趋势桶雷达 (Bucket Radar)
- Scatter plot: TMS vs CCS with lifecycle coloring
- Timeline heatmap
- Alert panel
- Bucket drill-down

---

## Running

```bash
# Terminal 1: API
cd api && uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev
```

---

## Production

FastAPI serves built React files:
```python
app.mount("/", StaticFiles(directory="frontend/dist", html=True))
```

Single process, single port (8000).