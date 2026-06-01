"""Pull transcript + metadata from YouTube and Instagram via yt-dlp."""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi

from app.config import settings
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
    hook_opening: str  # first ~5 seconds for hook comparison queries
    thumbnail_url: str | None

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
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }
    if settings.ytdlp_cookies_file:
        opts["cookiefile"] = settings.ytdlp_cookies_file
    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False)


def _pick_views(info: dict[str, Any]) -> int:
    """Instagram often omits view_count unless logged-in cookies are provided."""
    for key in ("view_count", "play_count", "impression_count"):
        val = info.get(key)
        if val is not None:
            try:
                n = int(val)
                if n > 0:
                    return n
            except (TypeError, ValueError):
                pass
    return 0


def _pick_thumbnail(info: dict[str, Any]) -> str | None:
    thumb = info.get("thumbnail")
    if thumb:
        return str(thumb)
    thumbs = info.get("thumbnails")
    if isinstance(thumbs, list) and thumbs:
        # prefer larger thumb entries
        for t in reversed(thumbs):
            if t.get("url"):
                return str(t["url"])
    return None


def _snippet_dicts(fetched) -> list[dict[str, Any]]:
    """Normalize youtube-transcript-api 1.x FetchedTranscript to {text, start}."""
    return [{"text": s.text, "start": s.start} for s in fetched]


def _snippets_from_youtube(yt_id: str) -> list[dict[str, Any]]:
    """youtube-transcript-api 1.x uses instance methods fetch() / list()."""
    api = YouTubeTranscriptApi()
    langs = ["en", "en-US", "en-GB"]
    try:
        return _snippet_dicts(api.fetch(yt_id, languages=langs))
    except (NoTranscriptFound, TranscriptsDisabled, VideoUnavailable):
        pass
    try:
        for transcript in api.list(yt_id):
            try:
                return _snippet_dicts(transcript.fetch())
            except Exception:
                continue
    except Exception:
        pass
    return []


def _youtube_transcript(yt_id: str) -> tuple[str, str]:
    """Return (full_transcript, first_5_seconds_hook)."""
    snippets = _snippets_from_youtube(yt_id)
    if not snippets:
        return "", ""
    full = " ".join(s["text"].strip() for s in snippets if s.get("text"))
    hook = " ".join(
        s["text"].strip()
        for s in snippets
        if s.get("text") and float(s.get("start", 0)) < 5.0
    )
    return full, hook


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

    views = _pick_views(info)
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
    hook_opening = ""
    if platform == "youtube":
        yt_id = _extract_youtube_id(url) or info.get("id", "")
        if yt_id:
            transcript, hook_opening = _youtube_transcript(yt_id)
    if not transcript:
        transcript = _subtitle_text_from_info(info)
    if not transcript and description:
        transcript = description[:8000]

    if not hook_opening and transcript:
        # estimate opening from duration when timestamps unavailable (IG, captions)
        dur = max(duration, 1)
        take = max(80, int(len(transcript) * min(5.0, dur) / dur))
        hook_opening = transcript[:take].strip()

    engagement = compute_engagement_rate(views, likes, comments)

    thumbnail_url = _pick_thumbnail(info)

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
        hook_opening=hook_opening.strip(),
        thumbnail_url=thumbnail_url,
    )
