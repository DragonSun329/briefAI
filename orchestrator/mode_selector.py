#!/usr/bin/env python3
"""
Pipeline Mode Selector

Manages dual-mode pipeline architecture:
- NEWS mode: General AI news briefing (existing pipeline)
- PRODUCT mode: AI product review intelligence (new pipeline)
- BOTH mode: Run both pipelines sequentially
"""

from enum import Enum
from pathlib import Path
from typing import Dict, Any, List
from loguru import logger


class PipelineMode(Enum):
    """Pipeline operating modes"""
    NEWS = "news"
    PRODUCT = "product"
    BOTH = "both"

    @classmethod
    def from_string(cls, mode_str: str) -> 'PipelineMode':
        """Convert string to PipelineMode enum"""
        mode_str = mode_str.lower()
        if mode_str in ['news', 'n']:
            return cls.NEWS
        elif mode_str in ['product', 'p', 'products']:
            return cls.PRODUCT
        elif mode_str in ['both', 'all']:
            return cls.BOTH
        else:
            raise ValueError(f"Invalid mode: {mode_str}. Use 'news', 'product', or 'both'")


class ModeConfig:
    """Configuration for a specific pipeline mode"""

    def __init__(self, mode: PipelineMode, base_dir: str = "."):
        """
        Initialize mode-specific configuration

        Args:
            mode: Pipeline mode (NEWS or PRODUCT)
            base_dir: Base directory for config files
        """
        if mode == PipelineMode.BOTH:
            raise ValueError("Cannot create ModeConfig for BOTH mode - use NEWS or PRODUCT")

        self.mode = mode
        self.base_dir = Path(base_dir)

        # Mode-specific config file paths
        self.sources_file = self.base_dir / f"config/sources_{mode.value}.json"
        self.categories_file = self.base_dir / f"config/categories_{mode.value}.json"
        self.template_file = self.base_dir / f"config/template_{mode.value}.md"

        # Mode-specific report settings
        if mode == PipelineMode.PRODUCT:
            self.report_prefix = "产品周报"
            self.report_dir = self.base_dir / "data/reports/product_reviews"
        else:
            self.report_prefix = "AI周报"
            self.report_dir = self.base_dir / "data/reports"

        # Mode-specific pipeline phases
        self.enabled_phases = self._get_enabled_phases()

        # Mode-specific scoring dimensions
        self.scoring_dimensions = self._get_scoring_dimensions()

        logger.info(f"Mode config initialized: {mode.value.upper()}")
        logger.debug(f"  Sources: {self.sources_file}")
        logger.debug(f"  Categories: {self.categories_file}")
        logger.debug(f"  Template: {self.template_file}")

    def _get_enabled_phases(self) -> List[str]:
        """
        Get list of enabled pipeline phases for this mode

        Returns:
            List of phase names
        """
        # Common phases (both modes)
        common_phases = [
            'initialization',
            'scraping',
            'tier1_filter',
            'tier2_batch_eval',
            'tier3_5d_eval',
            'ranking',
            'paraphrasing',
            'entity_background',
            'quality_validation',
            'report_generation',
            'finalization'
        ]

        # Product-specific phases (inserted after scraping)
        product_only_phases = [
            'review_extraction',      # After scraping
            'product_deduplication',  # After review_extraction
            'review_aggregation',     # After product_deduplication
            'trending_calculation'    # After tier3_5d_eval, before ranking
        ]

        if self.mode == PipelineMode.NEWS:
            return common_phases
        elif self.mode == PipelineMode.PRODUCT:
            # Insert product-specific phases in correct positions
            phases = common_phases.copy()

            # Insert review phases after scraping
            scraping_idx = phases.index('scraping')
            for i, phase in enumerate(product_only_phases[:3]):
                phases.insert(scraping_idx + 1 + i, phase)

            # Insert trending calculation after tier3_5d_eval
            tier3_idx = phases.index('tier3_5d_eval')
            phases.insert(tier3_idx + 1, product_only_phases[3])

            return phases
        else:
            return common_phases

    def _get_scoring_dimensions(self) -> Dict[str, Dict[str, Any]]:
        """
        Get 5D scoring dimensions for this mode

        Returns:
            Dictionary of dimension name -> {weight, description}
        """
        if self.mode == PipelineMode.NEWS:
            # NEWS mode: Original 5D dimensions
            return {
                'market_impact': {
                    'weight': 0.25,
                    'description': 'Industry-wide implications, market disruption potential'
                },
                'competitive_impact': {
                    'weight': 0.20,
                    'description': 'Effect on competitive landscape, market consolidation'
                },
                'strategic_relevance': {
                    'weight': 0.20,
                    'description': 'Alignment with CEO strategic priorities'
                },
                'operational_relevance': {
                    'weight': 0.15,
                    'description': 'Practical application to business operations'
                },
                'credibility': {
                    'weight': 0.10,
                    'description': 'Source reliability, evidence quality, verification status'
                }
            }
        elif self.mode == PipelineMode.PRODUCT:
            # PRODUCT mode: Product-focused 5D dimensions
            return {
                'viral_potential': {
                    'weight': 0.30,
                    'description': 'Trending signals, social buzz, upvote velocity'
                },
                'user_satisfaction': {
                    'weight': 0.25,
                    'description': 'Review sentiment, user ratings, testimonials'
                },
                'productivity_impact': {
                    'weight': 0.20,
                    'description': 'Value proposition, time savings, efficiency gains'
                },
                'innovation_factor': {
                    'weight': 0.15,
                    'description': 'Novelty, breakthrough features, differentiation'
                },
                'credibility': {
                    'weight': 0.10,
                    'description': 'Source reliability, verified reviews, authenticity'
                }
            }
        else:
            return {}

    def validate_config_files(self) -> Dict[str, bool]:
        """
        Check if all required config files exist

        Returns:
            Dictionary of file -> exists status
        """
        status = {
            'sources': self.sources_file.exists(),
            'categories': self.categories_file.exists(),
            'template': self.template_file.exists()
        }

        missing = [k for k, v in status.items() if not v]
        if missing:
            logger.warning(f"Missing config files for {self.mode.value} mode: {missing}")
        else:
            logger.info(f"All config files found for {self.mode.value} mode")

        return status

    def get_report_filename(self, date_str: str = None) -> str:
        """
        Generate report filename for this mode

        Args:
            date_str: Date string (e.g., "20251101"). If None, uses current date

        Returns:
            Report filename
        """
        if date_str is None:
            from datetime import datetime
            date_str = datetime.now().strftime("%Y%m%d")

        return f"{self.report_prefix}_{date_str}_cn.md"

    def __str__(self) -> str:
        return f"ModeConfig({self.mode.value})"

    def __repr__(self) -> str:
        return f"ModeConfig(mode={self.mode.value}, sources={self.sources_file.name})"


