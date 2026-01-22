"""
MCP Server Error Definitions

Custom exceptions for MCP tool and resource failures.
"""


class MCPToolError(Exception):
    """Base error for MCP tool failures."""

    def __init__(self, tool: str, message: str, retryable: bool = False):
        self.tool = tool
        self.retryable = retryable
        super().__init__(f"[{tool}] {message}")


class RateLimitedError(MCPToolError):
    """External API rate limited."""

    def __init__(self, tool: str, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(
            tool, f"Rate limited. Retry after {retry_after}s", retryable=True
        )


class ResourceNotFoundError(MCPToolError):
    """Requested resource doesn't exist."""

    def __init__(self, uri: str):
        super().__init__("resource", f"Not found: {uri}", retryable=False)


class ToolExecutionError(MCPToolError):
    """Tool execution failed."""

    def __init__(self, tool: str, message: str):
        super().__init__(tool, message, retryable=False)
