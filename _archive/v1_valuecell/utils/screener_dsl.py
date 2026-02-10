"""
Screener Query DSL

Simple domain-specific language for expressing screener criteria.
Supports natural expressions that convert to either SQL or programmatic filters.

Syntax Examples:
    media_score > 7 AND momentum_7d > 10%
    sector IN ("ai-foundation", "ai-infrastructure")
    has_divergence = true AND divergence_strength > 0.5
    media_score > technical_score
    last_signal_date > 7 days ago
    
Grammar:
    query       := expression (AND|OR expression)*
    expression  := field operator value | field operator field | "(" query ")"
    field       := identifier
    operator    := ">" | ">=" | "<" | "<=" | "=" | "!=" | "IN" | "NOT IN" | "CONTAINS"
    value       := number | string | boolean | list | date_expr
    date_expr   := number ("days"|"hours"|"weeks") "ago"
"""

from __future__ import annotations

import re
from typing import List, Dict, Any, Optional, Union, Tuple
from enum import Enum
from dataclasses import dataclass
from loguru import logger

from .screener_engine import (
    Criterion, CriteriaGroup, LogicalOperator, FilterOperator, CriterionType,
    SCREENABLE_FIELDS
)


# =============================================================================
# Token Types
# =============================================================================

class TokenType(str, Enum):
    """DSL token types."""
    FIELD = "FIELD"
    OPERATOR = "OPERATOR"
    VALUE = "VALUE"
    AND = "AND"
    OR = "OR"
    LPAREN = "LPAREN"
    RPAREN = "RPAREN"
    IN = "IN"
    NOT_IN = "NOT_IN"
    CONTAINS = "CONTAINS"
    BETWEEN = "BETWEEN"
    TRUE = "TRUE"
    FALSE = "FALSE"
    NULL = "NULL"
    STRING = "STRING"
    NUMBER = "NUMBER"
    PERCENT = "PERCENT"
    DATE_EXPR = "DATE_EXPR"
    COMMA = "COMMA"
    EOF = "EOF"


@dataclass
class Token:
    """A lexer token."""
    type: TokenType
    value: Any
    position: int


# =============================================================================
# Lexer
# =============================================================================

