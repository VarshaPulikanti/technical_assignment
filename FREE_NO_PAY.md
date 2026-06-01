# Free setup (no payment)

## Part 1 — Install Ollama (one time, ~5 min)

1. Open: **https://ollama.com/download**
2. Click **Download for Windows** → run the installer → finish install.
3. Close and open a **new** PowerShell window.
4. Run these two commands (wait until each finishes — downloads ~2–4 GB total):

```
ollama pull llama3.2
ollama pull mxbai-embed-large
```

5. Check Ollama is running:

```
ollama list
```

You should see `llama3.2` and `nomic-embed-text` in the list.

---

## Part 2 — Your project is already set to FREE mode

File `backend\.env` already has:

- `LLM_PROVIDER=ollama`
- `EMBEDDING_PROVIDER=ollama`

No OpenAI money needed.

---

## Part 3 — Run the app (every time)

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

Paste YouTube + Instagram URLs → **Analyze & Index**

First run can take **2–5 minutes** (slow but free).

---

## If `ollama` command not found

- Restart PC after installing Ollama, OR
- Open **Ollama** from Start menu (keeps it running in tray)

---

## Loom tip

Say: *"Production would use OpenAI for scale; for this demo I used Ollama locally to avoid API cost."*
