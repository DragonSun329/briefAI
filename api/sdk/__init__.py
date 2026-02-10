"""
briefAI Python SDK

Professional Python client for the briefAI API.

Usage:
    from briefai_sdk import BriefAIClient, QueryBuilder
    
    client = BriefAIClient(api_key="your_key")
    entities, _ = client.entities.search("openai")
"""

from .briefai_client import (
    # Main client
    BriefAIClient,
    AsyncBriefAIClient,
    
    # Query builder
    QueryBuilder,
    
    # Exceptions
    BriefAIError,
    AuthenticationError,
    RateLimitError,
    APIError,
    ValidationError,
    
    # Response models
    Entity,
    SignalScore,
    Profile,
    Divergence,
    ExportJob,
    Pagination,
    RateLimitInfo,
    
    # Convenience functions
    create_client,
    query,
)

__version__ = "1.0.0"
__all__ = [
    # Client
    "BriefAIClient",
    "AsyncBriefAIClient",
    "create_client",
    
    # Query
    "QueryBuilder",
    "query",
    
    # Exceptions
    "BriefAIError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    "ValidationError",
    
    # Models
    "Entity",
    "SignalScore",
    "Profile",
    "Divergence",
    "ExportJob",
    "Pagination",
    "RateLimitInfo",
]
