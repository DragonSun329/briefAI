"""
Signal Scorers Package

Per-category scoring modules that normalize raw signal data to 0-100 scale.
Each scorer handles a specific signal dimension:
- Technical: GitHub stars, HuggingFace downloads, research citations
- Company: Crunchbase rank, employee metrics
- Financial: Funding amounts, SEC filings
- Product: ProductHunt upvotes, app store rankings
- Media: News sentiment and coverage
- Podcast: Expert podcast discussions and mentions
"""

from .base_scorer import BaseScorer
from .technical_scorer import TechnicalScorer
from .company_scorer import CompanyScorer
from .financial_scorer import FinancialScorer
from .product_scorer import ProductScorer
from .media_scorer import MediaScorer
from .podcast_scorer import PodcastScorer

__all__ = [
    'BaseScorer',
    'TechnicalScorer',
    'CompanyScorer',
    'FinancialScorer',
    'ProductScorer',
    'MediaScorer',
    'PodcastScorer',
]


def get_scorer(category: str, source: str = None) -> BaseScorer:
    """
    Factory function to get scorer by category name.

    Args:
        category: Signal category (technical, company, financial, product, media)
        source: Optional source hint for specialized scorers (e.g., 'podcast')

    Returns:
        Appropriate scorer instance
    """
    # Handle podcast as a specialized media scorer
    if source == 'podcast' or category == 'podcast':
        return PodcastScorer()

    scorers = {
        'technical': TechnicalScorer,
        'company': CompanyScorer,
        'financial': FinancialScorer,
        'product': ProductScorer,
        'media': MediaScorer,
    }
    scorer_class = scorers.get(category.lower())
    if scorer_class is None:
        raise ValueError(f"Unknown category: {category}")
    return scorer_class()
