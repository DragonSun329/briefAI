"""
Company Detail Page Component

Streamlit component that displays a comprehensive company profile page,
similar to Polymarket/Perplexity's entity pages.

Features:
- Real-time stock price with chart (via yfinance)
- Prediction market probabilities (Polymarket, Metaculus, Manifold)
- Company fundamentals (market cap, PE, employees, etc.)
- Recent news with sentiment synthesis
- Multi-signal validation status from trend radar
"""

from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass
import json

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd

# Stock data
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class StockQuote:
    """Real-time stock quote data."""
    ticker: str
    price: float
    change: float
    change_pct: float
    prev_close: float
    open_price: float
    day_high: float
    day_low: float
    week_52_high: float
    week_52_low: float
    volume: int
    avg_volume: int
    market_cap: float
    pe_ratio: Optional[float]
    dividend_yield: Optional[float]
    eps: Optional[float]
    asof: datetime


@dataclass
class CompanyInfo:
    """Company fundamental information."""
    name: str
    ticker: Optional[str]
    exchange: Optional[str]
    industry: str
    sector: str
    country: str
    employees: Optional[int]
    founded: Optional[str]
    ceo: Optional[str]
    website: str
    description: str


@dataclass
class PredictionMarket:
    """Prediction market data for a company."""
    source: str  # polymarket, metaculus, manifold
    question: str
    probability: float  # 0-100
    volume: float
    change_24h: float  # probability change
    end_date: Optional[str]
    url: Optional[str]


# =============================================================================
# DATA FETCHERS
# =============================================================================

class StockDataFetcher:
    """Fetches stock data from Yahoo Finance."""

    # Ticker mapping for AI companies
    ENTITY_TO_TICKER = {
        "nvidia": "NVDA",
        "microsoft": "MSFT",
        "google": "GOOGL",
        "meta": "META",
        "amazon": "AMZN",
        "apple": "AAPL",
        "tesla": "TSLA",
        "amd": "AMD",
        "intel": "INTC",
        "broadcom": "AVGO",
        "oracle": "ORCL",
        "ibm": "IBM",
        "salesforce": "CRM",
        "adobe": "ADBE",
        "palantir": "PLTR",
        "snowflake": "SNOW",
        "databricks": None,  # Private
        "openai": None,  # Private
        "anthropic": None,  # Private
        "deepseek": None,  # Private
        "mistral": None,  # Private
    }

    def get_ticker(self, entity_key: str) -> Optional[str]:
        """Get ticker symbol for an entity."""
        return self.ENTITY_TO_TICKER.get(entity_key.lower())

    def fetch_quote(self, ticker: str) -> Optional[StockQuote]:
        """Fetch real-time quote for a ticker."""
        if not YFINANCE_AVAILABLE:
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            return StockQuote(
                ticker=ticker,
                price=info.get("currentPrice") or info.get("regularMarketPrice", 0),
                change=info.get("regularMarketChange", 0),
                change_pct=info.get("regularMarketChangePercent", 0),
                prev_close=info.get("previousClose", 0),
                open_price=info.get("open") or info.get("regularMarketOpen", 0),
                day_high=info.get("dayHigh") or info.get("regularMarketDayHigh", 0),
                day_low=info.get("dayLow") or info.get("regularMarketDayLow", 0),
                week_52_high=info.get("fiftyTwoWeekHigh", 0),
                week_52_low=info.get("fiftyTwoWeekLow", 0),
                volume=info.get("volume") or info.get("regularMarketVolume", 0),
                avg_volume=info.get("averageVolume", 0),
                market_cap=info.get("marketCap", 0),
                pe_ratio=info.get("trailingPE"),
                dividend_yield=info.get("dividendYield"),
                eps=info.get("trailingEps"),
                asof=datetime.now(),
            )
        except Exception as e:
            st.warning(f"Failed to fetch quote for {ticker}: {e}")
            return None

    def fetch_history(self, ticker: str, period: str = "1mo") -> Optional[pd.DataFrame]:
        """Fetch historical price data."""
        if not YFINANCE_AVAILABLE:
            return None

        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            return df
        except Exception:
            return None

    def fetch_company_info(self, ticker: str) -> Optional[CompanyInfo]:
        """Fetch company information."""
        if not YFINANCE_AVAILABLE:
            return None

        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            return CompanyInfo(
                name=info.get("longName", info.get("shortName", ticker)),
                ticker=ticker,
                exchange=info.get("exchange"),
                industry=info.get("industry", "Technology"),
                sector=info.get("sector", "Technology"),
                country=info.get("country", ""),
                employees=info.get("fullTimeEmployees"),
                founded=None,  # Not in yfinance
                ceo=None,  # Not in yfinance
                website=info.get("website", ""),
                description=info.get("longBusinessSummary", "")[:500] if info.get("longBusinessSummary") else "",
            )
        except Exception:
            return None


