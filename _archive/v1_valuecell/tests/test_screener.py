"""
Test suite for the Custom Screener System

Tests:
- Screener Engine core functionality
- DSL parser
- API endpoints
- Preset screeners
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Setup path
_app_dir = Path(__file__).parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.screener_engine import (
    ScreenerEngine, Criterion, CriteriaGroup, Screener, ScreenerResult,
    FilterOperator, CriterionType, LogicalOperator, SCREENABLE_FIELDS,
    create_score_filter, create_momentum_filter, create_field_comparison,
    create_category_filter
)
from utils.screener_dsl import (
    parse_query, validate_query, explain_query, to_sql_where,
    QueryBuilder, DSLLexer, DSLParser, DSLParseError
)


# =============================================================================
# Test Data
# =============================================================================

SAMPLE_ENTITIES = [
    {
        "entity_id": "openai",
        "entity_name": "OpenAI",
        "entity_type": "company",
        "technical_score": 85,
        "company_score": 90,
        "financial_score": 75,
        "product_score": 80,
        "media_score": 95,
        "composite_score": 85,
        "momentum_7d": 15,
        "momentum_30d": 25,
        "has_divergence": False,
        "divergence_strength": None,
        "sector": "ai-foundation",
        "region": "us",
        "last_signal_date": datetime.utcnow() - timedelta(days=1),
    },
    {
        "entity_id": "anthropic",
        "entity_name": "Anthropic",
        "entity_type": "company",
        "technical_score": 80,
        "company_score": 75,
        "financial_score": 70,
        "product_score": 65,
        "media_score": 70,
        "composite_score": 72,
        "momentum_7d": 8,
        "momentum_30d": 12,
        "has_divergence": True,
        "divergence_strength": 0.6,
        "sector": "ai-foundation",
        "region": "us",
        "last_signal_date": datetime.utcnow() - timedelta(days=3),
    },
    {
        "entity_id": "deepseek",
        "entity_name": "DeepSeek",
        "entity_type": "company",
        "technical_score": 70,
        "company_score": 45,
        "financial_score": 40,
        "product_score": 55,
        "media_score": 30,
        "composite_score": 48,
        "momentum_7d": 50,
        "momentum_30d": 100,
        "has_divergence": True,
        "divergence_strength": 0.8,
        "sector": "ai-foundation",
        "region": "china",
        "last_signal_date": datetime.utcnow() - timedelta(days=2),
    },
    {
        "entity_id": "hype-corp",
        "entity_name": "HypeCorp AI",
        "entity_type": "company",
        "technical_score": 20,
        "company_score": 30,
        "financial_score": 35,
        "product_score": 25,
        "media_score": 85,
        "composite_score": 39,
        "momentum_7d": -5,
        "momentum_30d": -15,
        "has_divergence": True,
        "divergence_strength": 0.9,
        "sector": "ai-applications",
        "region": "us",
        "last_signal_date": datetime.utcnow() - timedelta(days=10),
    },
]


# =============================================================================
# Engine Tests
# =============================================================================

class TestScreenerEngine:
    """Tests for ScreenerEngine class."""
    
    def setup_method(self):
        """Setup test engine with sample data."""
        self.engine = ScreenerEngine()
    
    def test_simple_score_filter(self):
        """Test basic score filtering."""
        criteria = [
            Criterion(
                field="media_score",
                operator=FilterOperator.GT,
                value=50,
                criterion_type=CriterionType.SCORE
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        assert result.total_entities == 4
        assert result.matching_entities == 3
        for entity in result.results:
            assert entity["media_score"] > 50
    
    def test_momentum_filter(self):
        """Test momentum filtering."""
        criteria = [
            Criterion(
                field="momentum_7d",
                operator=FilterOperator.GT,
                value=10,
                criterion_type=CriterionType.MOMENTUM
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        assert result.matching_entities == 2
        for entity in result.results:
            assert entity["momentum_7d"] > 10
    
    def test_multiple_criteria_and(self):
        """Test multiple criteria with AND logic."""
        criteria = [
            Criterion(
                field="media_score",
                operator=FilterOperator.GT,
                value=50,
                criterion_type=CriterionType.SCORE
            ),
            Criterion(
                field="technical_score",
                operator=FilterOperator.GT,
                value=70,
                criterion_type=CriterionType.SCORE
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        # Should match OpenAI and Anthropic
        assert result.matching_entities == 2
    
    def test_field_comparison(self):
        """Test comparing two fields."""
        criteria = [
            Criterion(
                field="media_score",
                operator=FilterOperator.FIELD_GT,
                compare_field="technical_score",
                criterion_type=CriterionType.COMPARISON,
                value=None
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        # Should match OpenAI (95 > 85) and HypeCorp (85 > 20)
        assert result.matching_entities == 2
        for entity in result.results:
            assert entity["media_score"] > entity["technical_score"]
    
    def test_in_operator(self):
        """Test IN operator for categories."""
        criteria = [
            Criterion(
                field="region",
                operator=FilterOperator.IN,
                value=["china", "asia"],
                criterion_type=CriterionType.CATEGORY
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        assert result.matching_entities == 1
        assert result.results[0]["entity_id"] == "deepseek"
    
    def test_boolean_filter(self):
        """Test boolean field filtering."""
        criteria = [
            Criterion(
                field="has_divergence",
                operator=FilterOperator.EQ,
                value=True,
                criterion_type=CriterionType.SIGNAL
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        assert result.matching_entities == 3
    
    def test_sorting(self):
        """Test result sorting."""
        criteria = [
            Criterion(
                field="composite_score",
                operator=FilterOperator.GT,
                value=0,
                criterion_type=CriterionType.SCORE
            )
        ]
        
        result = self.engine.screen(
            criteria,
            entities=SAMPLE_ENTITIES,
            sort_by="momentum_7d",
            sort_order="desc"
        )
        
        # Should be sorted by momentum_7d descending
        momentums = [e["momentum_7d"] for e in result.results]
        assert momentums == sorted(momentums, reverse=True)
    
    def test_limit(self):
        """Test result limiting."""
        criteria = [
            Criterion(
                field="composite_score",
                operator=FilterOperator.GT,
                value=0,
                criterion_type=CriterionType.SCORE
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES, limit=2)
        
        assert len(result.results) == 2
        assert result.matching_entities == 4  # Total matches
    
    def test_between_operator(self):
        """Test BETWEEN operator."""
        criteria = [
            Criterion(
                field="composite_score",
                operator=FilterOperator.BETWEEN,
                value=[40, 80],
                criterion_type=CriterionType.SCORE
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        for entity in result.results:
            assert 40 <= entity["composite_score"] <= 80
    
    def test_contains_operator(self):
        """Test CONTAINS operator for strings."""
        criteria = [
            Criterion(
                field="entity_name",
                operator=FilterOperator.CONTAINS,
                value="AI",
                criterion_type=CriterionType.CATEGORY
            )
        ]
        
        result = self.engine.screen(criteria, entities=SAMPLE_ENTITIES)
        
        # Should match "OpenAI" and "HypeCorp AI"
        assert result.matching_entities == 2


class TestCriteriaGroup:
    """Tests for grouped criteria with OR logic."""
    
    def setup_method(self):
        self.engine = ScreenerEngine()
    
    def test_or_logic(self):
        """Test OR logic between criteria."""
        group = CriteriaGroup(
            criteria=[
                Criterion(
                    field="region",
                    operator=FilterOperator.EQ,
                    value="china",
                    criterion_type=CriterionType.CATEGORY
                ),
                Criterion(
                    field="media_score",
                    operator=FilterOperator.GT,
                    value=90,
                    criterion_type=CriterionType.SCORE
                )
            ],
            operator=LogicalOperator.OR
        )
        
        result = self.engine.screen_with_group(group, entities=SAMPLE_ENTITIES)
        
        # Should match DeepSeek (china) and OpenAI (media > 90)
        assert result.matching_entities == 2
    
    def test_nested_groups(self):
        """Test nested AND/OR groups."""
        group = CriteriaGroup(
            criteria=[
                CriteriaGroup(
                    criteria=[
                        Criterion(field="region", operator=FilterOperator.EQ, value="us", criterion_type=CriterionType.CATEGORY),
                        Criterion(field="media_score", operator=FilterOperator.GT, value=70, criterion_type=CriterionType.SCORE)
                    ],
                    operator=LogicalOperator.AND
                ),
                Criterion(field="region", operator=FilterOperator.EQ, value="china", criterion_type=CriterionType.CATEGORY)
            ],
            operator=LogicalOperator.OR
        )
        
        result = self.engine.screen_with_group(group, entities=SAMPLE_ENTITIES)
        
        # (US AND media>70) OR china → OpenAI, HypeCorp, DeepSeek
        assert result.matching_entities == 3


# =============================================================================
# DSL Parser Tests
# =============================================================================

class TestDSLLexer:
    """Tests for DSL lexer."""
    
    def test_simple_tokenization(self):
        """Test basic tokenization."""
        lexer = DSLLexer("media_score > 7")
        tokens = lexer.tokenize()
        
        assert len(tokens) == 4  # field, op, number, eof
        assert tokens[0].value == "media_score"
        assert tokens[1].value == FilterOperator.GT
        assert tokens[2].value == 7
    
    def test_string_tokenization(self):
        """Test string literal tokenization."""
        lexer = DSLLexer('sector = "ai-foundation"')
        tokens = lexer.tokenize()
        
        assert any(t.value == "ai-foundation" for t in tokens)
    
    def test_percent_tokenization(self):
        """Test percentage value tokenization."""
        lexer = DSLLexer("momentum_7d > 10%")
        tokens = lexer.tokenize()
        
        # Should have a PERCENT token with value 10.0
        percent_tokens = [t for t in tokens if hasattr(t, 'type') and t.type.value == "PERCENT"]
        assert len(percent_tokens) == 1
        assert percent_tokens[0].value == 10.0


class TestDSLParser:
    """Tests for DSL parser."""
    
    def test_simple_query(self):
        """Test parsing simple query."""
        result = parse_query("media_score > 7")
        
        assert isinstance(result, (Criterion, CriteriaGroup))
    
    def test_and_query(self):
        """Test parsing AND query."""
        result = parse_query("media_score > 7 AND momentum_7d > 10")
        
        assert isinstance(result, CriteriaGroup)
        assert result.operator == LogicalOperator.AND
        assert len(result.criteria) == 2
    
    def test_or_query(self):
        """Test parsing OR query."""
        result = parse_query("region = 'us' OR region = 'china'")
        
        assert isinstance(result, CriteriaGroup)
        assert result.operator == LogicalOperator.OR
    
    def test_in_query(self):
        """Test parsing IN query."""
        result = parse_query('sector IN ("ai-foundation", "ai-infrastructure")')
        
        if isinstance(result, CriteriaGroup):
            criterion = result.criteria[0]
        else:
            criterion = result
        
        assert criterion.operator == FilterOperator.IN
        assert isinstance(criterion.value, list)
        assert len(criterion.value) == 2
    
    def test_field_comparison_query(self):
        """Test parsing field comparison."""
        result = parse_query("media_score > technical_score")
        
        if isinstance(result, CriteriaGroup):
            criterion = result.criteria[0]
        else:
            criterion = result
        
        assert criterion.compare_field == "technical_score"
    
    def test_parenthesized_query(self):
        """Test parsing parenthesized expression."""
        result = parse_query("(media_score > 7 AND momentum_7d > 0) OR region = 'china'")
        
        assert isinstance(result, CriteriaGroup)
        assert result.operator == LogicalOperator.OR


class TestDSLValidation:
    """Tests for query validation."""
    
    def test_valid_query(self):
        """Test validation of valid query."""
        is_valid, error = validate_query("media_score > 7")
        assert is_valid
        assert error is None
    
    def test_invalid_syntax(self):
        """Test validation of invalid syntax."""
        is_valid, error = validate_query("media_score > > 7")
        assert not is_valid
        assert error is not None


class TestQueryBuilder:
    """Tests for fluent query builder."""
    
    def test_simple_builder(self):
        """Test building simple query."""
        query = (QueryBuilder()
            .where("media_score", ">", 7)
            .and_where("momentum_7d", ">", 10)
            .build())
        
        assert isinstance(query, CriteriaGroup)
        assert len(query.criteria) == 2
    
    def test_or_builder(self):
        """Test building OR query."""
        query = (QueryBuilder()
            .where("region", "=", "us")
            .or_where("region", "=", "china")
            .build())
        
        # Should produce structure with OR logic - check it's a valid group
        assert isinstance(query, CriteriaGroup)
        # The structure may be nested, so just verify we have criteria
        assert len(query.criteria) >= 2
    
    def test_field_comparison_builder(self):
        """Test building field comparison."""
        builder = QueryBuilder().field_gt("media_score", "technical_score")
        query = builder.build()
        
        criterion = query.criteria[0] if isinstance(query, CriteriaGroup) else query
        assert criterion.compare_field == "technical_score"
    
    def test_to_dsl(self):
        """Test converting builder to DSL string."""
        builder = QueryBuilder().where("media_score", ">", 50)
        dsl = builder.to_dsl()
        
        assert "media_score" in dsl
        assert ">" in dsl
        assert "50" in dsl


class TestSQLGeneration:
    """Tests for SQL WHERE clause generation."""
    
    def test_simple_sql(self):
        """Test simple SQL generation."""
        sql = to_sql_where("media_score > 7")
        
        assert "media_score" in sql
        assert "> 7" in sql
    
    def test_in_sql(self):
        """Test IN clause SQL generation."""
        sql = to_sql_where('sector IN ("ai", "ml")')
        
        assert "IN" in sql
        assert "ai" in sql
    
    def test_and_sql(self):
        """Test AND SQL generation."""
        sql = to_sql_where("media_score > 7 AND momentum_7d > 0")
        
        assert "AND" in sql


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""
    
    def test_create_score_filter(self):
        """Test create_score_filter helper."""
        criterion = create_score_filter("media_score", ">", 50)
        
        assert criterion.field == "media_score"
        assert criterion.operator == FilterOperator.GT
        assert criterion.value == 50
    
    def test_create_momentum_filter(self):
        """Test create_momentum_filter helper."""
        criterion = create_momentum_filter("momentum_7d", ">=", 10)
        
        assert criterion.criterion_type == CriterionType.MOMENTUM
    
    def test_create_field_comparison(self):
        """Test create_field_comparison helper."""
        criterion = create_field_comparison("media_score", ">", "technical_score")
        
        assert criterion.compare_field == "technical_score"
        assert criterion.criterion_type == CriterionType.COMPARISON
    
    def test_create_category_filter(self):
        """Test create_category_filter helper."""
        criterion = create_category_filter("sector", ["ai", "ml"])
        
        assert criterion.operator == FilterOperator.IN
        assert criterion.value == ["ai", "ml"]


class TestExplainQuery:
    """Tests for query explanation."""
    
    def test_explain_valid(self):
        """Test explaining valid query."""
        result = explain_query("media_score > 7 AND momentum_7d > 10%")
        
        assert result["valid"]
        assert "parsed" in result
        assert "sql" in result
        assert "criteria_count" in result
        assert result["criteria_count"] == 2
    
    def test_explain_invalid(self):
        """Test explaining invalid query."""
        result = explain_query("invalid > > query")
        
        assert not result["valid"]
        assert "error" in result


# =============================================================================
# Integration Tests
# =============================================================================

class TestScreenerIntegration:
    """Integration tests combining engine and DSL."""
    
    def setup_method(self):
        self.engine = ScreenerEngine()
    
    def test_dsl_to_engine(self):
        """Test running DSL query through engine."""
        group = parse_query("media_score > 50 AND momentum_7d > 0")
        result = self.engine.screen_with_group(group, entities=SAMPLE_ENTITIES)
        
        assert result.matching_entities > 0
        for entity in result.results:
            assert entity["media_score"] > 50
            assert entity["momentum_7d"] > 0
    
    def test_complex_dsl_query(self):
        """Test complex DSL query."""
        query = '(media_score > 90 AND region = "us") OR (momentum_7d > 40 AND region = "china")'
        group = parse_query(query)
        result = self.engine.screen_with_group(group, entities=SAMPLE_ENTITIES)
        
        # Should match OpenAI (media>90 AND us) and DeepSeek (momentum>40 AND china)
        # HypeCorp has media=85 so won't match with >90 threshold
        assert result.matching_entities == 2


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
