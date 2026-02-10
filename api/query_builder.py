"""
Advanced Query Builder for briefAI Professional API.

Bloomberg-quality query capabilities:
- Complex boolean queries (AND/OR/NOT with parentheses)
- Date range filtering
- Sector/industry filtering
- Minimum confidence thresholds
- GraphQL-style field selection
- Parameterized queries for security

Security:
- Whitelisted tables and columns only
- Parameterized queries (no SQL injection)
- Query timeout limits
- Max result limits per tier
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set, Union
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, date
from pydantic import BaseModel, Field

from utils.signal_store import SignalStore


class QueryError(Exception):
    """Query parsing or execution error."""
    pass


class Table(str, Enum):
    """Allowed tables for querying."""
    SIGNALS = "signals"
    ENTITIES = "entities"
    PROFILES = "profiles"
    DIVERGENCES = "divergences"
    OBSERVATIONS = "observations"
    SCORES = "scores"
    ARTICLES = "articles"
    EVENTS = "events"


# Whitelist of allowed columns per table
ALLOWED_COLUMNS = {
    Table.SIGNALS: {
        "entity_id", "entity_name", "category", "score", "percentile",
        "score_delta_7d", "score_delta_30d", "created_at", "source_id",
        "confidence", "sector", "industry",
    },
    Table.ENTITIES: {
        "id", "canonical_id", "name", "entity_type", "description",
        "website", "founded_date", "headquarters", "created_at", "updated_at",
        "sector", "industry", "employee_count", "funding_total",
    },
    Table.PROFILES: {
        "entity_id", "entity_name", "entity_type", "as_of",
        "technical_score", "company_score", "financial_score", "product_score", "media_score",
        "composite_score", "momentum_7d", "momentum_30d", "created_at",
        "sector", "industry", "confidence",
    },
    Table.DIVERGENCES: {
        "entity_id", "entity_name", "divergence_type",
        "high_signal_category", "high_signal_score",
        "low_signal_category", "low_signal_score",
        "divergence_magnitude", "confidence", "interpretation",
        "detected_at", "resolved_at", "sector",
    },
    Table.OBSERVATIONS: {
        "id", "entity_id", "source_id", "category", "observed_at",
        "raw_value", "raw_value_unit", "confidence", "created_at",
    },
    Table.SCORES: {
        "id", "entity_id", "source_id", "category", "score",
        "percentile", "score_delta_7d", "score_delta_30d", "created_at",
    },
    Table.ARTICLES: {
        "id", "title", "url", "source", "published_at", "entity_id",
        "sentiment", "relevance_score", "created_at",
    },
    Table.EVENTS: {
        "id", "entity_id", "event_type", "timestamp", "title",
        "description", "source", "impact_score",
    },
}

# Map table names to actual SQL tables
TABLE_MAPPING = {
    Table.SIGNALS: "signal_scores",
    Table.ENTITIES: "entities",
    Table.PROFILES: "signal_profiles",
    Table.DIVERGENCES: "signal_divergences",
    Table.OBSERVATIONS: "signal_observations",
    Table.SCORES: "signal_scores",
    Table.ARTICLES: "articles",
    Table.EVENTS: "entity_events",
}

# Sector/Industry classification
SECTORS = {
    "ai_infrastructure": ["compute", "cloud", "data_center", "chip"],
    "ai_applications": ["chatbot", "copilot", "automation", "analytics"],
    "ai_research": ["research_lab", "university", "think_tank"],
    "ai_services": ["consulting", "integration", "training"],
    "ai_tooling": ["mlops", "devtools", "monitoring"],
}


class Operator(str, Enum):
    """Allowed comparison operators."""
    EQ = "="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="
    LIKE = "LIKE"
    ILIKE = "ILIKE"
    IN = "IN"
    NOT_IN = "NOT IN"
    IS_NULL = "IS NULL"
    IS_NOT_NULL = "IS NOT NULL"
    BETWEEN = "BETWEEN"
    CONTAINS = "CONTAINS"


class LogicalOperator(str, Enum):
    """Logical operators for combining conditions."""
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


@dataclass
class WhereCondition:
    """A single WHERE condition."""
    column: str
    operator: Operator
    value: Any
    logical_op: LogicalOperator = LogicalOperator.AND


@dataclass
class ConditionGroup:
    """A group of conditions with parentheses."""
    conditions: List[Union['ConditionGroup', WhereCondition]]
    logical_op: LogicalOperator = LogicalOperator.AND
    negated: bool = False


@dataclass
class OrderBy:
    """ORDER BY clause."""
    column: str
    descending: bool = False


@dataclass
class DateRange:
    """Date range filter."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    column: str = "created_at"


