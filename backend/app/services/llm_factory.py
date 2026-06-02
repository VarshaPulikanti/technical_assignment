"""LLM + embedding providers: OpenAI, Ollama, Gemini, or local (no Ollama for embed)."""

from __future__ import annotations

import httpx
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings


def ollama_reachable() -> tuple[bool, str]:
    """True if Ollama HTTP API is up."""
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        r = httpx.get(url, timeout=3.0)
        r.raise_for_status()
        return True, ""
    except Exception:
        return False, (
            "Ollama is not running. Open the Ollama app from the Start menu "
            "(whale icon), wait until it says running, then try again."
        )


def get_embeddings() -> Embeddings:
    provider = settings.embedding_provider.lower()
    if provider == "local":
        from langchain_community.embeddings import FastEmbedEmbeddings

        return FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    if provider == "ollama":
        ok, msg = ollama_reachable()
        if not ok:
            raise ConnectionError(msg)
        from langchain_community.embeddings import OllamaEmbeddings

        return OllamaEmbeddings(
            model=settings.ollama_embedding_model,
            base_url=settings.ollama_base_url,
        )
    if provider == "openai":
        return OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.openai_api_key or None,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}. Use local, ollama, or openai.")


def get_chat_llm() -> BaseChatModel:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
        ok, msg = ollama_reachable()
        if not ok:
            raise ConnectionError(msg)
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            model=settings.ollama_model,
            base_url=settings.ollama_base_url,
            temperature=0.2,
            num_predict=512,
        )
    if provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.gemini_api_key,
            temperature=0.2,
        )
    if provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key or None,
            temperature=0.2,
            streaming=True,
        )
    raise ValueError(f"Unknown LLM_PROVIDER: {provider}")


def assert_embeddings_ready() -> None:
    """Called before ingest — does not require Ollama unless embeddings use Ollama."""
    emb = settings.embedding_provider.lower()
    if emb == "openai" and not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required when EMBEDDING_PROVIDER=openai")
    if emb == "ollama":
        ok, msg = ollama_reachable()
        if not ok:
            raise ConnectionError(
                f"{msg} Or set EMBEDDING_PROVIDER=local in backend/.env and restart backend."
            )


def assert_providers_configured() -> None:
    """Called before chat — checks both embeddings config and LLM (incl. Ollama for chat)."""
    assert_embeddings_ready()
    llm = settings.llm_provider.lower()
    if llm == "openai" and not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required when LLM_PROVIDER=openai")
    if llm == "gemini" and not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY required when LLM_PROVIDER=gemini")
    if llm == "ollama":
        ok, msg = ollama_reachable()
        if not ok:
            raise ConnectionError(msg)
