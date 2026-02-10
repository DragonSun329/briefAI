"""Research chatbot API endpoints."""

from typing import List, Optional
from pathlib import Path
import sys

from fastapi import APIRouter, Query
from pydantic import BaseModel

# Setup paths
_app_dir = Path(__file__).parent.parent.parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

from utils.research_chatbot import get_chatbot


router = APIRouter(prefix="/api/research", tags=["research"])


class ChatRequest(BaseModel):
    query: str
    use_web_search: bool = False
    include_history: bool = True


class CitationOut(BaseModel):
    source_id: str
    source_name: str
    title: str
    url: Optional[str]
    snippet: str
    relevance: float


class ChatResponse(BaseModel):
    response: str
    citations: List[CitationOut]
    sources_searched: int
    relevant_sources: int
    used_web_search: bool
    timestamp: str


class MessageOut(BaseModel):
    role: str
    content: str
    citations: List[CitationOut]
    timestamp: str


class SourcesSummary(BaseModel):
    date: str
    total_sources: int
    by_pipeline: dict
    top_articles: List[dict]


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest, date: str = Query(None, description="Date YYYYMMDD")):
    """Send a message to the research chatbot."""
    chatbot = get_chatbot(date)
    result = chatbot.chat(
        query=request.query,
        use_web_search=request.use_web_search,
        include_history=request.include_history
    )
    return ChatResponse(**result)


@router.get("/history", response_model=List[MessageOut])
def get_history(date: str = Query(None, description="Date YYYYMMDD")):
    """Get conversation history."""
    chatbot = get_chatbot(date)
    return chatbot.get_history()


@router.delete("/history")
def clear_history(date: str = Query(None, description="Date YYYYMMDD")):
    """Clear conversation history."""
    chatbot = get_chatbot(date)
    chatbot.clear_history()
    return {"status": "cleared"}


@router.get("/sources", response_model=SourcesSummary)
def get_sources(date: str = Query(None, description="Date YYYYMMDD")):
    """Get summary of loaded sources."""
    chatbot = get_chatbot(date)
    if not chatbot.context_loaded:
        chatbot.load_context()
    return chatbot.get_sources_summary()


@router.post("/load")
def load_sources(
    date: str = Query(None, description="Date YYYYMMDD"),
    pipelines: List[str] = Query(None, description="Pipelines to load")
):
    """Load sources from specific pipelines."""
    chatbot = get_chatbot(date)
    loaded = chatbot.load_context(pipelines)
    return {"loaded": loaded, "total": len(chatbot.sources)}
