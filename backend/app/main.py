"""FastAPI backend — ingest two videos, index transcripts, stream RAG chat."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, HttpUrl

from app.config import settings
from app.services import rag
from app.services.video_fetcher import fetch_video
from app.services.vector_store import ingest_videos, session_exists

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


@app.post("/api/ingest")
def ingest(body: IngestRequest) -> dict[str, Any]:
    if not settings.openai_api_key:
        raise HTTPException(500, "OPENAI_API_KEY not configured")

    session_id = str(uuid.uuid4())[:12]
    try:
        video_a = fetch_video(str(body.youtube_url), "A")
        video_b = fetch_video(str(body.instagram_url), "B")
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch video data: {e}") from e

    if video_a.platform != "youtube":
        raise HTTPException(400, "First URL must be YouTube (Video A)")
    if video_b.platform != "instagram":
        raise HTTPException(400, "Second URL must be Instagram (Video B)")

    try:
        result = ingest_videos([video_a, video_b], session_id)
    except Exception as e:
        raise HTTPException(500, f"Indexing failed: {e}") from e

    rag.clear_history(session_id)
    return result


@app.post("/api/chat")
async def chat(body: ChatRequest):
    if not settings.openai_api_key:
        raise HTTPException(500, "OPENAI_API_KEY not configured")
    if not session_exists(body.session_id):
        raise HTTPException(404, f"Unknown session '{body.session_id}'. Run /api/ingest first.")

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
