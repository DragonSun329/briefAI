"""
MCP Prompts - Persona templates stored as Markdown files.

Provides dynamic loading of prompt templates with variable substitution.
"""

from pathlib import Path


def load_prompt(filename: str) -> str:
    """
    Load a Markdown prompt template.

    Args:
        filename: Name of the prompt file (e.g., "skeptic.md")

    Returns:
        Template content as string, ready for .format() substitution
    """
    prompt_path = Path(__file__).parent / filename
    if not prompt_path.exists():
        return f"Error: Prompt template {filename} not found."
    return prompt_path.read_text(encoding="utf-8")


def get_available_prompts() -> list[str]:
    """List all available prompt templates."""
    prompt_dir = Path(__file__).parent
    return [f.stem for f in prompt_dir.glob("*.md")]
