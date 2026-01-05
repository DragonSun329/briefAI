# Trend Radar Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Data API for querying VC/startup signals with on-demand refresh across three intensity tiers.

**Architecture:** FastAPI service with SQLite storage, pluggable parser registry for each VC source, tier-based source configuration with inheritance, and an internal Python client for Streamlit integration.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, BeautifulSoup4, Playwright (for JS sites), SQLite (dev) / Postgres (prod)

---

## Phase 1: Foundation (MVP)

### Task 1: Create Project Structure

**Files:**
- Create: `trend_radar/__init__.py`
- Create: `trend_radar/models.py`
- Create: `trend_radar/parsers/__init__.py`
- Create: `utils/config_loader.py`
- Create: `config/vc_sources.json`
- Create: `tests/trend_radar/__init__.py`

**Step 1: Create the trend_radar package structure**

```bash
mkdir -p trend_radar/parsers
mkdir -p tests/trend_radar
touch trend_radar/__init__.py
touch trend_radar/parsers/__init__.py
touch tests/trend_radar/__init__.py
```

**Step 2: Create the config loader utility**

Create `utils/config_loader.py`:

```python
"""Shared configuration loading utilities."""

import json
from pathlib import Path
from typing import Dict, List, Optional

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_vc_sources(path: Optional[str] = None) -> Dict:
    """Load VC sources configuration."""
    config_path = Path(path) if path else CONFIG_DIR / "vc_sources.json"
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def load_sources_for_tier(tier: Optional[str] = None, config: Optional[Dict] = None) -> List[Dict]:
    """
    Load sources for a specific tier, respecting inheritance.

    Tiers inherit from parent: deep -> standard -> lite
    Sources are deduped by id (child tier can override parent).
    """
    if config is None:
        config = load_vc_sources()

    tier = tier or config.get("default_tier", "standard")

    if tier not in config.get("tiers", {}):
        raise ValueError(f"Unknown tier: {tier}. Available: {list(config['tiers'].keys())}")

    # Build inheritance chain: [requested_tier, parent, grandparent, ...]
    inheritance_chain = []
    current = tier
    while current:
        inheritance_chain.append(current)
        current = config["tiers"][current].get("inherits")

    # Process from base (lite) to requested tier, deduping by id
    sources_by_id = {}
    for tier_name in reversed(inheritance_chain):
        for source in config["tiers"][tier_name].get("sources", []):
            if source.get("enabled", True):
                sources_by_id[source["id"]] = source

    return list(sources_by_id.values())
```

**Step 3: Create initial VC sources config**

Create `config/vc_sources.json`:

```json
{
  "default_tier": "standard",
  "tiers": {
    "lite": {
      "description": "Quick scan - highest signal sources (5-10)",
      "sources": [
        {
          "id": "yc_directory",
          "name": "Y Combinator",
          "type": "accelerator",
          "url": "https://www.ycombinator.com/companies",
          "filter_url": "https://www.ycombinator.com/companies?tags=AI",
          "parse_strategy": "yc_grid",
          "frequency": "daily",
          "enabled": true,
          "requires_js": true,
          "notes": "Use AI tag filter; respects robots.txt"
        },
        {
          "id": "a16z_portfolio",
          "name": "Andreessen Horowitz",
          "type": "vc_portfolio",
          "url": "https://a16z.com/portfolio/",
          "parse_strategy": "a16z_cards",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": false,
          "notes": "Filter by AI/ML category manually"
        },
        {
          "id": "sequoia_companies",
          "name": "Sequoia Capital",
          "type": "vc_portfolio",
          "url": "https://www.sequoiacap.com/our-companies/",
          "parse_strategy": "sequoia_list",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": true,
          "notes": "US portfolio page"
        }
      ]
    },
    "standard": {
      "description": "Full coverage - top VCs + accelerators (20-30)",
      "inherits": "lite",
      "sources": [
        {
          "id": "lightspeed_companies",
          "name": "Lightspeed Venture Partners",
          "type": "vc_portfolio",
          "url": "https://lsvp.com/companies/",
          "parse_strategy": "lightspeed_table",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": false,
          "notes": "Has stage and year fields"
        },
        {
          "id": "index_ventures",
          "name": "Index Ventures",
          "type": "vc_portfolio",
          "url": "https://www.indexventures.com/companies/",
          "parse_strategy": "index_grid",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": true,
          "notes": "Europe/US early and growth stage"
        },
        {
          "id": "greylock_portfolio",
          "name": "Greylock",
          "type": "vc_portfolio",
          "url": "https://greylock.com/portfolio/",
          "parse_strategy": "greylock_grid",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": false,
          "notes": "Has sector and stage info"
        }
      ]
    },
    "deep": {
      "description": "Comprehensive - all sources + cross-reference DBs (50-100+)",
      "inherits": "standard",
      "sources": [
        {
          "id": "bessemer_companies",
          "name": "Bessemer Venture Partners",
          "type": "vc_portfolio",
          "url": "https://www.bvp.com/companies",
          "parse_strategy": "bessemer_list",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": false,
          "notes": "Long-term portfolio tracking"
        },
        {
          "id": "hongshan_portfolio",
          "name": "HongShan (红杉中国)",
          "type": "vc_portfolio",
          "url": "https://www.hongshan.com/portfolio",
          "parse_strategy": "hongshan_grid",
          "frequency": "weekly",
          "enabled": true,
          "requires_js": true,
          "notes": "Partial member list only"
        }
      ]
    }
  }
}
```

**Step 4: Commit**

```bash
git add trend_radar/ utils/config_loader.py config/vc_sources.json tests/trend_radar/
git commit -m "feat(trend-radar): create project structure and config loader"
```

---

### Task 2: Add Config Loader Tests

**Files:**
- Create: `tests/trend_radar/test_config_loader.py`

**Step 1: Write the failing tests**

Create `tests/trend_radar/test_config_loader.py`:

