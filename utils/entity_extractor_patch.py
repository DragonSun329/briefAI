"""
Temporary patch for entity_extractor to handle Python 3.14 spaCy incompatibility
"""

import sys
import importlib.util

# Block spaCy import to prevent Python 3.14 compatibility errors
sys.modules['spacy'] = None  # type: ignore
sys.modules['spacy.tokens'] = None  # type: ignore
sys.modules['spacy.vocab'] = None  # type: ignore

print("WARNING: Entity extraction patched - spaCy disabled due to Python 3.14 incompatibility")
print("         Falling back to LLM-based entity extraction only")