class PredictionMarketFetcher:
    """Fetches prediction market data from saved scraper outputs."""

    def __init__(self, data_dir: Optional[Path] = None):
        self.data_dir = data_dir or Path(__file__).parent.parent / "data" / "alternative_signals"

    def _load_latest_file(self, prefix: str) -> Optional[Dict]:
        """Load the most recent file with given prefix."""
        import glob
        files = sorted(self.data_dir.glob(f"{prefix}_*.json"), reverse=True)
        if not files:
            return None
        try:
            with open(files[0], encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def fetch_for_entity(self, entity_name: str) -> List[PredictionMarket]:
        """Fetch prediction markets related to an entity."""
        markets = []
        entity_lower = entity_name.lower()

        # Load Polymarket data
        poly_data = self._load_latest_file("polymarket")
        if poly_data:
            for market in poly_data.get("markets", []):
                question = market.get("question", "").lower()
                if entity_lower in question or entity_name.upper() in market.get("question", ""):
                    probs = market.get("outcome_probabilities", {})
                    # Get the first (Yes) probability
                    prob = list(probs.values())[0] if probs else 50
                    markets.append(PredictionMarket(
                        source="Polymarket",
                        question=market.get("question", ""),
                        probability=prob,
                        volume=market.get("volume", 0),
                        change_24h=0,  # Would need historical data
                        end_date=market.get("end_date"),
                        url=f"https://polymarket.com/event/{market.get('slug', '')}",
                    ))

        # Load Metaculus data
        meta_data = self._load_latest_file("metaculus")
        if meta_data:
            for q in meta_data.get("questions", []):
                title = q.get("title", "").lower()
                if entity_lower in title:
                    markets.append(PredictionMarket(
                        source="Metaculus",
                        question=q.get("title", ""),
                        probability=q.get("community_prediction", 50) * 100,
                        volume=q.get("forecasters", 0),
                        change_24h=0,
                        end_date=q.get("resolve_time"),
                        url=q.get("url"),
                    ))

        # Load Manifold data
        manifold_data = self._load_latest_file("manifold")
        if manifold_data:
            for market in manifold_data.get("markets", []):
                question = market.get("question", "").lower()
                if entity_lower in question:
                    markets.append(PredictionMarket(
                        source="Manifold",
                        question=market.get("question", ""),
                        probability=market.get("probability", 0.5) * 100,
                        volume=market.get("volume", 0),
                        change_24h=0,
                        end_date=market.get("closeTime"),
                        url=market.get("url"),
                    ))

        return markets


class NewsDataFetcher:
    """Fetches news data from cache/article_contexts."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or Path(__file__).parent.parent / "data" / "cache" / "article_contexts"

    def fetch_for_entity(self, entity_name: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent news articles mentioning an entity."""
        articles = []
        entity_lower = entity_name.lower()

        if not self.cache_dir.exists():
            return articles

        # Load recent report caches
        for cache_file in sorted(self.cache_dir.glob("*.json"), reverse=True)[:7]:
            try:
                with open(cache_file, encoding="utf-8") as f:
                    data = json.load(f)

                for article in data.get("articles", []):
                    title = article.get("title", "").lower()
                    content = article.get("content", "").lower()

                    if entity_lower in title or entity_lower in content:
                        articles.append({
                            "title": article.get("title"),
                            "source": article.get("source", "Unknown"),
                            "date": article.get("date", cache_file.stem),
                            "score": article.get("score", 0),
                            "url": article.get("url"),
                            "summary": article.get("summary", article.get("content", "")[:200]),
                        })

                if len(articles) >= limit:
                    break

            except Exception:
                continue

        return articles[:limit]


# =============================================================================
# UI COMPONENTS
# =============================================================================

def render_price_header(quote: StockQuote, company_info: Optional[CompanyInfo], language: str = "en"):
    """Render the price header section similar to Polymarket."""
    t = {
        "en": {
            "prev_close": "Prev Close",
            "open": "Open",
            "day_range": "Day Range",
            "52w_range": "52W Range",
            "volume": "Volume",
            "avg_volume": "Avg Volume",
            "market_cap": "Market Cap",
            "pe_ratio": "P/E Ratio",
            "eps": "EPS",
            "dividend": "Dividend",
        },
        "zh": {
            "prev_close": "前一关闭",
            "open": "打开",
            "day_range": "日范围",
            "52w_range": "52W范围",
            "volume": "成交量",
            "avg_volume": "平均成交量",
            "market_cap": "市值",
            "pe_ratio": "市盈率",
            "eps": "每股收益",
            "dividend": "股息收益率",
        }
    }
    labels = t.get(language, t["en"])

    # Company name and ticker
    col1, col2 = st.columns([3, 1])
    with col1:
        company_name = company_info.name if company_info else quote.ticker
        st.markdown(f"## {company_name}")
        if company_info:
            st.caption(f"{quote.ticker} · {company_info.exchange or 'NASDAQ'} · {company_info.country or ''}")

    # Price display
    price_color = "green" if quote.change >= 0 else "red"
    change_sign = "+" if quote.change >= 0 else ""

    st.markdown(f"""
    <div style="display: flex; align-items: baseline; gap: 16px; margin: 16px 0;">
        <span style="font-size: 2.5em; font-weight: bold;">US${quote.price:,.2f}</span>
        <span style="font-size: 1.2em; color: {price_color};">
            {change_sign}US${quote.change:,.2f} ({change_sign}{quote.change_pct:.2f}%)
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Key metrics in columns
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(labels["prev_close"], f"${quote.prev_close:,.2f}")
        st.metric(labels["open"], f"${quote.open_price:,.2f}")

    with col2:
        st.metric(labels["day_range"], f"${quote.day_low:,.2f}-${quote.day_high:,.2f}")
        st.metric(labels["52w_range"], f"${quote.week_52_low:,.2f}-${quote.week_52_high:,.2f}")

    with col3:
        vol_str = f"{quote.volume:,.0f}" if quote.volume < 1_000_000_000 else f"{quote.volume/1_000_000_000:.2f}B"
        avg_vol_str = f"{quote.avg_volume:,.0f}" if quote.avg_volume < 1_000_000_000 else f"{quote.avg_volume/1_000_000_000:.2f}B"
        st.metric(labels["volume"], vol_str)
        st.metric(labels["avg_volume"], avg_vol_str)

    with col4:
        cap_str = f"${quote.market_cap/1_000_000_000:.2f}B" if quote.market_cap >= 1_000_000_000 else f"${quote.market_cap/1_000_000:.0f}M"
        st.metric(labels["market_cap"], cap_str)
        if quote.pe_ratio:
            st.metric(labels["pe_ratio"], f"{quote.pe_ratio:.2f}")


def render_price_chart(history_df: pd.DataFrame, ticker: str, period: str = "1M"):
    """Render an interactive price chart."""
    if history_df is None or history_df.empty:
        st.info("No historical data available")
        return

    fig = go.Figure()

    # Candlestick chart
    fig.add_trace(go.Candlestick(
        x=history_df.index,
        open=history_df['Open'],
        high=history_df['High'],
        low=history_df['Low'],
        close=history_df['Close'],
        name=ticker,
    ))

    # Styling
    fig.update_layout(
        title=f"{ticker} - {period}",
        yaxis_title="Price (USD)",
        xaxis_title="",
        template="plotly_dark",
        height=400,
        xaxis_rangeslider_visible=False,
        margin=dict(l=0, r=0, t=40, b=0),
    )

    st.plotly_chart(fig, use_container_width=True)


def render_prediction_markets(markets: List[PredictionMarket], language: str = "en"):
    """Render prediction markets section."""
    t = {
        "en": {
            "title": "Related Prediction Markets",
            "probability": "Probability",
            "volume": "Volume",
            "change": "Change",
            "no_markets": "No prediction markets found for this entity",
        },
        "zh": {
            "title": "相关预测市场",
            "probability": "概率",
            "volume": "成交量",
            "change": "变化",
            "no_markets": "未找到相关预测市场",
        }
    }
    labels = t.get(language, t["en"])

    st.subheader(f"🎯 {labels['title']}")

    if not markets:
        st.info(labels["no_markets"])
        return

    for market in markets[:5]:
        with st.container():
            col1, col2, col3 = st.columns([4, 1, 1])

            with col1:
                st.markdown(f"**{market.question[:80]}{'...' if len(market.question) > 80 else ''}**")
                st.caption(f"📊 {market.source}")

            with col2:
                prob_color = "green" if market.probability > 50 else "orange" if market.probability > 30 else "red"
                st.markdown(f"<span style='font-size: 1.5em; color: {prob_color};'>{market.probability:.1f}%</span>", unsafe_allow_html=True)

            with col3:
                vol_str = f"${market.volume:,.0f}" if market.volume < 1_000_000 else f"${market.volume/1_000_000:.1f}M"
                st.metric(labels["volume"], vol_str)

            st.divider()


def render_company_info_sidebar(company_info: CompanyInfo, language: str = "en"):
    """Render company information in sidebar format."""
    t = {
        "en": {
            "ticker": "Ticker",
            "market_cap": "Market Cap",
            "founded": "Founded",
            "ceo": "CEO",
            "employees": "Employees",
            "industry": "Industry",
            "sector": "Sector",
            "country": "Country",
            "exchange": "Exchange",
            "website": "Website",
        },
        "zh": {
            "ticker": "符号",
            "market_cap": "市值",
            "founded": "首次公开募股日期",
            "ceo": "首席执行官",
            "employees": "全职员工",
            "industry": "行业",
            "sector": "行业",
            "country": "国家",
            "exchange": "交换",
            "website": "网站",
        }
    }
    labels = t.get(language, t["en"])

    info_items = [
        (labels["ticker"], company_info.ticker),
        (labels["industry"], company_info.industry),
        (labels["sector"], company_info.sector),
        (labels["country"], company_info.country),
        (labels["exchange"], company_info.exchange),
    ]

    if company_info.employees:
        emp_str = f"{company_info.employees:,}" if company_info.employees < 10000 else f"{company_info.employees/10000:.1f}万"
        info_items.append((labels["employees"], emp_str))

    for label, value in info_items:
        if value:
            st.markdown(f"**{label}**: {value}")

    if company_info.description:
        st.markdown("---")
        st.markdown(company_info.description)
        if len(company_info.description) >= 500:
            st.caption("查看更多 ↓" if language == "zh" else "See more ↓")


def render_recent_news(news: List[Dict[str, Any]], language: str = "en"):
    """Render recent news section."""
    t = {
        "en": {
            "title": "Recent News",
            "no_news": "No recent news found",
        },
        "zh": {
            "title": "最新价格变动",
            "no_news": "未找到最近新闻",
        }
    }
    labels = t.get(language, t["en"])

    st.subheader(f"📰 {labels['title']}")

    if not news:
        st.info(labels["no_news"])
        return

    for article in news[:5]:
        with st.container():
            # Date and change indicator
            date_str = article.get("date", "")
            score = article.get("score", 0)
            score_indicator = "↗" if score > 7 else "↘" if score < 5 else "→"

            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"**{article['title'][:80]}{'...' if len(article['title']) > 80 else ''}**")
            with col2:
                st.caption(date_str)

            # Summary
            summary = article.get("summary", "")
            if summary:
                st.markdown(f"<span style='color: #888;'>{summary[:200]}{'...' if len(summary) > 200 else ''}</span>", unsafe_allow_html=True)

            # Source tags
            source = article.get("source", "")
            if source:
                st.caption(f"🏷️ {source}")

            st.divider()


# =============================================================================
# MAIN RENDER FUNCTION
# =============================================================================

def render_company_detail_page(entity_key: str, language: str = "en"):
    """
    Render the complete company detail page.

    Args:
        entity_key: Canonical entity key (e.g., "nvidia", "openai")
        language: Display language ("en" or "zh")
    """
    t = {
        "en": {
            "loading": "Loading company data...",
            "no_stock_data": "This company is not publicly traded. Showing available data.",
            "company_profile": "Company Profile",
        },
        "zh": {
            "loading": "加载公司数据...",
            "no_stock_data": "该公司未上市。显示可用数据。",
            "company_profile": "公司简介",
        }
    }
    labels = t.get(language, t["en"])

    # Initialize fetchers
    stock_fetcher = StockDataFetcher()
    prediction_fetcher = PredictionMarketFetcher()
    news_fetcher = NewsDataFetcher()

    # Get ticker for entity
    ticker = stock_fetcher.get_ticker(entity_key)

    # Layout: Main content + Sidebar
    col_main, col_sidebar = st.columns([3, 1])

    with col_main:
        if ticker:
            # Fetch stock data
            with st.spinner(labels["loading"]):
                quote = stock_fetcher.fetch_quote(ticker)
                company_info = stock_fetcher.fetch_company_info(ticker)
                history = stock_fetcher.fetch_history(ticker, period="1mo")

            if quote:
                # Price header
                render_price_header(quote, company_info, language)

                # Period selector
                period_options = {"1D": "1d", "5D": "5d", "1M": "1mo", "6M": "6mo", "YTD": "ytd", "1Y": "1y", "5Y": "5y", "MAX": "max"}
                selected_period = st.radio(
                    "Period",
                    options=list(period_options.keys()),
                    horizontal=True,
                    index=2,  # Default to 1M
                    key=f"period_{entity_key}"
                )

                # Fetch history for selected period
                history = stock_fetcher.fetch_history(ticker, period=period_options[selected_period])
                render_price_chart(history, ticker, selected_period)
            else:
                st.warning(labels["no_stock_data"])
        else:
            st.info(labels["no_stock_data"])

        st.divider()

        # Prediction markets
        predictions = prediction_fetcher.fetch_for_entity(entity_key)
        render_prediction_markets(predictions, language)

        st.divider()

        # Recent news
        news = news_fetcher.fetch_for_entity(entity_key)
        render_recent_news(news, language)

    with col_sidebar:
        st.subheader(labels["company_profile"])

        if ticker and company_info:
            render_company_info_sidebar(company_info, language)
        else:
            # Load from entity registry
            registry_path = Path(__file__).parent.parent / "config" / "entity_registry.json"
            if registry_path.exists():
                with open(registry_path, encoding="utf-8") as f:
                    registry = json.load(f)

                entity = registry.get(entity_key, {})
                if entity:
                    st.markdown(f"**{entity.get('canonical_name', entity_key)}**")
                    st.caption(entity.get("entity_type", "company"))

                    if entity.get("website"):
                        st.markdown(f"🌐 [{entity['website']}](https://{entity['website']})")

                    if entity.get("products"):
                        st.markdown("**Products:**")
                        st.markdown(", ".join(entity["products"][:5]))

        # Prediction market summary
        if predictions:
            st.divider()
            st.subheader("🎯 Market Sentiment")

            avg_prob = sum(m.probability for m in predictions) / len(predictions)
            total_volume = sum(m.volume for m in predictions)

            sentiment = "Bullish" if avg_prob > 60 else "Bearish" if avg_prob < 40 else "Neutral"
            sentiment_cn = "看涨" if avg_prob > 60 else "看跌" if avg_prob < 40 else "中性"

            st.metric(
                "Average Probability" if language == "en" else "平均概率",
                f"{avg_prob:.1f}%",
            )
            st.metric(
                "Total Volume" if language == "en" else "总成交量",
                f"${total_volume:,.0f}",
            )
            st.markdown(f"**Sentiment:** {sentiment if language == 'en' else sentiment_cn}")


def get_available_entities() -> List[Tuple[str, str]]:
    """Get list of available entities for selection."""
    registry_path = Path(__file__).parent.parent / "config" / "entity_registry.json"
    entities = []

    if registry_path.exists():
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)

        for key, entity in registry.items():
            if key.startswith("_"):
                continue
            entities.append((key, entity.get("canonical_name", key)))

    return sorted(entities, key=lambda x: x[1])


def get_company_link(entity_key: str, display_name: Optional[str] = None) -> str:
    """
    Generate a clickable link to a company detail page.

    Args:
        entity_key: Canonical entity key (e.g., "nvidia")
        display_name: Optional display name (defaults to entity_key)

    Returns:
        Markdown link string that can be used with st.markdown()
    """
    name = display_name or entity_key.replace("_", " ").title()
    return f"[{name}](?page=company&entity={entity_key})"


def render_company_link(entity_key: str, display_name: Optional[str] = None):
    """
    Render a clickable company link using Streamlit.

    Args:
        entity_key: Canonical entity key (e.g., "nvidia")
        display_name: Optional display name
    """
    name = display_name or entity_key.replace("_", " ").title()
    if st.button(f"📊 {name}", key=f"company_link_{entity_key}"):
        st.query_params["page"] = "company"
        st.query_params["entity"] = entity_key
        st.rerun()


# =============================================================================
# STANDALONE TEST
# =============================================================================

if __name__ == "__main__":
    st.set_page_config(page_title="Company Detail", layout="wide")

    # Entity selector
    entities = get_available_entities()
    entity_options = {name: key for key, name in entities}

    selected_name = st.selectbox(
        "Select Company",
        options=list(entity_options.keys()),
        index=list(entity_options.keys()).index("NVIDIA") if "NVIDIA" in entity_options else 0
    )

    if selected_name:
        entity_key = entity_options[selected_name]
        render_company_detail_page(entity_key, language="zh")
