"""
Financial Signal Scorer

Scores financial/capital flow signals:
- Funding: Total raised, recent rounds, valuation
- SEC EDGAR: IPO filings (S-1), quarterly reports
- VC portfolios: Investor quality (future)

Scoring methodology:
- Log scale for funding amounts (USD)
- Recency weighting for funding rounds
- Filing type scoring for SEC
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from .base_scorer import BaseScorer


class FinancialScorer(BaseScorer):
    """
    Scores financial/capital flow signals.

    Data sources:
    - funding: Total raised, recent rounds, lead investors
    - sec_edgar: S-1, 10-K, 10-Q filings
    - vc_portfolio: Investor quality signals (future)
    """

    # Component weights
    WEIGHTS = {
        'total_funding': 0.35,
        'recent_funding': 0.25,
        'funding_recency': 0.15,
        'sec_activity': 0.15,
        'investor_quality': 0.10,
    }

    # Funding thresholds (log scale)
    # $10B (10^10) = 100
    FUNDING_MAX_LOG = 10.0

    # SEC filing scores
    SEC_FILING_SCORES = {
        's-1': 100,      # IPO filing - highest signal
        's-1/a': 95,     # Amended S-1
        '424b': 90,      # Prospectus (post-IPO)
        '10-k': 70,      # Annual report (established company)
        '10-q': 50,      # Quarterly report
        '8-k': 40,       # Current report (material events)
        'def 14a': 35,   # Proxy statement
        '13f': 30,       # Institutional holdings
        '4': 20,         # Insider trading
    }

    @property
    def category(self) -> str:
        return "financial"

    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate financial score from raw data.

        Expected raw_data keys:
        - source: "funding" | "sec_edgar" | "crunchbase"
        - total_funding_usd: int
        - last_funding_amount: int
        - last_funding_date: str | datetime
        - funding_rounds: List[Dict]
        - filing_type: str (SEC)
        - filing_date: str | datetime
        - valuation: int
        - investors: List[str]
        """
        source = raw_data.get('source', 'funding')

        if source == 'sec_edgar':
            return self._score_sec_filing(raw_data)
        else:
            return self._score_funding(raw_data)

    def _score_funding(self, data: Dict[str, Any]) -> float:
        """Score funding-related data."""
        components = {}

        # Total funding (35%)
        total_funding = data.get('total_funding_usd', data.get('funding_total', 0))
        if total_funding > 0:
            funding_score = self.log_scale(total_funding, self.FUNDING_MAX_LOG)
            components['total_funding'] = (funding_score, self.WEIGHTS['total_funding'])

        # Most recent funding round (25%)
        last_funding = data.get('last_funding_amount', data.get('last_round_amount', 0))
        if last_funding > 0:
            recent_score = self.log_scale(last_funding, 9.0)  # $1B recent = 100
            components['recent_funding'] = (recent_score, self.WEIGHTS['recent_funding'])

        # Funding recency (15%)
        last_date = data.get('last_funding_date', data.get('last_round_date'))
        if last_date:
            recency = self._score_funding_recency(last_date)
            components['funding_recency'] = (recency, self.WEIGHTS['funding_recency'])

        # Valuation bonus (if available)
        valuation = data.get('valuation', data.get('post_money_valuation', 0))
        if valuation > 0:
            # $100B valuation (10^11) = 100
            valuation_score = self.log_scale(valuation, 11.0)
            # Add as bonus, reduce total funding weight
            components['valuation'] = (valuation_score, 0.15)
            if 'total_funding' in components:
                score, _ = components['total_funding']
                components['total_funding'] = (score, 0.25)

        # Investor quality (10%)
        investors = data.get('investors', data.get('lead_investors', []))
        if investors:
            investor_score = self._score_investors(investors)
            components['investor_quality'] = (investor_score, self.WEIGHTS['investor_quality'])

        if not components:
            return 0.0

        # Normalize weights
        total_weight = sum(w for _, w in components.values())
        normalized = {k: (s, w / total_weight) for k, (s, w) in components.items()}

        return self.weighted_average(normalized)

    def _score_sec_filing(self, data: Dict[str, Any]) -> float:
        """Score SEC EDGAR filing data."""
        filing_type = data.get('filing_type', '').lower()
        filing_date = data.get('filing_date')

        # Base score from filing type
        base_score = 0.0
        for key, score in self.SEC_FILING_SCORES.items():
            if key in filing_type:
                base_score = score
                break

        if base_score == 0:
            base_score = 30.0  # Default for unknown filing types

        # Apply recency decay (SEC filings have shorter relevance)
        if filing_date:
            recency = self._score_filing_recency(filing_date)
            # Weight: 70% filing importance, 30% recency
            return base_score * 0.7 + recency * 0.3

        return base_score * 0.7  # Without date, penalize slightly

    def _score_funding_recency(self, date: Any) -> float:
        """
        Score funding recency.
        Half-life: 180 days (6 months).
        """
        if isinstance(date, str):
            try:
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                return 50.0

        if not isinstance(date, datetime):
            return 50.0

        return self.recency_decay(date, half_life_days=180) * 100

    def _score_filing_recency(self, date: Any) -> float:
        """
        Score SEC filing recency.
        Half-life: 90 days (quarterly relevance).
        """
        if isinstance(date, str):
            try:
                date = datetime.fromisoformat(date.replace('Z', '+00:00'))
            except:
                return 50.0

        if not isinstance(date, datetime):
            return 50.0

        return self.recency_decay(date, half_life_days=90) * 100

    def _score_investors(self, investors: List[Any]) -> float:
        """
        Score investor quality.
        Known top-tier VCs get bonus points.
        """
        if not investors:
            return 30.0

        # Top-tier investors (non-exhaustive)
        top_tier = {
            'sequoia', 'a16z', 'andreessen horowitz', 'benchmark',
            'accel', 'greylock', 'kleiner perkins', 'founders fund',
            'index ventures', 'general catalyst', 'lightspeed',
            'tiger global', 'softbank', 'coatue', 'insight partners',
            'thrive capital', 'khosla ventures', 'bessemer',
            'ggv capital', 'redpoint', 'spark capital', 'ivp',
            'nea', 'battery ventures', 'scale venture',
        }

        # Corporate strategic investors
        strategic = {
            'google', 'microsoft', 'amazon', 'nvidia', 'meta',
            'apple', 'salesforce', 'intel', 'ibm', 'oracle',
        }

        investor_names = []
        for inv in investors:
            if isinstance(inv, str):
                investor_names.append(inv.lower())
            elif isinstance(inv, dict):
                name = inv.get('name', inv.get('investor_name', ''))
                investor_names.append(name.lower())

        # Count matches
        top_tier_count = sum(1 for name in investor_names
                            if any(t in name for t in top_tier))
        strategic_count = sum(1 for name in investor_names
                             if any(s in name for s in strategic))

        # Base score from investor count
        base_score = min(60.0, len(investors) * 10)

        # Bonuses
        top_tier_bonus = min(30.0, top_tier_count * 15)
        strategic_bonus = min(20.0, strategic_count * 10)

        return min(100.0, base_score + top_tier_bonus + strategic_bonus)

    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """Calculate confidence based on data source and completeness."""
        source = raw_data.get('source', 'funding')

        base_confidence = {
            'sec_edgar': 0.95,    # Official filings
            'crunchbase': 0.85,   # Aggregated data
            'funding': 0.80,
        }.get(source, 0.7)

        # Check for key data
        has_funding = raw_data.get('total_funding_usd', 0) > 0 or \
                      raw_data.get('funding_total', 0) > 0
        has_filing = raw_data.get('filing_type') is not None

        if not has_funding and not has_filing:
            return 0.3

        return base_confidence

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """Get breakdown of component scores."""
        components = {}

        total_funding = raw_data.get('total_funding_usd', raw_data.get('funding_total', 0))
        if total_funding > 0:
            components['total_funding'] = self.log_scale(total_funding, self.FUNDING_MAX_LOG)

        last_funding = raw_data.get('last_funding_amount', 0)
        if last_funding > 0:
            components['recent_round'] = self.log_scale(last_funding, 9.0)

        valuation = raw_data.get('valuation', 0)
        if valuation > 0:
            components['valuation'] = self.log_scale(valuation, 11.0)

        filing_type = raw_data.get('filing_type', '')
        if filing_type:
            components['sec_filing'] = self._score_sec_filing(raw_data)

        return components