```python
"""Tests for VC sources config loader."""

import pytest
from utils.config_loader import load_vc_sources, load_sources_for_tier


class TestLoadVcSources:
    """Tests for load_vc_sources function."""

    def test_loads_config_from_default_path(self):
        """Should load vc_sources.json from config directory."""
        config = load_vc_sources()

        assert "default_tier" in config
        assert "tiers" in config
        assert "lite" in config["tiers"]

    def test_config_has_required_tier_structure(self):
        """Each tier should have description and sources."""
        config = load_vc_sources()

        for tier_name, tier_data in config["tiers"].items():
            assert "description" in tier_data, f"Tier {tier_name} missing description"
            assert "sources" in tier_data or "inherits" in tier_data, \
                f"Tier {tier_name} must have sources or inherit"


class TestLoadSourcesForTier:
    """Tests for load_sources_for_tier function."""

    def test_lite_tier_returns_only_lite_sources(self):
        """Lite tier should return only its own sources."""
        sources = load_sources_for_tier("lite")

        assert len(sources) >= 1
        source_ids = [s["id"] for s in sources]
        assert "yc_directory" in source_ids

    def test_standard_tier_inherits_from_lite(self):
        """Standard tier should include all lite sources plus its own."""
        lite_sources = load_sources_for_tier("lite")
        standard_sources = load_sources_for_tier("standard")

        assert len(standard_sources) > len(lite_sources)

        # All lite source ids should be in standard
        lite_ids = {s["id"] for s in lite_sources}
        standard_ids = {s["id"] for s in standard_sources}
        assert lite_ids.issubset(standard_ids)

    def test_deep_tier_inherits_from_standard(self):
        """Deep tier should include all standard sources plus its own."""
        standard_sources = load_sources_for_tier("standard")
        deep_sources = load_sources_for_tier("deep")

        assert len(deep_sources) > len(standard_sources)

        standard_ids = {s["id"] for s in standard_sources}
        deep_ids = {s["id"] for s in deep_sources}
        assert standard_ids.issubset(deep_ids)

    def test_disabled_sources_are_excluded(self):
        """Sources with enabled=false should not be returned."""
        sources = load_sources_for_tier("lite")

        for source in sources:
            assert source.get("enabled", True) is True

    def test_default_tier_used_when_none_specified(self):
        """Should use default_tier from config when tier is None."""
        config = load_vc_sources()
        default_tier = config["default_tier"]

        sources_default = load_sources_for_tier(None)
        sources_explicit = load_sources_for_tier(default_tier)

        assert len(sources_default) == len(sources_explicit)

    def test_invalid_tier_raises_error(self):
        """Should raise ValueError for unknown tier."""
        with pytest.raises(ValueError, match="Unknown tier"):
            load_sources_for_tier("nonexistent")

    def test_each_source_has_required_fields(self):
        """Each source should have id, name, url, parse_strategy."""
        sources = load_sources_for_tier("deep")

        required_fields = ["id", "name", "url", "parse_strategy"]
        for source in sources:
            for field in required_fields:
                assert field in source, f"Source {source.get('id', 'unknown')} missing {field}"
```

**Step 2: Run tests to verify they pass**

```bash
pytest tests/trend_radar/test_config_loader.py -v
```

Expected: All tests PASS

**Step 3: Commit**

```bash
git add tests/trend_radar/test_config_loader.py
git commit -m "test(trend-radar): add config loader tests"
```

---

### Task 3: Create Database Models

**Files:**
- Create: `trend_radar/models.py`
- Create: `tests/trend_radar/test_models.py`

**Step 1: Write the failing test**

Create `tests/trend_radar/test_models.py`:

```python
"""Tests for Trend Radar database models."""

import pytest
from datetime import datetime, date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from trend_radar.models import Base, Source, Company, Observation


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestSourceModel:
    """Tests for Source model."""

    def test_create_source(self, db_session):
        """Should create a source with required fields."""
        source = Source(
            id="yc_directory",
            name="Y Combinator",
            type="accelerator",
            url="https://www.ycombinator.com/companies",
            parse_strategy="yc_grid",
            tier=1
        )
        db_session.add(source)
        db_session.commit()

        fetched = db_session.query(Source).filter_by(id="yc_directory").first()
        assert fetched is not None
        assert fetched.name == "Y Combinator"
        assert fetched.tier == 1


class TestCompanyModel:
    """Tests for Company model."""

    def test_create_company(self, db_session):
        """Should create a company with required fields."""
        company = Company(
            name="Acme AI",
            normalized_name="acme-ai",
            website="https://acme.ai"
        )
        db_session.add(company)
        db_session.commit()

        fetched = db_session.query(Company).filter_by(normalized_name="acme-ai").first()
        assert fetched is not None
        assert fetched.name == "Acme AI"

    def test_company_has_timestamps(self, db_session):
        """Company should track first_seen_global and last_seen_global."""
        company = Company(
            name="Acme AI",
            normalized_name="acme-ai",
            first_seen_global=date(2025, 1, 1),
            last_seen_global=date(2025, 1, 5)
        )
        db_session.add(company)
        db_session.commit()

        fetched = db_session.query(Company).first()
        assert fetched.first_seen_global == date(2025, 1, 1)


class TestObservationModel:
    """Tests for Observation model."""

    def test_create_observation_with_relationships(self, db_session):
        """Should link observation to source and company."""
        source = Source(
            id="yc_directory",
            name="Y Combinator",
            type="accelerator",
            url="https://yc.com",
            parse_strategy="yc_grid",
            tier=1
        )
        company = Company(
            name="Acme AI",
            normalized_name="acme-ai"
        )
        db_session.add_all([source, company])
        db_session.commit()

        observation = Observation(
            source_id=source.id,
            company_id=company.id,
            first_seen=date(2025, 1, 5),
            last_seen=date(2025, 1, 5),
            batch="W25",
            industry_tags=["AI", "DevTools"]
        )
        db_session.add(observation)
        db_session.commit()

        fetched = db_session.query(Observation).first()
        assert fetched.source.name == "Y Combinator"
        assert fetched.company.name == "Acme AI"
        assert fetched.batch == "W25"
        assert "AI" in fetched.industry_tags
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/trend_radar/test_models.py -v
```

Expected: FAIL with import error (models not implemented)

**Step 3: Write the implementation**

Create `trend_radar/models.py`:

```python
"""Database models for Trend Radar."""

import os
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    create_engine, Column, String, Integer, Boolean, Date, DateTime,
    ForeignKey, Text, JSON, Float
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker

# Database URL from environment, defaulting to SQLite for dev
DATABASE_URL = os.getenv(
    "TREND_RADAR_DB_URL",
    "sqlite:///data/trend_radar.db"
)

Base = declarative_base()


class Source(Base):
    """A VC portfolio or accelerator source to monitor."""

    __tablename__ = "sources"

    id = Column(String(100), primary_key=True)  # e.g., "yc_directory"
    name = Column(String(200), nullable=False)   # e.g., "Y Combinator"
    type = Column(String(50), nullable=False)    # "vc_portfolio" or "accelerator"
    url = Column(String(500), nullable=False)
    filter_url = Column(String(500), nullable=True)
    parse_strategy = Column(String(100), nullable=False)
    tier = Column(Integer, nullable=False, default=1)  # 1=lite, 2=standard, 3=deep
    frequency = Column(String(20), default="weekly")
    enabled = Column(Boolean, default=True)
    requires_js = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    last_fetched = Column(DateTime, nullable=True)

    # Relationships
    observations = relationship("Observation", back_populates="source")


class Company(Base):
    """A startup/company discovered from VC sources."""

    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    normalized_name = Column(String(200), nullable=False, unique=True, index=True)
    website = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    founded_year = Column(Integer, nullable=True)
    country = Column(String(100), nullable=True)

    # Precomputed metrics
    source_count = Column(Integer, default=0)
    first_seen_global = Column(Date, nullable=True)
    last_seen_global = Column(Date, nullable=True)
    rising_score = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    observations = relationship("Observation", back_populates="company")


class Observation(Base):
    """A sighting of a company in a specific source."""

    __tablename__ = "observations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(100), ForeignKey("sources.id"), nullable=False)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False)

    first_seen = Column(Date, nullable=False)
    last_seen = Column(Date, nullable=False)

    # Source-specific metadata
    stage = Column(String(50), nullable=True)       # "Seed", "Series A", etc.
    batch = Column(String(20), nullable=True)       # "W25", "S24" for YC
    industry_tags = Column(JSON, default=list)      # ["AI", "DevTools"]
    raw_data = Column(JSON, nullable=True)          # Original scraped data

    # Relationships
    source = relationship("Source", back_populates="observations")
    company = relationship("Company", back_populates="observations")


def get_engine():
    """Get SQLAlchemy engine."""
    return create_engine(DATABASE_URL)


def get_session():
    """Get a new database session."""
    engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/trend_radar/test_models.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add trend_radar/models.py tests/trend_radar/test_models.py
git commit -m "feat(trend-radar): add SQLAlchemy database models"
```

