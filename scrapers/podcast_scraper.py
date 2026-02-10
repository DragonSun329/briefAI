"""
Podcast Scraper for BriefAI.

Fetches transcripts from AI-focused podcast channels on YouTube,
extracts key insights using LLM, and outputs in standard article format.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from loguru import logger

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False
    logger.warning("yt-dlp not installed - podcast scraper will be limited")

from utils.youtube_transcript import fetch_transcript, TranscriptResult

# Optional LLM imports
try:
    from utils.provider_switcher import ProviderSwitcher
    LLM_AVAILABLE = True
except ImportError:
    try:
        from utils.llm_provider import create_provider
        LLM_AVAILABLE = True
    except ImportError:
        LLM_AVAILABLE = False


class LLMClientWrapper:
    """Wrapper to adapt ProviderSwitcher to simple generate() interface with fallback."""

    def __init__(self, switcher: "ProviderSwitcher"):
        self.switcher = switcher

    def generate(self, prompt: str) -> str:
        """Generate response from prompt with automatic fallback."""
        system_prompt = """You are an expert AI analyst who extracts key insights from podcast transcripts.
Your task is to identify the most important information for an executive audience interested in AI/tech trends.
Always respond in valid JSON format."""

        # Use switcher's query method which handles automatic fallback
        response = self.switcher.query(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=2000,
            temperature=0.3
        )
        return response


# AI-focused podcast channels
PODCAST_CHANNELS = {
    "all-in": {
        "channel_id": "UCESLZhusAkFfsNsApnjF_Cg",
        "name": "All-In Podcast",
        "credibility": 8,
        "focus": ["investing", "tech", "AI", "startups"],
    },
    "lex-fridman": {
        "channel_id": "UCSHZKyawb77ixDdsGog4iWA",
        "name": "Lex Fridman Podcast",
        "credibility": 9,
        "focus": ["AI", "research", "philosophy", "technology"],
    },
    "no-priors": {
        "channel_id": "UCSI7h9hydQ40K5MJHnCrQvw",
        "name": "No Priors",
        "credibility": 9,
        "focus": ["AI", "startups", "investing", "founders"],
    },
    "dwarkesh": {
        "channel_id": "UCXl4i9dYBrFOabk0xGmbkRA",
        "name": "Dwarkesh Podcast",
        "credibility": 8,
        "focus": ["AI", "research", "technology", "history"],
    },
    "latent-space": {
        "channel_id": "UCvi5jNRoRVm436TVAXet1kQ",
        "name": "Latent Space",
        "credibility": 9,
        "focus": ["AI", "engineering", "LLMs", "infrastructure"],
    },
    "lenny-podcast": {
        "channel_id": "UC6t1O76G0jYXOAoYCm153dA",
        "name": "Lenny's Podcast",
        "credibility": 8,
        "focus": ["product", "growth", "startups", "leadership"],
    },
    "gradient-dissent": {
        "channel_id": "UC9ieyMPLacBbuTOsR0alldA",
        "name": "Gradient Dissent",
        "credibility": 8,
        "focus": ["ML", "AI", "research", "tools"],
    },
    "practical-ai": {
        "channel_id": "UCIRYeDQviNEmpYrJpMaHBiw",
        "name": "Practical AI",
        "credibility": 7,
        "focus": ["AI", "ML", "applications", "tutorials"],
    },
}


@dataclass
class PodcastEpisode:
    """A podcast episode with metadata."""
    video_id: str
    title: str
    channel: str
    channel_name: str
    published_at: str
    duration_sec: int
    url: str
    thumbnail: str
    description: str


@dataclass
class PodcastArticle:
    """Processed podcast content in article format."""
    title: str
    url: str
    source: str
    date: str
    content: str  # Full transcript or summary
    summary: str  # LLM-generated summary
    entities: List[str]  # Extracted entities
    topics: List[str]
    credibility_score: int
    podcast_channel: str
    duration_min: int
    is_transcript: bool


def get_recent_videos(
    channel_id: str,
    max_results: int = 5,
    days_back: int = 7
) -> List[PodcastEpisode]:
    """
    Fetch recent videos from a YouTube channel.

    Args:
        channel_id: YouTube channel ID
        max_results: Maximum videos to fetch
        days_back: Only get videos from last N days

    Returns:
        List of PodcastEpisode objects
    """
    if not YTDLP_AVAILABLE:
        logger.error("yt-dlp required for fetching channel videos")
        return []

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
        'playlistend': max_results * 2,  # Fetch more to filter by date
    }

    channel_url = f"https://www.youtube.com/channel/{channel_id}/videos"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(channel_url, download=False)

        if not info or 'entries' not in info:
            return []

        cutoff_date = datetime.now() - timedelta(days=days_back)
        episodes = []

        for entry in info['entries']:
            if not entry:
                continue

            # Get full video info for duration
            video_id = entry.get('id')
            if not video_id:
                continue

            # Parse upload date if available
            upload_date = entry.get('upload_date')
            if upload_date:
                try:
                    video_date = datetime.strptime(upload_date, '%Y%m%d')
                    if video_date < cutoff_date:
                        continue
                except ValueError:
                    pass

            episodes.append(PodcastEpisode(
                video_id=video_id,
                title=entry.get('title', ''),
                channel=channel_id,
                channel_name=info.get('channel', ''),
                published_at=upload_date or '',
                duration_sec=entry.get('duration', 0) or 0,
                url=f"https://www.youtube.com/watch?v={video_id}",
                thumbnail=entry.get('thumbnail', ''),
                description=entry.get('description', '')[:500] if entry.get('description') else '',
            ))

            if len(episodes) >= max_results:
                break

        return episodes

    except Exception as e:
        logger.error(f"Failed to fetch videos from channel {channel_id}: {e}")
        return []


def extract_insights_from_transcript(
    transcript: TranscriptResult,
    episode: PodcastEpisode,
    llm_client=None
) -> Optional[PodcastArticle]:
    """
    Extract key insights from a podcast transcript using LLM.

    Args:
        transcript: TranscriptResult from youtube_transcript
        episode: PodcastEpisode metadata
        llm_client: Optional LLM client for summarization

    Returns:
        PodcastArticle with extracted insights
    """
    channel_config = None
    for ch_id, config in PODCAST_CHANNELS.items():
        if config['channel_id'] == episode.channel:
            channel_config = config
            break

    credibility = channel_config['credibility'] if channel_config else 7

    # If no LLM client, return raw transcript
    if not llm_client:
        return PodcastArticle(
            title=episode.title,
            url=episode.url,
            source=f"Podcast: {episode.channel_name}",
            date=episode.published_at,
            content=transcript.full_text[:10000],  # Truncate for storage
            summary=episode.description or transcript.full_text[:500],
            entities=[],
            topics=channel_config['focus'] if channel_config else [],
            credibility_score=credibility,
            podcast_channel=episode.channel_name,
            duration_min=episode.duration_sec // 60,
            is_transcript=True,
        )

    # Use LLM to extract insights
    try:
        prompt = f"""Analyze this podcast transcript and extract key insights.