class DSLLexer:
    """Tokenize a DSL query string."""
    
    # Operator patterns (order matters - longer first)
    OPERATORS = {
        ">=": FilterOperator.GTE,
        "<=": FilterOperator.LTE,
        "!=": FilterOperator.NEQ,
        ">": FilterOperator.GT,
        "<": FilterOperator.LT,
        "=": FilterOperator.EQ,
    }
    
    # Keywords
    KEYWORDS = {
        "and": TokenType.AND,
        "or": TokenType.OR,
        "in": TokenType.IN,
        "not in": TokenType.NOT_IN,
        "contains": TokenType.CONTAINS,
        "between": TokenType.BETWEEN,
        "true": TokenType.TRUE,
        "false": TokenType.FALSE,
        "null": TokenType.NULL,
        "is": TokenType.OPERATOR,
        "is not": TokenType.OPERATOR,
    }
    
    def __init__(self, text: str):
        self.text = text
        self.pos = 0
        self.tokens: List[Token] = []
    
    def tokenize(self) -> List[Token]:
        """Convert input text to token list."""
        self.tokens = []
        self.pos = 0
        
        while self.pos < len(self.text):
            self._skip_whitespace()
            if self.pos >= len(self.text):
                break
            
            char = self.text[self.pos]
            
            # Parentheses
            if char == '(':
                self.tokens.append(Token(TokenType.LPAREN, '(', self.pos))
                self.pos += 1
            elif char == ')':
                self.tokens.append(Token(TokenType.RPAREN, ')', self.pos))
                self.pos += 1
            elif char == ',':
                self.tokens.append(Token(TokenType.COMMA, ',', self.pos))
                self.pos += 1
            # String literals
            elif char in ('"', "'"):
                self.tokens.append(self._read_string(char))
            # Numbers (including negative)
            elif char.isdigit() or (char == '-' and self._peek().isdigit()):
                self.tokens.append(self._read_number())
            # Operators
            elif self._is_operator_start():
                self.tokens.append(self._read_operator())
            # Keywords and fields
            elif char.isalpha() or char == '_':
                self.tokens.append(self._read_identifier())
            else:
                self.pos += 1  # Skip unknown characters
        
        self.tokens.append(Token(TokenType.EOF, None, self.pos))
        return self.tokens
    
    def _skip_whitespace(self):
        """Skip whitespace characters."""
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1
    
    def _peek(self, offset: int = 1) -> str:
        """Peek at character at offset."""
        pos = self.pos + offset
        return self.text[pos] if pos < len(self.text) else ''
    
    def _read_string(self, quote: str) -> Token:
        """Read a quoted string literal."""
        start = self.pos
        self.pos += 1  # Skip opening quote
        value = ""
        
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == quote:
                self.pos += 1  # Skip closing quote
                break
            elif char == '\\' and self._peek() in (quote, '\\'):
                self.pos += 1
                value += self.text[self.pos]
            else:
                value += char
            self.pos += 1
        
        return Token(TokenType.STRING, value, start)
    
    def _read_number(self) -> Token:
        """Read a number (possibly with % suffix)."""
        start = self.pos
        value = ""
        
        # Handle negative
        if self.text[self.pos] == '-':
            value += '-'
            self.pos += 1
        
        # Read digits and decimal
        while self.pos < len(self.text) and (self.text[self.pos].isdigit() or self.text[self.pos] == '.'):
            value += self.text[self.pos]
            self.pos += 1
        
        # Check for percent
        if self.pos < len(self.text) and self.text[self.pos] == '%':
            self.pos += 1
            return Token(TokenType.PERCENT, float(value), start)
        
        # Return as float or int
        if '.' in value:
            return Token(TokenType.NUMBER, float(value), start)
        return Token(TokenType.NUMBER, int(value), start)
    
    def _is_operator_start(self) -> bool:
        """Check if current position starts an operator."""
        for op in self.OPERATORS:
            if self.text[self.pos:self.pos+len(op)] == op:
                return True
        return False
    
    def _read_operator(self) -> Token:
        """Read an operator."""
        start = self.pos
        
        # Try longer operators first
        for op in sorted(self.OPERATORS.keys(), key=len, reverse=True):
            if self.text[self.pos:self.pos+len(op)] == op:
                self.pos += len(op)
                return Token(TokenType.OPERATOR, self.OPERATORS[op], start)
        
        return Token(TokenType.OPERATOR, FilterOperator.EQ, start)
    
    def _read_identifier(self) -> Token:
        """Read an identifier (field name or keyword)."""
        start = self.pos
        value = ""
        
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] in '_-.'):
            value += self.text[self.pos]
            self.pos += 1
        
        lower = value.lower()
        
        # Check for "NOT IN"
        if lower == "not":
            self._skip_whitespace()
            if self.text[self.pos:self.pos+2].lower() == "in":
                self.pos += 2
                return Token(TokenType.NOT_IN, "NOT IN", start)
        
        # Check for "IS NOT"
        if lower == "is":
            self._skip_whitespace()
            if self.text[self.pos:self.pos+3].lower() == "not":
                self.pos += 3
                return Token(TokenType.OPERATOR, FilterOperator.IS_NOT_NULL, start)
            return Token(TokenType.OPERATOR, FilterOperator.IS_NULL, start)
        
        # Check for date expression (e.g., "7 days ago")
        if lower in ("days", "hours", "weeks", "day", "hour", "week"):
            # Look back for number
            for i in range(len(self.tokens) - 1, -1, -1):
                if self.tokens[i].type == TokenType.NUMBER:
                    num = self.tokens[i].value
                    self._skip_whitespace()
                    if self.text[self.pos:self.pos+3].lower() == "ago":
                        self.pos += 3
                        # Replace previous number token with date expression
                        self.tokens = self.tokens[:i]
                        return Token(TokenType.DATE_EXPR, f"{num} {value} ago", start)
                    break
        
        # Check keywords
        if lower in self.KEYWORDS:
            return Token(self.KEYWORDS[lower], value, start)
        
        # It's a field name
        return Token(TokenType.FIELD, value, start)


# =============================================================================
# Parser
# =============================================================================

