"""Chunk transcripts, embed with OpenAI, persist in ChromaDB tagged by video_id."""

from __future__ import annotations

from typing import Any

from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from app.config import settings
from app.services.video_fetcher import VideoMetadata


COLLECTION_NAME = "video_transcripts"
_active_sessions: set[str] = set()


def _metadata_doc_block(meta: VideoMetadata) -> str:
    return (
        f"[METADATA video_id={meta.video_id} platform={meta.platform}]\n"
        f"Title: {meta.title}\n"
        f"Creator: {meta.creator}\n"
        f"Followers: {meta.follower_count}\n"
        f"Views: {meta.views} | Likes: {meta.likes} | Comments: {meta.comments}\n"
        f"Engagement rate: {meta.engagement_rate}%\n"
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
            for i, chunk in enumerate(chunks):
                docs.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "video_id": v.video_id,
                            "chunk_index": i,
                            "source_type": "transcript",
                            "url": v.url,
                            "platform": v.platform,
                            "title": v.title,
                        },
                    )
                )
    return docs


def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.openai_api_key or None,
    )


def ingest_videos(videos: list[VideoMetadata], session_id: str) -> dict[str, Any]:
    """Replace collection for this session (namespace = session_id)."""
    docs = build_documents(videos)
    if not docs:
        raise ValueError("No content to index — transcripts/metadata empty for both videos.")

    embeddings = get_embeddings()
    # session-scoped collection so multiple demos don't collide
    collection = f"{COLLECTION_NAME}_{session_id}"

    Chroma.from_documents(
        documents=docs,
        embedding=embeddings,
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
    if session_id in _active_sessions:
        return True
    try:
        data = get_vectorstore(session_id).get()
        return bool(data.get("ids"))
    except Exception:
        return False


def get_vectorstore(session_id: str) -> Chroma:
    collection = f"{COLLECTION_NAME}_{session_id}"
    return Chroma(
        collection_name=collection,
        embedding_function=get_embeddings(),
        persist_directory=settings.chroma_persist_dir,
    )
