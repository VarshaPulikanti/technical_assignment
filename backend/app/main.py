"""FastAPI backend — ingest two videos, index transcripts, stream RAG chat."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from urllib.parse import unquote

import httpx
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field, HttpUrl

from app.config import settings
from app.services import rag
from app.services.llm_factory import assert_providers_configured
from app.services.video_fetcher import VideoMetadata, fetch_video
from app.services.vector_store import ingest_videos, session_exists

logger = logging.getLogger("uvicorn.error")

# session_id -> pending | ready | error message
_index_status: dict[str, str] = {}

app = FastAPI(title="Creator RAG Compare", version="1.0.0")

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    youtube_url: HttpUrl = Field(..., description="YouTube video URL (Video A)")
    instagram_url: HttpUrl = Field(..., description="Instagram Reel URL (Video B)")


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1, max_length=4000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/ollama-health")
async def ollama_health() -> dict[str, Any]:
    """Quick check that Ollama is reachable before chatting."""
    if settings.llm_provider.lower() != "ollama":
        return {"ok": True, "provider": settings.llm_provider}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
            model = settings.ollama_model
            has_model = any(model in n for n in names)
            return {
                "ok": has_model,
                "model": model,
                "models": names[:8],
                "hint": None
                if has_model
                else f"Run: ollama pull {model}",
            }
    except Exception as e:
        return {"ok": False, "error": str(e), "hint": "Open the Ollama app (whale icon in tray)."}


@app.get("/api/thumbnail")
def proxy_thumbnail(url: str) -> Response:
    """Proxy Instagram CDN images (browser blocks direct hotlink)."""
    if not url.startswith("http"):
        raise HTTPException(400, "Invalid thumbnail url")
    try:
        r = httpx.get(
            unquote(url),
            timeout=30,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.instagram.com/",
            },
        )
        r.raise_for_status()
        media = r.headers.get("content-type", "image/jpeg")
        return Response(content=r.content, media_type=media)
    except Exception as e:
        raise HTTPException(502, f"Thumbnail fetch failed: {e}") from e


@app.get("/api/config")
def show_config() -> dict[str, str]:
    """Check which AI provider is active (should be ollama when not paying OpenAI)."""
    return {
        "llm_provider": settings.llm_provider,
        "embedding_provider": settings.embedding_provider,
        "ollama_model": settings.ollama_model,
        "ollama_embedding_model": settings.ollama_embedding_model,
        "env_file": str(settings.model_config.get("env_file", "")),
    }


def _index_in_background(videos: list[VideoMetadata], session_id: str) -> None:
    try:
        logger.info("Indexing session %s (%s chunks to embed)…", session_id, "…")
        result = ingest_videos(videos, session_id)
        _index_status[session_id] = "ready"
        logger.info("Session %s ready — %s chunks indexed", session_id, result["chunk_count"])
    except Exception as e:
        logger.exception("Indexing failed for %s", session_id)
        _index_status[session_id] = f"error: {e}"


@app.get("/api/ingest/status/{session_id}")
def ingest_status(session_id: str) -> dict[str, Any]:
    status = _index_status.get(session_id, "unknown")
    ready = status == "ready" or session_exists(session_id)
    if ready:
        _index_status[session_id] = "ready"
    return {
        "session_id": session_id,
        "status": "ready" if ready else status,
        "chat_ready": ready,
    }


@app.post("/api/ingest")
def ingest(body: IngestRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    try:
        assert_providers_configured()
    except ValueError as e:
        raise HTTPException(500, str(e)) from e

    session_id = str(uuid.uuid4())[:12]
    logger.info("Fetching videos for session %s…", session_id)
    try:
        video_a = fetch_video(str(body.youtube_url), "A")
        video_b = fetch_video(str(body.instagram_url), "B")
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch video data: {e}") from e

    if video_a.platform != "youtube":
        raise HTTPException(400, "First URL must be YouTube (Video A)")
    if video_b.platform != "instagram":
        raise HTTPException(400, "Second URL must be Instagram (Video B)")

    rag.clear_history(session_id)
    _index_status[session_id] = "indexing"
    background_tasks.add_task(_index_in_background, [video_a, video_b], session_id)
    logger.info("Videos fetched for %s — cards returned; embedding runs in background", session_id)

    return {
        "session_id": session_id,
        "chunk_count": 0,
        "index_status": "indexing",
        "videos": [video_a.to_dict(), video_b.to_dict()],
    }


@app.post("/api/chat")
async def chat(body: ChatRequest):
    try:
        assert_providers_configured()
    except ValueError as e:
        raise HTTPException(500, str(e)) from e
    st = _index_status.get(body.session_id)
    if st == "indexing":
        raise HTTPException(409, "Still indexing — wait until status is ready.")
    if st and st.startswith("error"):
        raise HTTPException(500, st)
    if not session_exists(body.session_id):
        raise HTTPException(
            404,
            f"Session '{body.session_id}' not indexed. Click Analyze & Index again.",
        )

    async def event_gen():
        try:
            async for line in rag.stream_chat(body.session_id, body.message):
                yield line
        except Exception as e:
            import json

            yield json.dumps({"type": "error", "message": str(e)}) + "\n"

    return StreamingResponse(event_gen(), media_type="application/x-ndjson")


@app.delete("/api/session/{session_id}")
def reset_session(session_id: str) -> dict[str, str]:
    rag.clear_history(session_id)
    return {"status": "cleared"}
