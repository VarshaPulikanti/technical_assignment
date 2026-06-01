# Start here (simple steps)

## What went wrong
OpenAI said **no quota** = your API key has **no money/credits** left.

---

## EASIEST FIX (about 5 minutes) — add OpenAI credits

1. Open: https://platform.openai.com/settings/billing  
2. Sign in (same account as your API key).  
3. Click **Add payment method** → add a card.  
4. Click **Add credits** → put **$5** (enough for demo + Loom).  
5. Wait 1–2 minutes.

6. **Restart backend** (terminal where uvicorn runs):
   - Press `Ctrl + C`
   - Run:
   ```
   cd c:\Users\pulik\OneDrive\study\ml\projects\assignment\backend
   .\.venv\Scripts\activate
   uvicorn app.main:app --reload --port 8000
   ```

7. Browser → http://localhost:3000  
8. Paste YouTube URL + Instagram Reel URL → **Analyze & Index**

---

## FREE FIX (no card) — Ollama on your PC

1. Install: https://ollama.com/download (Windows → download → install)  
2. Open **new** PowerShell and run:
   ```
   ollama pull llama3.2
   ollama pull nomic-embed-text
   ```
   (Wait until both finish — can take 10–20 min.)

3. Open `backend\.env` in Notepad. **Add these lines at the top:**
   ```
   LLM_PROVIDER=ollama
   EMBEDDING_PROVIDER=ollama
   OLLAMA_MODEL=llama3.2
   OLLAMA_EMBEDDING_MODEL=nomic-embed-text
   ```

4. Restart backend (same as step 6 above).  
5. Test on http://localhost:3000

---

## Every time you work on this project

**Terminal 1 — backend**
```
cd c:\Users\pulik\OneDrive\study\ml\projects\assignment\backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — frontend**
```
cd c:\Users\pulik\OneDrive\study\ml\projects\assignment\frontend
npm run dev
```

**Browser:** http://localhost:3000

---

## When it works → record Loom → submit

Copy the 4-field reply from README and paste your Loom link.
