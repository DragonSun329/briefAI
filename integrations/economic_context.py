"""
Economic Context Module

Provides macroeconomic context for AI sector analysis:
- Key macro indicators (Fed funds rate, PMI, GDP growth)
- Interest rates (Fed funds, 10Y Treasury, 2Y Treasury)
- PMI/ISM data (enterprise spending proxy)
- Tech sector employment data
- VIX (market risk appetite)
- Market regime detection (risk-on/risk-off)
- Sector-specific context for AI signals
- Sector ETFs relative strength (QQQ, SOXX, IGV vs SPY)
- Geopolitical risk indicators

Data sources:
- FRED API (Federal Reserve Economic Data)
- Yahoo Finance for market indicators
- News scraping for geopolitical events
"""

import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

import numpy as np

try:
    import yfinance as yf
except ImportError:
    yf = None
    logger.warning("yfinance not installed")

try:
    from fredapi import Fred
except ImportError:
    Fred = None
    logger.warning("fredapi not installed - some economic indicators unavailable")

# Import regime classifier
try:
    from utils.regime_classifier import RegimeClassifier, MarketRegime as RegimeEnum
except ImportError:
    RegimeClassifier = None
    RegimeEnum = None


class MarketRegime(Enum):
    """Market regime classification."""
    RISK_ON = "risk_on"           # Bullish, favors growth/AI
    RISK_OFF = "risk_off"         # Bearish, defensive positioning
    TRANSITIONAL = "transitional"  # Unclear regime
    HIGH_VOLATILITY = "high_volatility"  # Elevated uncertainty


@dataclass
class EconomicSnapshot:
    """Point-in-time economic snapshot."""
    timestamp: datetime
    
    # Interest rates
    fed_funds_rate: Optional[float] = None
    treasury_10y: Optional[float] = None
    treasury_2y: Optional[float] = None
    yield_curve_spread: Optional[float] = None  # 10Y - 2Y
    
    # Growth indicators
    gdp_growth: Optional[float] = None
    pmi_manufacturing: Optional[float] = None
    pmi_services: Optional[float] = None
    
    # Inflation
    cpi_yoy: Optional[float] = None
    pce_core: Optional[float] = None
    
    # Labor
    unemployment_rate: Optional[float] = None
    nonfarm_payrolls_change: Optional[int] = None
    
    # Market indicators
    vix: Optional[float] = None
    sp500_level: Optional[float] = None
    nasdaq_level: Optional[float] = None
    
    # Regime
    regime: MarketRegime = MarketRegime.TRANSITIONAL
    regime_confidence: float = 0.5
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "interest_rates": {
                "fed_funds_rate": self.fed_funds_rate,
                "treasury_10y": self.treasury_10y,
                "treasury_2y": self.treasury_2y,
                "yield_curve_spread": self.yield_curve_spread,
            },
            "growth": {
                "gdp_growth": self.gdp_growth,
                "pmi_manufacturing": self.pmi_manufacturing,
                "pmi_services": self.pmi_services,
            },
            "inflation": {
                "cpi_yoy": self.cpi_yoy,
                "pce_core": self.pce_core,
            },
            "labor": {
                "unemployment_rate": self.unemployment_rate,
                "nonfarm_payrolls_change": self.nonfarm_payrolls_change,
            },
            "market": {
                "vix": self.vix,
                "sp500": self.sp500_level,
                "nasdaq": self.nasdaq_level,
            },
            "regime": {
                "classification": self.regime.value,
                "confidence": round(self.regime_confidence, 2),
            }
        }


@dataclass
class SectorContext:
    """AI sector-specific context."""
    
    # Sector rotation indicators
    tech_vs_market: float = 0.0  # Tech relative performance
    semis_vs_market: float = 0.0  # Semiconductor relative performance
    growth_vs_value: float = 0.0  # Growth factor performance
    
    # AI-specific
    ai_etf_performance: float = 0.0
    ai_sector_momentum: str = "neutral"
    
    # Risk assessment
    rate_sensitivity: str = "high"  # AI stocks are rate-sensitive
    macro_headwinds: List[str] = field(default_factory=list)
    macro_tailwinds: List[str] = field(default_factory=list)
    
    # Investment thesis context
    capex_cycle_stage: str = "expansion"  # expansion, peak, contraction, trough
    enterprise_spending_outlook: str = "positive"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "sector_rotation": {
                "tech_vs_market": round(self.tech_vs_market, 4),
                "semis_vs_market": round(self.semis_vs_market, 4),
                "growth_vs_value": round(self.growth_vs_value, 4),
            },
            "ai_specific": {
                "ai_etf_performance": round(self.ai_etf_performance, 4),
                "momentum": self.ai_sector_momentum,
            },
            "risk_factors": {
                "rate_sensitivity": self.rate_sensitivity,
                "headwinds": self.macro_headwinds,
                "tailwinds": self.macro_tailwinds,
            },
            "thesis_context": {
                "capex_cycle_stage": self.capex_cycle_stage,
                "enterprise_spending_outlook": self.enterprise_spending_outlook,
            }
        }


