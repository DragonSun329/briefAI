"""
Belief Updater v1.0 - Bayesian-Style Hypothesis Belief Updates.

Part of briefAI Gravity Engine v2.8: Evidence-Based Belief Updates.

This module maintains and updates belief states for hypotheses
based on accumulated evidence. Each hypothesis has a persistent
posterior confidence that evolves as new evidence arrives.

Key Concepts:
- Prior Confidence: Original hypothesis confidence
- Posterior Confidence: Updated belief after evidence
- Evidence Delta: Weighted average of accumulated evidence
- Safety Caps: Maximum confidence based on hypothesis quality

Update Rule:
    evidence_delta = Σ(evidence_score × weight) / Σ(weight)
    posterior = prior + learning_rate × evidence_delta
    posterior = clip(posterior, min_conf, max_conf)
    posterior = min(posterior, safety_cap)

No LLM calls. Deterministic updates.
"""

import json
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from loguru import logger

from utils.evidence_engine import (
    EvidenceResult,
    EvidenceDirection,
    EvidenceWeights,
)


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data" / "predictions"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class BeliefState:
    """
    Persistent belief state for a hypothesis.
    
    Tracks prior, posterior, and evidence accumulation.
    """
    hypothesis_id: str
    meta_id: str
    
    # Confidence values
    prior_confidence: float
    posterior_confidence: float
    
    # Evidence accumulation
    evidence_sum: float = 0.0
    weight_sum: float = 0.0
    support_count: int = 0
    contradict_count: int = 0
    neutral_count: int = 0
    
    # Quality flags
    review_required: bool = False
    weakly_validated: bool = False
    
    # Timestamps
    created_at: str = ""
    updated_at: str = ""
    
    # History (list of daily snapshots)
    history: List[Dict[str, Any]] = field(default_factory=list)
    
    def __post_init__(self):
        now = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'BeliefState':
        return cls(**d)
    
    @property
    def confidence_change(self) -> float:
        """Change in confidence from prior to posterior."""
        return self.posterior_confidence - self.prior_confidence
    
    @property
    def evidence_count(self) -> int:
        """Total evidence observations."""
        return self.support_count + self.contradict_count + self.neutral_count
    
    @property
    def support_ratio(self) -> Optional[float]:
        """Ratio of supporting to contradicting evidence."""
        if self.support_count + self.contradict_count == 0:
            return None
        return self.support_count / (self.support_count + self.contradict_count)
    
    def add_history_snapshot(self):
        """Add current state to history."""
        self.history.append({
            'date': datetime.now().strftime('%Y-%m-%d'),
            'posterior': round(self.posterior_confidence, 4),
            'evidence_count': self.evidence_count,
            'support_count': self.support_count,
            'contradict_count': self.contradict_count,
        })
    
    def get_trajectory(self) -> List[float]:
        """Get confidence trajectory from history."""
        return [h['posterior'] for h in self.history]


# =============================================================================
# BELIEF STORE
# =============================================================================

