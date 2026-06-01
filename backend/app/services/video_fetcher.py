"""Pull transcript + metadata from YouTube and Instagram via yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
)


@dataclass
class VideoMetadata:
    video_id: str  # "A" or "B"
    url: str
    platform: str
    title: str
    creator: str
    follower_count: int | None
    views: int
    likes: int
    comments: int
    hashtags: list[str]
    upload_date: str
    duration_seconds: int
    engagement_rate: float
    transcript: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _extract_youtube_id(url: str) -> str | None:
    patterns = [
        r"(?:v=|/shorts/|youtu\.be/)([a-zA-Z0-9_-]{11})",
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def _detect_platform(url: str) -> str:
    u = url.lower()
    if "instagram.com" in u or "instagr.am" in u:
        return "instagram"
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    raise ValueError(f"Unsupported URL (need YouTube or Instagram): {url}")


def _parse_hashtags(description: str, tags: list[str] | None) -> list[str]:
    found = re.findall(r"#(\w+)", description or "")
    merged = list(dict.fromkeys([*(tags or []), *found]))
    return merged[:30]


def _fetch_ytdlp_info(url: str) -> dict[str, Any]:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _youtube_transcript(yt_id: str) -> str:
    try:
        snippets = YouTubeTranscriptApi.get_transcript(yt_id, languages=["en", "en-US", "en-GB"])
        return " ".join(s["text"].strip() for s in snippets if s.get("text"))
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable):
        pass

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(yt_id)
        for t in transcript_list:
            try:
                snippets = t.fetch()
                return " ".join(s["text"].strip() for s in snippets if s.get("text"))
            except Exception:
                continue
    except Exception:
        pass
    return ""


def _subtitle_text_from_info(info: dict[str, Any]) -> str:
    """Fallback transcript from auto-captions (Instagram / YT without API transcript)."""
    subs = info.get("subtitles") or {}
    auto = info.get("automatic_captions") or {}
    for pool in (subs, auto):
        for lang in ("en", "en-US", "en-orig"):
            tracks = pool.get(lang) or pool.get("en")
            if not tracks:
                continue
            # prefer vtt
            for fmt in tracks:
                if fmt.get("ext") in ("vtt", "srv3", "json3"):
                    url = fmt.get("url")
                    if url:
                        import httpx

                        r = httpx.get(url, timeout=30)
                        if r.status_code == 200:
                            text = r.text
                            # strip WEBVTT cues roughly
                            lines = [
                                ln.strip()
                                for ln in text.splitlines()
                                if ln.strip()
                                and not ln.startswith("WEBVTT")
                                and "-->" not in ln
                                and not ln.isdigit()
                            ]
                            return " ".join(lines)
    return ""


def compute_engagement_rate(views: int, likes: int, comments: int) -> float:
    if views <= 0:
        return 0.0
    return round(((likes + comments) / views) * 100, 4)


def fetch_video(url: str, video_id: str) -> VideoMetadata:
    platform = _detect_platform(url)
    info = _fetch_ytdlp_info(url)

    views = int(info.get("view_count") or 0)
    likes = int(info.get("like_count") or 0)
    comments = int(info.get("comment_count") or 0)
    duration = int(info.get("duration") or 0)
    upload = str(info.get("upload_date") or info.get("release_date") or "")
    if upload and len(upload) == 8:
        upload = f"{upload[:4]}-{upload[4:6]}-{upload[6:8]}"

    description = info.get("description") or ""
    tags = info.get("tags") or []
    hashtags = _parse_hashtags(description, tags)

    creator = (
        info.get("uploader")
        or info.get("channel")
        or info.get("creator")
        or info.get("uploader_id")
        or "unknown"
    )
    follower_count = info.get("channel_follower_count") or info.get("follower_count")

    transcript = ""
    if platform == "youtube":
        yt_id = _extract_youtube_id(url) or info.get("id", "")
        if yt_id:
            transcript = _youtube_transcript(yt_id)
    if not transcript:
        transcript = _subtitle_text_from_info(info)
    if not transcript and description:
        # last resort for reels with thin metadata
        transcript = description[:8000]

    engagement = compute_engagement_rate(views, likes, comments)

    return VideoMetadata(
        video_id=video_id,
        url=url,
        platform=platform,
        title=info.get("title") or "Untitled",
        creator=str(creator),
        follower_count=int(follower_count) if follower_count is not None else None,
        views=views,
        likes=likes,
        comments=comments,
        hashtags=hashtags,
        upload_date=upload,
        duration_seconds=duration,
        engagement_rate=engagement,
        transcript=transcript.strip(),
    )