---

### Task 4: Create Parser Registry and Base Parser

**Files:**
- Create: `trend_radar/parsers/__init__.py`
- Create: `trend_radar/parsers/base.py`
- Create: `tests/trend_radar/test_parser_registry.py`

**Step 1: Write the failing test**

Create `tests/trend_radar/test_parser_registry.py`:

```python
"""Tests for parser registry."""

import pytest
from trend_radar.parsers import get_parser, register_parser, PARSER_REGISTRY


class TestParserRegistry:
    """Tests for parser registration and retrieval."""

    def test_get_registered_parser(self):
        """Should return parser function for known strategy."""
        # Register a test parser
        def dummy_parser(html: str, config: dict) -> list:
            return []

        register_parser("test_strategy", dummy_parser)

        parser = get_parser("test_strategy")
        assert parser == dummy_parser

    def test_get_unknown_parser_raises_error(self):
        """Should raise ValueError for unknown parse strategy."""
        with pytest.raises(ValueError, match="Unknown parse_strategy"):
            get_parser("nonexistent_strategy")

    def test_parser_returns_list_of_dicts(self):
        """Parser function should return list of company dicts."""
        def sample_parser(html: str, config: dict) -> list:
            return [
                {"name": "Test Co", "website": "https://test.co"}
            ]

        register_parser("sample", sample_parser)
        parser = get_parser("sample")

        result = parser("<html></html>", {"id": "test"})
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "Test Co"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/trend_radar/test_parser_registry.py -v
```

Expected: FAIL with import error

**Step 3: Write the implementation**

Update `trend_radar/parsers/__init__.py`:

```python
"""
Parser registry for VC portfolio sources.

Each source has a unique parse_strategy that maps to a parser function.
Parsers are pure functions: (html, source_config) -> list[dict]
"""

from typing import Callable, Dict, List

# Registry mapping strategy names to parser functions
PARSER_REGISTRY: Dict[str, Callable[[str, dict], List[dict]]] = {}


def register_parser(strategy: str, parser_fn: Callable[[str, dict], List[dict]]) -> None:
    """Register a parser function for a strategy name."""
    PARSER_REGISTRY[strategy] = parser_fn


def get_parser(strategy: str) -> Callable[[str, dict], List[dict]]:
    """Get parser function for a strategy name."""
    if strategy not in PARSER_REGISTRY:
        available = list(PARSER_REGISTRY.keys())
        raise ValueError(
            f"Unknown parse_strategy: {strategy}. "
            f"Available: {available}"
        )
    return PARSER_REGISTRY[strategy]


# Import parsers to trigger registration
# (Add imports here as parsers are created)
# from trend_radar.parsers import yc_grid, a16z_cards, ...
```

Create `trend_radar/parsers/base.py`:

```python
"""Base utilities for parsers."""

from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from loguru import logger


def normalize_company_name(name: str) -> str:
    """
    Normalize company name for deduplication.

    Examples:
        "Acme AI, Inc." -> "acme-ai-inc"
        "OpenAI" -> "openai"
    """
    import re

    # Lowercase
    normalized = name.lower().strip()

    # Remove common suffixes
    for suffix in [", inc.", ", inc", " inc.", " inc", ", llc", " llc", ", ltd", " ltd"]:
        if normalized.endswith(suffix):
            normalized = normalized[:-len(suffix)]

    # Replace non-alphanumeric with hyphens
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)

    # Remove leading/trailing hyphens
    normalized = normalized.strip("-")

    return normalized


def create_company_dict(
    name: str,
    website: Optional[str] = None,
    description: Optional[str] = None,
    industry_tags: Optional[List[str]] = None,
    batch: Optional[str] = None,
    stage: Optional[str] = None,
    country: Optional[str] = None,
    founded_year: Optional[int] = None,
    raw_data: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create a normalized company dictionary.

    All parsers should use this to ensure consistent output format.
    """
    return {
        "name": name.strip(),
        "normalized_name": normalize_company_name(name),
        "website": website.strip() if website else None,
        "description": description.strip() if description else None,
        "industry_tags": industry_tags or [],
        "batch": batch,
        "stage": stage,
        "country": country,
        "founded_year": founded_year,
        "raw_data": raw_data,
    }


def safe_select_text(element, selector: str, default: str = "") -> str:
    """Safely select and extract text from a BeautifulSoup element."""
    if element is None:
        return default
    found = element.select_one(selector)
    return found.get_text(strip=True) if found else default


def safe_get_attr(element, attr: str, default: str = "") -> str:
    """Safely get an attribute from a BeautifulSoup element."""
    if element is None:
        return default
    return element.get(attr, default) or default
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/trend_radar/test_parser_registry.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add trend_radar/parsers/ tests/trend_radar/test_parser_registry.py
git commit -m "feat(trend-radar): add parser registry and base utilities"
```

---

### Task 5: Implement YC Directory Parser

**Files:**
- Create: `trend_radar/parsers/yc_grid.py`
- Create: `tests/fixtures/yc_grid_sample.html`
- Create: `tests/trend_radar/test_yc_parser.py`

**Step 1: Create test fixture**

Create `tests/fixtures/yc_grid_sample.html`:

```html
<!DOCTYPE html>
<html>
<head><title>YC Companies</title></head>
<body>
<div class="company-card" data-href="https://anthropic.com">
  <span class="company-name">Anthropic</span>
  <span class="company-description">AI safety company building reliable AI systems</span>
  <span class="batch">S21</span>
  <div class="tags">
    <span class="tag">Artificial Intelligence</span>
    <span class="tag">B2B</span>
  </div>
  <span class="location">San Francisco, CA</span>
</div>
<div class="company-card" data-href="https://openai.com">
  <span class="company-name">OpenAI</span>
  <span class="company-description">Creating safe AGI</span>
  <span class="batch">W16</span>
  <div class="tags">
    <span class="tag">Artificial Intelligence</span>
  </div>
  <span class="location">San Francisco, CA</span>
</div>
<div class="company-card">
  <!-- Missing name - should be skipped -->
  <span class="company-description">Some description</span>
</div>
</body>
</html>
```