class BeliefStore:
    """
    Persists belief states to JSON files.
    
    Uses:
    - beliefs.json: Current belief states for all hypotheses
    - belief_history.jsonl: Append-only history of all updates
    """
    
    def __init__(self, data_dir: Path = None):
        """Initialize belief store."""
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.beliefs_file = self.data_dir / "beliefs.json"
        self.history_file = self.data_dir / "belief_history.jsonl"
        
        logger.debug(f"BeliefStore initialized at {self.data_dir}")
    
    def load_beliefs(self) -> Dict[str, BeliefState]:
        """Load all belief states."""
        if not self.beliefs_file.exists():
            return {}
        
        try:
            with open(self.beliefs_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            beliefs = {}
            for hyp_id, state_dict in data.items():
                beliefs[hyp_id] = BeliefState.from_dict(state_dict)
            
            return beliefs
            
        except Exception as e:
            logger.warning(f"Failed to load beliefs: {e}")
            return {}
    
    def save_beliefs(self, beliefs: Dict[str, BeliefState]):
        """Save all belief states."""
        data = {hyp_id: state.to_dict() for hyp_id, state in beliefs.items()}
        
        with open(self.beliefs_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.debug(f"Saved {len(beliefs)} belief states")
    
    def get_belief(self, hypothesis_id: str) -> Optional[BeliefState]:
        """Get belief state for a specific hypothesis."""
        beliefs = self.load_beliefs()
        return beliefs.get(hypothesis_id)
    
    def update_belief(self, state: BeliefState):
        """Update or create a belief state."""
        beliefs = self.load_beliefs()
        beliefs[state.hypothesis_id] = state
        self.save_beliefs(beliefs)
    
    def append_history(self, state: BeliefState):
        """Append belief update to history log."""
        entry = {
            'hypothesis_id': state.hypothesis_id,
            'meta_id': state.meta_id,
            'date': datetime.now().strftime('%Y-%m-%d'),
            'timestamp': datetime.now().isoformat(),
            'prior': state.prior_confidence,
            'posterior': state.posterior_confidence,
            'evidence_count': state.evidence_count,
            'support_count': state.support_count,
            'contradict_count': state.contradict_count,
        }
        
        with open(self.history_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    
    def load_history(self, hypothesis_id: str = None) -> List[Dict[str, Any]]:
        """Load belief history, optionally filtered by hypothesis."""
        if not self.history_file.exists():
            return []
        
        history = []
        with open(self.history_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if hypothesis_id is None or entry.get('hypothesis_id') == hypothesis_id:
                            history.append(entry)
                    except Exception:
                        pass
        
        return history


# =============================================================================
# BELIEF UPDATER
# =============================================================================

class BeliefUpdater:
    """
    Updates hypothesis beliefs based on accumulated evidence.
    
    Implements the belief update rule:
        evidence_delta = Σ(evidence_score × weight) / Σ(weight)
        posterior = prior + learning_rate × evidence_delta
    """
    
    def __init__(
        self,
        data_dir: Path = None,
        weights: EvidenceWeights = None,
    ):
        """
        Initialize belief updater.
        
        Args:
            data_dir: Data directory for belief storage
            weights: Evidence weights configuration
        """
        if data_dir is None:
            data_dir = DEFAULT_DATA_DIR
        
        if weights is None:
            weights = EvidenceWeights()
        
        self.store = BeliefStore(data_dir)
        self.weights = weights
        
        logger.debug("BeliefUpdater initialized")
    
    def get_or_create_belief(
        self,
        hypothesis_id: str,
        meta_id: str,
        prior_confidence: float,
        review_required: bool = False,
        weakly_validated: bool = False,
    ) -> BeliefState:
        """
        Get existing belief state or create new one.
        
        Args:
            hypothesis_id: Hypothesis ID
            meta_id: Meta-signal ID
            prior_confidence: Original confidence (used if creating new)
            review_required: Whether hypothesis requires review
            weakly_validated: Whether hypothesis is weakly validated
        
        Returns:
            BeliefState for the hypothesis
        """
        existing = self.store.get_belief(hypothesis_id)
        
        if existing:
            return existing
        
        # Create new belief state
        return BeliefState(
            hypothesis_id=hypothesis_id,
            meta_id=meta_id,
            prior_confidence=prior_confidence,
            posterior_confidence=prior_confidence,
            review_required=review_required,
            weakly_validated=weakly_validated,
        )
    
    def update_belief(
        self,
        state: BeliefState,
        evidence: List[EvidenceResult],
    ) -> BeliefState:
        """
        Update belief state with new evidence.
        
        Args:
            state: Current belief state
            evidence: List of new evidence results
        
        Returns:
            Updated belief state
        """
        if not evidence:
            return state
        
        # Filter to informative evidence only
        informative = [e for e in evidence if e.is_informative]
        
        if not informative:
            # Update counts for neutral evidence
            neutral_count = sum(
                1 for e in evidence
                if e.direction == EvidenceDirection.NEUTRAL.value
            )
            state.neutral_count += neutral_count
            state.updated_at = datetime.now().isoformat()
            return state
        
        # Accumulate weighted evidence
        for e in informative:
            weighted_score = e.evidence_score * e.weight
            state.evidence_sum += weighted_score
            state.weight_sum += e.weight
            
            if e.direction == EvidenceDirection.SUPPORT.value:
                state.support_count += 1
            elif e.direction == EvidenceDirection.CONTRADICT.value:
                state.contradict_count += 1
        
        # Count neutral evidence
        neutral_count = sum(
            1 for e in evidence
            if e.direction == EvidenceDirection.NEUTRAL.value
        )
        state.neutral_count += neutral_count
        
        # Calculate evidence delta
        if state.weight_sum > 0:
            evidence_delta = state.evidence_sum / state.weight_sum
        else:
            evidence_delta = 0.0
        
        # Update posterior
        learning_rate = self.weights.learning_rate
        min_conf = self.weights.update_params.get('min_confidence', 0.05)
        max_conf = self.weights.update_params.get('max_confidence', 0.98)
        
        new_posterior = state.prior_confidence + learning_rate * evidence_delta
        
        # Clip to valid range
        new_posterior = max(min_conf, min(max_conf, new_posterior))
        
        # Apply safety caps
        if state.review_required:
            cap = self.weights.get_safety_cap('review_required')
            new_posterior = min(new_posterior, cap)
        elif state.weakly_validated:
            cap = self.weights.get_safety_cap('weakly_validated')
            new_posterior = min(new_posterior, cap)
        
        state.posterior_confidence = round(new_posterior, 4)
        state.updated_at = datetime.now().isoformat()
        
        return state
    
    def process_evidence_batch(
        self,
        evidence_results: List[EvidenceResult],
        hypothesis_priors: Dict[str, Dict[str, Any]] = None,
    ) -> Dict[str, BeliefState]:
        """
        Process a batch of evidence results and update beliefs.
        
        Args:
            evidence_results: List of evidence results to process
            hypothesis_priors: Optional dict of hypothesis metadata
                              {hyp_id: {prior_confidence, meta_id, review_required, ...}}
        
        Returns:
            Dict of updated belief states by hypothesis ID
        """
        if hypothesis_priors is None:
            hypothesis_priors = {}
        
        # Group evidence by hypothesis
        evidence_by_hyp: Dict[str, List[EvidenceResult]] = {}
        for e in evidence_results:
            if e.hypothesis_id not in evidence_by_hyp:
                evidence_by_hyp[e.hypothesis_id] = []
            evidence_by_hyp[e.hypothesis_id].append(e)
        
        # Update each hypothesis
        updated_beliefs = {}
        
        for hyp_id, evidence_list in evidence_by_hyp.items():
            # Get prior info
            prior_info = hypothesis_priors.get(hyp_id, {})
            prior_conf = prior_info.get('prior_confidence', 0.5)
            meta_id = prior_info.get('meta_id', evidence_list[0].meta_id)
            review_required = prior_info.get('review_required', False)
            weakly_validated = prior_info.get('weakly_validated', False)
            
            # Get or create belief state
            state = self.get_or_create_belief(
                hypothesis_id=hyp_id,
                meta_id=meta_id,
                prior_confidence=prior_conf,
                review_required=review_required,
                weakly_validated=weakly_validated,
            )
            
            # Update with evidence
            state = self.update_belief(state, evidence_list)
            
            # Add history snapshot
            state.add_history_snapshot()
            
            # Persist
            self.store.update_belief(state)
            self.store.append_history(state)
            
            updated_beliefs[hyp_id] = state
            
            logger.info(
                f"Updated belief {hyp_id}: "
                f"{state.prior_confidence:.2f} → {state.posterior_confidence:.2f} "
                f"({state.confidence_change:+.2f})"
            )
        
        return updated_beliefs
    
    def get_belief_summary(self) -> Dict[str, Any]:
        """Get summary of all belief states."""
        beliefs = self.store.load_beliefs()
        
        if not beliefs:
            return {
                'total_hypotheses': 0,
                'average_posterior': None,
                'strengthened_count': 0,
                'weakened_count': 0,
            }
        
        posteriors = [b.posterior_confidence for b in beliefs.values()]
        changes = [b.confidence_change for b in beliefs.values()]
        
        return {
            'total_hypotheses': len(beliefs),
            'average_posterior': round(sum(posteriors) / len(posteriors), 4),
            'min_posterior': round(min(posteriors), 4),
            'max_posterior': round(max(posteriors), 4),
            'strengthened_count': sum(1 for c in changes if c > 0),
            'weakened_count': sum(1 for c in changes if c < 0),
            'unchanged_count': sum(1 for c in changes if c == 0),
        }


# =============================================================================
# TESTS
# =============================================================================

def _test_belief_state():
    """Test BeliefState dataclass."""
    state = BeliefState(
        hypothesis_id='hyp_001',
        meta_id='meta_001',
        prior_confidence=0.65,
        posterior_confidence=0.65,
    )
    
    assert state.confidence_change == 0.0
    assert state.evidence_count == 0
    assert state.support_ratio is None
    
    # Update counts
    state.support_count = 3
    state.contradict_count = 1
    state.posterior_confidence = 0.72
    
    assert state.confidence_change == 0.07
    assert state.evidence_count == 4
    assert state.support_ratio == 0.75
    
    print("[PASS] _test_belief_state")


def _test_belief_update():
    """Test belief update calculation."""
    updater = BeliefUpdater()
    
    state = BeliefState(
        hypothesis_id='hyp_001',
        meta_id='meta_001',
        prior_confidence=0.60,
        posterior_confidence=0.60,
    )
    
    # Create supporting evidence
    evidence = [
        EvidenceResult(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            direction=EvidenceDirection.SUPPORT.value,
            evidence_score=0.8,
            effect_size=0.25,
            weight=0.9,
        ),
    ]
    
    updated = updater.update_belief(state, evidence)
    
    # Should have increased
    assert updated.posterior_confidence > updated.prior_confidence
    assert updated.support_count == 1
    assert updated.contradict_count == 0
    
    print("[PASS] _test_belief_update")


def _test_safety_caps():
    """Test safety caps are applied."""
    updater = BeliefUpdater()
    
    # Hypothesis requiring review
    state = BeliefState(
        hypothesis_id='hyp_001',
        meta_id='meta_001',
        prior_confidence=0.55,
        posterior_confidence=0.55,
        review_required=True,
    )
    
    # Strong supporting evidence
    evidence = [
        EvidenceResult(
            prediction_id='pred_001',
            hypothesis_id='hyp_001',
            meta_id='meta_001',
            entity='nvidia',
            canonical_metric='filing_mentions',
            category='financial',
            expected_direction='up',
            direction=EvidenceDirection.SUPPORT.value,
            evidence_score=1.0,
            effect_size=0.5,
            weight=1.0,
        ),
    ]
    
    updated = updater.update_belief(state, evidence)
    
    # Should be capped at 0.60 for review_required
    assert updated.posterior_confidence <= 0.60
    
    print("[PASS] _test_safety_caps")


def run_tests():
    """Run all belief updater tests."""
    print("\n=== BELIEF UPDATER TESTS ===\n")
    
    _test_belief_state()
    _test_belief_update()
    _test_safety_caps()
    
    print("\n=== ALL TESTS PASSED ===")


if __name__ == "__main__":
    run_tests()
