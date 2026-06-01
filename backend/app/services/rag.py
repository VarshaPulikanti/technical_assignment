"""LangChain RAG with streaming, citations, and per-session chat memory."""

from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from langchain.chains import create_history_aware_retriever, create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI

from app.config import settings
from app.services.vector_store import get_vectorstore

# in-process session memory (swap Redis for multi-instance prod)
_session_histories: dict[str, list] = {}


SYSTEM = """You are a creator analytics assistant comparing two short-form videos (Video A and Video B).

Use ONLY the provided context. Video A and Video B are labeled in metadata (video_id field).

When answering:
- Cite sources inline as [Video A, chunk N] or [Video B, metadata] using chunk_index and video_id from context.
- For engagement rate questions, use the exact engagement_rate from metadata when available.
- For hook comparisons, focus on transcript chunks with low chunk_index (opening content).
- Be specific and actionable for improvement suggestions.

If context is insufficient, say what is missing — do not invent stats."""


def _docs_to_sources(docs) -> list[dict]:
    return [
        {
            "video_id": d.metadata.get("video_id"),
            "chunk_index": d.metadata.get("chunk_index"),
            "source_type": d.metadata.get("source_type"),
            "title": d.metadata.get("title"),
            "excerpt": (d.page_content or "")[:200],
        }
        for d in (docs or [])
    ]


def _get_history(session_id: str) -> list:
    if session_id not in _session_histories:
        _session_histories[session_id] = []
    return _session_histories[session_id]


def clear_history(session_id: str) -> None:
    _session_histories.pop(session_id, None)


def _build_chain(session_id: str):
    llm = ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key or None,
        temperature=0.2,
        streaming=True,
    )
    retriever = get_vectorstore(session_id).as_retriever(search_kwargs={"k": 8})

    contextualize_q = ChatPromptTemplate.from_messages(
        [
            ("system", "Rephrase the follow-up question to be standalone given chat history."),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    history_aware_retriever = create_history_aware_retriever(llm, retriever, contextualize_q)

    qa_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM + "\n\nContext:\n{context}"),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )
    question_answer_chain = create_stuff_documents_chain(llm, qa_prompt)
    return create_retrieval_chain(history_aware_retriever, question_answer_chain)


async def stream_chat(session_id: str, message: str) -> AsyncGenerator[str, None]:
    chain = _build_chain(session_id)
    history = _get_history(session_id)

    # preview sources while model streams (final list may refine after retrieval)
    preview = _docs_to_sources(get_vectorstore(session_id).similarity_search(message, k=8))
    yield json.dumps({"type": "sources", "sources": preview}) + "\n"

    full_answer = ""
    context_docs = []

    async for event in chain.astream_events(
        {"input": message, "chat_history": history},
        version="v2",
    ):
        kind = event.get("event")
        if kind == "on_retriever_end":
            output = event.get("data", {}).get("output")
            if output:
                context_docs = output if isinstance(output, list) else getattr(output, "documents", output)
        if kind == "on_chat_model_stream":
            chunk = event.get("data", {}).get("chunk")
            if chunk and getattr(chunk, "content", None):
                delta = chunk.content
                if isinstance(delta, str) and delta:
                    full_answer += delta
                    yield json.dumps({"type": "token", "content": delta}) + "\n"

    if not full_answer:
        result = await chain.ainvoke({"input": message, "chat_history": history})
        full_answer = result.get("answer", "")
        context_docs = result.get("context") or context_docs
        if full_answer:
            yield json.dumps({"type": "token", "content": full_answer}) + "\n"

    final_sources = _docs_to_sources(context_docs) or preview
    yield json.dumps({"type": "sources", "sources": final_sources}) + "\n"

    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=full_answer))
    yield json.dumps({"type": "done"}) + "\n"


def chat_sync(session_id: str, message: str) -> dict[str, Any]:
    """Non-streaming fallback."""
    import asyncio

    tokens = []
    sources = []

    async def _run():
        nonlocal sources
        async for line in stream_chat(session_id, message):
            data = json.loads(line)
            if data["type"] == "sources":
                sources = data["sources"]
            elif data["type"] == "token":
                tokens.append(data["content"])

    asyncio.run(_run())
    return {"answer": "".join(tokens), "sources": sources}