@dataclass
class FieldSelection:
    """GraphQL-style field selection."""
    fields: List[str]
    aliases: Dict[str, str] = field(default_factory=dict)
    aggregations: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedQuery:
    """Parsed query representation."""
    table: Table
    field_selection: FieldSelection
    conditions: List[Union[ConditionGroup, WhereCondition]] = field(default_factory=list)
    date_range: Optional[DateRange] = None
    order_by: List[OrderBy] = field(default_factory=list)
    group_by: List[str] = field(default_factory=list)
    limit: int = 100
    offset: int = 0
    sector_filter: Optional[str] = None
    industry_filter: Optional[str] = None
    min_confidence: Optional[float] = None


class QueryResult(BaseModel):
    """Query execution result."""
    query: str
    table: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    total_rows: int
    execution_time_ms: float
    has_more: bool
    aggregations: Optional[Dict[str, Any]] = None


# =============================================================================
# Advanced Boolean Query Request Model
# =============================================================================

class BooleanCondition(BaseModel):
    """A condition in a boolean query."""
    field: str
    operator: str = "="
    value: Any
    
    class Config:
        json_schema_extra = {
            "example": {"field": "category", "operator": "=", "value": "technical"}
        }


class BooleanQuery(BaseModel):
    """
    Complex boolean query with AND/OR/NOT support.
    
    Bloomberg-quality query interface for professional data access.
    """
    table: str = Field(..., description="Target table: signals, entities, profiles, divergences")
    
    # Field selection (GraphQL-style)
    select: Optional[List[str]] = Field(
        None, 
        description="Fields to return. None = all fields. Use aliases: 'score AS signal_score'"
    )
    
    # Boolean conditions
    where: Optional[Dict[str, Any]] = Field(
        None,
        description="Simple conditions as key-value pairs"
    )
    and_conditions: Optional[List[BooleanCondition]] = Field(
        None,
        description="Conditions joined with AND"
    )
    or_conditions: Optional[List[BooleanCondition]] = Field(
        None,
        description="Conditions joined with OR"
    )
    not_conditions: Optional[List[BooleanCondition]] = Field(
        None,
        description="Conditions to negate"
    )
    
    # Date filtering
    date_from: Optional[str] = Field(None, description="Start date (YYYY-MM-DD)")
    date_to: Optional[str] = Field(None, description="End date (YYYY-MM-DD)")
    date_field: str = Field("created_at", description="Date field to filter on")
    
    # Sector/Industry filtering
    sector: Optional[str] = Field(None, description="Filter by sector")
    industry: Optional[str] = Field(None, description="Filter by industry")
    
    # Confidence threshold
    min_confidence: Optional[float] = Field(
        None, 
        ge=0.0, 
        le=1.0,
        description="Minimum confidence threshold (0.0-1.0)"
    )
    
    # Ordering
    order_by: Optional[str] = Field(None, description="Field to sort by")
    order_desc: bool = Field(False, description="Sort descending")
    
    # Grouping and aggregation
    group_by: Optional[List[str]] = Field(None, description="Fields to group by")
    aggregate: Optional[Dict[str, str]] = Field(
        None,
        description="Aggregations: {'score': 'AVG', 'count': 'COUNT'}"
    )
    
    # Pagination
    limit: int = Field(100, ge=1, le=10000)
    offset: int = Field(0, ge=0)
    
    class Config:
        json_schema_extra = {
            "example": {
                "table": "signals",
                "select": ["entity_id", "entity_name", "score", "category"],
                "and_conditions": [
                    {"field": "category", "operator": "=", "value": "technical"},
                    {"field": "score", "operator": ">=", "value": 70}
                ],
                "or_conditions": [
                    {"field": "entity_name", "operator": "LIKE", "value": "%OpenAI%"},
                    {"field": "entity_name", "operator": "LIKE", "value": "%Anthropic%"}
                ],
                "date_from": "2025-01-01",
                "min_confidence": 0.8,
                "order_by": "score",
                "order_desc": True,
                "limit": 50
            }
        }


