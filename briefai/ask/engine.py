"""
Ask Mode Engine - Agentic research loop.

Implements the core ask workflow:
1. Plan: Generate a research plan
2. Execute: Run tools to gather evidence
3. Reflect: Evaluate evidence quality
4. Answer: Generate answer with measurable checks

The engine is deterministic given:
- Same question
- Same local artifacts
- Same LLM seed (if supported)
"""

import json
import time
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

from briefai.ask.models import (
    AskLogEntry,
    ToolCallRecord,
    MeasurableCheck,
    EvidenceLink,
    EvidenceRef,
    SourceCategory,
)
from briefai.ask.tools import ToolRegistry, ToolResult, DataMissing
from briefai.ask.scratchpad import Scratchpad
from briefai.ask.quality_gates import QualityGates, QualityAssessment
from briefai.ask.freshness import get_latest_artifact_dates, FreshnessSummary
from briefai.ask.intent_router import route_intent, IntentPlan, Intent
from briefai.ask.reflection import (
    validate_answer,
    ValidationReport,
    ValidationStatus,
    get_repair_instructions,
    create_partial_confidence_banner,
)
from briefai.ask.evidence_anchor import (
    generate_evidence_appendix,
    extract_citations_from_answer,
    StableEvidenceRef,
)


# =============================================================================
# CONSTANTS
# =============================================================================

MAX_ITERATIONS = 10
DEFAULT_EXPERIMENT = "v2_2_forward_test"


# =============================================================================
# LLM INTERFACE (MINIMAL)
# =============================================================================

def get_llm_response(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.0,  # Deterministic
) -> str:
    """
    Get LLM response. Uses briefAI's LLM client.
    
    Temperature 0.0 for determinism.
    """
    # Import here to avoid circular deps
    try:
        from utils.llm_client import get_completion
        return get_completion(
            prompt=prompt,
            system_prompt=system_prompt or "",
            temperature=temperature,
        )
    except ImportError:
        # Fallback: try ollama directly
        try:
            import ollama
            response = ollama.generate(
                model="llama3.2",
                prompt=f"{system_prompt or ''}\n\n{prompt}",
                options={"temperature": temperature},
            )
            return response.get("response", "")
        except Exception as e:
            logger.error(f"LLM unavailable: {e}")
            return f"[LLM unavailable: {e}]"


# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_PROMPT = """You are a research analyst for briefAI, an AI industry intelligence platform.
You have access to local data artifacts from the daily pipeline.

Your responses must be:
1. Grounded in evidence from the tools
2. Include measurable predictions (metric + direction + window)
3. Acknowledge limitations when data is missing

Available tools:
{tool_docs}

When answering, always cite your evidence sources."""


PLANNING_PROMPT = """Question: {question}

Plan your research approach. What data do you need to gather?
Think step by step about which tools to use and in what order.

Output your plan as a numbered list of steps.
Each step should specify: [tool_name] - what to search for and why.
"""


TOOL_SELECTION_PROMPT = """Question: {question}

Plan: {plan}

