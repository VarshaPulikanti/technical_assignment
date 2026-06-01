# Run from backend/ — installs deps in order to avoid chroma/langchain conflicts
$ErrorActionPreference = "Stop"
python -m venv .venv
.\.venv\Scripts\pip install --upgrade pip
.\.venv\Scripts\pip install fastapi "uvicorn[standard]" python-dotenv pydantic-settings httpx youtube-transcript-api "yt-dlp>=2024.12.0"
.\.venv\Scripts\pip install "langchain==0.3.27" "langchain-openai==0.3.35" "langchain-community==0.3.31" "langchain-text-splitters==0.3.11" "chromadb>=0.5.23" tiktoken
Write-Host "Done. Copy ..\.env.example to .env and add OPENAI_API_KEY"
