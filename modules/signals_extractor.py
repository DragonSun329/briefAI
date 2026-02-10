from __future__ import annotations

from typing import List, Optional
from utils.schemas import Document, RiskSignal
from utils.llm_client_enhanced import LLMClient
from utils.scoring_engine import ScoringEngine
import uuid


class SignalsExtractor:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm = llm_client or LLMClient()
        self.scorer = ScoringEngine()

    def extract_from_documents(self, documents: List[Document]) -> List[RiskSignal]:
        signals: List[RiskSignal] = []
        for doc in documents:
            try:
                # Use chat method to summarize content
                response = self.llm.chat(
                    system_prompt="You are a helpful assistant that summarizes text concisely.",
                    user_message=f"Summarize the following in 2-3 sentences:\n\n{doc.content[:2000]}",
                    max_tokens=256
                )
                summary = response if response else ""
                # Placeholder heuristic scoring; to be replaced by structured LLM extraction
                impact, relevance, recency, credibility = 6.0, 6.0, 6.0, (doc.credibility or 6.0)
                scores = {
                    'market_impact': impact,
                    'competitive_impact': relevance,
                    'strategic_relevance': recency,
                    'operational_relevance': credibility,
                    'credibility': credibility
                }
                risk_score = self.scorer.calculate_weighted_score(scores)
                signals.append(
                    RiskSignal(
                        id=str(uuid.uuid4()),
                        document_id=doc.id,
                        title=summary.split("\n")[0][:120] if summary else "Detected signal",
                        signal_type=None,
                        evidence_span=None,
                        impact=impact,
                        relevance=relevance,
                        recency=recency,
                        credibility=credibility,
                        risk_score=risk_score,
                        entities=[],
                        domains=[],
                        source=doc.metadata.get("source"),
                        published_date=doc.published_at,
                        summary=summary,
                    )
                )
            except Exception:
                continue
        return signals