class EconomicContextProvider:
    """
    Provides economic and market context for AI sector analysis.
    
    Combines multiple data sources to give a comprehensive
    macroeconomic backdrop for briefAI signals.
    """
    
    # FRED series IDs - expanded for comprehensive economic coverage
    FRED_SERIES = {
        # Interest rates
        "fed_funds": "FEDFUNDS",           # Federal Funds Rate
        "fed_funds_target": "DFEDTARU",    # Fed Funds Target Upper
        "treasury_10y": "GS10",            # 10-Year Treasury
        "treasury_2y": "GS2",              # 2-Year Treasury
        "treasury_3m": "GS3M",             # 3-Month Treasury
        "treasury_30y": "GS30",            # 30-Year Treasury
        "real_rate_10y": "REAINTRATREARAT10Y",  # 10Y Real Rate
        
        # PMI/ISM Data (enterprise spending proxies)
        "ism_manufacturing": "MANEMP",     # Manufacturing Employment
        "ism_services": "NMFBSI",          # ISM Services PMI (if available)
        "industrial_production": "INDPRO", # Industrial Production Index
        "capacity_utilization": "TCU",     # Capacity Utilization
        "new_orders_durable": "DGORDER",   # New Orders Durable Goods
        
        # GDP and Growth
        "gdp_growth": "A191RL1Q225SBEA",   # Real GDP Growth
        "gdp_now": "GDPNOW",               # Atlanta Fed GDPNow
        
        # Inflation
        "cpi_yoy": "CPIAUCSL",             # CPI All Items
        "cpi_core": "CPILFESL",            # Core CPI (ex food/energy)
        "pce_core": "PCEPILFE",            # Core PCE (Fed's preferred)
        "ppi": "PPIACO",                   # Producer Price Index
        
        # Labor Market
        "unemployment": "UNRATE",           # Unemployment Rate
        "nonfarm_payrolls": "PAYEMS",      # Total Nonfarm Payrolls
        "initial_claims": "ICSA",          # Initial Jobless Claims
        "continued_claims": "CCSA",        # Continued Claims
        "jolts_openings": "JTSJOL",        # JOLTS Job Openings
        "quit_rate": "JTSQUR",             # Quit Rate
        
        # Tech Sector Employment
        "tech_employment": "CES5051200001", # Information Services Employment
        "computer_employment": "CES5000000001", # Computer/Electronic Products
        "professional_services": "CES6000000001", # Professional/Business Services
        
        # Financial Conditions
        "financial_conditions": "NFCI",     # Chicago Fed Financial Conditions
        "credit_spread_bbb": "BAMLC0A4CBBB", # BBB Credit Spread
        "credit_spread_hy": "BAMLH0A0HYM2", # High Yield Spread
        
        # Consumer
        "consumer_sentiment": "UMCSENT",   # U Michigan Consumer Sentiment
        "consumer_confidence": "CSCICP03USM665S", # Consumer Confidence
        "retail_sales": "RSAFS",           # Retail Sales
        
        # Housing (tech worker relocation indicator)
        "housing_starts": "HOUST",
        "building_permits": "PERMIT",
    }
    
    # Yahoo Finance tickers for market indicators - expanded
    MARKET_TICKERS = {
        # Major Indices
        "vix": "^VIX",
        "sp500": "^GSPC",
        "nasdaq": "^IXIC",
        "nasdaq100": "^NDX",
        "russell2000": "^RUT",
        "dow": "^DJI",
        
        # Sector ETFs (for relative strength)
        "tech_etf": "XLK",         # Technology Select Sector
        "semi_etf": "SMH",         # VanEck Semiconductor
        "software_etf": "IGV",     # iShares Software ETF
        "qqq": "QQQ",              # Invesco QQQ (Nasdaq-100)
        "soxx": "SOXX",            # iShares Semiconductor ETF
        
        # Factor ETFs
        "growth_etf": "IWF",       # iShares Russell 1000 Growth
        "value_etf": "IWD",        # iShares Russell 1000 Value
        "momentum_etf": "MTUM",    # iShares MSCI USA Momentum
        "quality_etf": "QUAL",     # iShares MSCI USA Quality
        
        # AI/Thematic
        "ai_etf": "BOTZ",          # Global X Robotics & AI
        "arkk": "ARKK",            # ARK Innovation ETF
        "arkg": "ARKG",            # ARK Genomic Revolution
        
        # Defensive (for rotation analysis)
        "utilities": "XLU",
        "healthcare": "XLV",
        "staples": "XLP",
        
        # Fixed Income
        "tlt": "TLT",              # 20+ Year Treasury
        "shy": "SHY",              # 1-3 Year Treasury
        "lqd": "LQD",              # Investment Grade Corp
        "hyg": "HYG",              # High Yield Corp
        
        # Currency/Commodities
        "dxy": "DX-Y.NYB",         # US Dollar Index
        "gold": "GLD",
        "oil": "USO",
        
        # China/EM (for geopolitical context)
        "china_etf": "FXI",        # iShares China Large-Cap
        "em_etf": "EEM",           # iShares MSCI Emerging Markets
        "kweb": "KWEB",            # KraneShares China Internet
    }
    
    def __init__(self, fred_api_key: Optional[str] = None):
        """
        Initialize economic context provider.
        
        Args:
            fred_api_key: FRED API key (optional, enables more indicators)
        """
        self.fred_api_key = fred_api_key
        self.fred = None
        
        if fred_api_key and Fred:
            try:
                self.fred = Fred(api_key=fred_api_key)
                logger.info("FRED API initialized")
            except Exception as e:
                logger.warning(f"Could not initialize FRED API: {e}")
        
        self._cache: Dict[str, Any] = {}
        self._cache_age = 3600  # 1 hour cache
        
        logger.info("EconomicContextProvider initialized")
    
    def _get_fred_value(self, series_id: str) -> Optional[float]:
        """Fetch latest value from FRED."""
        if not self.fred:
            return None
        
        try:
            data = self.fred.get_series(series_id)
            if data is not None and len(data) > 0:
                return float(data.iloc[-1])
        except Exception as e:
            logger.warning(f"Error fetching FRED series {series_id}: {e}")
        
        return None
    
    def _get_market_data(self, ticker: str, period: str = "1mo") -> Dict[str, Any]:
        """Fetch market data from Yahoo Finance."""
        if yf is None:
            return {}
        
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period=period)
            
            if hist.empty:
                return {}
            
            current = hist['Close'].iloc[-1]
            start = hist['Close'].iloc[0]
            change = (current - start) / start
            
            return {
                "current": float(current),
                "change": float(change),
                "high": float(hist['High'].max()),
                "low": float(hist['Low'].min()),
            }
        except Exception as e:
            logger.warning(f"Error fetching {ticker}: {e}")
            return {}
    
    def get_economic_snapshot(self) -> EconomicSnapshot:
        """
        Get current economic snapshot.
        
        Combines FRED data and market indicators.
        """
        snapshot = EconomicSnapshot(timestamp=datetime.now())
        
        # FRED indicators (if available)
        if self.fred:
            snapshot.fed_funds_rate = self._get_fred_value(self.FRED_SERIES["fed_funds"])
            snapshot.treasury_10y = self._get_fred_value(self.FRED_SERIES["treasury_10y"])
            snapshot.treasury_2y = self._get_fred_value(self.FRED_SERIES["treasury_2y"])
            snapshot.gdp_growth = self._get_fred_value(self.FRED_SERIES["gdp_growth"])
            snapshot.cpi_yoy = self._get_fred_value(self.FRED_SERIES["cpi_yoy"])
            snapshot.unemployment_rate = self._get_fred_value(self.FRED_SERIES["unemployment"])
        
        # Market indicators from Yahoo Finance
        vix_data = self._get_market_data(self.MARKET_TICKERS["vix"])
        if vix_data:
            snapshot.vix = vix_data.get("current")
        
        sp500_data = self._get_market_data(self.MARKET_TICKERS["sp500"])
        if sp500_data:
            snapshot.sp500_level = sp500_data.get("current")
        
        nasdaq_data = self._get_market_data(self.MARKET_TICKERS["nasdaq"])
        if nasdaq_data:
            snapshot.nasdaq_level = nasdaq_data.get("current")
        
        # Calculate yield curve spread
        if snapshot.treasury_10y and snapshot.treasury_2y:
            snapshot.yield_curve_spread = snapshot.treasury_10y - snapshot.treasury_2y
        
        # Determine market regime
        snapshot.regime, snapshot.regime_confidence = self._detect_regime(snapshot)
        
        return snapshot
    
    def _detect_regime(
        self, 
        snapshot: EconomicSnapshot
    ) -> Tuple[MarketRegime, float]:
        """
        Detect current market regime.
        
        Uses VIX, yield curve, and momentum to classify regime.
        """
        risk_on_score = 0
        risk_off_score = 0
        confidence = 0.5
        
        # VIX analysis
        if snapshot.vix is not None:
            if snapshot.vix < 15:
                risk_on_score += 2
            elif snapshot.vix < 20:
                risk_on_score += 1
            elif snapshot.vix > 30:
                risk_off_score += 2
            elif snapshot.vix > 25:
                risk_off_score += 1
            
            # High volatility check
            if snapshot.vix > 35:
                return MarketRegime.HIGH_VOLATILITY, 0.8
        
        # Yield curve analysis
        if snapshot.yield_curve_spread is not None:
            if snapshot.yield_curve_spread < 0:
                risk_off_score += 2  # Inverted = recession signal
            elif snapshot.yield_curve_spread > 0.5:
                risk_on_score += 1
        
        # GDP growth analysis
        if snapshot.gdp_growth is not None:
            if snapshot.gdp_growth > 2:
                risk_on_score += 1
            elif snapshot.gdp_growth < 0:
                risk_off_score += 2
        
        # Calculate regime
        total_score = risk_on_score + risk_off_score
        if total_score > 0:
            confidence = abs(risk_on_score - risk_off_score) / total_score
        
        if risk_on_score > risk_off_score + 1:
            return MarketRegime.RISK_ON, min(0.9, 0.5 + confidence)
        elif risk_off_score > risk_on_score + 1:
            return MarketRegime.RISK_OFF, min(0.9, 0.5 + confidence)
        else:
            return MarketRegime.TRANSITIONAL, 0.4
    
    def get_sector_context(self, lookback_days: int = 30) -> SectorContext:
        """
        Get AI sector-specific context.
        
        Analyzes sector rotation and AI-specific indicators.
        """
        context = SectorContext()
        
        # Get sector data
        period = f"{lookback_days}d"
        
        tech = self._get_market_data(self.MARKET_TICKERS["tech_etf"], period)
        sp500 = self._get_market_data(self.MARKET_TICKERS["sp500"], period)
        semis = self._get_market_data(self.MARKET_TICKERS["semi_etf"], period)
        growth = self._get_market_data(self.MARKET_TICKERS["growth_etf"], period)
        value = self._get_market_data(self.MARKET_TICKERS["value_etf"], period)
        ai_etf = self._get_market_data(self.MARKET_TICKERS["ai_etf"], period)
        
        # Calculate relative performance
        if tech and sp500:
            context.tech_vs_market = tech.get("change", 0) - sp500.get("change", 0)
        
        if semis and sp500:
            context.semis_vs_market = semis.get("change", 0) - sp500.get("change", 0)
        
        if growth and value:
            context.growth_vs_value = growth.get("change", 0) - value.get("change", 0)
        
        if ai_etf:
            context.ai_etf_performance = ai_etf.get("change", 0)
        
        # Determine AI sector momentum
        if context.semis_vs_market > 0.02 and context.tech_vs_market > 0.01:
            context.ai_sector_momentum = "strong_bullish"
        elif context.semis_vs_market > 0 or context.tech_vs_market > 0:
            context.ai_sector_momentum = "bullish"
        elif context.semis_vs_market < -0.02 and context.tech_vs_market < -0.01:
            context.ai_sector_momentum = "bearish"
        elif context.semis_vs_market < 0 or context.tech_vs_market < 0:
            context.ai_sector_momentum = "weak"
        else:
            context.ai_sector_momentum = "neutral"
        
        # Identify headwinds and tailwinds
        context.macro_headwinds = []
        context.macro_tailwinds = []
        
        # Rate sensitivity
        if context.growth_vs_value < -0.02:
            context.macro_headwinds.append("Rising rate environment favoring value")
        elif context.growth_vs_value > 0.02:
            context.macro_tailwinds.append("Growth/tech leadership")
        
        # Semiconductor cycle
        if context.semis_vs_market > 0.05:
            context.macro_tailwinds.append("Strong semiconductor cycle")
        elif context.semis_vs_market < -0.05:
            context.macro_headwinds.append("Weak semiconductor demand")
        
        # AI-specific factors
        if context.ai_etf_performance > 0.03:
            context.macro_tailwinds.append("AI thematic momentum")
        elif context.ai_etf_performance < -0.03:
            context.macro_headwinds.append("AI sector rotation out")
        
        return context
    
    def get_interest_rate_analysis(self) -> Dict[str, Any]:
        """
        Get comprehensive interest rate analysis.
        
        Covers:
        - Fed funds rate and target
        - Treasury yields (2Y, 10Y, 30Y)
        - Yield curve analysis
        - Real rates
        """
        rates = {
            "timestamp": datetime.now().isoformat(),
            "fed_policy": {},
            "treasuries": {},
            "yield_curve": {},
            "real_rates": {},
            "assessment": {},
        }
        
        # Initialize to None for use outside FRED block
        fed_funds = None
        
        if self.fred:
            # Fed policy
            fed_funds = self._get_fred_value(self.FRED_SERIES["fed_funds"])
            rates["fed_policy"]["fed_funds_rate"] = fed_funds
            
            # Treasury yields
            t2y = self._get_fred_value(self.FRED_SERIES["treasury_2y"])
            t10y = self._get_fred_value(self.FRED_SERIES["treasury_10y"])
            t30y = self._get_fred_value(self.FRED_SERIES.get("treasury_30y"))
            t3m = self._get_fred_value(self.FRED_SERIES.get("treasury_3m"))
            
            rates["treasuries"] = {
                "3m": t3m,
                "2y": t2y,
                "10y": t10y,
                "30y": t30y,
            }
            
            # Yield curve spreads
            if t10y and t2y:
                rates["yield_curve"]["10y_2y_spread"] = round(t10y - t2y, 3)
                rates["yield_curve"]["inverted"] = t10y < t2y
            
            if t10y and t3m:
                rates["yield_curve"]["10y_3m_spread"] = round(t10y - t3m, 3)
            
            # Real rates
            real_10y = self._get_fred_value(self.FRED_SERIES.get("real_rate_10y"))
            if real_10y:
                rates["real_rates"]["10y_real"] = real_10y
        
        # Rate environment assessment
        assessment = []
        yc = rates["yield_curve"]
        
        if yc.get("inverted"):
            assessment.append("Yield curve inverted - recession risk elevated")
        if fed_funds and fed_funds > 5:
            assessment.append("Restrictive Fed policy - headwind for growth stocks")
        elif fed_funds and fed_funds < 2:
            assessment.append("Accommodative Fed policy - tailwind for growth")
        
        rates["assessment"]["notes"] = assessment
        rates["assessment"]["rate_environment"] = (
            "restrictive" if (fed_funds and fed_funds > 4.5) else
            "neutral" if (fed_funds and fed_funds > 2.5) else
            "accommodative"
        ) if fed_funds else "unknown"
        
        return rates
    
    def get_pmi_ism_analysis(self) -> Dict[str, Any]:
        """
        Get PMI/ISM data as enterprise spending proxy.
        
        PMI > 50 indicates expansion, < 50 indicates contraction.
        Key for AI infrastructure spending outlook.
        """
        pmi_data = {
            "timestamp": datetime.now().isoformat(),
            "manufacturing": {},
            "services": {},
            "leading_indicators": {},
            "enterprise_spending_outlook": "neutral",
        }
        
        if self.fred:
            # Manufacturing indicators
            industrial_prod = self._get_fred_value(self.FRED_SERIES.get("industrial_production"))
            capacity_util = self._get_fred_value(self.FRED_SERIES.get("capacity_utilization"))
            durable_orders = self._get_fred_value(self.FRED_SERIES.get("new_orders_durable"))
            
            pmi_data["manufacturing"] = {
                "industrial_production": industrial_prod,
                "capacity_utilization": capacity_util,
                "durable_goods_orders": durable_orders,
            }
            
            # Note: ISM PMI requires subscription, using proxies
            # Capacity utilization >80% suggests strong spending
            if capacity_util:
                if capacity_util > 80:
                    pmi_data["manufacturing"]["assessment"] = "Strong utilization - capex cycle expansion"
                elif capacity_util > 75:
                    pmi_data["manufacturing"]["assessment"] = "Moderate utilization"
                else:
                    pmi_data["manufacturing"]["assessment"] = "Weak utilization - capex headwind"
        
        # Enterprise spending outlook for AI/tech
        cu = pmi_data["manufacturing"].get("capacity_utilization", 77)
        if cu and cu > 78:
            pmi_data["enterprise_spending_outlook"] = "expansion"
        elif cu and cu > 74:
            pmi_data["enterprise_spending_outlook"] = "moderate"
        else:
            pmi_data["enterprise_spending_outlook"] = "contraction"
        
        return pmi_data
    
    def get_tech_employment_data(self) -> Dict[str, Any]:
        """
        Get tech sector employment data.
        
        Tracks hiring trends in:
        - Information services
        - Computer/electronics
        - Professional services (consulting, cloud)
        """
        employment = {
            "timestamp": datetime.now().isoformat(),
            "tech_employment": {},
            "trends": {},
            "assessment": {},
        }
        
        if self.fred:
            tech_emp = self._get_fred_value(self.FRED_SERIES.get("tech_employment"))
            computer_emp = self._get_fred_value(self.FRED_SERIES.get("computer_employment"))
            prof_services = self._get_fred_value(self.FRED_SERIES.get("professional_services"))
            
            employment["tech_employment"] = {
                "information_services": tech_emp,
                "computer_electronics": computer_emp,
                "professional_services": prof_services,
            }
            
            # Overall labor market
            unemployment = self._get_fred_value(self.FRED_SERIES["unemployment"])
            initial_claims = self._get_fred_value(self.FRED_SERIES.get("initial_claims"))
            
            employment["labor_market"] = {
                "unemployment_rate": unemployment,
                "initial_claims": initial_claims,
            }
            
            # Assessment
            if unemployment:
                if unemployment < 4:
                    employment["assessment"]["market_tightness"] = "Very tight labor market"
                elif unemployment < 5:
                    employment["assessment"]["market_tightness"] = "Tight labor market"
                else:
                    employment["assessment"]["market_tightness"] = "Loosening labor market"
        
        return employment
    
    def get_vix_analysis(self) -> Dict[str, Any]:
        """
        Comprehensive VIX analysis for risk appetite.
        
        VIX levels:
        - <15: Low volatility, complacency
        - 15-20: Normal
        - 20-25: Elevated caution
        - 25-30: High volatility
        - >30: Fear/crisis
        - >40: Extreme fear
        """
        vix_data = {
            "timestamp": datetime.now().isoformat(),
            "current": None,
            "percentile": None,
            "regime": "normal",
            "change_1w": None,
            "change_1m": None,
            "term_structure": {},
            "risk_assessment": {},
        }
        
        # Get VIX data
        vix = self._get_market_data(self.MARKET_TICKERS["vix"], "3mo")
        
        if vix:
            current = vix.get("current", 20)
            vix_data["current"] = round(current, 2)
            vix_data["change"] = round(vix.get("change", 0) * 100, 2)
            
            # Calculate percentile (rough estimate)
            # Historical VIX: ~12-80 range, median ~17
            if current <= 12:
                vix_data["percentile"] = 5
            elif current <= 15:
                vix_data["percentile"] = 20
            elif current <= 18:
                vix_data["percentile"] = 40
            elif current <= 22:
                vix_data["percentile"] = 60
            elif current <= 28:
                vix_data["percentile"] = 80
            else:
                vix_data["percentile"] = 95
            
            # Regime classification
            if current < 15:
                vix_data["regime"] = "complacent"
                vix_data["risk_assessment"]["market_mood"] = "Risk-on, low fear"
            elif current < 20:
                vix_data["regime"] = "normal"
                vix_data["risk_assessment"]["market_mood"] = "Normal volatility"
            elif current < 25:
                vix_data["regime"] = "elevated"
                vix_data["risk_assessment"]["market_mood"] = "Caution rising"
            elif current < 30:
                vix_data["regime"] = "high"
                vix_data["risk_assessment"]["market_mood"] = "Elevated fear"
            elif current < 40:
                vix_data["regime"] = "fear"
                vix_data["risk_assessment"]["market_mood"] = "High fear"
            else:
                vix_data["regime"] = "extreme"
                vix_data["risk_assessment"]["market_mood"] = "Extreme fear/crisis"
            
            # Risk assessment for AI signals
            vix_data["risk_assessment"]["signal_reliability"] = (
                "low" if current > 30 else
                "moderate" if current > 25 else
                "high"
            )
            vix_data["risk_assessment"]["position_sizing"] = (
                "reduce" if current > 30 else
                "cautious" if current > 25 else
                "normal"
            )
        
        return vix_data
    
    def get_sector_etf_relative_strength(self, period: str = "1mo") -> Dict[str, Any]:
        """
        Calculate relative strength of key sector ETFs vs SPY.
        
        Key ETFs for AI context:
        - QQQ (Nasdaq-100 / big tech)
        - SOXX (Semiconductors)
        - IGV (Software)
        """
        rs_data = {
            "timestamp": datetime.now().isoformat(),
            "period": period,
            "spy_return": None,
            "sectors": {},
            "rankings": [],
            "ai_sector_strength": "neutral",
        }
        
        # Get SPY baseline
        spy = self._get_market_data(self.MARKET_TICKERS["sp500"], period)
        if not spy:
            return rs_data
        
        spy_return = spy.get("change", 0)
        rs_data["spy_return"] = round(spy_return * 100, 2)
        
        # Key sectors for AI
        sector_tickers = {
            "QQQ (Nasdaq-100)": self.MARKET_TICKERS.get("qqq", "QQQ"),
            "SOXX (Semiconductors)": self.MARKET_TICKERS.get("soxx", "SOXX"),
            "IGV (Software)": self.MARKET_TICKERS.get("software_etf", "IGV"),
            "XLK (Tech Sector)": self.MARKET_TICKERS.get("tech_etf", "XLK"),
            "SMH (Semis)": self.MARKET_TICKERS.get("semi_etf", "SMH"),
            "ARKK (Innovation)": self.MARKET_TICKERS.get("arkk", "ARKK"),
            "XLU (Utilities)": self.MARKET_TICKERS.get("utilities", "XLU"),
            "FXI (China)": self.MARKET_TICKERS.get("china_etf", "FXI"),
            "KWEB (China Internet)": self.MARKET_TICKERS.get("kweb", "KWEB"),
        }
        
        for name, ticker in sector_tickers.items():
            data = self._get_market_data(ticker, period)
            if data:
                sector_return = data.get("change", 0)
                relative_strength = sector_return - spy_return
                
                rs_data["sectors"][name] = {
                    "return": round(sector_return * 100, 2),
                    "relative_strength": round(relative_strength * 100, 2),
                    "outperforming": relative_strength > 0,
                }
        
        # Rank sectors
        rs_data["rankings"] = sorted(
            [(name, s["relative_strength"]) for name, s in rs_data["sectors"].items()],
            key=lambda x: x[1],
            reverse=True
        )
        
        # Assess AI sector strength
        qqq_rs = rs_data["sectors"].get("QQQ (Nasdaq-100)", {}).get("relative_strength", 0)
        soxx_rs = rs_data["sectors"].get("SOXX (Semiconductors)", {}).get("relative_strength", 0)
        igv_rs = rs_data["sectors"].get("IGV (Software)", {}).get("relative_strength", 0)
        
        avg_ai_rs = (qqq_rs + soxx_rs + igv_rs) / 3
        
        if avg_ai_rs > 3:
            rs_data["ai_sector_strength"] = "strong_outperformance"
        elif avg_ai_rs > 1:
            rs_data["ai_sector_strength"] = "outperforming"
        elif avg_ai_rs > -1:
            rs_data["ai_sector_strength"] = "inline"
        elif avg_ai_rs > -3:
            rs_data["ai_sector_strength"] = "underperforming"
        else:
            rs_data["ai_sector_strength"] = "strong_underperformance"
        
        return rs_data
    
    def get_geopolitical_risk_context(self) -> Dict[str, Any]:
        """
        Get geopolitical risk context for tech/AI sector.
        
        Key risks:
        - US-China tech tensions
        - Export controls
        - Chip supply chain
        - AI regulation
        """
        geo_risk = {
            "timestamp": datetime.now().isoformat(),
            "us_china_tension_level": "moderate",
            "risk_factors": [],
            "opportunities": [],
            "exposure_indicators": {},
            "overall_risk_level": "moderate",
        }
        
        # Check China-exposed ETFs for stress signals
        china = self._get_market_data(self.MARKET_TICKERS.get("china_etf", "FXI"), "1mo")
        kweb = self._get_market_data(self.MARKET_TICKERS.get("kweb", "KWEB"), "1mo")
        spy = self._get_market_data(self.MARKET_TICKERS["sp500"], "1mo")
        
        if china and spy:
            china_vs_spy = china.get("change", 0) - spy.get("change", 0)
            geo_risk["exposure_indicators"]["china_vs_spy_1m"] = round(china_vs_spy * 100, 2)
            
            if china_vs_spy < -0.10:
                geo_risk["risk_factors"].append("China ETF significant underperformance - elevated tension signal")
                geo_risk["us_china_tension_level"] = "elevated"
        
        if kweb and spy:
            kweb_vs_spy = kweb.get("change", 0) - spy.get("change", 0)
            geo_risk["exposure_indicators"]["kweb_vs_spy_1m"] = round(kweb_vs_spy * 100, 2)
            
            if kweb_vs_spy < -0.15:
                geo_risk["risk_factors"].append("China internet stocks weak - regulatory/geopolitical concerns")
        
        # Load risk indicators from config if available
        risk_config_path = Path(__file__).parent.parent / "config" / "risk_indicators.json"
        if risk_config_path.exists():
            try:
                with open(risk_config_path, 'r') as f:
                    config = json.load(f)
                    geo_risk["configured_risks"] = config.get("geopolitical", {})
            except (json.JSONDecodeError, IOError):
                pass
        
        # Overall risk assessment
        risk_count = len(geo_risk["risk_factors"])
        if risk_count >= 3:
            geo_risk["overall_risk_level"] = "high"
        elif risk_count >= 1:
            geo_risk["overall_risk_level"] = "elevated"
        else:
            geo_risk["overall_risk_level"] = "moderate"
        
        return geo_risk
    
    def get_comprehensive_macro_context(self) -> Dict[str, Any]:
        """
        Get all macro context in one call.
        
        Combines:
        - Interest rates
        - PMI/enterprise spending
        - Tech employment
        - VIX/risk appetite
        - Sector relative strength
        - Geopolitical risk
        - Regime classification
        """
        context = {
            "timestamp": datetime.now().isoformat(),
            "interest_rates": self.get_interest_rate_analysis(),
            "pmi_enterprise": self.get_pmi_ism_analysis(),
            "tech_employment": self.get_tech_employment_data(),
            "vix_analysis": self.get_vix_analysis(),
            "sector_strength": self.get_sector_etf_relative_strength(),
            "geopolitical": self.get_geopolitical_risk_context(),
        }
        
        # Use regime classifier if available
        if RegimeClassifier:
            try:
                classifier = RegimeClassifier()
                regime_data = classifier.get_regime_for_ai_signals()
                context["regime"] = regime_data
            except Exception as e:
                logger.warning(f"Could not get regime classification: {e}")
                context["regime"] = {"regime": "unknown", "confidence": 0}
        
        # Generate summary
        context["summary"] = self._generate_macro_summary(context)
        
        return context
    
    def _generate_macro_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate human-readable macro summary."""
        summary = {
            "headline": "",
            "key_points": [],
            "signal_implications": {},
        }
        
        # Rate environment
        rate_env = context.get("interest_rates", {}).get("assessment", {}).get("rate_environment", "unknown")
        if rate_env == "restrictive":
            summary["key_points"].append("Restrictive monetary policy - headwind for growth/AI")
        elif rate_env == "accommodative":
            summary["key_points"].append("Accommodative monetary policy - tailwind for growth/AI")
        
        # VIX regime
        vix_regime = context.get("vix_analysis", {}).get("regime", "normal")
        if vix_regime in ["fear", "extreme"]:
            summary["key_points"].append(f"High volatility ({vix_regime}) - reduce signal confidence")
        elif vix_regime == "complacent":
            summary["key_points"].append("Low volatility - risk of complacency")
        
        # Sector strength
        sector_strength = context.get("sector_strength", {}).get("ai_sector_strength", "neutral")
        if sector_strength in ["strong_outperformance", "outperforming"]:
            summary["key_points"].append("AI/tech sectors showing relative strength")
        elif sector_strength in ["underperforming", "strong_underperformance"]:
            summary["key_points"].append("AI/tech sectors underperforming - sector rotation")
        
        # Enterprise spending
        spending = context.get("pmi_enterprise", {}).get("enterprise_spending_outlook", "moderate")
        summary["key_points"].append(f"Enterprise spending outlook: {spending}")
        
        # Geopolitical
        geo_risk = context.get("geopolitical", {}).get("overall_risk_level", "moderate")
        if geo_risk in ["elevated", "high"]:
            summary["key_points"].append(f"Geopolitical risk {geo_risk} - monitor China exposure")
        
        # Signal implications
        summary["signal_implications"] = {
            "confidence_modifier": self._calculate_confidence_modifier(context),
            "bullish_bias_adjustment": self._calculate_bullish_adjustment(context),
            "recommendation": self._get_macro_recommendation(context),
        }
        
        # Headline
        regime = context.get("regime", {}).get("regime", "unknown")
        summary["headline"] = f"Market Regime: {regime.upper()} | VIX: {vix_regime} | AI Sector: {sector_strength}"
        
        return summary
    
    def _calculate_confidence_modifier(self, context: Dict[str, Any]) -> float:
        """Calculate signal confidence modifier based on macro."""
        modifier = 1.0
        
        # VIX impact
        vix_regime = context.get("vix_analysis", {}).get("regime", "normal")
        vix_modifiers = {
            "complacent": 1.0,
            "normal": 1.0,
            "elevated": 0.9,
            "high": 0.8,
            "fear": 0.65,
            "extreme": 0.5,
        }
        modifier *= vix_modifiers.get(vix_regime, 1.0)
        
        # Sector strength impact
        sector = context.get("sector_strength", {}).get("ai_sector_strength", "inline")
        if sector in ["strong_outperformance", "outperforming"]:
            modifier *= 1.1
        elif sector in ["underperforming", "strong_underperformance"]:
            modifier *= 0.9
        
        return round(min(1.2, max(0.4, modifier)), 2)
    
    def _calculate_bullish_adjustment(self, context: Dict[str, Any]) -> float:
        """Calculate bullish bias adjustment."""
        adjustment = 0.0
        
        # Regime impact
        regime = context.get("regime", {}).get("regime", "unknown")
        regime_adj = {
            "bull": 0.15,
            "recovery": 0.1,
            "sideways": 0.0,
            "bear": -0.15,
            "crisis": -0.2,
        }
        adjustment += regime_adj.get(regime, 0)
        
        # Sector strength
        sector = context.get("sector_strength", {}).get("ai_sector_strength", "inline")
        if sector == "strong_outperformance":
            adjustment += 0.1
        elif sector == "strong_underperformance":
            adjustment -= 0.1
        
        return round(adjustment, 2)
    
    def _get_macro_recommendation(self, context: Dict[str, Any]) -> str:
        """Get macro-based recommendation."""
        regime = context.get("regime", {}).get("regime", "unknown")
        vix = context.get("vix_analysis", {}).get("regime", "normal")
        sector = context.get("sector_strength", {}).get("ai_sector_strength", "inline")
        
        if vix in ["fear", "extreme"]:
            return "Reduce position sizes, widen stops, focus on quality"
        
        if regime == "bull" and sector in ["outperforming", "strong_outperformance"]:
            return "Favorable environment for AI signals, lean bullish"
        
        if regime == "bear":
            return "Cautious on bullish signals, require higher conviction"
        
        return "Neutral environment, selective signal execution"
    
    def generate_ai_sector_outlook(self) -> Dict[str, Any]:
        """
        Generate comprehensive AI sector outlook.
        
        Combines economic snapshot and sector context into
        an actionable outlook for AI investments.
        """
        snapshot = self.get_economic_snapshot()
        sector = self.get_sector_context()
        
        # Generate outlook
        outlook = {
            "timestamp": datetime.now().isoformat(),
            "economic_snapshot": snapshot.to_dict(),
            "sector_context": sector.to_dict(),
        }
        
        # Overall assessment
        bullish_factors = 0
        bearish_factors = 0
        
        # Regime contribution
        if snapshot.regime == MarketRegime.RISK_ON:
            bullish_factors += 2
        elif snapshot.regime == MarketRegime.RISK_OFF:
            bearish_factors += 2
        elif snapshot.regime == MarketRegime.HIGH_VOLATILITY:
            bearish_factors += 1
        
        # Sector momentum contribution
        if sector.ai_sector_momentum in ["strong_bullish", "bullish"]:
            bullish_factors += 2
        elif sector.ai_sector_momentum in ["bearish"]:
            bearish_factors += 2
        
        # Rate environment
        if sector.growth_vs_value > 0:
            bullish_factors += 1
        elif sector.growth_vs_value < 0:
            bearish_factors += 1
        
        # Generate assessment
        net_score = bullish_factors - bearish_factors
        
        if net_score >= 3:
            overall = "strongly_favorable"
            recommendation = "Overweight AI sector"
        elif net_score >= 1:
            overall = "favorable"
            recommendation = "Maintain AI exposure"
        elif net_score <= -3:
            overall = "unfavorable"
            recommendation = "Underweight AI sector"
        elif net_score <= -1:
            overall = "cautious"
            recommendation = "Reduce aggressive positions"
        else:
            overall = "neutral"
            recommendation = "Selective exposure"
        
        outlook["assessment"] = {
            "overall": overall,
            "bullish_factors": bullish_factors,
            "bearish_factors": bearish_factors,
            "net_score": net_score,
            "recommendation": recommendation,
        }
        
        # Key considerations for AI signals
        outlook["ai_signal_context"] = {
            "sentiment_reliability": self._assess_sentiment_reliability(snapshot, sector),
            "momentum_relevance": self._assess_momentum_relevance(sector),
            "key_risks": self._identify_key_risks(snapshot, sector),
            "key_catalysts": self._identify_catalysts(snapshot, sector),
        }
        
        return outlook
    
    def _assess_sentiment_reliability(
        self, 
        snapshot: EconomicSnapshot, 
        sector: SectorContext
    ) -> str:
        """Assess how reliable sentiment signals are in current environment."""
        if snapshot.regime == MarketRegime.HIGH_VOLATILITY:
            return "low - high volatility distorts sentiment-price relationship"
        elif snapshot.regime == MarketRegime.RISK_OFF:
            return "moderate - bearish macro may override positive sentiment"
        elif sector.ai_sector_momentum in ["strong_bullish"]:
            return "high - sector tailwinds support bullish sentiment"
        else:
            return "moderate - standard conditions"
    
    def _assess_momentum_relevance(self, sector: SectorContext) -> str:
        """Assess how relevant momentum signals are."""
        if abs(sector.tech_vs_market) > 0.05:
            return "high - strong sector trends"
        elif abs(sector.semis_vs_market) > 0.03:
            return "moderate - semiconductor cycle in focus"
        else:
            return "neutral - no strong directional bias"
    
    def _identify_key_risks(
        self, 
        snapshot: EconomicSnapshot, 
        sector: SectorContext
    ) -> List[str]:
        """Identify key macro risks for AI sector."""
        risks = list(sector.macro_headwinds)
        
        if snapshot.vix and snapshot.vix > 25:
            risks.append("Elevated market volatility")
        
        if snapshot.yield_curve_spread and snapshot.yield_curve_spread < 0:
            risks.append("Inverted yield curve (recession risk)")
        
        if snapshot.fed_funds_rate and snapshot.fed_funds_rate > 4.5:
            risks.append("High interest rate environment")
        
        return risks
    
    def _identify_catalysts(
        self, 
        snapshot: EconomicSnapshot, 
        sector: SectorContext
    ) -> List[str]:
        """Identify potential catalysts for AI sector."""
        catalysts = list(sector.macro_tailwinds)
        
        if snapshot.vix and snapshot.vix < 15:
            catalysts.append("Low volatility supports risk assets")
        
        if sector.semis_vs_market > 0.03:
            catalysts.append("Semiconductor leadership indicates AI demand")
        
        return catalysts
    
    def contextualize_signal(
        self,
        entity_id: str,
        briefai_sentiment: float,
        briefai_momentum: str
    ) -> Dict[str, Any]:
        """
        Contextualize a briefAI signal with macro backdrop.
        
        Args:
            entity_id: Entity identifier
            briefai_sentiment: briefAI sentiment (0-10)
            briefai_momentum: briefAI momentum assessment
            
        Returns:
            Dict with signal context and adjustments
        """
        outlook = self.generate_ai_sector_outlook()
        
        # Base signal interpretation
        signal_bullish = briefai_sentiment > 6.0 or briefai_momentum == "bullish"
        signal_bearish = briefai_sentiment < 4.0 or briefai_momentum == "bearish"
        
        # Macro adjustment
        macro_score = outlook["assessment"]["net_score"]
        
        adjustment = 0
        notes = []
        
        if signal_bullish:
            if macro_score >= 2:
                adjustment = 0.5
                notes.append("Bullish signal supported by favorable macro")
            elif macro_score <= -2:
                adjustment = -1.0
                notes.append("Caution: Bullish signal in unfavorable macro")
        elif signal_bearish:
            if macro_score <= -2:
                adjustment = -0.5
                notes.append("Bearish signal confirmed by weak macro")
            elif macro_score >= 2:
                adjustment = 0.5
                notes.append("Bearish signal may be contrarian in strong macro")
        
        # Volatility adjustment
        snapshot = outlook["economic_snapshot"]
        if snapshot["market"].get("vix") and snapshot["market"]["vix"] > 25:
            notes.append("High volatility - widen confidence intervals")
        
        return {
            "entity_id": entity_id,
            "original_sentiment": briefai_sentiment,
            "original_momentum": briefai_momentum,
            "macro_context": {
                "regime": snapshot["regime"]["classification"],
                "overall_assessment": outlook["assessment"]["overall"],
            },
            "signal_adjustment": {
                "sentiment_modifier": adjustment,
                "adjusted_sentiment": max(0, min(10, briefai_sentiment + adjustment)),
                "notes": notes,
            },
            "reliability": outlook["ai_signal_context"]["sentiment_reliability"],
            "key_risks": outlook["ai_signal_context"]["key_risks"],
            "timestamp": datetime.now().isoformat(),
        }


if __name__ == "__main__":
    print("Testing Economic Context Provider")
    print("=" * 60)
    
    provider = EconomicContextProvider()
    
    # Get economic snapshot
    print("\n1. Economic Snapshot")
    print("-" * 40)
    snapshot = provider.get_economic_snapshot()
    print(f"  VIX: {snapshot.vix}")
    print(f"  S&P 500: {snapshot.sp500_level}")
    print(f"  Market Regime: {snapshot.regime.value}")
    print(f"  Regime Confidence: {snapshot.regime_confidence:.2f}")
    
    # Get sector context
    print("\n2. AI Sector Context")
    print("-" * 40)
    sector = provider.get_sector_context()
    print(f"  Tech vs Market: {sector.tech_vs_market*100:.2f}%")
    print(f"  Semis vs Market: {sector.semis_vs_market*100:.2f}%")
    print(f"  AI Sector Momentum: {sector.ai_sector_momentum}")
    print(f"  Headwinds: {sector.macro_headwinds}")
    print(f"  Tailwinds: {sector.macro_tailwinds}")
    
    # Generate outlook
    print("\n3. AI Sector Outlook")
    print("-" * 40)
    outlook = provider.generate_ai_sector_outlook()
    assessment = outlook["assessment"]
    print(f"  Overall: {assessment['overall']}")
    print(f"  Recommendation: {assessment['recommendation']}")
    print(f"  Net Score: {assessment['net_score']}")
    
    # Contextualize a signal
    print("\n4. Signal Contextualization")
    print("-" * 40)
    context = provider.contextualize_signal("nvidia", 7.5, "bullish")
    print(f"  Original sentiment: {context['original_sentiment']}")
    print(f"  Adjusted sentiment: {context['signal_adjustment']['adjusted_sentiment']}")
    print(f"  Reliability: {context['reliability']}")
    for note in context['signal_adjustment']['notes']:
        print(f"    - {note}")