class DSLParser:
    """Parse tokenized DSL into criteria."""
    
    def __init__(self, tokens: List[Token]):
        self.tokens = tokens
        self.pos = 0
    
    def parse(self) -> CriteriaGroup:
        """Parse tokens into a CriteriaGroup."""
        return self._parse_or_expression()
    
    def _current(self) -> Token:
        """Get current token."""
        return self.tokens[self.pos] if self.pos < len(self.tokens) else Token(TokenType.EOF, None, -1)
    
    def _peek(self, offset: int = 1) -> Token:
        """Peek at token at offset."""
        pos = self.pos + offset
        return self.tokens[pos] if pos < len(self.tokens) else Token(TokenType.EOF, None, -1)
    
    def _advance(self) -> Token:
        """Advance to next token and return current."""
        token = self._current()
        self.pos += 1
        return token
    
    def _expect(self, token_type: TokenType) -> Token:
        """Expect a specific token type."""
        token = self._current()
        if token.type != token_type:
            raise DSLParseError(f"Expected {token_type.value}, got {token.type.value} at position {token.position}")
        return self._advance()
    
    def _parse_or_expression(self) -> CriteriaGroup:
        """Parse OR expression (lowest precedence)."""
        left = self._parse_and_expression()
        
        while self._current().type == TokenType.OR:
            self._advance()  # consume OR
            right = self._parse_and_expression()
            
            # Merge into OR group
            if isinstance(left, CriteriaGroup) and left.operator == LogicalOperator.OR:
                left.criteria.extend(right.criteria if isinstance(right, CriteriaGroup) else [right])
            else:
                left = CriteriaGroup(
                    criteria=[left, right] if not isinstance(right, CriteriaGroup) else [left] + right.criteria,
                    operator=LogicalOperator.OR
                )
        
        return left
    
    def _parse_and_expression(self) -> Union[CriteriaGroup, Criterion]:
        """Parse AND expression."""
        left = self._parse_primary()
        
        while self._current().type == TokenType.AND:
            self._advance()  # consume AND
            right = self._parse_primary()
            
            # Merge into AND group
            if isinstance(left, CriteriaGroup) and left.operator == LogicalOperator.AND:
                left.criteria.append(right)
            else:
                left = CriteriaGroup(
                    criteria=[left, right],
                    operator=LogicalOperator.AND
                )
        
        return left
    
    def _parse_primary(self) -> Union[CriteriaGroup, Criterion]:
        """Parse primary expression (comparison or grouped)."""
        token = self._current()
        
        # Parenthesized expression
        if token.type == TokenType.LPAREN:
            self._advance()  # consume (
            expr = self._parse_or_expression()
            self._expect(TokenType.RPAREN)
            return expr
        
        # Field comparison
        if token.type == TokenType.FIELD:
            return self._parse_comparison()
        
        raise DSLParseError(f"Unexpected token: {token.type.value} at position {token.position}")
    
    def _parse_comparison(self) -> Criterion:
        """Parse a field comparison."""
        field_token = self._expect(TokenType.FIELD)
        field_name = field_token.value
        
        current = self._current()
        
        # Handle IN / NOT IN
        if current.type == TokenType.IN:
            self._advance()
            values = self._parse_value_list()
            return Criterion(
                field=field_name,
                operator=FilterOperator.IN,
                value=values,
                criterion_type=self._infer_criterion_type(field_name)
            )
        
        if current.type == TokenType.NOT_IN:
            self._advance()
            values = self._parse_value_list()
            return Criterion(
                field=field_name,
                operator=FilterOperator.NOT_IN,
                value=values,
                criterion_type=self._infer_criterion_type(field_name)
            )
        
        # Handle CONTAINS
        if current.type == TokenType.CONTAINS:
            self._advance()
            value = self._parse_value()
            return Criterion(
                field=field_name,
                operator=FilterOperator.CONTAINS,
                value=value,
                criterion_type=self._infer_criterion_type(field_name)
            )
        
        # Handle BETWEEN
        if current.type == TokenType.BETWEEN:
            self._advance()
            low = self._parse_value()
            self._expect(TokenType.AND)
            high = self._parse_value()
            return Criterion(
                field=field_name,
                operator=FilterOperator.BETWEEN,
                value=[low, high],
                criterion_type=self._infer_criterion_type(field_name)
            )
        
        # Standard comparison operator
        op_token = self._expect(TokenType.OPERATOR)
        operator = op_token.value
        
        # Check if comparing to another field
        if self._current().type == TokenType.FIELD:
            compare_field = self._advance().value
            
            # Map operator to field comparison
            field_op_map = {
                FilterOperator.GT: FilterOperator.FIELD_GT,
                FilterOperator.LT: FilterOperator.FIELD_LT,
                FilterOperator.GTE: FilterOperator.FIELD_GTE,
                FilterOperator.LTE: FilterOperator.FIELD_LTE,
            }
            
            return Criterion(
                field=field_name,
                operator=field_op_map.get(operator, FilterOperator.FIELD_GT),
                compare_field=compare_field,
                criterion_type=CriterionType.COMPARISON,
                value=None
            )
        
        # Regular value comparison
        value = self._parse_value()
        criterion_type = self._infer_criterion_type(field_name)
        
        # Handle date expressions
        if isinstance(value, str) and "ago" in value.lower():
            criterion_type = CriterionType.DATE
        
        return Criterion(
            field=field_name,
            operator=operator,
            value=value,
            criterion_type=criterion_type
        )
    
    def _parse_value(self) -> Any:
        """Parse a single value."""
        token = self._current()
        
        if token.type == TokenType.NUMBER:
            self._advance()
            return token.value
        
        if token.type == TokenType.PERCENT:
            self._advance()
            return token.value  # Already a float
        
        if token.type == TokenType.STRING:
            self._advance()
            return token.value
        
        if token.type == TokenType.TRUE:
            self._advance()
            return True
        
        if token.type == TokenType.FALSE:
            self._advance()
            return False
        
        if token.type == TokenType.NULL:
            self._advance()
            return None
        
        if token.type == TokenType.DATE_EXPR:
            self._advance()
            return token.value
        
        # Field names as values (for field comparisons)
        if token.type == TokenType.FIELD:
            self._advance()
            return token.value
        
        raise DSLParseError(f"Expected value, got {token.type.value} at position {token.position}")
    
    def _parse_value_list(self) -> List[Any]:
        """Parse a list of values: (value, value, ...)"""
        self._expect(TokenType.LPAREN)
        values = [self._parse_value()]
        
        while self._current().type == TokenType.COMMA:
            self._advance()  # consume comma
            values.append(self._parse_value())
        
        self._expect(TokenType.RPAREN)
        return values
    
    def _infer_criterion_type(self, field: str) -> CriterionType:
        """Infer criterion type from field name."""
        field_info = SCREENABLE_FIELDS.get(field, {})
        category = field_info.get("category", "")
        
        type_map = {
            "scores": CriterionType.SCORE,
            "momentum": CriterionType.MOMENTUM,
            "category": CriterionType.CATEGORY,
            "signals": CriterionType.SIGNAL,
            "dates": CriterionType.DATE,
        }
        
        return type_map.get(category, CriterionType.SCORE)


