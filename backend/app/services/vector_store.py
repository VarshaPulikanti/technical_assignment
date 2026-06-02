"""Chunk transcripts, embed, persist in ChromaDB tagged by video_id."""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import settings
from app.services.llm_factory import get_embeddings
from app.services.video_fetcher import VideoMetadata

logger = logging.getLogger(__name__)

COLLECTION_NAME = "video_transcripts"
_active_sessions: set[str] = set()


def _collection_name(session_id: str) -> str:
    return f"{COLLECTION_NAME}_{session_id}"


def _chroma_client() -> chromadb.PersistentClient:
    return chromadb.PersistentClient(path=settings.chroma_persist_dir)


def delete_session_collection(session_id: str) -> None:
    """Remove a session index (fixes corrupted / wrong-embedding collections)."""
    name = _collection_name(session_id)
    try:
        _chroma_client().delete_collection(name)
    except Exception:
        pass
    _active_sessions.discard(session_id)


def _metadata_doc_block(meta: VideoMetadata) -> str:
    return (
        f"[METADATA video_id={meta.video_id} platform={meta.platform}]\n"
        f"Title: {meta.title}\n"
        f"Creator: {meta.creator}\n"
        f"Followers: {meta.follower_count}\n"
        f"Views: {meta.views if meta.views > 0 else 'not available (Instagram may hide views)'} | "
        f"Likes: {meta.likes} | Comments: {meta.comments}\n"
        f"Engagement rate: {meta.engagement_rate}%"
        f"{'' if meta.views > 0 else ' (N/A when views hidden)'}\n"
        f"Upload date: {meta.upload_date} | Duration: {meta.duration_seconds}s\n"
        f"Hashtags: {', '.join(meta.hashtags)}\n"
    )


def build_documents(videos: list[VideoMetadata]) -> list[Document]:
    docs: list[Document] = []
    for v in videos:
        docs.append(
            Document(
                page_content=_metadata_doc_block(v),
                metadata={
                    "video_id": v.video_id,
                    "chunk_index": -1,
                    "source_type": "metadata",
                    "url": v.url,
                    "platform": v.platform,
                    "title": v.title,
                },
            )
        )
        if v.hook_opening:
            docs.append(
                Document(
                    page_content=f"[HOOK first 5 seconds — video_id={v.video_id}]\n{v.hook_opening}",
                    metadata={
                        "video_id": v.video_id,
                        "chunk_index": 0,
                        "source_type": "hook",
                        "url": v.url,
                        "platform": v.platform,
                        "title": v.title,
                    },
                )
            )
        if v.transcript:
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
            )
            chunks = splitter.split_text(v.transcript)
            if len(chunks) > settings.max_chunks_per_video:
                chunks = chunks[: settings.max_chunks_per_video]
            start_idx = 1 if v.hook_opening else 0
            for i, chunk in enumerate(chunks):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "video_id": v.video_id,
                            "chunk_index": i + start_idx,
                            "source_type": "transcript",
                            "url": v.url,
                            "platform": v.platform,
                            "title": v.title,
                        },
                    )
                )
    return docs


def ingest_videos(videos: list[VideoMetadata], session_id: str) -> dict[str, Any]:
    """Build a fresh Chroma collection for this session."""
    docs = build_documents(videos)
    if not docs:
        raise ValueError("No content to index — transcripts/metadata empty for both videos.")

    delete_session_collection(session_id)

    collection = _collection_name(session_id)
    Chroma.from_documents(
        documents=docs,
        embedding=get_embeddings(),
        collection_name=collection,
        persist_directory=settings.chroma_persist_dir,
    )
    _active_sessions.add(session_id)
    return {
        "session_id": session_id,
        "collection": collection,
        "chunk_count": len(docs),
        "videos": [v.to_dict() for v in videos],
    }


def session_exists(session_id: str) -> bool:
    """True only if the collection exists and search works (not corrupt / empty)."""
    name = _collection_name(session_id)
    try:
        client = _chroma_client()
        col = client.get_collection(name)
        if col.count() < 1:
            return False
        store = get_vectorstore(session_id)
        store.similarity_search("engagement rate", k=1)
        _active_sessions.add(session_id)
        return True
    except Exception as e:
        logger.debug("session_exists(%s) failed: %s", session_id, e)
        _active_sessions.discard(session_id)
        return False


def get_vectorstore(session_id: str) -> Chroma:
    return Chroma(
        collection_name=_collection_name(session_id),
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )
