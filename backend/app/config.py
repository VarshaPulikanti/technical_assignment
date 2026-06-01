from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    embedding_model: str = "text-embedding-3-small"
    chroma_persist_dir: str = "./data/chroma"
    chunk_size: int = 500
    chunk_overlap: int = 80
    cors_origins: str = "http://localhost:3000"
    # Optional: path to Netscape cookies.txt for Instagram (yt-dlp)
    ytdlp_cookies_file: str = ""


settings = Settings()