# =============================================================================
# Errors
# =============================================================================

class DSLParseError(Exception):
    """Error during DSL parsing."""
    pass


class DSLValidationError(Exception):
    """Error validating DSL query."""
    pass


# =============================================================================
# High-Level API
# =============================================================================

def parse_query(query: str) -> CriteriaGroup:
    """
    Parse a DSL query string into a CriteriaGroup.
    
    Args:
        query: DSL query string
        
    Returns:
        CriteriaGroup ready for screening
        
    Examples:
        >>> parse_query("media_score > 7 AND momentum_7d > 10%")
        >>> parse_query('sector IN ("ai-foundation", "ai-infrastructure")')
        >>> parse_query("media_score > technical_score")
    """
    try:
        lexer = DSLLexer(query)
        tokens = lexer.tokenize()
        parser = DSLParser(tokens)
        return parser.parse()
    except Exception as e:
        raise DSLParseError(f"Failed to parse query: {e}")


def parse_to_criteria(query: str) -> List[Criterion]:
    """
    Parse a DSL query and flatten to a list of criteria.
    Only works for simple AND queries.
    """
    group = parse_query(query)
    
    if isinstance(group, Criterion):
        return [group]
    
    if group.operator == LogicalOperator.AND:
        criteria = []
        for item in group.criteria:
            if isinstance(item, Criterion):
                criteria.append(item)
            elif isinstance(item, CriteriaGroup) and item.operator == LogicalOperator.AND:
                # Flatten nested AND groups
                for sub in item.criteria:
                    if isinstance(sub, Criterion):
                        criteria.append(sub)
        return criteria
    
    raise DSLValidationError("Cannot flatten OR queries to simple criteria list")


