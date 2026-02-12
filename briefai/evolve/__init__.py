"""
briefAI Engine Evolution System

Applies approved config patches to create new engine versions.
All changes are tracked via git commits and tags.
"""

from .cli import apply_patch, validate_patch_document

__all__ = ["apply_patch", "validate_patch_document"]
