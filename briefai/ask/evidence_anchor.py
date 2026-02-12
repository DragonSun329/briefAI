"""
Stable Evidence Citations for Ask Mode v1.2.

Replaces fragile line-number citations with stable anchors:
- JSON: Anchor by object id (#meta_id=<id>, #prediction_id=<id>)
- Markdown: Anchor by heading slug + quote hash

Format: [evidence: path#anchor_type=value&quote=hash]
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from loguru import logger


# =============================================================================
# ANCHOR TYPES
# =============================================================================

class AnchorType(str, Enum):
    """Types of stable anchors."""
    META_ID = "meta_id"
    PREDICTION_ID = "prediction_id"
    SIGNAL_ID = "signal_id"
    ENTITY_ID = "entity_id"
    HYPOTHESIS_ID = "hypothesis_id"
    HEADING = "heading"
    QUOTE = "quote"
    SECTION = "section"


# =============================================================================
# STABLE EVIDENCE REF
# =============================================================================

@dataclass
class StableEvidenceRef:
    """
    Stable evidence reference that survives file edits.
    
    Format: [evidence: path#anchor_type=value&quote=hash]
    
    Examples:
    - [evidence: data/meta_signals/meta_signals_2026-02-11.json#meta_id=52f11143]
    - [evidence: data/briefs/analyst_brief_2026-02-11.md#heading=ai-chip-market&quote=8fa21c3a]
    """
    artifact_path: str
    anchor_type: AnchorType
    anchor_value: str
    quote_hash: Optional[str] = None  # sha1(sentence)[:8]
    as_of_date: Optional[str] = None
    relevance_hint: Optional[str] = None
    
    # Original context for verification
    original_text: Optional[str] = None
    
    def to_citation(self) -> str:
        """Generate the stable citation string."""
        anchor_str = f"{self.anchor_type.value}={self.anchor_value}"
        
        if self.quote_hash:
            anchor_str += f"&quote={self.quote_hash}"
        
        return f"[evidence: {self.artifact_path}#{anchor_str}]"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_path": self.artifact_path,
            "anchor_type": self.anchor_type.value,
            "anchor_value": self.anchor_value,
            "quote_hash": self.quote_hash,
            "as_of_date": self.as_of_date,
            "relevance_hint": self.relevance_hint,
        }
    
    @classmethod
    def from_citation(cls, citation: str) -> Optional["StableEvidenceRef"]:
        """Parse a citation string back into StableEvidenceRef."""
        # Pattern: [evidence: path#anchor_type=value(&quote=hash)?]
        match = re.match(
            r"\[evidence:\s*([^#]+)#(\w+)=([^&\]]+)(?:&quote=([a-f0-9]+))?\]",
            citation
        )
        
        if not match:
            return None
        
        path = match.group(1).strip()
        anchor_type_str = match.group(2)
        anchor_value = match.group(3)
        quote_hash = match.group(4)
        
        try:
            anchor_type = AnchorType(anchor_type_str)
        except ValueError:
            anchor_type = AnchorType.SECTION  # Fallback
        
        return cls(
            artifact_path=path,
            anchor_type=anchor_type,
            anchor_value=anchor_value,
            quote_hash=quote_hash,
        )
    
    def __str__(self) -> str:
        return self.to_citation()


# =============================================================================
# HASH GENERATION
# =============================================================================

def compute_quote_hash(text: str) -> str:
    """
    Compute a stable hash for a quote.
    
    Normalizes whitespace before hashing for stability.
    Returns first 8 chars of sha1.
    """
    # Normalize: lowercase, collapse whitespace
    normalized = " ".join(text.lower().split())
    hash_bytes = hashlib.sha1(normalized.encode('utf-8')).hexdigest()
    return hash_bytes[:8]


def slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    # Lowercase, replace spaces with hyphens, remove special chars
    slug = text.lower()
    slug = re.sub(r'[^\w\s-]', '', slug)
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


# =============================================================================
# JSON ANCHORING
# =============================================================================

def create_json_anchor(
    filepath: str,
    data: Dict[str, Any],
    context_text: Optional[str] = None,
) -> StableEvidenceRef:
    """
    Create a stable anchor for JSON data.
    
    Looks for id fields in order of preference:
    - meta_id
    - prediction_id
    - signal_id
    - hypothesis_id
    - entity_id
    - id
    """
    # ID field priority
    id_fields = [
        ("meta_id", AnchorType.META_ID),
        ("prediction_id", AnchorType.PREDICTION_ID),
        ("signal_id", AnchorType.SIGNAL_ID),
        ("hypothesis_id", AnchorType.HYPOTHESIS_ID),
        ("entity_id", AnchorType.ENTITY_ID),
        ("id", AnchorType.SIGNAL_ID),
    ]
    
    anchor_type = AnchorType.SECTION
    anchor_value = "root"
    
    for field_name, atype in id_fields:
        if field_name in data:
            anchor_type = atype
            anchor_value = str(data[field_name])
            break
    
    # Compute quote hash if context provided
    quote_hash = None
    if context_text:
        quote_hash = compute_quote_hash(context_text)
    
    # Extract date from path if present
    as_of_date = None
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath)
    if date_match:
        as_of_date = date_match.group(1)
    
    return StableEvidenceRef(
        artifact_path=filepath,
        anchor_type=anchor_type,
        anchor_value=anchor_value,
        quote_hash=quote_hash,
        as_of_date=as_of_date,
        original_text=context_text,
    )


# =============================================================================
# MARKDOWN ANCHORING
# =============================================================================

def find_nearest_heading(content: str, target_text: str) -> Optional[str]:
    """Find the nearest heading before the target text."""
    # Find position of target text
    pos = content.lower().find(target_text.lower()[:50])
    if pos == -1:
        return None
    
    # Find all headings before this position
    headings = list(re.finditer(r"^#+\s+(.+)$", content[:pos], re.MULTILINE))
    
    if not headings:
        return None
    
    # Return the last (nearest) heading
    return headings[-1].group(1).strip()


def extract_sentence(content: str, target_text: str) -> Optional[str]:
    """Extract the sentence containing the target text."""
    # Find the target
    pos = content.lower().find(target_text.lower()[:30])
    if pos == -1:
        return None
    
    # Find sentence boundaries
    # Look backward for sentence start
    start = pos
    while start > 0 and content[start - 1] not in '.!?\n':
        start -= 1
    
    # Look forward for sentence end
    end = pos + len(target_text)
    while end < len(content) and content[end] not in '.!?\n':
        end += 1
    
    sentence = content[start:end + 1].strip()
    
    # Limit length
    if len(sentence) > 200:
        sentence = sentence[:200]
    
    return sentence


def create_markdown_anchor(
    filepath: str,
    content: str,
    context_text: str,
) -> StableEvidenceRef:
    """
    Create a stable anchor for Markdown content.
    
    Uses heading slug + quote hash format.
    """
    # Find nearest heading
    heading = find_nearest_heading(content, context_text)
    heading_slug = slugify(heading) if heading else "document"
    
    # Extract sentence for hash
    sentence = extract_sentence(content, context_text)
    quote_hash = compute_quote_hash(sentence or context_text)
    
    # Extract date from path
    as_of_date = None
    date_match = re.search(r"(\d{4}-\d{2}-\d{2})", filepath)
    if date_match:
        as_of_date = date_match.group(1)
    
    return StableEvidenceRef(
        artifact_path=filepath,
        anchor_type=AnchorType.HEADING,
        anchor_value=heading_slug,
        quote_hash=quote_hash,
        as_of_date=as_of_date,
        original_text=sentence or context_text[:100],
    )


# =============================================================================
# MAIN API
# =============================================================================

def generate_evidence_ref(
    filepath: str,
    context_text: str,
    data: Optional[Dict[str, Any]] = None,
) -> StableEvidenceRef:
    """
    Generate a stable evidence reference for any file type.
    
    Args:
        filepath: Path to the artifact file
        context_text: Text snippet being cited
        data: For JSON files, the parsed object being cited
    
    Returns:
        StableEvidenceRef with stable anchors
    """
    filepath = str(filepath)
    
    # Determine file type and anchor accordingly
    if filepath.endswith('.json') or filepath.endswith('.jsonl'):
        if data:
            return create_json_anchor(filepath, data, context_text)
        else:
            # No data provided, use quote hash only
            return StableEvidenceRef(
                artifact_path=filepath,
                anchor_type=AnchorType.QUOTE,
                anchor_value="content",
                quote_hash=compute_quote_hash(context_text),
            )
    
    elif filepath.endswith('.md'):
        # Try to load content for heading detection
        try:
            path = Path(filepath)
            if not path.is_absolute():
                # Try relative to briefAI data
                base_path = Path(__file__).parent.parent.parent
                path = base_path / filepath
            
            if path.exists():
                content = path.read_text(encoding='utf-8')
                return create_markdown_anchor(filepath, content, context_text)
        except Exception as e:
            logger.debug(f"Could not load markdown for anchoring: {e}")
        
        # Fallback: quote hash only
        return StableEvidenceRef(
            artifact_path=filepath,
            anchor_type=AnchorType.QUOTE,
            anchor_value="document",
            quote_hash=compute_quote_hash(context_text),
        )
    
    else:
        # Unknown file type: use quote hash
        return StableEvidenceRef(
            artifact_path=filepath,
            anchor_type=AnchorType.QUOTE,
            anchor_value="content",
            quote_hash=compute_quote_hash(context_text),
        )


# =============================================================================
# EVIDENCE APPENDIX GENERATOR
# =============================================================================

def generate_evidence_appendix(refs: List[StableEvidenceRef]) -> str:
    """
    Generate a deduplicated 'Evidence Used' appendix section.
    
    Args:
        refs: List of evidence references used in the answer
    
    Returns:
        Markdown-formatted appendix section
    """
    if not refs:
        return ""
    
    # Deduplicate by citation string
    seen = set()
    unique_refs = []
    
    for ref in refs:
        citation = ref.to_citation()
        if citation not in seen:
            seen.add(citation)
            unique_refs.append(ref)
    
    # Sort by artifact path for readability
    unique_refs.sort(key=lambda r: r.artifact_path)
    
    # Build appendix
    lines = [
        "",
        "---",
        "",
        "## Evidence Used",
        "",
    ]
    
    for ref in unique_refs:
        date_str = f" (as of {ref.as_of_date})" if ref.as_of_date else ""
        hint_str = f" — {ref.relevance_hint}" if ref.relevance_hint else ""
        lines.append(f"- {ref.to_citation()}{date_str}{hint_str}")
    
    return "\n".join(lines)


# =============================================================================
# CITATION EXTRACTION
# =============================================================================

def extract_citations_from_answer(answer: str) -> List[StableEvidenceRef]:
    """
    Extract all citations from an answer text.
    
    Returns list of parsed StableEvidenceRef objects.
    """
    # Find all citation patterns
    pattern = r"\[evidence:[^\]]+\]"
    citations = re.findall(pattern, answer)
    
    refs = []
    for citation in citations:
        ref = StableEvidenceRef.from_citation(citation)
        if ref:
            refs.append(ref)
    
    return refs


def validate_citation_format(citation: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a citation follows the stable format.
    
    Returns:
        (is_valid, error_message)
    """
    # Check basic format
    if not citation.startswith("[evidence:"):
        return False, "Must start with [evidence:"
    
    if not citation.endswith("]"):
        return False, "Must end with ]"
    
    # Check for anchor
    if "#" not in citation:
        return False, "Missing anchor (#)"
    
    # Check anchor format
    anchor_part = citation.split("#")[1].rstrip("]")
    if "=" not in anchor_part:
        return False, "Anchor must have format: type=value"
    
    # Warn about line number anchors (fragile)
    if re.search(r"#L\d+", citation):
        return False, "Line number anchors (L123) are fragile; use stable anchors"
    
    return True, None