def validate_query(query: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a DSL query string.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        group = parse_query(query)
        
        # Recursively validate all criteria
        errors = _validate_criteria_group(group)
        if errors:
            return False, "; ".join(errors)
        
        return True, None
        
    except DSLParseError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Validation error: {e}"


def _validate_criteria_group(group: Union[CriteriaGroup, Criterion]) -> List[str]:
    """Recursively validate a criteria group."""
    errors = []
    
    if isinstance(group, Criterion):
        # Validate field exists
        if group.field not in SCREENABLE_FIELDS:
            # Allow unknown fields (might be custom)
            pass
        return errors
    
    for item in group.criteria:
        errors.extend(_validate_criteria_group(item))
    
    return errors


def to_sql_where(query: str, table_alias: str = "e") -> str:
    """
    Convert a DSL query to SQL WHERE clause.
    
    Args:
        query: DSL query string
        table_alias: Table alias to use for fields
        
    Returns:
        SQL WHERE clause string
        
    Example:
        >>> to_sql_where("media_score > 7 AND sector = 'ai'")
        "e.media_score > 7 AND e.sector = 'ai'"
    """
    group = parse_query(query)
    return _group_to_sql(group, table_alias)


def _group_to_sql(group: Union[CriteriaGroup, Criterion], alias: str) -> str:
    """Convert a criteria group to SQL."""
    if isinstance(group, Criterion):
        return _criterion_to_sql(group, alias)
    
    parts = [_group_to_sql(item, alias) for item in group.criteria]
    joiner = f" {group.operator} "
    return f"({joiner.join(parts)})"


def _criterion_to_sql(criterion: Criterion, alias: str) -> str:
    """Convert a single criterion to SQL."""
    field = f"{alias}.{criterion.field}"
    
    # Handle field comparison
    if criterion.compare_field:
        op_map = {
            FilterOperator.FIELD_GT: ">",
            FilterOperator.FIELD_LT: "<",
            FilterOperator.FIELD_GTE: ">=",
            FilterOperator.FIELD_LTE: "<=",
        }
        op = op_map.get(criterion.operator, ">")
        return f"{field} {op} {alias}.{criterion.compare_field}"
    
    # Handle different operators
    if criterion.operator == FilterOperator.IN:
        values = ", ".join(_sql_value(v) for v in criterion.value)
        return f"{field} IN ({values})"
    
    if criterion.operator == FilterOperator.NOT_IN:
        values = ", ".join(_sql_value(v) for v in criterion.value)
        return f"{field} NOT IN ({values})"
    
    if criterion.operator == FilterOperator.CONTAINS:
        return f"{field} LIKE '%{criterion.value}%'"
    
    if criterion.operator == FilterOperator.STARTS_WITH:
        return f"{field} LIKE '{criterion.value}%'"
    
    if criterion.operator == FilterOperator.ENDS_WITH:
        return f"{field} LIKE '%{criterion.value}'"
    
    if criterion.operator == FilterOperator.BETWEEN:
        return f"{field} BETWEEN {_sql_value(criterion.value[0])} AND {_sql_value(criterion.value[1])}"
    
    if criterion.operator == FilterOperator.IS_NULL:
        return f"{field} IS NULL"
    
    if criterion.operator == FilterOperator.IS_NOT_NULL:
        return f"{field} IS NOT NULL"
    
    # Standard comparison
    op_map = {
        FilterOperator.EQ: "=",
        FilterOperator.NEQ: "!=",
        FilterOperator.GT: ">",
        FilterOperator.GTE: ">=",
        FilterOperator.LT: "<",
        FilterOperator.LTE: "<=",
    }
    
    op = op_map.get(criterion.operator, "=")
    value = _sql_value(criterion.value)
    
    return f"{field} {op} {value}"


def _sql_value(value: Any) -> str:
    """Convert a Python value to SQL literal."""
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        # Handle date expressions
        if "ago" in value.lower():
            match = re.match(r"(\d+)\s*(days?|hours?|weeks?)\s*ago", value.lower())
            if match:
                num = match.group(1)
                unit = match.group(2)
                if "day" in unit:
                    return f"NOW() - INTERVAL '{num} days'"
                elif "hour" in unit:
                    return f"NOW() - INTERVAL '{num} hours'"
                elif "week" in unit:
                    return f"NOW() - INTERVAL '{num} weeks'"
        # Escape single quotes
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return str(value)


# =============================================================================
# Query Builder Helpers
# =============================================================================

class QueryBuilder:
    """
    Fluent interface for building screener queries.
    
    Usage:
        query = (QueryBuilder()
            .where("media_score", ">", 7)
            .and_where("momentum_7d", ">", 10)
            .or_where("has_divergence", "=", True)
            .build())
    """
    
    def __init__(self):
        self._criteria: List[Tuple[str, Criterion]] = []  # (conjunction, criterion)
    
    def where(self, field: str, operator: str, value: Any) -> "QueryBuilder":
        """Add a WHERE criterion."""
        criterion = Criterion(
            field=field,
            operator=FilterOperator(operator),
            value=value,
            criterion_type=self._infer_type(field)
        )
        self._criteria.append(("AND", criterion))
        return self
    
    def and_where(self, field: str, operator: str, value: Any) -> "QueryBuilder":
        """Add an AND criterion."""
        return self.where(field, operator, value)
    
    def or_where(self, field: str, operator: str, value: Any) -> "QueryBuilder":
        """Add an OR criterion."""
        criterion = Criterion(
            field=field,
            operator=FilterOperator(operator),
            value=value,
            criterion_type=self._infer_type(field)
        )
        self._criteria.append(("OR", criterion))
        return self
    
    def field_gt(self, field_a: str, field_b: str) -> "QueryBuilder":
        """Add field comparison: field_a > field_b"""
        criterion = Criterion(
            field=field_a,
            operator=FilterOperator.FIELD_GT,
            compare_field=field_b,
            criterion_type=CriterionType.COMPARISON,
            value=None
        )
        self._criteria.append(("AND", criterion))
        return self
    
    def in_list(self, field: str, values: List[Any]) -> "QueryBuilder":
        """Add IN criterion."""
        criterion = Criterion(
            field=field,
            operator=FilterOperator.IN,
            value=values,
            criterion_type=self._infer_type(field)
        )
        self._criteria.append(("AND", criterion))
        return self
    
    def between(self, field: str, low: Any, high: Any) -> "QueryBuilder":
        """Add BETWEEN criterion."""
        criterion = Criterion(
            field=field,
            operator=FilterOperator.BETWEEN,
            value=[low, high],
            criterion_type=self._infer_type(field)
        )
        self._criteria.append(("AND", criterion))
        return self
    
    def build(self) -> CriteriaGroup:
        """Build the criteria group."""
        if not self._criteria:
            return CriteriaGroup(criteria=[])
        
        # Group by conjunction
        and_criteria = []
        or_criteria = []
        
        for conj, criterion in self._criteria:
            if conj == "AND":
                and_criteria.append(criterion)
            else:
                or_criteria.append(criterion)
        
        # Build structure
        if not or_criteria:
            return CriteriaGroup(criteria=and_criteria, operator=LogicalOperator.AND)
        
        if not and_criteria:
            return CriteriaGroup(criteria=or_criteria, operator=LogicalOperator.OR)
        
        # Mixed: (AND conditions) OR (individual OR conditions)
        return CriteriaGroup(
            criteria=[
                CriteriaGroup(criteria=and_criteria, operator=LogicalOperator.AND),
                *or_criteria
            ],
            operator=LogicalOperator.OR
        )
    
    def build_list(self) -> List[Criterion]:
        """Build as simple list (AND only)."""
        return [c for _, c in self._criteria]
    
    def to_dsl(self) -> str:
        """Convert back to DSL string."""
        parts = []
        for conj, criterion in self._criteria:
            if parts:
                parts.append(conj)
            
            if criterion.compare_field:
                parts.append(f"{criterion.field} {self._op_to_str(criterion.operator)} {criterion.compare_field}")
            elif criterion.operator == FilterOperator.IN:
                values = ", ".join(f'"{v}"' if isinstance(v, str) else str(v) for v in criterion.value)
                parts.append(f'{criterion.field} IN ({values})')
            elif criterion.operator == FilterOperator.BETWEEN:
                parts.append(f"{criterion.field} BETWEEN {criterion.value[0]} AND {criterion.value[1]}")
            else:
                value = f'"{criterion.value}"' if isinstance(criterion.value, str) else criterion.value
                parts.append(f"{criterion.field} {self._op_to_str(criterion.operator)} {value}")
        
        return " ".join(parts)
    
    def _infer_type(self, field: str) -> CriterionType:
        """Infer criterion type from field."""
        field_info = SCREENABLE_FIELDS.get(field, {})
        category = field_info.get("category", "")
        
        type_map = {
            "scores": CriterionType.SCORE,
            "momentum": CriterionType.MOMENTUM,
            "category": CriterionType.CATEGORY,
            "signals": CriterionType.SIGNAL,
            "dates": CriterionType.DATE,
        }
        
        return type_map.get(category, CriterionType.SCORE)
    
    def _op_to_str(self, op: FilterOperator) -> str:
        """Convert operator enum to string."""
        op_map = {
            FilterOperator.EQ: "=",
            FilterOperator.NEQ: "!=",
            FilterOperator.GT: ">",
            FilterOperator.GTE: ">=",
            FilterOperator.LT: "<",
            FilterOperator.LTE: "<=",
            FilterOperator.FIELD_GT: ">",
            FilterOperator.FIELD_LT: "<",
            FilterOperator.FIELD_GTE: ">=",
            FilterOperator.FIELD_LTE: "<=",
            FilterOperator.IN: "IN",
            FilterOperator.NOT_IN: "NOT IN",
            FilterOperator.CONTAINS: "CONTAINS",
        }
        return op_map.get(op, "=")


# =============================================================================
# Convenience Functions
# =============================================================================

def quick_screen(query: str, store=None, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Quick screening with DSL query.
    
    Usage:
        results = quick_screen("media_score > 7 AND momentum_7d > 10%")
    """
    from .screener_engine import ScreenerEngine
    
    engine = ScreenerEngine(store=store)
    group = parse_query(query)
    result = engine.screen_with_group(group, limit=limit)
    return result.results


def explain_query(query: str) -> Dict[str, Any]:
    """
    Explain a DSL query in human terms.
    
    Returns:
        Dictionary with query breakdown and explanation
    """
    try:
        group = parse_query(query)
        
        return {
            "valid": True,
            "original": query,
            "parsed": _explain_group(group),
            "sql": to_sql_where(query),
            "criteria_count": _count_criteria(group)
        }
    except Exception as e:
        return {
            "valid": False,
            "original": query,
            "error": str(e)
        }


def _explain_group(group: Union[CriteriaGroup, Criterion], depth: int = 0) -> Dict[str, Any]:
    """Recursively explain a criteria group."""
    if isinstance(group, Criterion):
        return {
            "type": "criterion",
            "field": group.field,
            "operator": group.operator.value if hasattr(group.operator, 'value') else str(group.operator),
            "value": group.value,
            "compare_field": group.compare_field,
            "criterion_type": group.criterion_type.value if hasattr(group.criterion_type, 'value') else str(group.criterion_type),
            "human": _criterion_to_human(group)
        }
    
    return {
        "type": "group",
        "operator": group.operator.value if hasattr(group.operator, 'value') else str(group.operator),
        "criteria": [_explain_group(item, depth + 1) for item in group.criteria],
        "human": " {} ".format(group.operator).join(
            _criterion_to_human(c) if isinstance(c, Criterion) else f"({_group_to_human(c)})"
            for c in group.criteria
        )
    }


def _criterion_to_human(criterion: Criterion) -> str:
    """Convert criterion to human-readable string."""
    if criterion.compare_field:
        return f"{criterion.field} is greater than {criterion.compare_field}"
    
    op_human = {
        FilterOperator.EQ: "equals",
        FilterOperator.NEQ: "does not equal",
        FilterOperator.GT: "is greater than",
        FilterOperator.GTE: "is at least",
        FilterOperator.LT: "is less than",
        FilterOperator.LTE: "is at most",
        FilterOperator.IN: "is one of",
        FilterOperator.NOT_IN: "is not one of",
        FilterOperator.CONTAINS: "contains",
    }
    
    op_str = op_human.get(criterion.operator, str(criterion.operator))
    return f"{criterion.field} {op_str} {criterion.value}"


def _group_to_human(group: CriteriaGroup) -> str:
    """Convert group to human-readable string."""
    return " {} ".format(group.operator).join(
        _criterion_to_human(c) if isinstance(c, Criterion) else f"({_group_to_human(c)})"
        for c in group.criteria
    )


def _count_criteria(group: Union[CriteriaGroup, Criterion]) -> int:
    """Count total criteria in a group."""
    if isinstance(group, Criterion):
        return 1
    return sum(_count_criteria(item) for item in group.criteria)
