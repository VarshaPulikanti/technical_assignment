"""LangChain RAG: history-aware retriever + retrieval chain, streaming + memory."""

from __future__ import annotations

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

CONTEXTUALIZE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "Given chat history and the latest user question, rewrite it as a standalone "
            "search query for video transcripts. Do not answer — only output the query.",
        ),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
    ]
)

QA_SYSTEM = """You are a creator analytics assistant comparing Video A (YouTube) and Video B (Instagram).

Use ONLY the retrieved context below. Cite sources as [Video A, chunk N], [Video B, hook], or [Video B, metadata].
Compute engagement rate as (likes + comments) / views × 100 when views are available.
If Instagram views are hidden, say so — never invent view counts.

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
    """LangChain: history-aware retriever + stuff-documents QA chain."""
    retriever = get_vectorstore(session_id).as_retriever(search_kwargs={"k": 6})
    llm = get_chat_llm()
    history_aware_retriever = create_history_aware_retriever(
        llm, retriever, CONTEXTUALIZE_PROMPT
    )
    qa_chain = create_stuff_documents_chain(llm, QA_PROMPT)
    return create_retrieval_chain(history_aware_retriever, qa_chain)


async def stream_chat(session_id: str, message: str) -> AsyncGenerator[str, None]:
    yield json.dumps({"type": "status", "content": "Retrieving relevant chunks (LangChain)…"}) + "\n"

    chain = _build_rag_chain(session_id)
    history = _get_history(session_id)
    inputs = {"input": message, "chat_history": history}

    sources_sent = False
    full_answer = ""

    provider = settings.llm_provider.lower()
    gen_msg = (
        "Generating answer (Ollama on CPU may take 1–2 min)…"
        if provider == "ollama"
        else "Generating answer…"
    )
    yield json.dumps({"type": "status", "content": gen_msg}) + "\n"

    try:
        async for chunk in chain.astream(inputs):
            if "context" in chunk and chunk["context"] and not sources_sent:
                yield json.dumps(
                    {"type": "sources", "sources": _docs_to_sources(chunk["context"])}
                ) + "\n"
                sources_sent = True

            if "answer" in chunk and chunk["answer"]:
                ans = chunk["answer"]
                text = ans if isinstance(ans, str) else getattr(ans, "content", "") or ""
                if text:
                    full_answer += text
                    yield json.dumps({"type": "token", "content": text}) + "\n"

        if not full_answer.strip():
            result = await chain.ainvoke(inputs)
            if not sources_sent and result.get("context"):
                yield json.dumps(
                    {"type": "sources", "sources": _docs_to_sources(result["context"])}
                ) + "\n"
                sources_sent = True
            answer = result.get("answer", "")
            text = answer.content if hasattr(answer, "content") else str(answer)
            if text:
                full_answer = text
                yield json.dumps({"type": "token", "content": text}) + "\n"

    except Exception as e:
        err = str(e)
        if "allocate" in err.lower() or "terminated" in err.lower():
            err = (
                "Ollama ran out of memory. Quit Ollama from the tray, reopen it, "
                "restart the backend, then send one message at a time."
            )
        yield json.dumps({"type": "error", "message": err}) + "\n"
        yield json.dumps({"type": "done"}) + "\n"
        return

    if not full_answer.strip():
        full_answer = (
            "No LLM response. Check Ollama/OpenAI is running and the session is indexed."
        )
        yield json.dumps({"type": "token", "content": full_answer}) + "\n"

    history.append(HumanMessage(content=message))
    history.append(AIMessage(content=full_answer))
    yield json.dumps({"type": "done"}) + "\n"