**Step 2: Write the failing test**

Create `tests/trend_radar/test_yc_parser.py`:

```python
"""Tests for YC directory parser."""

import pytest
from pathlib import Path

from trend_radar.parsers.yc_grid import parse_yc_grid


@pytest.fixture
def yc_sample_html():
    """Load sample YC HTML fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "yc_grid_sample.html"
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def source_config():
    """Sample source config for YC."""
    return {
        "id": "yc_directory",
        "name": "Y Combinator",
        "type": "accelerator"
    }


class TestYCGridParser:
    """Tests for parse_yc_grid function."""

    def test_parses_company_cards(self, yc_sample_html, source_config):
        """Should extract companies from YC grid."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        assert len(companies) == 2  # Skips card without name

    def test_extracts_company_name(self, yc_sample_html, source_config):
        """Should extract company name."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        names = [c["name"] for c in companies]
        assert "Anthropic" in names
        assert "OpenAI" in names

    def test_extracts_normalized_name(self, yc_sample_html, source_config):
        """Should create normalized name for dedup."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        anthropic = next(c for c in companies if c["name"] == "Anthropic")
        assert anthropic["normalized_name"] == "anthropic"

    def test_extracts_website(self, yc_sample_html, source_config):
        """Should extract website URL."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        anthropic = next(c for c in companies if c["name"] == "Anthropic")
        assert anthropic["website"] == "https://anthropic.com"

    def test_extracts_batch(self, yc_sample_html, source_config):
        """Should extract YC batch (e.g., S21, W16)."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        anthropic = next(c for c in companies if c["name"] == "Anthropic")
        assert anthropic["batch"] == "S21"

    def test_extracts_industry_tags(self, yc_sample_html, source_config):
        """Should extract industry tags."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        anthropic = next(c for c in companies if c["name"] == "Anthropic")
        assert "Artificial Intelligence" in anthropic["industry_tags"]
        assert "B2B" in anthropic["industry_tags"]

    def test_extracts_description(self, yc_sample_html, source_config):
        """Should extract company description."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        anthropic = next(c for c in companies if c["name"] == "Anthropic")
        assert "AI safety" in anthropic["description"]

    def test_skips_cards_without_name(self, yc_sample_html, source_config):
        """Should skip company cards that have no name."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        # The fixture has 3 cards, but one has no name
        assert len(companies) == 2

    def test_preserves_raw_data(self, yc_sample_html, source_config):
        """Should preserve raw HTML snippet for debugging."""
        companies = parse_yc_grid(yc_sample_html, source_config)

        anthropic = next(c for c in companies if c["name"] == "Anthropic")
        assert "raw_data" in anthropic
        assert "html" in anthropic["raw_data"]
```

**Step 3: Run test to verify it fails**

```bash
pytest tests/trend_radar/test_yc_parser.py -v
```

Expected: FAIL with import error

**Step 4: Write the implementation**

Create `trend_radar/parsers/yc_grid.py`:

```python
"""Parser for Y Combinator company directory."""

from typing import Dict, List, Any
from bs4 import BeautifulSoup
from loguru import logger

from trend_radar.parsers import register_parser
from trend_radar.parsers.base import create_company_dict, safe_select_text, safe_get_attr


def parse_yc_grid(html: str, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse YC directory grid into normalized company dicts.

    Args:
        html: Raw HTML from YC companies page
        source_config: Source configuration dict

    Returns:
        List of company dicts with normalized fields
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    for card in soup.select(".company-card"):
        try:
            # Extract name - skip if missing
            name_el = card.select_one(".company-name")
            if not name_el:
                logger.debug(f"Skipping card without name in {source_config['id']}")
                continue

            name = name_el.get_text(strip=True)
            if not name:
                continue

            # Extract other fields
            website = card.get("data-href") or card.get("href")
            description = safe_select_text(card, ".company-description")
            batch = safe_select_text(card, ".batch") or None

            # Extract tags
            tags = [tag.get_text(strip=True) for tag in card.select(".tag")]

            # Extract location (approximate country)
            location = safe_select_text(card, ".location")
            country = None
            if location:
                # Simple heuristic: last part after comma is country/state
                parts = location.split(",")
                if len(parts) >= 2:
                    country = parts[-1].strip()

            # Create normalized company dict
            company = create_company_dict(
                name=name,
                website=website,
                description=description,
                industry_tags=tags,
                batch=batch,
                country=country,
                raw_data={"html": str(card)[:2000]}  # Preserve for debugging
            )

            companies.append(company)

        except Exception as e:
            logger.warning(
                f"Failed to parse card in {source_config['id']}: {e}",
                exc_info=True
            )
            continue

    logger.info(f"Parsed {len(companies)} companies from {source_config['id']}")
    return companies


# Register the parser
register_parser("yc_grid", parse_yc_grid)
```

Update `trend_radar/parsers/__init__.py` to import the parser:

```python
"""
Parser registry for VC portfolio sources.

Each source has a unique parse_strategy that maps to a parser function.
Parsers are pure functions: (html, source_config) -> list[dict]
"""

from typing import Callable, Dict, List

# Registry mapping strategy names to parser functions
PARSER_REGISTRY: Dict[str, Callable[[str, dict], List[dict]]] = {}


def register_parser(strategy: str, parser_fn: Callable[[str, dict], List[dict]]) -> None:
    """Register a parser function for a strategy name."""
    PARSER_REGISTRY[strategy] = parser_fn


def get_parser(strategy: str) -> Callable[[str, dict], List[dict]]:
    """Get parser function for a strategy name."""
    if strategy not in PARSER_REGISTRY:
        available = list(PARSER_REGISTRY.keys())
        raise ValueError(
            f"Unknown parse_strategy: {strategy}. "
            f"Available: {available}"
        )
    return PARSER_REGISTRY[strategy]


# Import parsers to trigger registration
from trend_radar.parsers import yc_grid  # noqa: F401, E402
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/trend_radar/test_yc_parser.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
mkdir -p tests/fixtures
git add trend_radar/parsers/yc_grid.py tests/fixtures/yc_grid_sample.html tests/trend_radar/test_yc_parser.py trend_radar/parsers/__init__.py
git commit -m "feat(trend-radar): implement YC directory parser with tests"
```

---

### Task 6: Implement Generic Table Parser

**Files:**
- Create: `trend_radar/parsers/generic.py`
- Create: `tests/fixtures/generic_table_sample.html`
- Create: `tests/trend_radar/test_generic_parser.py`