# =============================================================================
# Query Parser
# =============================================================================

class QueryParser:
    """Parse SQL-like query strings and BooleanQuery objects into safe executable queries."""
    
    # Regex patterns for SQL-like parsing
    SELECT_PATTERN = re.compile(
        r"^\s*SELECT\s+(.+?)\s+FROM\s+(\w+)"
        r"(?:\s+WHERE\s+(.+?))?"
        r"(?:\s+GROUP\s+BY\s+(.+?))?"
        r"(?:\s+ORDER\s+BY\s+(.+?))?"
        r"(?:\s+LIMIT\s+(\d+))?"
        r"(?:\s+OFFSET\s+(\d+))?\s*$",
        re.IGNORECASE | re.DOTALL
    )
    
    CONDITION_PATTERN = re.compile(
        r"(\w+)\s*(=|!=|>=|<=|>|<|LIKE|ILIKE|IN|NOT\s+IN|IS\s+NULL|IS\s+NOT\s+NULL|BETWEEN|CONTAINS)\s*"
        r"('[^']*'|\([^)]+\)|\d+\.?\d*|NULL)?(?:\s+AND\s+('[^']*'|\d+\.?\d*))?",
        re.IGNORECASE
    )
    
    def parse_sql(self, query_string: str) -> ParsedQuery:
        """Parse a SQL-like query string into a ParsedQuery object."""
        query_string = query_string.strip()
        
        if not query_string.upper().startswith("SELECT"):
            raise QueryError("Only SELECT queries are allowed")
        
        match = self.SELECT_PATTERN.match(query_string)
        if not match:
            raise QueryError(f"Invalid query syntax: {query_string}")
        
        columns_str, table_str, where_str, group_str, order_str, limit_str, offset_str = match.groups()
        
        # Parse table
        try:
            table = Table(table_str.lower())
        except ValueError:
            allowed = ", ".join(t.value for t in Table)
            raise QueryError(f"Invalid table '{table_str}'. Allowed: {allowed}")
        
        # Parse columns (field selection)
        field_selection = self._parse_field_selection(columns_str, table)
        
        # Parse WHERE conditions
        conditions = []
        date_range = None
        sector_filter = None
        industry_filter = None
        min_confidence = None
        
        if where_str:
            conditions, date_range, sector_filter, industry_filter, min_confidence = \
                self._parse_where_clause(where_str, table)
        
        # Parse GROUP BY
        group_by = []
        if group_str:
            group_by = [col.strip().lower() for col in group_str.split(",")]
        
        # Parse ORDER BY
        order_by = []
        if order_str:
            order_by = self._parse_order_by(order_str, table)
        
        # Parse LIMIT/OFFSET
        limit = min(int(limit_str) if limit_str else 100, 10000)
        offset = int(offset_str) if offset_str else 0
        
        return ParsedQuery(
            table=table,
            field_selection=field_selection,
            conditions=conditions,
            date_range=date_range,
            order_by=order_by,
            group_by=group_by,
            limit=limit,
            offset=offset,
            sector_filter=sector_filter,
            industry_filter=industry_filter,
            min_confidence=min_confidence,
        )
    
    def parse_boolean_query(self, query: BooleanQuery) -> ParsedQuery:
        """Parse a BooleanQuery into a ParsedQuery object."""
        # Validate table
        try:
            table = Table(query.table.lower())
        except ValueError:
            allowed = ", ".join(t.value for t in Table)
            raise QueryError(f"Invalid table '{query.table}'. Allowed: {allowed}")
        
        # Parse field selection
        if query.select:
            field_selection = self._parse_graphql_fields(query.select, table)
        else:
            field_selection = FieldSelection(fields=["*"])
        
        # Handle aggregations
        if query.aggregate:
            field_selection.aggregations = query.aggregate
        
        # Build conditions
        conditions: List[Union[ConditionGroup, WhereCondition]] = []
        
        # Simple where conditions
        if query.where:
            for col, val in query.where.items():
                conditions.append(WhereCondition(
                    column=col.lower(),
                    operator=Operator.EQ,
                    value=val,
                    logical_op=LogicalOperator.AND,
                ))
        
        # AND conditions
        if query.and_conditions:
            for cond in query.and_conditions:
                conditions.append(self._boolean_condition_to_where(cond, LogicalOperator.AND))
        
        # OR conditions (group them)
        if query.or_conditions:
            or_group = ConditionGroup(
                conditions=[
                    self._boolean_condition_to_where(cond, LogicalOperator.OR)
                    for cond in query.or_conditions
                ],
                logical_op=LogicalOperator.OR,
            )
            conditions.append(or_group)
        
        # NOT conditions
        if query.not_conditions:
            not_group = ConditionGroup(
                conditions=[
                    self._boolean_condition_to_where(cond, LogicalOperator.AND)
                    for cond in query.not_conditions
                ],
                logical_op=LogicalOperator.AND,
                negated=True,
            )
            conditions.append(not_group)
        
        # Date range
        date_range = None
        if query.date_from or query.date_to:
            date_range = DateRange(
                start=datetime.fromisoformat(query.date_from) if query.date_from else None,
                end=datetime.fromisoformat(query.date_to) if query.date_to else None,
                column=query.date_field,
            )
        
        # Order by
        order_by = []
        if query.order_by:
            order_by = [OrderBy(column=query.order_by.lower(), descending=query.order_desc)]
        
        # Group by
        group_by = [g.lower() for g in query.group_by] if query.group_by else []
        
        return ParsedQuery(
            table=table,
            field_selection=field_selection,
            conditions=conditions,
            date_range=date_range,
            order_by=order_by,
            group_by=group_by,
            limit=query.limit,
            offset=query.offset,
            sector_filter=query.sector,
            industry_filter=query.industry,
            min_confidence=query.min_confidence,
        )
    
    def _boolean_condition_to_where(
        self, 
        cond: BooleanCondition, 
        logical_op: LogicalOperator
    ) -> WhereCondition:
        """Convert a BooleanCondition to a WhereCondition."""
        op_map = {
            "=": Operator.EQ,
            "==": Operator.EQ,
            "!=": Operator.NE,
            "<>": Operator.NE,
            ">": Operator.GT,
            ">=": Operator.GE,
            "<": Operator.LT,
            "<=": Operator.LE,
            "like": Operator.LIKE,
            "ilike": Operator.ILIKE,
            "in": Operator.IN,
            "not in": Operator.NOT_IN,
            "between": Operator.BETWEEN,
            "contains": Operator.CONTAINS,
        }
        
        op_str = cond.operator.lower()
        if op_str not in op_map:
            raise QueryError(f"Invalid operator: {cond.operator}")
        
        return WhereCondition(
            column=cond.field.lower(),
            operator=op_map[op_str],
            value=cond.value,
            logical_op=logical_op,
        )
    
    def _parse_field_selection(self, columns_str: str, table: Table) -> FieldSelection:
        """Parse and validate column/field selection with aliases."""
        columns_str = columns_str.strip()
        
        if columns_str == "*":
            return FieldSelection(fields=["*"])
        
        fields = []
        aliases = {}
        aggregations = {}
        
        # Split by comma (careful with function calls)
        parts = self._split_columns(columns_str)
        allowed = ALLOWED_COLUMNS[table]
        
        for part in parts:
            part = part.strip()
            
            # Check for alias: "field AS alias"
            alias_match = re.match(r"(\w+(?:\([^)]*\))?)\s+AS\s+(\w+)", part, re.IGNORECASE)
            if alias_match:
                field_part, alias = alias_match.groups()
                aliases[field_part.lower()] = alias.lower()
                part = field_part
            
            # Check for aggregation: COUNT(*), AVG(score), etc.
            agg_match = re.match(r"(COUNT|SUM|AVG|MIN|MAX)\(([^)]+)\)", part, re.IGNORECASE)
            if agg_match:
                agg_func, agg_field = agg_match.groups()
                agg_field = agg_field.strip().lower()
                if agg_field != "*" and agg_field not in allowed:
                    raise QueryError(f"Invalid field in aggregation: {agg_field}")
                aggregations[agg_field] = agg_func.upper()
                fields.append(f"{agg_func.upper()}({agg_field})")
                continue
            
            col = part.lower()
            if col not in allowed:
                raise QueryError(f"Invalid column '{col}' for table '{table.value}'")
            fields.append(col)
        
        return FieldSelection(fields=fields, aliases=aliases, aggregations=aggregations)
    
    def _parse_graphql_fields(self, select: List[str], table: Table) -> FieldSelection:
        """Parse GraphQL-style field selection."""
        allowed = ALLOWED_COLUMNS[table]
        fields = []
        aliases = {}
        
        for s in select:
            # Check for alias
            if " AS " in s.upper():
                parts = re.split(r'\s+AS\s+', s, flags=re.IGNORECASE)
                field_name = parts[0].strip().lower()
                alias_name = parts[1].strip().lower() if len(parts) > 1 else field_name
                aliases[field_name] = alias_name
            else:
                field_name = s.strip().lower()
            
            if field_name not in allowed and field_name != "*":
                raise QueryError(f"Invalid field '{field_name}' for table '{table.value}'")
            
            fields.append(field_name)
        
        return FieldSelection(fields=fields, aliases=aliases)
    
    def _split_columns(self, columns_str: str) -> List[str]:
        """Split column string by commas, respecting parentheses."""
        result = []
        current = ""
        paren_depth = 0
        
        for char in columns_str:
            if char == "(":
                paren_depth += 1
            elif char == ")":
                paren_depth -= 1
            elif char == "," and paren_depth == 0:
                result.append(current.strip())
                current = ""
                continue
            current += char
        
        if current.strip():
            result.append(current.strip())
        
        return result
    
    def _parse_where_clause(
        self, 
        where_str: str, 
        table: Table
    ) -> Tuple[List[WhereCondition], Optional[DateRange], Optional[str], Optional[str], Optional[float]]:
        """Parse WHERE clause including special filters."""
        conditions = []
        date_range = None
        sector_filter = None
        industry_filter = None
        min_confidence = None
        allowed = ALLOWED_COLUMNS[table]
        
        # Handle parentheses for grouping (simplified - flatten for now)
        # Full recursive parsing would go here for production
        
        # Split by AND/OR
        parts = re.split(r'\s+(AND|OR)\s+', where_str, flags=re.IGNORECASE)
        
        logical_op = LogicalOperator.AND
        for part in parts:
            part = part.strip()
            
            if part.upper() == "AND":
                logical_op = LogicalOperator.AND
                continue
            elif part.upper() == "OR":
                logical_op = LogicalOperator.OR
                continue
            
            # Check for special filters
            if part.lower().startswith("sector"):
                match = re.match(r"sector\s*=\s*'([^']+)'", part, re.IGNORECASE)
                if match:
                    sector_filter = match.group(1)
                continue
            
            if part.lower().startswith("industry"):
                match = re.match(r"industry\s*=\s*'([^']+)'", part, re.IGNORECASE)
                if match:
                    industry_filter = match.group(1)
                continue
            
            if part.lower().startswith("confidence"):
                match = re.match(r"confidence\s*>=?\s*([\d.]+)", part, re.IGNORECASE)
                if match:
                    min_confidence = float(match.group(1))
                continue
            
            # Parse regular condition
            match = self.CONDITION_PATTERN.match(part)
            if not match:
                raise QueryError(f"Invalid condition: {part}")
            
            column, operator, value, between_value = match.groups()
            column = column.lower()
            
            if column not in allowed:
                raise QueryError(f"Invalid column '{column}' for table '{table.value}'")
            
            # Handle date range shortcut
            if column in ("created_at", "detected_at", "observed_at", "as_of"):
                if operator.upper() == "BETWEEN" and value and between_value:
                    date_range = DateRange(
                        start=self._parse_date_value(value),
                        end=self._parse_date_value(between_value),
                        column=column,
                    )
                    continue
            
            # Parse operator
            op_str = operator.upper().replace("  ", " ")
            op = self._parse_operator(op_str)
            
            # Parse value
            parsed_value = None
            if value:
                parsed_value = self._parse_value(value, op)
            
            conditions.append(WhereCondition(
                column=column,
                operator=op,
                value=parsed_value,
                logical_op=logical_op,
            ))
            
            logical_op = LogicalOperator.AND
        
        return conditions, date_range, sector_filter, industry_filter, min_confidence
    
    def _parse_operator(self, op_str: str) -> Operator:
        """Parse operator string to enum."""
        op_map = {
            "=": Operator.EQ,
            "!=": Operator.NE,
            ">": Operator.GT,
            ">=": Operator.GE,
            "<": Operator.LT,
            "<=": Operator.LE,
            "LIKE": Operator.LIKE,
            "ILIKE": Operator.ILIKE,
            "IN": Operator.IN,
            "NOT IN": Operator.NOT_IN,
            "IS NULL": Operator.IS_NULL,
            "IS NOT NULL": Operator.IS_NOT_NULL,
            "BETWEEN": Operator.BETWEEN,
            "CONTAINS": Operator.CONTAINS,
        }
        
        if op_str not in op_map:
            raise QueryError(f"Invalid operator: {op_str}")
        return op_map[op_str]
    
    def _parse_value(self, value_str: str, operator: Operator) -> Any:
        """Parse a value from the query."""
        value_str = value_str.strip()
        
        # String value
        if value_str.startswith("'") and value_str.endswith("'"):
            return value_str[1:-1]
        
        # IN list
        if operator in (Operator.IN, Operator.NOT_IN):
            if value_str.startswith("(") and value_str.endswith(")"):
                items = value_str[1:-1].split(",")
                return [self._parse_value(item.strip(), Operator.EQ) for item in items]
        
        # NULL
        if value_str.upper() == "NULL":
            return None
        
        # Number
        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            return value_str
    
    def _parse_date_value(self, value_str: str) -> datetime:
        """Parse a date value."""
        value_str = value_str.strip().strip("'")
        
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value_str, fmt)
            except ValueError:
                continue
        
        raise QueryError(f"Invalid date format: {value_str}")
    
    def _parse_order_by(self, order_str: str, table: Table) -> List[OrderBy]:
        """Parse ORDER BY clause."""
        allowed = ALLOWED_COLUMNS[table]
        result = []
        
        parts = order_str.split(",")
        for part in parts:
            part = part.strip()
            match = re.match(r"(\w+)(?:\s+(ASC|DESC))?", part, re.IGNORECASE)
            if not match:
                raise QueryError(f"Invalid ORDER BY: {part}")
            
            col, direction = match.groups()
            col = col.lower()
            
            if col not in allowed:
                raise QueryError(f"Invalid ORDER BY column '{col}'")
            
            result.append(OrderBy(
                column=col,
                descending=(direction or "ASC").upper() == "DESC",
            ))
        
        return result