Scratchpad (what we've done so far):
{scratchpad}

Evidence gathered: {evidence_count} sources from categories: {categories}

Based on what we've gathered, what tool should we call next?
If we have enough evidence, respond with: DONE

Otherwise, respond with a JSON object:
{{"tool": "tool_name", "arguments": {{"arg1": "value1"}}}}

Only use tools from: {available_tools}
"""


REFLECTION_PROMPT = """Question: {question}

Plan: {plan}

Evidence gathered:
{evidence_summary}

Reflect on the evidence quality:
1. Do we have >= 2 different source categories? (Currently: {categories})
2. Are there any gaps in our evidence?
3. Can we make measurable predictions?

If evidence is insufficient, suggest what additional data to gather.
If sufficient, summarize the key findings.
"""


ANSWER_PROMPT = """Question: {question}

{freshness_banner}

Evidence with Citations:
{evidence_summary}

Quality Assessment: {quality_notes}

Generate a comprehensive answer based on the evidence.

Your answer MUST include:

## Key Takeaways
- Each bullet MUST include at least one citation in format: [evidence: path#anchor]
- Use the exact citations provided in the evidence summary

## What to Watch
- At least 2 measurable predictions in format:
  - PREDICTION: [entity] [metric] will [direction] within [N] days [evidence: citation]

## Confidence & Caveats
- State overall confidence level
- Note any data gaps or limitations

IMPORTANT: Every claim must have a citation. Use the [evidence: ...] format exactly.
If evidence is insufficient, say so clearly and suggest next steps."""


# =============================================================================
# ENGINE
# =============================================================================

@dataclass
class EngineConfig:
    """Configuration for the ask engine."""
    experiment_id: str = DEFAULT_EXPERIMENT
    max_iterations: int = MAX_ITERATIONS
    temperature: float = 0.0
    verbose: bool = False
    use_intent_router: bool = True  # v1.1: Enable intent-based routing


class AskEngine:
    """
    Agentic research engine for interactive questions.
    
    Usage:
        engine = AskEngine(experiment_id="v2_2_forward_test")
        result = engine.ask("What signals suggest OpenAI pricing changes?")
        print(result.final_answer)
    """
    
    def __init__(
        self,
        experiment_id: str = DEFAULT_EXPERIMENT,
        config: Optional[EngineConfig] = None,
    ):
        self.experiment_id = experiment_id
        self.config = config or EngineConfig(experiment_id=experiment_id)
        
        self.tool_registry = ToolRegistry()
        self.quality_gates = QualityGates()
        
        # Validate experiment exists
        self._validate_experiment()
    
    def _validate_experiment(self) -> None:
        """Validate experiment path exists."""
        from briefai.ask.tools import validate_experiment_path
        
        if not validate_experiment_path(self.experiment_id):
            logger.warning(f"Experiment path not found: {self.experiment_id}")
    
    def ask(self, question: str) -> AskLogEntry:
        """
        Run the agentic research loop.
        
        Args:
            question: Research question to answer
        
        Returns:
            AskLogEntry with full trace and answer
        """
        start_time = time.time()
        
        # v1.1: Get freshness info
        self._freshness = get_latest_artifact_dates(self.experiment_id)
        
        # v1.1: Route intent to reduce tool thrash
        if self.config.use_intent_router:
            self._intent_plan = route_intent(question)
            max_iterations = self._intent_plan.max_iterations
            if self.config.verbose:
                logger.info(f"Intent: {self._intent_plan.intent} (conf={self._intent_plan.confidence:.2f})")
        else:
            self._intent_plan = None
            max_iterations = self.config.max_iterations
        
        # Initialize scratchpad
        scratchpad = Scratchpad()
        
        # Create log entry
        log_entry = AskLogEntry(
            question=question,
            experiment_id=self.experiment_id,
            plan="",
            commit_hash=self._get_commit_hash(),
            engine_tag=self._get_engine_tag(),
        )
        
        # Phase 1: Plan (with intent guidance)
        plan = self._generate_plan(question)
        log_entry.plan = plan
        scratchpad.add_plan(plan)
        
        if self.config.verbose:
            logger.info(f"Plan: {plan[:200]}...")
        
        # Phase 2: Execute tools
        all_evidence = []
        all_evidence_refs = []  # v1.1: Track citations
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            scratchpad.next_iteration()
            log_entry.loop_iterations = iteration
            
            # Get next tool call
            tool_call = self._select_next_tool(
                question=question,
                plan=plan,
                scratchpad=scratchpad,
                evidence=all_evidence,
            )
            
            if tool_call is None or tool_call.get("done"):
                if self.config.verbose:
                    logger.info(f"Loop complete after {iteration} iterations")
                break
            
            tool_name = tool_call.get("tool", "")
            arguments = tool_call.get("arguments", {})
            
            # Check for loops
            warning = scratchpad.check_tool_call(tool_name, arguments)
            if warning:
                log_entry.loop_warnings.append(warning)
                if self.config.verbose:
                    logger.warning(warning)
                # Don't break, let LLM handle it
            
            # Execute tool
            result = self._execute_tool(tool_name, arguments)
            
            # Record in scratchpad
            scratchpad.add_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                result_summary=result.summary,
                result_type="data_missing" if result.is_missing else "success",
            )
            
            # Record in log
            log_entry.tool_calls.append(ToolCallRecord(
                tool_name=tool_name,
                arguments=arguments,
                result_summary=result.summary,
                result_type="data_missing" if result.is_missing else "success",
            ))
            log_entry.tool_results_summaries.append(result.summary)
            
            # Collect evidence
            if result.success:
                all_evidence.extend(result.evidence_links)
                # v1.1: Collect evidence refs for citations
                if hasattr(result, 'evidence_refs') and result.evidence_refs:
                    all_evidence_refs.extend(result.evidence_refs)
            
            if self.config.verbose:
                logger.info(f"[{iteration}] {tool_name} → {result.summary[:100]}")
        
        # Add accumulated warnings
        log_entry.loop_warnings.extend(scratchpad.get_loop_warnings())
        
        # Phase 3: Reflect
        reflection = self._reflect(question, plan, all_evidence)
        scratchpad.add_reflection(reflection)
        
        # Phase 4: Quality assessment
        # First, get tentative answer to check for strong claims
        tentative_answer = self._generate_answer(question, all_evidence, [])
        
        has_strong = self.quality_gates.has_strong_conclusion(tentative_answer)
        measurable_checks = self.quality_gates.extract_measurable_checks_from_answer(tentative_answer)
        
        quality = self.quality_gates.evaluate(
            evidence_links=all_evidence,
            measurable_checks=measurable_checks,
            has_strong_conclusion=has_strong,
        )
        
        # Phase 5: Generate draft answer with freshness banner and citations
        draft_answer = self._generate_answer(
            question=question,
            evidence=all_evidence,
            evidence_refs=all_evidence_refs,
            quality_notes=quality.notes,
        )
        
        # v1.1: Prepend freshness banner
        freshness_banner = self._freshness.to_banner()
        draft_with_banner = f"{freshness_banner}\n\n{draft_answer}"
        
        # v1.2: Phase 6 - Reflection Self-Check Loop
        validation_report = validate_answer(
            answer=draft_with_banner,
            evidence_refs=all_evidence_refs,
            freshness_info=self._freshness,
        )
        
        # Log reflection check
        scratchpad._entries.append(scratchpad._entries[0].__class__(
            iteration=scratchpad._iteration,
            action="reflection_check",
            content=f"Validation: {validation_report.status.value}, {validation_report.passed_count}/{len(validation_report.rules)} passed",
            metadata=validation_report.to_dict(),
        ))
        
        final_answer = draft_with_banner
        repair_attempted = False
        
        # Attempt ONE repair if validation failed
        if validation_report.needs_repair:
            if self.config.verbose:
                logger.info(f"Validation failed ({validation_report.failed_count} issues), attempting repair...")
            
            repair_attempted = True
            repair_instructions = get_repair_instructions(validation_report)
            
            # Log repair attempt
            scratchpad._entries.append(scratchpad._entries[0].__class__(
                iteration=scratchpad._iteration,
                action="reflection_repair_attempt",
                content=repair_instructions,
                metadata={"failed_rules": [r.rule_name for r in validation_report.get_failed_rules()]},
            ))
            
            # Generate repaired answer
            repaired_answer = self._generate_repaired_answer(
                question=question,
                draft_answer=draft_answer,
                repair_instructions=repair_instructions,
                evidence=all_evidence,
                evidence_refs=all_evidence_refs,
            )
            
            repaired_with_banner = f"{freshness_banner}\n\n{repaired_answer}"
            
            # Re-validate
            repair_validation = validate_answer(
                answer=repaired_with_banner,
                evidence_refs=all_evidence_refs,
                freshness_info=self._freshness,
            )
            
            if repair_validation.status == ValidationStatus.PASSED:
                final_answer = repaired_with_banner
                validation_report = repair_validation
                if self.config.verbose:
                    logger.info("Repair successful!")
            else:
                # Still failing - add partial confidence banner
                partial_banner = create_partial_confidence_banner(repair_validation)
                final_answer = f"{partial_banner}\n\n{repaired_with_banner}"
                validation_report = repair_validation
                if self.config.verbose:
                    logger.warning(f"Repair incomplete, {repair_validation.failed_count} issues remain")
        
        # v1.2: Add Evidence Appendix
        evidence_appendix = generate_evidence_appendix(all_evidence_refs)
        if evidence_appendix:
            final_answer = final_answer + evidence_appendix
        
        # Re-extract checks from final answer
        measurable_checks = self.quality_gates.extract_measurable_checks_from_answer(final_answer)
        
        # Finalize log entry
        log_entry.evidence_links = all_evidence
        log_entry.measurable_checks = measurable_checks
        log_entry.final_answer = final_answer
        log_entry.confidence_level = quality.confidence_level
        log_entry.review_required = quality.review_required or validation_report.status != ValidationStatus.PASSED
        log_entry.quality_notes = quality.notes + quality.suggested_next_steps
        
        # v1.2: Add validation status to notes
        if validation_report.status != ValidationStatus.PASSED:
            log_entry.quality_notes.append(f"Reflection validation: {validation_report.status.value}")
            for rule in validation_report.get_failed_rules():
                log_entry.quality_notes.append(f"  - {rule.rule_name}: {rule.message}")
        if repair_attempted:
            log_entry.quality_notes.append("Repair attempted: yes")
        
        log_entry.duration_ms = int((time.time() - start_time) * 1000)
        
        scratchpad.add_answer(final_answer)
        
        # Save to ask log
        self._save_log_entry(log_entry)
        
        return log_entry
    
    # -------------------------------------------------------------------------
    # Phase implementations
    # -------------------------------------------------------------------------
    
    def _generate_plan(self, question: str) -> str:
        """Generate a research plan."""
        prompt = PLANNING_PROMPT.format(question=question)
        system = SYSTEM_PROMPT.format(tool_docs=self.tool_registry.get_tool_docs())
        
        return get_llm_response(prompt, system, self.config.temperature)
    
    def _select_next_tool(
        self,
        question: str,
        plan: str,
        scratchpad: Scratchpad,
        evidence: List[EvidenceLink],
    ) -> Optional[Dict[str, Any]]:
        """Select the next tool to call or decide we're done."""
        categories = sorted(set(e.category.value for e in evidence if e.category != SourceCategory.UNKNOWN))
        
        prompt = TOOL_SELECTION_PROMPT.format(
            question=question,
            plan=plan,
            scratchpad=scratchpad.format_for_context(),
            evidence_count=len(evidence),
            categories=", ".join(categories) or "none yet",
            available_tools=", ".join(self.tool_registry.list_tools()),
        )
        
        response = get_llm_response(prompt, temperature=self.config.temperature)
        
        # Check for DONE
        if "DONE" in response.upper():
            return {"done": True}
        
        # Parse JSON
        try:
            # Find JSON in response
            import re
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.debug(f"Failed to parse tool selection: {e}")
        
        return None
    
    def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Execute a tool and return result."""
        return self.tool_registry.execute(tool_name, arguments)
    
    def _reflect(
        self,
        question: str,
        plan: str,
        evidence: List[EvidenceLink],
    ) -> str:
        """Reflect on gathered evidence."""
        categories = sorted(set(e.category.value for e in evidence if e.category != SourceCategory.UNKNOWN))
        
        evidence_summary = "\n".join([
            f"- [{e.source_type}] {e.snippet}" for e in evidence[:10]
        ])
        
        prompt = REFLECTION_PROMPT.format(
            question=question,
            plan=plan,
            evidence_summary=evidence_summary or "No evidence gathered",
            categories=", ".join(categories) or "none",
        )
        
        return get_llm_response(prompt, temperature=self.config.temperature)
    
    def _generate_answer(
        self,
        question: str,
        evidence: List[EvidenceLink],
        evidence_refs: List[EvidenceRef] = None,  # v1.1
        quality_notes: List[str] = None,
    ) -> str:
        """Generate the final answer with citations."""
        evidence_refs = evidence_refs or []
        quality_notes = quality_notes or []
        
        # v1.1: Build evidence summary with grep-able citations
        evidence_lines = []
        for i, e in enumerate(evidence[:15]):
            # Find matching evidence ref for citation
            citation = ""
            if i < len(evidence_refs):
                citation = f" {evidence_refs[i].to_citation()}"
            evidence_lines.append(f"- [{e.source_type}] {e.snippet}{citation}")
        
        evidence_summary = "\n".join(evidence_lines) if evidence_lines else "No evidence gathered"
        
        # v1.1: Generate freshness banner
        freshness_banner = self._freshness.to_banner() if hasattr(self, '_freshness') else ""
        
        prompt = ANSWER_PROMPT.format(
            question=question,
            freshness_banner=freshness_banner,
            evidence_summary=evidence_summary,
            quality_notes="\n".join(quality_notes) or "No quality issues",
        )
        
        return get_llm_response(prompt, temperature=self.config.temperature)
    
    def _generate_repaired_answer(
        self,
        question: str,
        draft_answer: str,
        repair_instructions: str,
        evidence: List[EvidenceLink],
        evidence_refs: List[EvidenceRef] = None,
    ) -> str:
        """
        v1.2: Generate a repaired answer based on validation feedback.
        
        This is the ONE allowed repair iteration.
        """
        evidence_refs = evidence_refs or []
        
        # Build evidence summary with citations
        evidence_lines = []
        for i, e in enumerate(evidence[:15]):
            citation = ""
            if i < len(evidence_refs):
                citation = f" {evidence_refs[i].to_citation()}"
            evidence_lines.append(f"- [{e.source_type}] {e.snippet}{citation}")
        
        evidence_summary = "\n".join(evidence_lines) if evidence_lines else "No evidence"
        
        repair_prompt = f"""You previously generated this answer:

---
{draft_answer}
---

{repair_instructions}

Available evidence (use these citations):
{evidence_summary}

Generate a CORRECTED answer that fixes all the validation issues.
Make sure to:
1. Include all required sections (Key Takeaways, What to Watch)
2. Add [evidence: path#anchor] citations to each claim
3. Include PREDICTION lines with: entity, metric, direction, timeframe
4. Keep the same core findings, just improve the structure and citations

Corrected answer:"""
        
        return get_llm_response(repair_prompt, temperature=self.config.temperature)
    
    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------
    
    def _save_log_entry(self, entry: AskLogEntry) -> Path:
        """Save log entry to append-only ask log."""
        from briefai.ask.tools import get_experiment_path
        
        exp_path = get_experiment_path(self.experiment_id)
        ask_logs_dir = exp_path / "ask_logs"
        ask_logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = ask_logs_dir / "ask_history.jsonl"
        
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(entry.to_jsonl() + "\n")
        
        logger.info(f"Saved ask log to {log_file}")
        return log_file
    
    def _get_commit_hash(self) -> str:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"
    
    def _get_engine_tag(self) -> Optional[str]:
        """Get current engine tag if on a tagged commit."""
        try:
            result = subprocess.run(
                ["git", "describe", "--tags", "--exact-match"],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None


# =============================================================================
# WRITE PROTECTION
# =============================================================================

class WriteProtection:
    """
    Validates that ask mode doesn't write to protected paths.
    
    Protected:
    - forecast_history.jsonl (in any experiment)
    - daily_snapshot/*.json
    - run_metadata/*.json
    """
    
    PROTECTED_PATTERNS = [
        "forecast_history.jsonl",
        "daily_snapshot_",
        "run_metadata_",
    ]
    
    @classmethod
    def is_protected(cls, path: Path) -> bool:
        """Check if a path is write-protected."""
        name = path.name
        for pattern in cls.PROTECTED_PATTERNS:
            if pattern in name:
                return True
        return False
    
    @classmethod
    def validate_write(cls, path: Path) -> None:
        """Raise if attempting to write to protected path."""
        if cls.is_protected(path):
            raise PermissionError(
                f"Ask mode cannot write to protected file: {path}\n"
                f"Protected patterns: {cls.PROTECTED_PATTERNS}"
            )


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

def ask(
    question: str,
    experiment_id: str = DEFAULT_EXPERIMENT,
    verbose: bool = False,
) -> AskLogEntry:
    """
    Convenience function to run a single ask query.
    
    Usage:
        from briefai.ask import ask
        result = ask("What signals suggest AI chip demand growth?")
        print(result.final_answer)
    """
    config = EngineConfig(experiment_id=experiment_id, verbose=verbose)
    engine = AskEngine(experiment_id=experiment_id, config=config)
    return engine.ask(question)
