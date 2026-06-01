# Creator Video RAG — Technical Assignment

Compare **one YouTube video (A)** and **one Instagram Reel (B)**: pull transcripts + metadata, index in **ChromaDB**, chat with **LangChain** (history-aware retriever + retrieval chain). Built for the engineering screening brief.

**Repo:** https://github.com/VarshaPulikanti/technical_assignment

## What I built

| Requirement | How |
|-------------|-----|
| Two URLs (YT + IG), dynamic | `POST /api/ingest` → `yt-dlp` + `youtube-transcript-api` |
| Metadata + transcript | views, likes, comments, creator, followers, hashtags, date, duration |
| Engagement rate | `(likes + comments) / views × 100` in `video_fetcher.py` |
| Chunk + embed + vector DB | ChromaDB, metadata `video_id` = `A` or `B` |
| Hook (first ~5s) | Separate chunk with `source_type: hook` |
| LangChain RAG | `create_history_aware_retriever` + `create_retrieval_chain` in `rag.py` |
| Stream + cite + memory | NDJSON stream; sources from retriever; in-session `chat_history` |
| Next.js UI | Side-by-side cards + chat (`CreatorApp.tsx`) |

## Stack (and why)

- **FastAPI** — async ingest, background embedding, NDJSON chat stream.
- **LangChain 0.3** — required orchestration; history-aware retriever so follow-ups like “compare *their* hooks” still retrieve the right chunks.
- **ChromaDB (local)** — fine for demo and single-tenant; at **~1000 creators/day** I’d move embeddings to **pgvector** on Postgres (one bill, SQL backups, `tenant_id` + `session_id` indexes) or **Pinecone serverless** if we only need vector search without joins.
- **Embeddings** — `text-embedding-3-small` (OpenAI) for production cost; **Ollama `mxbai-embed-large`** for free local demos.
- **LLM** — `gpt-4o-mini` for best cost/quality on short Q&A; **Ollama `llama3.2`** when avoiding API spend (slower on CPU).
- **Chunk size 500 / overlap 80** — short-form scripts are dense; smaller chunks help “first 5 seconds” and hook questions without blowing token budget.

### Cost @ 1000 creators/day (rough)

~2 videos × ~20 chunks × 1000 sessions ≈ 40k embed calls/day → **~$1–2/day** on small embeddings. Chat dominates: ~5 turns × ~3k tokens × 1000 ≈ **$15–40/day** on gpt-4o-mini. Vectors are not the bottleneck — **LLM tokens are**. Mitigations: cache FAQ answers per session, batch nightly embeds, optional reranker on top-20 instead of raising `k`.

### What breaks at scale

- In-memory chat history and per-session Chroma collections on one machine.
- Instagram view counts often need cookies (`YTDLP_COOKIES_FILE`).
- Ollama on a laptop OOMs if you run embed + chat + multiple tabs — use OpenAI for the Loom or restart Ollama between ingest and chat.

## Setup

```powershell
# 1) Backend
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy ..\.env.example .env
# Edit backend\.env — set OPENAI_API_KEY (recommended for demo) OR ollama providers

uvicorn app.main:app --host 127.0.0.1 --port 8000
# Do NOT use --reload while indexing (kills background embed jobs)

# 2) Frontend
cd frontend
npm install
# frontend\.env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000 → paste **YouTube** + **Instagram Reel** URLs → **Analyze & Index** → wait for “ready” → chat.

**Ollama (free):** install Ollama app, `ollama pull llama3.2`, `ollama pull mxbai-embed-large`, set `LLM_PROVIDER=ollama` and `EMBEDDING_PROVIDER=ollama` in `backend/.env`.

## API

| Endpoint | Purpose |
|----------|---------|
| `POST /api/ingest` | Fetch both videos; index in background |
| `GET /api/ingest/status/{session_id}` | Poll until `chat_ready` |
| `POST /api/chat` | NDJSON: `status` → `sources` → `token`* → `done` |
| `GET /api/config` | Active LLM/embedding provider |
| `GET /api/ollama-health` | Ollama reachability check |
| `GET /health` | Liveness |

## Loom demo script (live, start to finish)

1. Start backend + frontend; show `.env` provider (OpenAI or Ollama).
2. Paste two **real** public URLs (YouTube + IG Reel).
3. **Analyze & Index** — show side-by-side cards (stats, engagement, thumbnails).
4. Ask all five suggested questions; point at **streaming** text and **source chips** (video A/B + chunk).
5. **Follow-up** without re-stating context (e.g. “What should B change about the hook?”) → shows **memory**.
6. 60s on scale: Chroma → pgvector, mini vs 4o, embed batching, IG cookies.

## Project layout

```
assignment/
├── backend/app/
│   ├── main.py
│   ├── config.py
│   └── services/
│       ├── video_fetcher.py   # ingest + engagement
│       ├── vector_store.py    # Chroma + chunk tags
│       └── rag.py             # LangChain retrieval chain
├── frontend/app/CreatorApp.tsx
├── .env.example
└── README.md
```

## Assignment checklist (self-review)

| Item | Done |
|------|------|
| Full-stack, dynamic (no hard-coded answers) | Yes |
| LangChain + embeddings + ChromaDB | Yes (`rag.py`, `vector_store.py`) |
| YouTube + Instagram mandatory | Enforced in `main.py` |
| Transcript + full metadata | Yes |
| Engagement rate formula | Yes |
| Chunks tagged `video_id` A/B | Yes |
| Stream + cite + memory | Yes |
| Next.js cards + chat | Yes |
| README + `.env.example` + git history | Yes |
| Loom + GitHub submission | **You** record Loom and reply with URLs |

## Author

Varsha Pulikanti — technical screening submission.