**Step 1: Create test fixture**

Create `tests/fixtures/generic_table_sample.html`:

```html
<!DOCTYPE html>
<html>
<body>
<table class="portfolio-table">
  <thead>
    <tr>
      <th>Company</th>
      <th>Stage</th>
      <th>Sector</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><a href="https://stripe.com">Stripe</a></td>
      <td>Growth</td>
      <td>Fintech</td>
    </tr>
    <tr>
      <td><a href="https://figma.com">Figma</a></td>
      <td>Growth</td>
      <td>Design Tools</td>
    </tr>
  </tbody>
</table>
</body>
</html>
```

**Step 2: Write the failing test**

Create `tests/trend_radar/test_generic_parser.py`:

```python
"""Tests for generic table parser."""

import pytest
from pathlib import Path

from trend_radar.parsers.generic import parse_generic_table


@pytest.fixture
def table_sample_html():
    """Load sample table HTML fixture."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "generic_table_sample.html"
    return fixture_path.read_text(encoding="utf-8")


@pytest.fixture
def source_config():
    """Sample source config."""
    return {
        "id": "test_portfolio",
        "name": "Test VC",
        "type": "vc_portfolio"
    }


class TestGenericTableParser:
    """Tests for parse_generic_table function."""

    def test_parses_table_rows(self, table_sample_html, source_config):
        """Should extract companies from table rows."""
        companies = parse_generic_table(table_sample_html, source_config)

        assert len(companies) == 2

    def test_extracts_company_name_from_link(self, table_sample_html, source_config):
        """Should extract company name from anchor text."""
        companies = parse_generic_table(table_sample_html, source_config)

        names = [c["name"] for c in companies]
        assert "Stripe" in names
        assert "Figma" in names

    def test_extracts_website_from_href(self, table_sample_html, source_config):
        """Should extract website from anchor href."""
        companies = parse_generic_table(table_sample_html, source_config)

        stripe = next(c for c in companies if c["name"] == "Stripe")
        assert stripe["website"] == "https://stripe.com"

    def test_extracts_stage(self, table_sample_html, source_config):
        """Should extract stage from second column."""
        companies = parse_generic_table(table_sample_html, source_config)

        stripe = next(c for c in companies if c["name"] == "Stripe")
        assert stripe["stage"] == "Growth"

    def test_extracts_sector_as_tag(self, table_sample_html, source_config):
        """Should extract sector as industry tag."""
        companies = parse_generic_table(table_sample_html, source_config)

        stripe = next(c for c in companies if c["name"] == "Stripe")
        assert "Fintech" in stripe["industry_tags"]
```

**Step 3: Run test to verify it fails**

```bash
pytest tests/trend_radar/test_generic_parser.py -v
```

Expected: FAIL with import error

**Step 4: Write the implementation**

Create `trend_radar/parsers/generic.py`:

```python
"""Generic parsers for common HTML patterns."""

from typing import Dict, List, Any
from bs4 import BeautifulSoup
from loguru import logger

from trend_radar.parsers import register_parser
from trend_radar.parsers.base import create_company_dict


def parse_generic_table(html: str, source_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Parse a simple HTML table with company data.

    Assumes table structure:
    - First column: Company name (with optional link)
    - Second column: Stage (optional)
    - Third column: Sector/Industry (optional)

    Args:
        html: Raw HTML containing a table
        source_config: Source configuration dict

    Returns:
        List of company dicts
    """
    soup = BeautifulSoup(html, "html.parser")
    companies = []

    # Find the main table (prefer .portfolio-table class, fallback to first table)
    table = soup.select_one(".portfolio-table") or soup.select_one("table")
    if not table:
        logger.warning(f"No table found in {source_config['id']}")
        return companies

    # Get tbody rows (skip header)
    rows = table.select("tbody tr")
    if not rows:
        # Fallback: skip first row as header
        rows = table.select("tr")[1:]

    for row in rows:
        try:
            cells = row.select("td")
            if not cells:
                continue

            # First cell: company name and link
            first_cell = cells[0]
            link = first_cell.select_one("a")

            if link:
                name = link.get_text(strip=True)
                website = link.get("href")
            else:
                name = first_cell.get_text(strip=True)
                website = None

            if not name:
                continue

            # Second cell: stage (optional)
            stage = None
            if len(cells) > 1:
                stage = cells[1].get_text(strip=True) or None

            # Third cell: sector/industry (optional)
            industry_tags = []
            if len(cells) > 2:
                sector = cells[2].get_text(strip=True)
                if sector:
                    industry_tags = [sector]

            company = create_company_dict(
                name=name,
                website=website,
                stage=stage,
                industry_tags=industry_tags,
                raw_data={"html": str(row)[:1000]}
            )

            companies.append(company)

        except Exception as e:
            logger.warning(f"Failed to parse row in {source_config['id']}: {e}")
            continue

    logger.info(f"Parsed {len(companies)} companies from {source_config['id']}")
    return companies


# Register the parser
register_parser("generic_table", parse_generic_table)
```

Update `trend_radar/parsers/__init__.py`:

```python
"""
Parser registry for VC portfolio sources.

Each source has a unique parse_strategy that maps to a parser function.
Parsers are pure functions: (html, source_config) -> list[dict]
"""

from typing import Callable, Dict, List

# Registry mapping strategy names to parser functions
PARSER_REGISTRY: Dict[str, Callable[[str, dict], List[dict]]] = {}


def register_parser(strategy: str, parser_fn: Callable[[str, dict], List[dict]]) -> None:
    """Register a parser function for a strategy name."""
    PARSER_REGISTRY[strategy] = parser_fn


def get_parser(strategy: str) -> Callable[[str, dict], List[dict]]:
    """Get parser function for a strategy name."""
    if strategy not in PARSER_REGISTRY:
        available = list(PARSER_REGISTRY.keys())
        raise ValueError(
            f"Unknown parse_strategy: {strategy}. "
            f"Available: {available}"
        )
    return PARSER_REGISTRY[strategy]


# Import parsers to trigger registration
from trend_radar.parsers import yc_grid  # noqa: F401, E402
from trend_radar.parsers import generic   # noqa: F401, E402
```

**Step 5: Run test to verify it passes**

```bash
pytest tests/trend_radar/test_generic_parser.py -v
```

Expected: All tests PASS

**Step 6: Commit**

```bash
git add trend_radar/parsers/generic.py tests/fixtures/generic_table_sample.html tests/trend_radar/test_generic_parser.py trend_radar/parsers/__init__.py
git commit -m "feat(trend-radar): implement generic table parser"
```

---

### Task 7: Create Crawler Module

**Files:**
- Create: `trend_radar/crawler.py`
- Create: `tests/trend_radar/test_crawler.py`

**Step 1: Write the failing test**

Create `tests/trend_radar/test_crawler.py`:

```python
"""Tests for crawler module."""

import pytest
from unittest.mock import Mock, patch

from trend_radar.crawler import Crawler, Fetcher


class TestFetcher:
    """Tests for Fetcher class."""

    @patch("trend_radar.crawler.requests.get")
    def test_fetch_html_page(self, mock_get):
        """Should fetch HTML content from URL."""
        mock_response = Mock()
        mock_response.text = "<html><body>Test</body></html>"
        mock_response.status_code = 200
        mock_get.return_value = mock_response

        fetcher = Fetcher()
        html = fetcher.fetch("https://example.com", requires_js=False)

        assert html == "<html><body>Test</body></html>"
        mock_get.assert_called_once()

    @patch("trend_radar.crawler.requests.get")
    def test_fetch_with_retry_on_failure(self, mock_get):
        """Should retry on transient failures."""
        mock_response_fail = Mock()
        mock_response_fail.status_code = 503
        mock_response_fail.raise_for_status.side_effect = Exception("503 Error")

        mock_response_ok = Mock()
        mock_response_ok.text = "<html>OK</html>"
        mock_response_ok.status_code = 200

        mock_get.side_effect = [mock_response_fail, mock_response_ok]

        fetcher = Fetcher(max_retries=2, retry_delay=0.01)
        html = fetcher.fetch("https://example.com", requires_js=False)

        assert html == "<html>OK</html>"
        assert mock_get.call_count == 2


class TestCrawler:
    """Tests for Crawler class."""

    def test_crawl_source_calls_parser(self):
        """Should call registered parser for source."""
        mock_fetcher = Mock()
        mock_fetcher.fetch.return_value = "<html></html>"

        mock_parser = Mock(return_value=[{"name": "Test Co"}])

        with patch("trend_radar.crawler.get_parser", return_value=mock_parser):
            crawler = Crawler(fetcher=mock_fetcher)
            source = {
                "id": "test_source",
                "url": "https://test.com",
                "parse_strategy": "test_parser"
            }

            companies = crawler.crawl_source(source)

            assert len(companies) == 1
            assert companies[0]["name"] == "Test Co"
            mock_parser.assert_called_once()

    def test_crawl_uses_filter_url_when_available(self):
        """Should prefer filter_url over url."""
        mock_fetcher = Mock()
        mock_fetcher.fetch.return_value = "<html></html>"

        mock_parser = Mock(return_value=[])

        with patch("trend_radar.crawler.get_parser", return_value=mock_parser):
            crawler = Crawler(fetcher=mock_fetcher)
            source = {
                "id": "test_source",
                "url": "https://test.com/all",
                "filter_url": "https://test.com/ai-only",
                "parse_strategy": "test_parser"
            }

            crawler.crawl_source(source)

            mock_fetcher.fetch.assert_called_with(
                "https://test.com/ai-only",
                requires_js=False
            )
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/trend_radar/test_crawler.py -v
```

Expected: FAIL with import error

**Step 3: Write the implementation**

Create `trend_radar/crawler.py`:

```python
"""Crawler for fetching and parsing VC portfolio pages."""

import time
from typing import Dict, List, Any, Optional

import requests
from loguru import logger

from trend_radar.parsers import get_parser


class Fetcher:
    """HTTP fetcher with retry logic."""

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        timeout: int = 30,
        user_agent: str = "TrendRadar/1.0 (AI Startup Monitor)"
    ):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.headers = {"User-Agent": user_agent}

    def fetch(self, url: str, requires_js: bool = False) -> str:
        """
        Fetch HTML content from URL.

        Args:
            url: URL to fetch
            requires_js: If True, use Playwright (not implemented yet)

        Returns:
            HTML content as string
        """
        if requires_js:
            # TODO: Implement Playwright fetching in Phase 3
            logger.warning(f"JS rendering requested but not implemented. Falling back to requests: {url}")

        last_error = None
        for attempt in range(self.max_retries):
            try:
                response = requests.get(
                    url,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                return response.text

            except Exception as e:
                last_error = e
                logger.warning(f"Fetch attempt {attempt + 1}/{self.max_retries} failed for {url}: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (attempt + 1))  # Exponential backoff

        raise last_error


class Crawler:
    """Orchestrates fetching and parsing of VC sources."""

    def __init__(self, fetcher: Optional[Fetcher] = None):
        self.fetcher = fetcher or Fetcher()

    def crawl_source(self, source: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Crawl a single source and return parsed companies.

        Args:
            source: Source config dict with url, parse_strategy, etc.

        Returns:
            List of parsed company dicts
        """
        source_id = source.get("id", "unknown")
        url = source.get("filter_url") or source["url"]
        requires_js = source.get("requires_js", False)

        logger.info(f"Crawling source: {source_id} ({url})")

        try:
            # Fetch HTML
            html = self.fetcher.fetch(url, requires_js=requires_js)

            # Get parser and parse
            parser = get_parser(source["parse_strategy"])
            companies = parser(html, source)

            logger.info(f"Crawled {len(companies)} companies from {source_id}")
            return companies

        except Exception as e:
            logger.error(f"Failed to crawl {source_id}: {e}")
            return []

    def crawl_tier(self, sources: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Crawl all sources in a tier.

        Args:
            sources: List of source config dicts

        Returns:
            Dict mapping source_id to list of companies
        """
        results = {}

        for source in sources:
            if not source.get("enabled", True):
                continue

            source_id = source["id"]
            companies = self.crawl_source(source)
            results[source_id] = companies

        total = sum(len(v) for v in results.values())
        logger.info(f"Crawled {len(results)} sources, {total} total companies")

        return results
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/trend_radar/test_crawler.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add trend_radar/crawler.py tests/trend_radar/test_crawler.py
git commit -m "feat(trend-radar): implement crawler with retry logic"
```

---

### Task 8: Create Normalizer Module

**Files:**
- Create: `trend_radar/normalizer.py`
- Create: `tests/trend_radar/test_normalizer.py`

**Step 1: Write the failing test**

Create `tests/trend_radar/test_normalizer.py`:

```python
"""Tests for normalizer module."""

import pytest
from datetime import date

from trend_radar.normalizer import Normalizer


class TestNormalizer:
    """Tests for Normalizer class."""

    def test_merge_companies_deduplicates_by_normalized_name(self):
        """Should merge companies with same normalized name."""
        normalizer = Normalizer()

        crawl_results = {
            "source_a": [
                {"name": "Acme AI", "normalized_name": "acme-ai", "website": "https://acme.ai"}
            ],
            "source_b": [
                {"name": "Acme AI, Inc.", "normalized_name": "acme-ai", "website": "https://acme.ai"}
            ]
        }

        companies = normalizer.merge_crawl_results(crawl_results)

        assert len(companies) == 1
        assert companies[0]["normalized_name"] == "acme-ai"

    def test_merge_tracks_source_count(self):
        """Should count how many sources mention each company."""
        normalizer = Normalizer()

        crawl_results = {
            "source_a": [
                {"name": "Acme AI", "normalized_name": "acme-ai"}
            ],
            "source_b": [
                {"name": "Acme AI", "normalized_name": "acme-ai"}
            ],
            "source_c": [
                {"name": "Other Co", "normalized_name": "other-co"}
            ]
        }

        companies = normalizer.merge_crawl_results(crawl_results)

        acme = next(c for c in companies if c["normalized_name"] == "acme-ai")
        other = next(c for c in companies if c["normalized_name"] == "other-co")

        assert acme["source_count"] == 2
        assert other["source_count"] == 1

    def test_merge_collects_observations_from_each_source(self):
        """Should collect observation data from each source."""
        normalizer = Normalizer()

        crawl_results = {
            "yc_directory": [
                {"name": "Acme AI", "normalized_name": "acme-ai", "batch": "W25"}
            ],
            "a16z_portfolio": [
                {"name": "Acme AI", "normalized_name": "acme-ai", "stage": "Seed"}
            ]
        }

        companies = normalizer.merge_crawl_results(crawl_results)

        acme = companies[0]
        assert len(acme["observations"]) == 2

        yc_obs = next(o for o in acme["observations"] if o["source_id"] == "yc_directory")
        assert yc_obs["batch"] == "W25"

        a16z_obs = next(o for o in acme["observations"] if o["source_id"] == "a16z_portfolio")
        assert a16z_obs["stage"] == "Seed"

    def test_merge_combines_industry_tags(self):
        """Should combine industry tags from all sources."""
        normalizer = Normalizer()

        crawl_results = {
            "source_a": [
                {"name": "Acme", "normalized_name": "acme", "industry_tags": ["AI", "B2B"]}
            ],
            "source_b": [
                {"name": "Acme", "normalized_name": "acme", "industry_tags": ["AI", "Fintech"]}
            ]
        }

        companies = normalizer.merge_crawl_results(crawl_results)

        acme = companies[0]
        # Should have unique tags from both
        assert "AI" in acme["all_industry_tags"]
        assert "B2B" in acme["all_industry_tags"]
        assert "Fintech" in acme["all_industry_tags"]
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/trend_radar/test_normalizer.py -v
```

Expected: FAIL with import error

**Step 3: Write the implementation**

Create `trend_radar/normalizer.py`:

```python
"""Normalizer for merging and deduplicating crawled company data."""

from datetime import date
from typing import Dict, List, Any, Set
from loguru import logger


class Normalizer:
    """Merges crawl results and deduplicates companies."""

    def merge_crawl_results(
        self,
        crawl_results: Dict[str, List[Dict[str, Any]]],
        crawl_date: date = None
    ) -> List[Dict[str, Any]]:
        """
        Merge companies from multiple sources, deduplicating by normalized_name.

        Args:
            crawl_results: Dict mapping source_id to list of company dicts
            crawl_date: Date of crawl (defaults to today)

        Returns:
            List of merged company dicts with observations
        """
        crawl_date = crawl_date or date.today()

        # Dict to accumulate companies by normalized_name
        companies_by_name: Dict[str, Dict[str, Any]] = {}

        for source_id, companies in crawl_results.items():
            for company in companies:
                normalized_name = company.get("normalized_name")
                if not normalized_name:
                    logger.warning(f"Company missing normalized_name: {company.get('name')}")
                    continue

                if normalized_name not in companies_by_name:
                    # First time seeing this company
                    companies_by_name[normalized_name] = {
                        "name": company.get("name"),
                        "normalized_name": normalized_name,
                        "website": company.get("website"),
                        "description": company.get("description"),
                        "founded_year": company.get("founded_year"),
                        "country": company.get("country"),
                        "source_count": 0,
                        "first_seen_global": crawl_date,
                        "last_seen_global": crawl_date,
                        "all_industry_tags": set(),
                        "observations": []
                    }

                merged = companies_by_name[normalized_name]

                # Update source count
                merged["source_count"] += 1

                # Merge industry tags
                for tag in company.get("industry_tags", []):
                    merged["all_industry_tags"].add(tag)

                # Fill in missing fields from this source
                if not merged["website"] and company.get("website"):
                    merged["website"] = company["website"]
                if not merged["description"] and company.get("description"):
                    merged["description"] = company["description"]
                if not merged["country"] and company.get("country"):
                    merged["country"] = company["country"]
                if not merged["founded_year"] and company.get("founded_year"):
                    merged["founded_year"] = company["founded_year"]

                # Add observation
                observation = {
                    "source_id": source_id,
                    "first_seen": crawl_date,
                    "last_seen": crawl_date,
                    "stage": company.get("stage"),
                    "batch": company.get("batch"),
                    "industry_tags": company.get("industry_tags", []),
                    "raw_data": company.get("raw_data")
                }
                merged["observations"].append(observation)

        # Convert sets to lists for JSON serialization
        result = []
        for company in companies_by_name.values():
            company["all_industry_tags"] = list(company["all_industry_tags"])
            result.append(company)

        # Sort by source_count descending (most mentioned first)
        result.sort(key=lambda c: c["source_count"], reverse=True)

        logger.info(f"Merged {sum(len(v) for v in crawl_results.values())} raw companies into {len(result)} unique companies")

        return result
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/trend_radar/test_normalizer.py -v
```

Expected: All tests PASS

**Step 5: Commit**

```bash
git add trend_radar/normalizer.py tests/trend_radar/test_normalizer.py
git commit -m "feat(trend-radar): implement normalizer for company deduplication"
```

---

### Task 9: Create CLI Integration

**Files:**
- Create: `trend_radar/jobs.py`
- Modify: `main.py`

**Step 1: Write the jobs module**

Create `trend_radar/jobs.py`:

