"""
Company Presence Scorer

Scores company/organizational strength from market position signals:
- Crunchbase: CB Rank, employee count, growth metrics
- LinkedIn: Employee count, growth rate (future)
- Company registrations: Age, HQ location (future)

Scoring methodology:
- Uses bracket-based scoring for rankings (CB Rank)
- Log scale for employee counts
- Incorporates growth metrics for momentum
"""

from typing import Dict, Any, Optional
from datetime import datetime
from .base_scorer import BaseScorer


class CompanyScorer(BaseScorer):
    """
    Scores company presence/organizational strength signals.

    Data sources:
    - crunchbase: CB Rank, employee count, founded date
    - linkedin: Employee count, growth rate (future)
    """

    # CB Rank brackets (lower rank = better)
    # Rank 1-100 is top tier, etc.
    CB_RANK_BRACKETS = [
        (100, 100),      # Top 100 = score 100
        (500, 90),       # 101-500 = score 90
        (1000, 80),      # 501-1000 = score 80
        (5000, 65),      # 1001-5000 = score 65
        (10000, 50),     # 5001-10000 = score 50
        (50000, 35),     # 10001-50000 = score 35
        (100000, 20),    # 50001-100000 = score 20
        (float('inf'), 10),  # Beyond 100K = score 10
    ]

    # Component weights
    WEIGHTS = {
        'cb_rank': 0.40,
        'employee_count': 0.25,
        'employee_growth': 0.15,
        'company_age': 0.10,
        'funding_stage': 0.10,
    }

    @property
    def category(self) -> str:
        return "company"

    def score(self, raw_data: Dict[str, Any]) -> float:
        """
        Calculate company presence score from raw data.

        Expected raw_data keys:
        - source: "crunchbase" | "linkedin"
        - cb_rank: int (Crunchbase rank)
        - rank: int (alias for cb_rank)
        - employee_count: int
        - employee_growth_yoy: float (percentage)
        - founded_date: str | datetime
        - funding_stage: str (e.g., "Series C", "IPO")
        """
        source = raw_data.get('source', 'crunchbase')

        components = {}

        # CB Rank (40%)
        cb_rank = raw_data.get('cb_rank', raw_data.get('rank'))
        if cb_rank is not None:
            rank_score = self._score_cb_rank(cb_rank)
            components['cb_rank'] = (rank_score, self.WEIGHTS['cb_rank'])

        # Employee count (25%)
        employee_count = raw_data.get('employee_count', raw_data.get('employees'))
        if employee_count is not None:
            employee_score = self._score_employee_count(employee_count)
            components['employee_count'] = (employee_score, self.WEIGHTS['employee_count'])

        # Employee growth (15%)
        growth = raw_data.get('employee_growth_yoy', raw_data.get('growth_rate'))
        if growth is not None:
            growth_score = self._score_growth(growth)
            components['employee_growth'] = (growth_score, self.WEIGHTS['employee_growth'])

        # Company age (10%)
        founded = raw_data.get('founded_date', raw_data.get('founded'))
        if founded:
            age_score = self._score_company_age(founded)
            components['company_age'] = (age_score, self.WEIGHTS['company_age'])

        # Funding stage (10%)
        stage = raw_data.get('funding_stage', raw_data.get('stage'))
        if stage:
            stage_score = self._score_funding_stage(stage)
            components['funding_stage'] = (stage_score, self.WEIGHTS['funding_stage'])

        if not components:
            return 0.0

        # Normalize weights for available components
        total_weight = sum(w for _, w in components.values())
        normalized = {
            k: (s, w / total_weight) for k, (s, w) in components.items()
        }

        return self.weighted_average(normalized)

    def _score_cb_rank(self, rank: int) -> float:
        """
        Score Crunchbase rank using bracket system.
        Lower rank = better score.
        """
        if rank <= 0:
            return 0.0

        return self.bracket_scale(rank, self.CB_RANK_BRACKETS)

    def _score_employee_count(self, count: int) -> float:
        """
        Score employee count using log scale.
        10K employees (10^4) = 100
        """
        if count <= 0:
            return 0.0

        # Log scale: 10K employees = 100
        return self.log_scale(count, max_log=4.0)

    def _score_growth(self, growth_percent: float) -> float:
        """
        Score YoY employee growth.
        Uses linear scale capped at 100%.
        """
        # Cap at 100% growth for scoring
        capped_growth = min(100.0, max(-50.0, growth_percent))

        # Map -50% to 100% growth -> 0 to 100 score
        score = ((capped_growth + 50) / 150) * 100
        return round(score, 2)

    def _score_company_age(self, founded: Any) -> float:
        """
        Score company age.
        Sweet spot: 3-10 years (established but agile).
        """
        if isinstance(founded, str):
            try:
                # Try parsing year only
                if len(founded) == 4:
                    founded_year = int(founded)
                else:
                    founded_date = datetime.fromisoformat(founded.replace('Z', '+00:00'))
                    founded_year = founded_date.year
            except:
                return 50.0  # Default for unparseable
        elif isinstance(founded, datetime):
            founded_year = founded.year
        elif isinstance(founded, int):
            founded_year = founded
        else:
            return 50.0

        current_year = datetime.utcnow().year
        age_years = current_year - founded_year

        if age_years < 0:
            return 50.0

        # Scoring curve:
        # < 1 year: 30 (too new)
        # 1-3 years: 50-70 (early stage)
        # 3-10 years: 80-100 (sweet spot)
        # 10-20 years: 70-80 (established)
        # > 20 years: 50-60 (legacy)
        if age_years < 1:
            return 30.0
        elif age_years < 3:
            return 50.0 + (age_years / 3) * 20  # 50-70
        elif age_years <= 10:
            # Peak at 5-7 years
            if age_years <= 7:
                return 80.0 + ((age_years - 3) / 4) * 20  # 80-100
            else:
                return 100.0 - ((age_years - 7) / 3) * 10  # 100-90
        elif age_years <= 20:
            return 90.0 - ((age_years - 10) / 10) * 20  # 90-70
        else:
            return max(50.0, 70.0 - ((age_years - 20) / 10) * 10)  # 70-50

    def _score_funding_stage(self, stage: str) -> float:
        """Score company funding stage."""
        if not stage:
            return 30.0

        stage_lower = stage.lower().strip()

        # Stage scoring
        stage_scores = {
            'seed': 30,
            'pre-seed': 25,
            'angel': 25,
            'series a': 45,
            'series b': 60,
            'series c': 75,
            'series d': 85,
            'series e': 90,
            'series f': 92,
            'series g': 94,
            'late stage': 88,
            'growth': 80,
            'private equity': 85,
            'ipo': 100,
            'public': 100,
            'acquired': 70,
            'm&a': 70,
        }

        for key, score in stage_scores.items():
            if key in stage_lower:
                return float(score)

        return 40.0  # Default for unknown stages

    def get_confidence(self, raw_data: Dict[str, Any]) -> float:
        """Calculate confidence based on data completeness."""
        source = raw_data.get('source', 'crunchbase')

        base_confidence = {
            'crunchbase': 0.9,
            'linkedin': 0.85,
        }.get(source, 0.6)

        # Check data completeness
        key_fields = ['cb_rank', 'rank', 'employee_count', 'employees']
        has_key_field = any(raw_data.get(f) for f in key_fields)

        if not has_key_field:
            return 0.3

        return base_confidence

    def get_component_scores(self, raw_data: Dict[str, Any]) -> Dict[str, float]:
        """Get breakdown of component scores."""
        components = {}

        cb_rank = raw_data.get('cb_rank', raw_data.get('rank'))
        if cb_rank:
            components['cb_rank'] = self._score_cb_rank(cb_rank)

        employees = raw_data.get('employee_count', raw_data.get('employees'))
        if employees:
            components['employee_count'] = self._score_employee_count(employees)

        growth = raw_data.get('employee_growth_yoy')
        if growth:
            components['employee_growth'] = self._score_growth(growth)

        return components
