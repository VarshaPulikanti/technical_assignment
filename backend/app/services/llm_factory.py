"""LLM + embedding providers: OpenAI (default), Ollama (free local), Gemini (free tier)."""

from __future__ import annotations

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import settings


def get_embeddings() -> Embeddings:
    provider = settings.embedding_provider.lower()
    if provider == "ollama":
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
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")


def get_chat_llm() -> BaseChatModel:
    provider = settings.llm_provider.lower()
    if provider == "ollama":
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


def assert_providers_configured() -> None:
    emb = settings.embedding_provider.lower()
    llm = settings.llm_provider.lower()

    if emb == "openai" and not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required when EMBEDDING_PROVIDER=openai")
    if llm == "openai" and not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY required when LLM_PROVIDER=openai")
    if llm == "gemini" and not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY required when LLM_PROVIDER=gemini")
