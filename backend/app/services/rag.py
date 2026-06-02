"""LangChain RAG: retrieval chain, streaming, citations, session memory."""

from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator

from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import settings
from app.services.llm_factory import get_chat_llm
from app.services.vector_store import get_vectorstore

_session_histories: dict[str, list] = {}
_CHAT_TIMEOUT_SEC = 180

CONTEXTUALIZE_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", "Rewrite the question as a standalone search query. Output only the query."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

QA_SYSTEM = """You are a creator analytics assistant comparing Video A (YouTube) and Video B (Instagram).

Use ONLY the context below. Cite [Video A, chunk N] or [Video B, hook/metadata].
Engagement rate = (likes + comments) / views × 100 when views exist.
If Instagram views are hidden, say so.

Context:
{context}"""

QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", QA_SYSTEM),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)


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


def _build_rag_chain(session_id: str):
    provider = settings.llm_provider.lower()
    k = 4 if provider in ("ollama", "gemini") else 6
    retriever = get_vectorstore(session_id).as_retriever(search_kwargs={"k": k})
    llm = get_chat_llm()
    qa_chain = create_stuff_documents_chain(llm, QA_PROMPT)

    # Single LLM call — saves Gemini/Ollama quota; chat_history still in QA prompt.
    if provider in ("ollama", "gemini"):
        return create_retrieval_chain(retriever, qa_chain)

    history_aware = create_history_aware_retriever(llm, retriever, CONTEXTUALIZE_PROMPT)
    return create_retrieval_chain(history_aware, qa_chain)


async def _run_chain(chain, inputs: dict) -> tuple[str, list]:
    """Run retrieval chain with timeout; return (answer, context docs)."""
    full_answer = ""
    context_docs: list = []

    async def _consume():
        nonlocal full_answer, context_docs
        async for chunk in chain.astream(inputs):
            if chunk.get("context"):
                context_docs = chunk["context"]
            if chunk.get("answer"):
                ans = chunk["answer"]
                text = ans if isinstance(ans, str) else getattr(ans, "content", "") or ""
                full_answer += text
        if not full_answer.strip():
            result = await chain.ainvoke(inputs)
            context_docs = result.get("context") or context_docs
            answer = result.get("answer", "")
            full_answer = answer.content if hasattr(answer, "content") else str(answer)

    await asyncio.wait_for(_consume(), timeout=_CHAT_TIMEOUT_SEC)
    return full_answer, context_docs


async def stream_chat(session_id: str, message: str) -> AsyncGenerator[str, None]:
    history = _get_history(session_id)
    inputs = {"input": message, "chat_history": history}
    use_ollama = settings.llm_provider.lower() == "ollama"

    yield json.dumps({"type": "status", "content": "Searching transcripts…"}) + "\n"

    try:
        chain = _build_rag_chain(session_id)
    except Exception as e:
        yield json.dumps({"type": "error", "message": str(e)}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        return

    wait = (
        "Ollama generating (30–120 sec). Quit other Ollama apps if stuck; send once only."
        if use_ollama
        else "Generating answer…"
    )
    yield json.dumps({"type": "status", "content": wait}) + "\n"

    try:
        full_answer, context_docs = await _run_chain(chain, inputs)
        if context_docs:
            yield json.dumps({"type": "sources", "sources": _docs_to_sources(context_docs)}) + "\n"
        if full_answer.strip():
            yield json.dumps({"type": "token", "content": full_answer}) + "\n"
        else:
            yield json.dumps(
                {
                    "type": "token",
                    "content": "No answer from the model. Restart Ollama (tray → Quit → reopen).",
                }
            ) + "\n"

    except asyncio.TimeoutError:
        yield json.dumps(
            {
                "type": "error",
                "message": "Chat timed out after 3 min. Restart Ollama and the backend, then try again.",
            }
        ) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        return
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower():
            prov = settings.llm_provider.lower()
            if prov == "gemini":
                err = (
                    "Gemini API quota/rate limit hit. Wait 1–2 minutes and try again, "
                    "or set GEMINI_MODEL=gemini-2.5-flash in backend/.env and restart backend."
                )
            elif prov == "openai":
                err = "OpenAI quota exceeded — add billing or switch LLM_PROVIDER=gemini/ollama."
            else:
                err = "API rate limit exceeded. Wait a minute and retry."
        elif "allocate" in err.lower() or "terminated" in err.lower():
            err = "Ollama out of memory — Quit Ollama from system tray, reopen, retry."
        elif "hnsw" in err.lower() or "nothing found on disk" in err.lower():
            err = (
                "Search index is broken (old/corrupt data). Click Analyze & Index again "
                "and wait until chat is ready, then retry."
            )
        yield json.dumps({"type": "error", "message": err}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        return

    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=full_answer or ""))
    yield json.dumps({"type": "done"}) + "\n"
