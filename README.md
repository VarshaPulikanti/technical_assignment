# Creator Video RAG — Technical Assignment

Full-stack RAG chatbot that ingests **one YouTube video (A)** and **one Instagram Reel (B)**, indexes transcripts + metadata in **ChromaDB**, and answers creator questions via **LangChain** with **streaming**, **source citations**, and **multi-turn memory**.

## What it does

1. Accepts two URLs (YouTube + Instagram — required platforms).
2. Pulls **transcript** + **metadata** (views, likes, comments, creator, followers, hashtags, upload date, duration) using **yt-dlp** + **youtube-transcript-api**.
3. Computes **engagement rate**: `(likes + comments) / views × 100`.
4. Chunks transcripts, embeds with **OpenAI `text-embedding-3-small`**, stores in **ChromaDB** with `video_id` tags (`A` / `B`).
5. **LangChain** retrieval chain with history-aware retriever — stream answers and cite chunk sources.
6. **Next.js** UI: side-by-side video cards + chat with suggested prompts.

## Stack choices (and why)

| Layer | Choice | Reasoning |
|--------|--------|-----------|
| Backend | **FastAPI** | Async streaming, simple NDJSON SSE-style responses, fast to ship. |
| Orchestration | **LangChain** | Required; history-aware retriever + `create_retrieval_chain` covers memory + RAG without custom glue. |
| Embeddings | **OpenAI text-embedding-3-small** | Cheap ($0.02/1M tokens), strong quality for short-form transcripts. At 1000 creators/day × ~2 videos × ~20 chunks ≈ 40k chunks/day — embedding cost stays in low tens of dollars vs larger models. |
| Vector DB | **ChromaDB (local persist)** | Zero infra for demo; `video_id` in metadata filters mentally per chunk. **At scale (1000 creators/day):** move to **pgvector** on existing Postgres (one bill, SQL backups, tenant_id + session_id indexes) or **Pinecone serverless** if pure vector ops and auto-scale matter more than JOINs with billing tables. |
| LLM | **gpt-4o-mini** | Best cost/quality for structured Q&A on small context; full **gpt-4o** only if you see systematic reasoning gaps in evals. |
| Transcripts | **youtube-transcript-api** + **yt-dlp** subs | No Whisper GPU cost for most YT/IG public reels; fallback to auto-captions/description keeps pipeline dynamic. |
| Frontend | **Next.js 15** | Client-side streaming parse of NDJSON; minimal deps = less lag. |

### Chunk size: 500 / overlap 80

- Short-form scripts are dense; 500 chars ≈ 1–2 spoken sentences — good retrieval granularity for “first 5 seconds” hook questions (early chunks have low `chunk_index`).
- 80 overlap avoids cutting mid-thought across chunk boundaries.
- **Breaks at 10k users:** single-node Chroma + in-memory chat history. Fix: Redis session store + pgvector with `(session_id, video_id)` composite index.

### Cost sketch @ 1000 creators/day

Assume ~2 videos, ~15 transcript chunks + 1 metadata doc each → ~32 embed calls + ~5 chat turns × 8 retrieved chunks:

- Embeddings: ~32 × 500 tokens × 1000 ≈ 16M tokens/day → **~$0.32/day** on small embedding model.
- LLM: ~5 × 3k tokens in/out × 1000 ≈ **~$15–40/day** on mini (depends on answer length).
- **Bottleneck isn’t vectors** — it’s LLM tokens. Cache metadata answers (“engagement rate of each”) keyed by `session_id` if users repeat FAQs.

**Higher quality / lower cost alternative at scale:** batch embed nightly, serve hot sessions from Redis, use **reranker** (Cohere rerank or bge-reranker) on top-20 instead of bigger k — improves citation precision without larger LLM.

## Prerequisites

- Python 3.11+
- Node 18+
- OpenAI API key
- Public YouTube + Instagram Reel URLs (Instagram may need logged-in cookies for some reels — see below)

## Setup

```bash
# Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy ..\.env.example .env       # add OPENAI_API_KEY
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
echo NEXT_PUBLIC_API_URL=http://localhost:8000 > .env.local
npm run dev
```

Open http://localhost:3000

## API

- `POST /api/ingest` — `{ "youtube_url": "...", "instagram_url": "..." }` → session_id + video stats + chunk count
- `POST /api/chat` — NDJSON stream: `sources` → `token`* → `done`
- `GET /health`

## Instagram notes

yt-dlp works for many public Reels. If metadata/transcript is empty:

- Update yt-dlp: `pip install -U yt-dlp`
- Optional: export `INSTAGRAM_COOKIES` via browser cookies file (documented in yt-dlp wiki)

## Demo script (Loom)

1. Start backend + frontend.
2. Paste real YouTube + Instagram URLs.
3. Click **Analyze & Index** — show cards updating with live stats.
4. Ask each suggested question; show streaming + source citations.
5. Ask a **follow-up** (“elaborate on B’s hook”) to show **memory**.
6. Explain scale/cost trade-offs from this README.

## Project structure

```
assignment/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   └── services/
│   │       ├── video_fetcher.py
│   │       ├── vector_store.py
│   │       └── rag.py
│   └── requirements.txt
├── frontend/
│   └── app/page.tsx
├── .env.example
└── README.md
```

## Assignment checklist

| Requirement | Status |
|-------------|--------|
| YouTube + Instagram URLs (dynamic ingest) | Yes |
| Transcript + full metadata | yt-dlp + youtube-transcript-api |
| Engagement rate `(likes+comments)/views×100` | Computed server-side |
| Chunk + embed + vector DB with `video_id` A/B | ChromaDB |
| LangChain RAG + 5 question types | Suggested prompts in UI |
| Stream + cite sources + memory | NDJSON stream, chunk citations, history-aware retriever |
| Next.js side-by-side cards + chat | Yes |
| README + `.env.example` + multiple commits | Yes |

**Install tip (Windows):** `cd backend; .\install.ps1` if `pip install -r requirements.txt` conflicts.

## Author

Varsha Pulikanti — technical screening submission.