Podcast: {episode.title}
Channel: {episode.channel_name}
Duration: {episode.duration_sec // 60} minutes

Transcript (first 8000 chars):
{transcript.full_text[:8000]}

Please provide:
1. A 2-3 sentence executive summary
2. Key entities mentioned (companies, people, products)
3. Main topics discussed
4. Notable claims or predictions

Format as JSON:
{{
    "summary": "...",
    "entities": ["entity1", "entity2"],
    "topics": ["topic1", "topic2"],
    "key_claims": ["claim1", "claim2"]
}}"""

        response = llm_client.generate(prompt)

        # Parse LLM response
        try:
            # Find JSON in response
            json_match = response[response.find('{'):response.rfind('}')+1]
            parsed = json.loads(json_match)

            return PodcastArticle(
                title=episode.title,
                url=episode.url,
                source=f"Podcast: {episode.channel_name}",
                date=episode.published_at,
                content=transcript.full_text[:10000],
                summary=parsed.get('summary', episode.description or ''),
                entities=parsed.get('entities', []),
                topics=parsed.get('topics', channel_config['focus'] if channel_config else []),
                credibility_score=credibility,
                podcast_channel=episode.channel_name,
                duration_min=episode.duration_sec // 60,
                is_transcript=True,
            )
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM response for {episode.video_id}")

    except Exception as e:
        logger.error(f"LLM extraction failed for {episode.video_id}: {e}")

    # Fallback to basic extraction
    return PodcastArticle(
        title=episode.title,
        url=episode.url,
        source=f"Podcast: {episode.channel_name}",
        date=episode.published_at,
        content=transcript.full_text[:10000],
        summary=episode.description or transcript.full_text[:500],
        entities=[],
        topics=channel_config['focus'] if channel_config else [],
        credibility_score=credibility,
        podcast_channel=episode.channel_name,
        duration_min=episode.duration_sec // 60,
        is_transcript=True,
    )


def scrape_podcasts(
    channels: List[str] = None,
    max_per_channel: int = 3,
    days_back: int = 7,
    llm_client=None,
    output_dir: Path = None
) -> List[Dict[str, Any]]:
    """
    Scrape recent podcast episodes and extract transcripts.

    Args:
        channels: List of channel keys (defaults to all)
        max_per_channel: Max episodes per channel
        days_back: Only get episodes from last N days
        llm_client: Optional LLM client for summarization
        output_dir: Output directory for results

    Returns:
        List of article dicts
    """
    if channels is None:
        channels = list(PODCAST_CHANNELS.keys())

    if output_dir is None:
        output_dir = Path(__file__).parent.parent / "data" / "cache"

    output_dir.mkdir(parents=True, exist_ok=True)

    all_articles = []

    for channel_key in channels:
        if channel_key not in PODCAST_CHANNELS:
            logger.warning(f"Unknown channel: {channel_key}")
            continue

        config = PODCAST_CHANNELS[channel_key]
        logger.info(f"Scraping {config['name']}...")

        # Get recent videos
        episodes = get_recent_videos(
            config['channel_id'],
            max_results=max_per_channel,
            days_back=days_back
        )

        logger.info(f"Found {len(episodes)} recent episodes from {config['name']}")

        for episode in episodes:
            # Skip very short videos (likely clips)
            if episode.duration_sec < 600:  # < 10 min
                logger.debug(f"Skipping short video: {episode.title}")
                continue

            # Fetch transcript
            logger.info(f"Fetching transcript for: {episode.title[:50]}...")
            transcript = fetch_transcript(episode.video_id)

            if not transcript:
                logger.warning(f"No transcript for: {episode.title}")
                continue

            # Extract insights
            article = extract_insights_from_transcript(
                transcript, episode, llm_client
            )

            if article:
                all_articles.append(asdict(article))
                logger.info(f"Processed: {episode.title[:50]}")

    # Save results
    if all_articles:
        output_file = output_dir / f"podcasts_{datetime.now().strftime('%Y%m%d')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_articles, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(all_articles)} podcast articles to {output_file}")

    return all_articles


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape AI podcasts")
    parser.add_argument(
        "--channels",
        nargs="+",
        default=None,
        help="Channels to scrape (default: all)"
    )
    parser.add_argument(
        "--max-per-channel",
        type=int,
        default=3,
        help="Max episodes per channel"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=7,
        help="Days to look back"
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Use LLM to analyze transcripts and extract insights"
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="openrouter",
        choices=["openrouter", "kimi"],
        help="LLM provider to use (default: openrouter)"
    )

    args = parser.parse_args()

    print(f"Available channels: {list(PODCAST_CHANNELS.keys())}")
    print()

    # Initialize LLM client if analysis requested
    llm_client = None
    if args.analyze:
        if not LLM_AVAILABLE:
            print("ERROR: LLM provider not available. Install required dependencies.")
            sys.exit(1)
        try:
            # Use ProviderSwitcher for automatic fallback across free models
            switcher = ProviderSwitcher()
            llm_client = LLMClientWrapper(switcher)
            print("LLM analysis enabled with OpenRouter free model fallback")
            print(f"Fallback order: kimi → tier1_quality → tier2_balanced → tier3_fast")
        except Exception as e:
            print(f"ERROR: Failed to initialize LLM provider: {e}")
            sys.exit(1)

    articles = scrape_podcasts(
        channels=args.channels,
        max_per_channel=args.max_per_channel,
        days_back=args.days_back,
        llm_client=llm_client,
    )

    print(f"\nScraped {len(articles)} podcast episodes")
    for article in articles:
        title = article['title'][:55].encode('ascii', 'replace').decode('ascii')
        print(f"  - {title}... ({article['duration_min']}min)")
        if args.analyze and article.get('summary'):
            # Show first 150 chars of summary
            summary = article['summary'][:150].encode('ascii', 'replace').decode('ascii')
            print(f"    Summary: {summary}...")
            if article.get('entities'):
                print(f"    Entities: {', '.join(article['entities'][:5])}")