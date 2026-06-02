from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Always load backend/.env even if uvicorn is started from another folder
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Providers: openai | ollama | gemini (llm only for gemini)
    llm_provider: str = "openai"
    embedding_provider: str = "openai"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_embedding_model: str = "nomic-embed-text"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    chroma_persist_dir: str = "./data/chroma"
    chunk_size: int = 500
    chunk_overlap: int = 80
    max_chunks_per_video: int = 20
    cors_origins: str = "http://localhost:3000"
    # Optional: path to Netscape cookies.txt for Instagram (yt-dlp)
    ytdlp_cookies_file: str = ""


settings = Settings()
