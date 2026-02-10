"""Briefing reports API endpoints."""

import re
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel


router = APIRouter(prefix="/api/briefings", tags=["briefings"])

# Reports directory
_app_dir = Path(__file__).parent.parent.parent
_reports_dir = _app_dir / "data" / "reports"


class BriefingMeta(BaseModel):
    """Briefing metadata."""
    pipeline: str
    date: str
    filename: str


class BriefingSummary(BaseModel):
    """Parsed briefing summary."""
    pipeline: str
    date: str
    title: str
    executive_summary: str
    top_risks: List[str]
    article_count: int


class BriefingContent(BaseModel):
    """Full briefing content."""
    pipeline: str
    date: str
    title: str
    content: str
    executive_summary: str


def parse_executive_summary(content: str) -> str:
    """Extract executive summary from markdown content."""
    # Look for Executive Summary section
    patterns = [
        r'## 📊 概览 / Executive Summary\s*\n\n(.*?)(?=\n---|\n## )',
        r'## Executive Summary\s*\n\n(.*?)(?=\n---|\n## )',
        r'## 📊 概览\s*\n\n(.*?)(?=\n---|\n## )',
    ]

    for pattern in patterns:
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()

    # Fallback: return first few paragraphs
    lines = content.split('\n')
    summary_lines = []
    in_content = False

    for line in lines:
        if line.startswith('---'):
            if in_content:
                break
            in_content = True
            continue
        if in_content and line.strip():
            summary_lines.append(line)
            if len(summary_lines) >= 3:
                break

    return '\n'.join(summary_lines)


def parse_title(content: str) -> str:
    """Extract title from markdown content."""
    match = re.match(r'^# (.+)$', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Daily Briefing"


def parse_top_risks(content: str) -> List[str]:
    """Extract top risk signals from content."""
    risks = []

    # Look for risk section
    risk_match = re.search(
        r'## 🚨 顶级风险信号 / Top Risk Signals\s*\n(.*?)(?=\n## )',
        content,
        re.DOTALL
    )

    if risk_match:
        risk_section = risk_match.group(1)
        # Extract bullet points or numbered items
        items = re.findall(r'[-•]\s*(.+?)(?=\n|$)', risk_section)
        risks = [item.strip() for item in items if item.strip()][:5]

    return risks


@router.get("/available")
def get_available_briefings(date: Optional[str] = None) -> List[BriefingMeta]:
    """Get list of available briefings, optionally filtered by date."""
    briefings = []

    if not _reports_dir.exists():
        return briefings

    for file in _reports_dir.glob("*_briefing_*.md"):
        # Parse filename: {pipeline}_briefing_{date}.md
        match = re.match(r'(.+)_briefing_(\d{8})\.md', file.name)
        if match:
            pipeline = match.group(1)
            file_date = match.group(2)

            if date and file_date != date:
                continue

            briefings.append(BriefingMeta(
                pipeline=pipeline,
                date=file_date,
                filename=file.name
            ))

    # Sort by date descending, then pipeline
    briefings.sort(key=lambda b: (b.date, b.pipeline), reverse=True)
    return briefings


@router.get("/summary")
def get_briefing_summaries(date: str = Query(..., description="Date in YYYYMMDD format")) -> List[BriefingSummary]:
    """Get executive summaries for all briefings on a given date."""
    summaries = []

    if not _reports_dir.exists():
        return summaries

    for file in _reports_dir.glob(f"*_briefing_{date}.md"):
        match = re.match(r'(.+)_briefing_(\d{8})\.md', file.name)
        if not match:
            continue

        pipeline = match.group(1)
        content = file.read_text(encoding='utf-8')

        summaries.append(BriefingSummary(
            pipeline=pipeline,
            date=date,
            title=parse_title(content),
            executive_summary=parse_executive_summary(content),
            top_risks=parse_top_risks(content),
            article_count=content.count('#### ')  # Count article sections
        ))

    # Sort by pipeline name for consistent ordering
    pipeline_order = {'ai': 0, 'news': 1, 'product': 2, 'investing': 3}
    summaries.sort(key=lambda s: pipeline_order.get(s.pipeline, 99))

    return summaries


@router.get("/{pipeline}/{date}")
def get_briefing(pipeline: str, date: str) -> BriefingContent:
    """Get full briefing content for a specific pipeline and date."""
    filename = f"{pipeline}_briefing_{date}.md"
    filepath = _reports_dir / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Briefing not found: {filename}")

    content = filepath.read_text(encoding='utf-8')

    return BriefingContent(
        pipeline=pipeline,
        date=date,
        title=parse_title(content),
        content=content,
        executive_summary=parse_executive_summary(content)
    )