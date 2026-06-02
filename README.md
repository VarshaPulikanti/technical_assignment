# Creator Video RAG — Technical Assignment

Compare **one YouTube video (A)** and **one Instagram Reel (B)**: pull transcripts + metadata, index in **ChromaDB**, chat with **LangChain** (`create_retrieval_chain`). Built for the engineering screening brief.

**Repo:** https://github.com/VarshaPulikanti/technical_assignment

## What it does

| Requirement | Implementation |
|-------------|----------------|
| YouTube + Instagram URLs (dynamic) | `POST /api/ingest` — `yt-dlp` + `youtube-transcript-api` |
| Transcript + metadata | views, likes, comments, creator, followers, hashtags, date, duration |
| Engagement rate | `(likes + comments) / views × 100` in `video_fetcher.py` |
| Chunk + embed + vector DB | ChromaDB; every chunk tagged `video_id` **A** or **B** |
| Hook (~5 seconds) | `source_type: hook` chunk per video |
| LangChain RAG | `create_retrieval_chain` + `create_stuff_documents_chain` in `rag.py` |
| Stream + cite + memory | NDJSON stream; source list per answer; session `chat_history` |
| Next.js UI | Side-by-side video cards + chat (`CreatorApp.tsx`) |

## Stack (and why)

- **FastAPI** — async ingest, background indexing, streaming chat.
- **LangChain 0.3** — required orchestration; retrieval chain with session memory in the QA prompt.
- **ChromaDB (local persist)** — zero infra for the demo; at **~1000 creators/day** → **pgvector** on Postgres (SQL + `session_id` indexes) or **Pinecone serverless** if we only need vectors.
- **Embeddings** — **FastEmbed** (`BAAI/bge-small-en-v1.5`) locally — free, no Ollama needed for indexing.
- **LLM** — **Gemini 2.5 Flash** (free API key from Google AI Studio) for chat; optional OpenAI/Ollama via `.env`.
- **Chunk size 500 / overlap 80** — good granularity for short-form and hook questions.

### Cost @ 1000 creators/day (rough)

~2 videos × ~20 chunks × 1000 creators ≈ **40k embeds/day** → low cost with local or small embedding models. **Chat tokens** dominate (~$15–40/day on a small cloud LLM). Mitigations: cache repeated questions per session, batch embeds overnight, rerank top-20 instead of large `k`.

### What breaks at scale

- Per-session Chroma on one server; move to pgvector + job queue.
- In-memory chat history → Redis or DB.
- Instagram may hide views — optional `YTDLP_COOKIES_FILE` in `.env`.

## Setup

```powershell
# From repo root
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Copy env template (secrets stay out of git)
copy ..\.env.example .env
# Edit backend\.env — set GEMINI_API_KEY from https://aistudio.google.com/apikey
# Defaults: LLM_PROVIDER=gemini, EMBEDDING_PROVIDER=local, GEMINI_MODEL=gemini-2.5-flash

uvicorn app.main:app --host 127.0.0.1 --port 8000
# Do NOT use --reload while indexing (can interrupt background embed)

# New terminal — frontend
cd frontend
npm install
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
npm run dev
```

Open **http://localhost:3000** → paste YouTube + Instagram Reel URLs → **Analyze & Index** → wait for chat ready → ask questions.

**Optional:** `LLM_PROVIDER=ollama` for local chat (keep `EMBEDDING_PROVIDER=local`). Open Ollama app before chatting.

## API

| Endpoint | Purpose |
|----------|---------|
| `POST /api/ingest` | Fetch both videos; index in background |
| `GET /api/ingest/status/{session_id}` | Poll until `chat_ready` |
| `POST /api/chat` | NDJSON: `status` → `sources` → `token` → `done` |
| `GET /api/config` | Active providers |
| `GET /health` | Liveness |

## Project layout

```
assignment/
├── backend/app/services/   # video_fetcher, vector_store, rag, llm_factory
├── frontend/app/CreatorApp.tsx
├── .env.example
└── README.md
```

## Author

Varsha Pulikanti — technical screening submission.