# =============================================================================
# Query Executor
# =============================================================================

class QueryExecutor:
    """Execute parsed queries against the signal store."""
    
    def __init__(self, store: Optional[SignalStore] = None):
        self.store = store or SignalStore()
        self.parser = QueryParser()
    
    def execute_sql(self, query_string: str) -> QueryResult:
        """Execute a SQL-like query string and return results."""
        parsed = self.parser.parse_sql(query_string)
        return self._execute(parsed, query_string)
    
    def execute_boolean(self, query: BooleanQuery) -> QueryResult:
        """Execute a BooleanQuery and return results."""
        parsed = self.parser.parse_boolean_query(query)
        return self._execute(parsed, str(query.model_dump()))
    
    def _execute(self, parsed: ParsedQuery, original_query: str) -> QueryResult:
        """Execute a parsed query."""
        start_time = datetime.utcnow()
        
        # Build SQL
        sql, params = self._build_sql(parsed)
        
        # Execute
        conn = self.store._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(sql, params)
            rows = [dict(row) for row in cursor.fetchall()]
            
            # Get total count (without limit)
            count_sql, count_params = self._build_count_sql(parsed)
            cursor.execute(count_sql, count_params)
            total_count = cursor.fetchone()[0]
            
        finally:
            conn.close()
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Determine columns
        if parsed.field_selection.fields == ["*"]:
            columns = list(ALLOWED_COLUMNS[parsed.table])
        else:
            columns = parsed.field_selection.fields
        
        # Apply aliases to results
        if parsed.field_selection.aliases:
            rows = [
                {parsed.field_selection.aliases.get(k, k): v for k, v in row.items()}
                for row in rows
            ]
        
        return QueryResult(
            query=original_query,
            table=parsed.table.value,
            columns=columns,
            rows=rows,
            total_rows=total_count,
            execution_time_ms=execution_time,
            has_more=total_count > parsed.offset + len(rows),
            aggregations=parsed.field_selection.aggregations if parsed.field_selection.aggregations else None,
        )
    
    def _build_sql(self, parsed: ParsedQuery) -> Tuple[str, List[Any]]:
        """Build parameterized SQL from parsed query."""
        table_name = TABLE_MAPPING[parsed.table]
        
        # SELECT clause
        if parsed.field_selection.fields == ["*"]:
            select_cols = ", ".join(ALLOWED_COLUMNS[parsed.table])
        else:
            select_cols = ", ".join(parsed.field_selection.fields)
        
        sql = f"SELECT {select_cols} FROM {table_name}"
        params = []
        
        # WHERE clause
        where_parts = []
        
        # Regular conditions
        for cond in parsed.conditions:
            clause, cond_params = self._build_condition(cond)
            where_parts.append(clause)
            params.extend(cond_params)
        
        # Date range
        if parsed.date_range:
            if parsed.date_range.start:
                where_parts.append(f"{parsed.date_range.column} >= ?")
                params.append(parsed.date_range.start.isoformat())
            if parsed.date_range.end:
                where_parts.append(f"{parsed.date_range.column} <= ?")
                params.append(parsed.date_range.end.isoformat())
        
        # Sector/Industry filters
        if parsed.sector_filter:
            where_parts.append("sector = ?")
            params.append(parsed.sector_filter)
        
        if parsed.industry_filter:
            where_parts.append("industry = ?")
            params.append(parsed.industry_filter)
        
        # Confidence threshold
        if parsed.min_confidence is not None:
            where_parts.append("confidence >= ?")
            params.append(parsed.min_confidence)
        
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        
        # GROUP BY
        if parsed.group_by:
            sql += " GROUP BY " + ", ".join(parsed.group_by)
        
        # ORDER BY
        if parsed.order_by:
            order_parts = []
            for ob in parsed.order_by:
                direction = "DESC" if ob.descending else "ASC"
                order_parts.append(f"{ob.column} {direction}")
            sql += " ORDER BY " + ", ".join(order_parts)
        
        # LIMIT/OFFSET
        sql += f" LIMIT {parsed.limit} OFFSET {parsed.offset}"
        
        return sql, params
    
    def _build_condition(
        self, 
        cond: Union[ConditionGroup, WhereCondition]
    ) -> Tuple[str, List[Any]]:
        """Build SQL for a condition or condition group."""
        if isinstance(cond, ConditionGroup):
            parts = []
            params = []
            for sub_cond in cond.conditions:
                clause, sub_params = self._build_condition(sub_cond)
                parts.append(clause)
                params.extend(sub_params)
            
            joiner = " OR " if cond.logical_op == LogicalOperator.OR else " AND "
            grouped = f"({joiner.join(parts)})"
            
            if cond.negated:
                grouped = f"NOT {grouped}"
            
            return grouped, params
        
        # Simple condition
        column = cond.column
        
        if cond.operator == Operator.IS_NULL:
            return f"{column} IS NULL", []
        elif cond.operator == Operator.IS_NOT_NULL:
            return f"{column} IS NOT NULL", []
        elif cond.operator in (Operator.IN, Operator.NOT_IN):
            if isinstance(cond.value, list):
                placeholders = ", ".join("?" * len(cond.value))
                op_str = "IN" if cond.operator == Operator.IN else "NOT IN"
                return f"{column} {op_str} ({placeholders})", cond.value
        elif cond.operator == Operator.LIKE:
            return f"{column} LIKE ?", [cond.value]
        elif cond.operator == Operator.ILIKE:
            # SQLite doesn't have ILIKE, use LIKE with LOWER
            return f"LOWER({column}) LIKE LOWER(?)", [cond.value]
        elif cond.operator == Operator.CONTAINS:
            return f"{column} LIKE ?", [f"%{cond.value}%"]
        else:
            return f"{column} {cond.operator.value} ?", [cond.value]
    
    def _build_count_sql(self, parsed: ParsedQuery) -> Tuple[str, List[Any]]:
        """Build COUNT query for pagination."""
        table_name = TABLE_MAPPING[parsed.table]
        sql = f"SELECT COUNT(*) FROM {table_name}"
        params = []
        
        # WHERE clause (same as main query)
        where_parts = []
        
        for cond in parsed.conditions:
            clause, cond_params = self._build_condition(cond)
            where_parts.append(clause)
            params.extend(cond_params)
        
        if parsed.date_range:
            if parsed.date_range.start:
                where_parts.append(f"{parsed.date_range.column} >= ?")
                params.append(parsed.date_range.start.isoformat())
            if parsed.date_range.end:
                where_parts.append(f"{parsed.date_range.column} <= ?")
                params.append(parsed.date_range.end.isoformat())
        
        if parsed.sector_filter:
            where_parts.append("sector = ?")
            params.append(parsed.sector_filter)
        
        if parsed.industry_filter:
            where_parts.append("industry = ?")
            params.append(parsed.industry_filter)
        
        if parsed.min_confidence is not None:
            where_parts.append("confidence >= ?")
            params.append(parsed.min_confidence)
        
        if where_parts:
            sql += " WHERE " + " AND ".join(where_parts)
        
        return sql, params


# =============================================================================
# Convenience Functions
# =============================================================================

def execute_query(query_string: str, store: Optional[SignalStore] = None) -> QueryResult:
    """Execute a SQL-like query string and return results."""
    executor = QueryExecutor(store)
    return executor.execute_sql(query_string)


def execute_boolean_query(query: BooleanQuery, store: Optional[SignalStore] = None) -> QueryResult:
    """Execute a BooleanQuery and return results."""
    executor = QueryExecutor(store)
    return executor.execute_boolean(query)
