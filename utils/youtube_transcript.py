"""
YouTube Transcript Fetcher for BriefAI.

Extracts transcripts from YouTube videos using youtube-transcript-api
with yt-dlp as fallback. Adapted from pod.ai transcript_api.
"""

import re
import asyncio
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, Tuple

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable
    )
    TRANSCRIPT_API_AVAILABLE = True
except ImportError:
    TRANSCRIPT_API_AVAILABLE = False

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

from loguru import logger


# Video ID validation pattern (11 chars, alphanumeric + -_)
VIDEO_ID_PATTERN = re.compile(r'^[a-zA-Z0-9_-]{11}$')
YTDLP_TIMEOUT = 30


@dataclass
class TranscriptSegment:
    """A single transcript segment with timing."""
    start_sec: float
    end_sec: float
    text: str


@dataclass
class TranscriptResult:
    """Complete transcript result."""
    video_id: str
    language: str
    segments: List[TranscriptSegment]
    strategy: str  # "youtube-transcript-api" or "yt-dlp"
    is_auto_generated: bool
    full_text: str  # Concatenated text for LLM processing


def validate_video_id(video_id: str) -> bool:
    """Validate YouTube video ID format."""
    return bool(VIDEO_ID_PATTERN.match(video_id))


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract video ID from URL or return ID if already valid."""
    if validate_video_id(url_or_id):
        return url_or_id

    # Try to extract from various URL formats
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)

    return None


def clean_text(text: str) -> str:
    """Clean transcript text."""
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    text = re.sub(r'\[.*?\]', '', text)  # Remove [Music], [Applause], etc.
    text = re.sub(r'\(.*?\)', '', text)  # Remove (inaudible), etc.
    return text.strip()


def _fetch_via_youtube_transcript_api(
    video_id: str,
    preferred_lang: str = "en"
) -> Tuple[List[TranscriptSegment], str, bool]:
    """
    Fetch transcript using youtube-transcript-api.

    Returns:
        (segments, language, is_auto_generated)
    """
    if not TRANSCRIPT_API_AVAILABLE:
        raise ImportError("youtube-transcript-api not installed")

    transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

    # Language fallback
    languages = [preferred_lang, 'en', 'en-US', 'en-GB']

    # Try manual captions first
    try:
        transcript_data = transcript_list.find_manually_created_transcript(languages)
        is_auto = False
    except NoTranscriptFound:
        transcript_data = transcript_list.find_generated_transcript(languages)
        is_auto = True

    transcript = transcript_data.fetch()

    segments = []
    for entry in transcript:
        text = clean_text(entry['text'])
        if text:
            segments.append(TranscriptSegment(
                start_sec=round(entry['start'], 2),
                end_sec=round(entry['start'] + entry['duration'], 2),
                text=text
            ))

    return segments, transcript_data.language_code, is_auto


def _fetch_via_ytdlp(
    video_id: str,
    preferred_lang: str = "en"
) -> Tuple[List[TranscriptSegment], str, bool]:
    """
    Fetch transcript using yt-dlp.

    Returns:
        (segments, language, is_auto_generated)
    """
    if not YTDLP_AVAILABLE:
        raise ImportError("yt-dlp not installed")

    import requests

    language_priority = [preferred_lang, 'en', 'en-US', 'en-GB']

    ydl_opts = {
        'skip_download': True,
        'writesubtitles': True,
        'writeautomaticsub': True,
        'subtitleslangs': language_priority,
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': YTDLP_TIMEOUT,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(
            f"https://www.youtube.com/watch?v={video_id}",
            download=False
        )

    subtitles = info.get('subtitles', {})
    automatic_captions = info.get('automatic_captions', {})

    subtitle_url = None
    language_code = None
    is_auto = False

    # Try manual captions first
    for lang in language_priority:
        if lang in subtitles:
            for format_data in subtitles[lang]:
                if format_data.get('ext') == 'json3':
                    subtitle_url = format_data['url']
                    language_code = lang
                    is_auto = False
                    break
            if subtitle_url:
                break

    # Fall back to auto-generated
    if not subtitle_url:
        for lang in language_priority:
            if lang in automatic_captions:
                for format_data in automatic_captions[lang]:
                    if format_data.get('ext') == 'json3':
                        subtitle_url = format_data['url']
                        language_code = lang
                        is_auto = True
                        break
                if subtitle_url:
                    break

    if not subtitle_url:
        raise ValueError(f"No captions available for video {video_id}")

    # Download and parse
    resp = requests.get(subtitle_url, timeout=YTDLP_TIMEOUT)
    resp.raise_for_status()
    subtitle_data = resp.json()

    # Parse JSON3 format
    segments = []
    for event in subtitle_data.get('events', []):
        if 'tStartMs' not in event:
            continue

        start_ms = event.get('tStartMs', 0)
        duration_ms = event.get('dDurationMs', 0)

        text_parts = []
        for seg in event.get('segs', []):
            if 'utf8' in seg:
                text_parts.append(seg['utf8'])

        text = clean_text(''.join(text_parts))
        if text and duration_ms > 0:
            segments.append(TranscriptSegment(
                start_sec=round(start_ms / 1000.0, 2),
                end_sec=round((start_ms + duration_ms) / 1000.0, 2),
                text=text
            ))

    return segments, language_code, is_auto


def fetch_transcript(
    video_id_or_url: str,
    preferred_lang: str = "en"
) -> Optional[TranscriptResult]:
    """
    Fetch transcript for a YouTube video.

    Args:
        video_id_or_url: YouTube video ID or URL
        preferred_lang: Preferred language code

    Returns:
        TranscriptResult or None if unavailable
    """
    video_id = extract_video_id(video_id_or_url)
    if not video_id:
        logger.warning(f"Invalid video ID/URL: {video_id_or_url}")
        return None

    # Try youtube-transcript-api first
    try:
        segments, language, is_auto = _fetch_via_youtube_transcript_api(
            video_id, preferred_lang
        )
        strategy = "youtube-transcript-api"
        logger.debug(f"Got transcript via youtube-transcript-api for {video_id}")
    except Exception as e:
        logger.debug(f"youtube-transcript-api failed for {video_id}: {e}")

        # Try yt-dlp fallback
        try:
            segments, language, is_auto = _fetch_via_ytdlp(video_id, preferred_lang)
            strategy = "yt-dlp"
            logger.debug(f"Got transcript via yt-dlp for {video_id}")
        except Exception as e2:
            logger.warning(f"All transcript methods failed for {video_id}: {e2}")
            return None

    if not segments:
        return None

    # Concatenate full text
    full_text = " ".join(seg.text for seg in segments)

    return TranscriptResult(
        video_id=video_id,
        language=language,
        segments=segments,
        strategy=strategy,
        is_auto_generated=is_auto,
        full_text=full_text
    )


async def fetch_transcript_async(
    video_id_or_url: str,
    preferred_lang: str = "en"
) -> Optional[TranscriptResult]:
    """Async wrapper for fetch_transcript."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        lambda: fetch_transcript(video_id_or_url, preferred_lang)
    )


if __name__ == "__main__":
    # Test
    result = fetch_transcript("dQw4w9WgXcQ")
    if result:
        print(f"Video: {result.video_id}")
        print(f"Language: {result.language}")
        print(f"Strategy: {result.strategy}")
        print(f"Auto-generated: {result.is_auto_generated}")
        print(f"Segments: {len(result.segments)}")
        print(f"First 200 chars: {result.full_text[:200]}...")
    else:
        print("Failed to fetch transcript")