class DualModePipeline:
    """Manages dual-mode pipeline execution"""

    def __init__(self, mode: PipelineMode, base_dir: str = "."):
        """
        Initialize dual-mode pipeline manager

        Args:
            mode: Pipeline mode (NEWS, PRODUCT, or BOTH)
            base_dir: Base directory for config files
        """
        self.mode = mode
        self.base_dir = Path(base_dir)

        # Create mode configs
        if mode == PipelineMode.BOTH:
            self.news_config = ModeConfig(PipelineMode.NEWS, base_dir)
            self.product_config = ModeConfig(PipelineMode.PRODUCT, base_dir)
            self.configs = [self.news_config, self.product_config]
        elif mode == PipelineMode.NEWS:
            self.news_config = ModeConfig(PipelineMode.NEWS, base_dir)
            self.configs = [self.news_config]
        elif mode == PipelineMode.PRODUCT:
            self.product_config = ModeConfig(PipelineMode.PRODUCT, base_dir)
            self.configs = [self.product_config]
        else:
            raise ValueError(f"Invalid mode: {mode}")

        logger.info(f"Dual-mode pipeline initialized: {mode.value.upper()}")

    def get_execution_plan(self) -> List[Dict[str, Any]]:
        """
        Get execution plan for selected mode(s)

        Returns:
            List of execution steps, each with mode and config
        """
        plan = []

        if self.mode == PipelineMode.BOTH:
            plan.append({
                'order': 1,
                'mode': PipelineMode.NEWS,
                'config': self.news_config,
                'description': 'Run NEWS mode pipeline (general AI news briefing)'
            })
            plan.append({
                'order': 2,
                'mode': PipelineMode.PRODUCT,
                'config': self.product_config,
                'description': 'Run PRODUCT mode pipeline (AI product review intelligence)'
            })
        else:
            plan.append({
                'order': 1,
                'mode': self.mode,
                'config': self.configs[0],
                'description': f'Run {self.mode.value.upper()} mode pipeline'
            })

        return plan

    def validate_all_configs(self) -> bool:
        """
        Validate all config files for selected mode(s)

        Returns:
            True if all configs are valid, False otherwise
        """
        all_valid = True

        for config in self.configs:
            status = config.validate_config_files()
            if not all(status.values()):
                all_valid = False
                logger.error(f"Config validation failed for {config.mode.value} mode")

        return all_valid


# Convenience functions

def get_mode_config(mode_str: str, base_dir: str = ".") -> ModeConfig:
    """
    Get mode configuration from mode string

    Args:
        mode_str: Mode string ("news", "product", or "both")
        base_dir: Base directory for config files

    Returns:
        ModeConfig instance

    Raises:
        ValueError: If mode is BOTH (use DualModePipeline instead)
    """
    mode = PipelineMode.from_string(mode_str)

    if mode == PipelineMode.BOTH:
        raise ValueError("Use DualModePipeline for BOTH mode")

    return ModeConfig(mode, base_dir)


def create_dual_mode_pipeline(mode_str: str, base_dir: str = ".") -> DualModePipeline:
    """
    Create dual-mode pipeline from mode string

    Args:
        mode_str: Mode string ("news", "product", or "both")
        base_dir: Base directory for config files

    Returns:
        DualModePipeline instance
    """
    mode = PipelineMode.from_string(mode_str)
    return DualModePipeline(mode, base_dir)


if __name__ == "__main__":
    # Example usage
    import sys

    if len(sys.argv) > 1:
        mode_str = sys.argv[1]

        try:
            pipeline = create_dual_mode_pipeline(mode_str)

            print(f"\n{'='*80}")
            print(f"Dual-Mode Pipeline: {pipeline.mode.value.upper()}")
            print(f"{'='*80}\n")

            # Validate configs
            if pipeline.validate_all_configs():
                print("✅ All config files validated\n")
            else:
                print("❌ Config validation failed\n")

            # Show execution plan
            plan = pipeline.get_execution_plan()
            print("Execution Plan:")
            for step in plan:
                print(f"  {step['order']}. {step['description']}")
                print(f"     Config: {step['config']}")
            print()

        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)
    else:
        print("Usage:")
        print("  python mode_selector.py <mode>")
        print()
        print("Modes:")
        print("  news     - Run NEWS mode pipeline only")
        print("  product  - Run PRODUCT mode pipeline only")
        print("  both     - Run both pipelines sequentially")
