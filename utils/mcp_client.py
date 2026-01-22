"""
MCP Client for BriefAI

Client that connects BriefAI's LLM providers to the MCP server
for tool invocation, resource fetching, and prompt retrieval.
"""

import json
import asyncio
from typing import Optional, Dict, Any, List
from pathlib import Path
from loguru import logger

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("MCP SDK not installed. Install with: pip install mcp")


class MCPClient:
    """Client for BriefAI MCP server integration."""

    def __init__(self, server_script: str = "mcp_server/main.py"):
        """
        Initialize MCP client.

        Args:
            server_script: Path to the MCP server script
        """
        if not MCP_AVAILABLE:
            raise ImportError("MCP SDK not installed. Install with: pip install mcp")

        self.server_script = server_script
        self.server_params = StdioServerParameters(
            command="python",
            args=["-m", "mcp_server.main"]
        )
        self._session: Optional[ClientSession] = None
        self._tools_cache: Dict[str, Any] = {}
        self._resources_cache: Dict[str, Any] = {}
        self._prompts_cache: Dict[str, Any] = {}

    async def connect(self):
        """Establish connection to MCP server."""
        if self._session is not None:
            return

        transport = await stdio_client(self.server_params)
        self._session = ClientSession(*transport)
        await self._session.initialize()

        # Cache available tools
        tools_result = await self._session.list_tools()
        self._tools_cache = {t.name: t for t in tools_result.tools}

        # Cache available resources
        resources_result = await self._session.list_resources()
        self._resources_cache = {r.uri: r for r in resources_result.resources}

        # Cache available prompts
        prompts_result = await self._session.list_prompts()
        self._prompts_cache = {p.name: p for p in prompts_result.prompts}

        logger.info(f"MCP connected. Tools: {list(self._tools_cache.keys())}")
        logger.info(f"Resources: {list(self._resources_cache.keys())}")
        logger.info(f"Prompts: {list(self._prompts_cache.keys())}")

    async def disconnect(self):
        """Close connection to MCP server."""
        if self._session:
            await self._session.close()
            self._session = None

    async def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """
        Execute a tool and return result as string.

        Args:
            name: Tool name
            arguments: Tool arguments

        Returns:
            Tool result as string
        """
        if not self._session:
            await self.connect()

        result = await self._session.call_tool(name, arguments)
        return result.content[0].text

    async def read_resource(self, uri: str) -> str:
        """
        Read a resource by URI.

        Args:
            uri: Resource URI (e.g., "trend://latest")

        Returns:
            Resource content as string
        """
        if not self._session:
            await self.connect()

        result = await self._session.read_resource(uri)
        return result.contents[0].text

    async def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """
        Get a prompt template with arguments.

        Args:
            name: Prompt name (e.g., "skeptic")
            arguments: Template variables

        Returns:
            Rendered prompt string
        """
        if not self._session:
            await self.connect()

        result = await self._session.get_prompt(name, arguments or {})
        return result.messages[0].content.text

    def get_tool_descriptions(self) -> str:
        """
        Format tool descriptions for LLM prompt injection.

        Returns:
            Formatted string describing available tools
        """
        if not self._tools_cache:
            return "No tools available."

        lines = []
        for name, tool in self._tools_cache.items():
            # Build argument description
            schema = tool.inputSchema or {}
            properties = schema.get("properties", {})
            args_desc = ", ".join(
                f"{arg}: {info.get('type', 'any')}"
                for arg, info in properties.items()
            )
            desc = tool.description or "No description"
            lines.append(f"- {name}({args_desc}): {desc}")

        return "\n".join(lines)

    def list_tools(self) -> List[str]:
        """Get list of available tool names."""
        return list(self._tools_cache.keys())

    def list_resources(self) -> List[str]:
        """Get list of available resource URIs."""
        return list(self._resources_cache.keys())

    def list_prompts(self) -> List[str]:
        """Get list of available prompt names."""
        return list(self._prompts_cache.keys())


class SyncMCPClient:
    """Synchronous wrapper for MCPClient."""

    def __init__(self, server_script: str = "mcp_server/main.py"):
        self._async_client = MCPClient(server_script)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create event loop."""
        if self._loop is None or self._loop.is_closed():
            try:
                self._loop = asyncio.get_running_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        return self._loop

    def connect(self):
        """Connect to MCP server."""
        loop = self._get_loop()
        loop.run_until_complete(self._async_client.connect())

    def disconnect(self):
        """Disconnect from MCP server."""
        loop = self._get_loop()
        loop.run_until_complete(self._async_client.disconnect())

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> str:
        """Call a tool synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(self._async_client.call_tool(name, arguments))

    def read_resource(self, uri: str) -> str:
        """Read a resource synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(self._async_client.read_resource(uri))

    def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> str:
        """Get a prompt synchronously."""
        loop = self._get_loop()
        return loop.run_until_complete(self._async_client.get_prompt(name, arguments))

    def get_tool_descriptions(self) -> str:
        """Get tool descriptions."""
        return self._async_client.get_tool_descriptions()

    def list_tools(self) -> List[str]:
        """List available tools."""
        return self._async_client.list_tools()

    def list_resources(self) -> List[str]:
        """List available resources."""
        return self._async_client.list_resources()

    def list_prompts(self) -> List[str]:
        """List available prompts."""
        return self._async_client.list_prompts()


def parse_tool_call(response: str) -> Optional[Dict[str, Any]]:
    """
    Parse tool call JSON from LLM response.

    Used for simulated function calling with Kimi/OpenRouter.

    Args:
        response: LLM response text

    Returns:
        Dict with 'tool' and 'args' keys, or None if not a tool call
    """
    try:
        # Try to find JSON in the response
        text = response.strip()

        # Direct JSON object
        if text.startswith("{"):
            data = json.loads(text)
            if "tool" in data and "args" in data:
                return data

        # JSON in code block
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            json_text = text[start:end].strip()
            data = json.loads(json_text)
            if "tool" in data and "args" in data:
                return data

        # Generic code block
        if "```" in text:
            start = text.find("```") + 3
            # Skip language identifier if present
            newline = text.find("\n", start)
            if newline != -1 and newline - start < 20:
                start = newline + 1
            end = text.find("```", start)
            json_text = text[start:end].strip()
            data = json.loads(json_text)
            if "tool" in data and "args" in data:
                return data

    except (json.JSONDecodeError, ValueError):
        pass

    return None


# Tool prompt template for simulated function calling
TOOL_CALLING_PROMPT = """You have access to the following tools:

{tool_descriptions}

To use a tool, respond with JSON in this exact format:
{{"tool": "tool_name", "args": {{"arg1": "value1"}}}}

If you don't need a tool, respond normally with your analysis."""