```python
"""Job runners for Trend Radar operations."""

from datetime import date
from typing import Optional, Dict, Any, List
from loguru import logger

from utils.config_loader import load_sources_for_tier
from trend_radar.crawler import Crawler
from trend_radar.normalizer import Normalizer
from trend_radar.models import init_db, get_session, Source, Company, Observation


def run_refresh(
    tier: str = "standard",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Run a full refresh for a tier.

    Args:
        tier: Which tier to refresh (lite, standard, deep)
        dry_run: If True, crawl but don't save to database

    Returns:
        Dict with refresh statistics
    """
    logger.info(f"Starting refresh for tier: {tier}")

    # Load sources for tier
    sources = load_sources_for_tier(tier)
    logger.info(f"Loaded {len(sources)} sources for tier {tier}")

    # Initialize database
    if not dry_run:
        init_db()

    # Crawl all sources
    crawler = Crawler()
    crawl_results = crawler.crawl_tier(sources)

    # Normalize and dedupe
    normalizer = Normalizer()
    companies = normalizer.merge_crawl_results(crawl_results)

    # Save to database
    if not dry_run:
        saved_count = _save_to_database(companies, sources)
    else:
        saved_count = 0
        logger.info("Dry run - skipping database save")

    result = {
        "tier": tier,
        "sources_crawled": len(crawl_results),
        "raw_companies": sum(len(v) for v in crawl_results.values()),
        "unique_companies": len(companies),
        "saved_to_db": saved_count,
        "dry_run": dry_run
    }

    logger.info(f"Refresh complete: {result}")
    return result


def _save_to_database(
    companies: List[Dict[str, Any]],
    sources: List[Dict[str, Any]]
) -> int:
    """Save crawled companies to database."""
    session = get_session()
    saved_count = 0

    try:
        # Ensure sources exist in DB
        for source_config in sources:
            existing = session.query(Source).filter_by(id=source_config["id"]).first()
            if not existing:
                source = Source(
                    id=source_config["id"],
                    name=source_config["name"],
                    type=source_config.get("type", "vc_portfolio"),
                    url=source_config["url"],
                    filter_url=source_config.get("filter_url"),
                    parse_strategy=source_config["parse_strategy"],
                    tier=_get_tier_number(source_config),
                    frequency=source_config.get("frequency", "weekly"),
                    enabled=source_config.get("enabled", True),
                    requires_js=source_config.get("requires_js", False),
                    notes=source_config.get("notes")
                )
                session.add(source)

        session.commit()

        # Save companies and observations
        for company_data in companies:
            # Find or create company
            company = session.query(Company).filter_by(
                normalized_name=company_data["normalized_name"]
            ).first()

            if not company:
                company = Company(
                    name=company_data["name"],
                    normalized_name=company_data["normalized_name"],
                    website=company_data.get("website"),
                    description=company_data.get("description"),
                    founded_year=company_data.get("founded_year"),
                    country=company_data.get("country"),
                    source_count=company_data["source_count"],
                    first_seen_global=company_data["first_seen_global"],
                    last_seen_global=company_data["last_seen_global"]
                )
                session.add(company)
                session.flush()  # Get the ID
                saved_count += 1
            else:
                # Update existing company
                company.source_count = company_data["source_count"]
                company.last_seen_global = company_data["last_seen_global"]
                if company_data.get("website") and not company.website:
                    company.website = company_data["website"]

            # Add/update observations
            for obs_data in company_data.get("observations", []):
                existing_obs = session.query(Observation).filter_by(
                    source_id=obs_data["source_id"],
                    company_id=company.id
                ).first()

                if not existing_obs:
                    observation = Observation(
                        source_id=obs_data["source_id"],
                        company_id=company.id,
                        first_seen=obs_data["first_seen"],
                        last_seen=obs_data["last_seen"],
                        stage=obs_data.get("stage"),
                        batch=obs_data.get("batch"),
                        industry_tags=obs_data.get("industry_tags", []),
                        raw_data=obs_data.get("raw_data")
                    )
                    session.add(observation)
                else:
                    existing_obs.last_seen = obs_data["last_seen"]

        session.commit()
        logger.info(f"Saved {saved_count} new companies to database")

    except Exception as e:
        session.rollback()
        logger.error(f"Database save failed: {e}")
        raise
    finally:
        session.close()

    return saved_count


def _get_tier_number(source_config: Dict) -> int:
    """Map tier name to number (for legacy compatibility)."""
    # This is a simplification - in practice we'd track which tier the source came from
    return 1
```

**Step 2: Add CLI arguments to main.py**

Add to the argument parser section in `main.py` (around line 915):

```python
    parser.add_argument(
        '--trend-radar-api',
        action='store_true',
        help='Start the Trend Radar FastAPI server'
    )

    parser.add_argument(
        '--trend-radar-refresh',
        action='store_true',
        help='Run a one-off Trend Radar refresh'
    )

    parser.add_argument(
        '--tier',
        choices=['lite', 'standard', 'deep'],
        default='standard',
        help='Tier for trend radar refresh (default: standard)'
    )

    parser.add_argument(
        '--dry-run-radar',
        action='store_true',
        help='Trend radar: crawl but do not save to database'
    )
```

Add to the main() function, before the existing mode checks:

```python
    # Trend Radar modes
    if args.trend_radar_api:
        logger.info("Starting Trend Radar API server...")
        import uvicorn
        from trend_radar.api import app
        uvicorn.run(app, host="0.0.0.0", port=8100)
        return

    if args.trend_radar_refresh:
        from trend_radar.jobs import run_refresh
        result = run_refresh(
            tier=args.tier,
            dry_run=args.dry_run_radar if hasattr(args, 'dry_run_radar') else False
        )
        logger.info(f"Trend Radar refresh complete: {result}")
        return
```

**Step 3: Test the CLI**

```bash
python main.py --trend-radar-refresh --tier lite --dry-run-radar
```

Expected: Should crawl lite tier sources and show stats (no DB save)

**Step 4: Commit**

```bash
git add trend_radar/jobs.py main.py
git commit -m "feat(trend-radar): add CLI integration for refresh command"
```

---

### Task 10: Run All Tests and Create Phase 1 Summary

**Step 1: Run full test suite**

```bash
pytest tests/trend_radar/ -v --tb=short
```

Expected: All tests PASS

**Step 2: Create data directory if needed**

```bash
mkdir -p data
```

**Step 3: Final Phase 1 commit**

```bash
git add -A
git commit -m "feat(trend-radar): complete Phase 1 foundation

Phase 1 delivers:
- Data models (Source, Company, Observation)
- Config loader with tier inheritance
- Parser registry with YC and generic table parsers
- Crawler with retry logic
- Normalizer for company deduplication
- CLI refresh command (--trend-radar-refresh)

Ready for Phase 2: FastAPI endpoints"
```

---

## Phase 2: API Layer

### Task 11: Create FastAPI Application

**Files:**
- Create: `trend_radar/api.py`
- Create: `trend_radar/schemas.py`
- Create: `tests/trend_radar/test_api.py`

(Detailed steps follow same TDD pattern as Phase 1)

---

## Phase Summary

**Phase 1 Complete (Tasks 1-10):**
- Project structure and config loader
- SQLAlchemy models with relationships
- Parser registry + YC parser + generic table parser
- Crawler with retry logic
- Normalizer for deduplication
- CLI integration

**Phase 2 (Tasks 11-16):**
- FastAPI app with Pydantic schemas
- `/companies`, `/companies/new`, `/sources` endpoints
- Pagination and filtering
- Internal client for Streamlit
- `/refresh` endpoint with job tracking

**Phase 3 (Tasks 17-22):**
- Additional parsers (a16z, Sequoia, etc.)
- Playwright integration for JS sites
- `rising_score` computation
- `/stats` endpoint

**Phase 4 (Tasks 23-26):**
- Deep tier sources
- `/clusters` endpoint
- Semantic search (optional)
