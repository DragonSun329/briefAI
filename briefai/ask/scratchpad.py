"""
Append-only Scratchpad with loop prevention.

Tracks all tool calls and detects:
1. Repeated calls to the same tool with identical arguments
2. Calls to the same tool exceeding threshold (default 3)
3. Similar queries (semantic deduplication)

This prevents infinite loops in the agentic reasoning.
"""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict

from loguru import logger


def _utc_now_iso() -> str:
    """Get current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class ScratchpadEntry:
    """Single entry in the scratchpad."""
    iteration: int
    action: str                      # "plan", "tool_call", "reflect", "answer"
    content: str
    timestamp: str = field(default_factory=_utc_now_iso)
    metadata: Dict[str, Any] = field(default_factory=dict)


class Scratchpad:
    """
    Append-only scratchpad with loop detection.
    
    Usage:
        pad = Scratchpad()
        pad.add_plan("I will search for signals...")
        
        # Check before calling tool
        warning = pad.check_tool_call("search_signals", {"query": "openai"})
        if warning:
            logger.warning(warning)
        
        # Record the call
        pad.add_tool_call("search_signals", {"query": "openai"}, result_summary)
        
        # Get all warnings at end
        warnings = pad.get_loop_warnings()
    """
    
    # Default thresholds
    MAX_SAME_TOOL_CALLS = 3
    SIMILARITY_THRESHOLD = 0.85  # For query similarity detection
    
    def __init__(
        self,
        max_same_tool_calls: int = MAX_SAME_TOOL_CALLS,
        similarity_threshold: float = SIMILARITY_THRESHOLD,
    ):
        self.max_same_tool_calls = max_same_tool_calls
        self.similarity_threshold = similarity_threshold
        
        # Append-only log
        self._entries: List[ScratchpadEntry] = []
        self._iteration = 0
        
        # Loop detection state
        self._tool_call_counts: Dict[str, int] = defaultdict(int)
        self._call_signatures: Set[str] = set()
        self._query_hashes: Dict[str, List[str]] = defaultdict(list)  # tool -> [query_hashes]
        
        # Warnings accumulated
        self._warnings: List[str] = []
    
    # -------------------------------------------------------------------------
    # Public API: Add entries
    # -------------------------------------------------------------------------
    
    def add_plan(self, plan: str) -> None:
        """Record a planning step."""
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="plan",
            content=plan,
        ))
    
    def add_reflection(self, reflection: str) -> None:
        """Record a reflection step."""
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="reflect",
            content=reflection,
        ))
    
    def add_answer(self, answer: str) -> None:
        """Record the final answer."""
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="answer",
            content=answer,
        ))
    
    # v1.2: New record types for reflection loop
    def add_reflection_check(self, validation_result: Dict[str, Any]) -> None:
        """Record a reflection validation check."""
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="reflection_check",
            content=f"Validation: {validation_result.get('status', 'unknown')}",
            metadata=validation_result,
        ))
    
    def add_reflection_repair(self, repair_instructions: str, failed_rules: List[str]) -> None:
        """Record a reflection repair attempt."""
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="reflection_repair_attempt",
            content=repair_instructions,
            metadata={"failed_rules": failed_rules},
        ))
    
    def add_diff_analysis(self, diff_result: Dict[str, Any]) -> None:
        """Record a diff analysis for daily change queries."""
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="diff_analysis",
            content=f"Daily diff: {diff_result.get('total_changes', 0)} changes",
            metadata=diff_result,
        ))
    
    def add_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result_summary: str,
        result_type: str = "success",
    ) -> Optional[str]:
        """
        Record a tool call and return any warning.
        
        Returns:
            Warning message if loop detected, None otherwise.
        """
        # Create signature for exact duplicate detection
        sig = self._make_signature(tool_name, arguments)
        
        # Record the call
        self._entries.append(ScratchpadEntry(
            iteration=self._iteration,
            action="tool_call",
            content=f"{tool_name}({json.dumps(arguments, ensure_ascii=False)})",
            metadata={
                "tool_name": tool_name,
                "arguments": arguments,
                "result_summary": result_summary[:500],  # Truncate
                "result_type": result_type,
                "signature": sig,
            },
        ))
        
        # Update counts
        self._tool_call_counts[tool_name] += 1
        self._call_signatures.add(sig)
        
        # Track query-like arguments for similarity detection
        query_arg = self._extract_query(arguments)
        if query_arg:
            query_hash = self._hash_query(query_arg)
            self._query_hashes[tool_name].append(query_hash)
        
        return None  # Warning already checked in check_tool_call
    
    def next_iteration(self) -> int:
        """Advance to next iteration and return the new iteration number."""
        self._iteration += 1
        return self._iteration
    
    # -------------------------------------------------------------------------
    # Public API: Loop detection
    # -------------------------------------------------------------------------
    
    def check_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Optional[str]:
        """
        Check if a tool call should proceed.
        
        Returns:
            Warning message if loop detected, None otherwise.
        """
        warnings = []
        
        # Check 1: Exact duplicate
        sig = self._make_signature(tool_name, arguments)
        if sig in self._call_signatures:
            warning = f"⚠️ LOOP: Exact duplicate call to {tool_name}({arguments})"
            warnings.append(warning)
            self._warnings.append(warning)
        
        # Check 2: Too many calls to same tool
        if self._tool_call_counts[tool_name] >= self.max_same_tool_calls:
            warning = f"⚠️ LOOP: {tool_name} called {self._tool_call_counts[tool_name]} times (max={self.max_same_tool_calls})"
            warnings.append(warning)
            self._warnings.append(warning)
        
        # Check 3: Similar queries
        query_arg = self._extract_query(arguments)
        if query_arg and tool_name in self._query_hashes:
            new_hash = self._hash_query(query_arg)
            for existing_hash in self._query_hashes[tool_name]:
                if self._is_similar_hash(new_hash, existing_hash):
                    warning = f"⚠️ LOOP: Similar query detected for {tool_name}: '{query_arg}'"
                    warnings.append(warning)
                    self._warnings.append(warning)
                    break
        
        return " | ".join(warnings) if warnings else None
    
    def get_loop_warnings(self) -> List[str]:
        """Get all accumulated loop warnings."""
        return list(self._warnings)
    
    def get_tool_call_count(self, tool_name: str) -> int:
        """Get number of times a tool was called."""
        return self._tool_call_counts[tool_name]
    
    def get_total_tool_calls(self) -> int:
        """Get total number of tool calls."""
        return sum(self._tool_call_counts.values())
    
    # -------------------------------------------------------------------------
    # Public API: Read entries
    # -------------------------------------------------------------------------
    
    def get_entries(self) -> List[ScratchpadEntry]:
        """Get all entries (read-only copy)."""
        return list(self._entries)
    
    def get_entries_by_action(self, action: str) -> List[ScratchpadEntry]:
        """Get entries filtered by action type."""
        return [e for e in self._entries if e.action == action]
    
    def get_tool_results(self) -> List[Dict[str, Any]]:
        """Get all tool call results."""
        return [e.metadata for e in self._entries if e.action == "tool_call"]
    
    def format_for_context(self, max_chars: int = 4000) -> str:
        """Format scratchpad for inclusion in LLM context."""
        lines = []
        for entry in self._entries:
            if entry.action == "tool_call":
                meta = entry.metadata
                lines.append(f"[{entry.action}] {meta['tool_name']} → {meta['result_type']}: {meta['result_summary'][:200]}")
            else:
                lines.append(f"[{entry.action}] {entry.content[:300]}")
        
        result = "\n".join(lines)
        if len(result) > max_chars:
            result = result[:max_chars] + "\n... (truncated)"
        return result
    
    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    
    def _make_signature(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Create a unique signature for a tool call."""
        # Normalize arguments for consistent hashing
        args_str = json.dumps(arguments, sort_keys=True, ensure_ascii=False)
        return f"{tool_name}:{args_str}"
    
    def _extract_query(self, arguments: Dict[str, Any]) -> Optional[str]:
        """Extract the query-like argument from tool arguments."""
        # Common query argument names
        for key in ["query", "entity", "date", "q", "search"]:
            if key in arguments:
                val = arguments[key]
                if isinstance(val, str):
                    return val
        return None
    
    def _hash_query(self, query: str) -> str:
        """Create a normalized hash of a query for similarity detection."""
        # Normalize: lowercase, remove extra whitespace, sort words
        normalized = " ".join(sorted(query.lower().split()))
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _is_similar_hash(self, hash1: str, hash2: str) -> bool:
        """
        Check if two query hashes are similar.
        
        For now, uses exact match on normalized hash.
        Future: could use edit distance on original queries.
        """
        return hash1 == hash2
