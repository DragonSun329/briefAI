"""
BriefAI MCP Server

Model Context Protocol server providing tools, resources, and prompts
for JIT context loading and adversarial agent support.

Usage:
    python -m mcp_server.main
    # or
    fastmcp run mcp_server/main.py
"""

from fastmcp import FastMCP

# Initialize server
mcp = FastMCP("briefai-mcp")

# Register tool modules
from mcp_server.tools import github_tools, web_scraper, data_tools, search_tools
from mcp_server.resources import trend_db

github_tools.register(mcp)
web_scraper.register(mcp)
data_tools.register(mcp)
search_tools.register(mcp)
trend_db.register(mcp)

# Register prompts with dynamic loading
from mcp_server.prompts import load_prompt


@mcp.prompt()
def hypeman(entity_name: str) -> str:
    """Bull thesis generator persona.

    Args:
        entity_name: Name of the entity to analyze
    """
    template = load_prompt("hypeman.md")
    return template.format(entity_name=entity_name)


@mcp.prompt()
def skeptic(entity_name: str, bull_thesis: str = "") -> str:
    """Bear thesis generator persona.

    Args:
        entity_name: Name of the entity to analyze
        bull_thesis: The bull case to counter (optional)
    """
    template = load_prompt("skeptic.md")
    return template.format(entity_name=entity_name, bull_thesis=bull_thesis or "N/A")


@mcp.prompt()
def arbiter(bull_thesis: str, bear_thesis: str) -> str:
    """Synthesis and scoring persona.

    Args:
        bull_thesis: The bull case from Hype-Man
        bear_thesis: The bear case from Skeptic
    """
    template = load_prompt("arbiter.md")
    return template.format(bull_thesis=bull_thesis, bear_thesis=bear_thesis)


if __name__ == "__main__":
    mcp.run()
