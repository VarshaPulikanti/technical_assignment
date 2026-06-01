"use client";

import { useCallback, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type VideoMeta = {
  video_id: string;
  url: string;
  platform: string;
  title: string;
  creator: string;
  follower_count: number | null;
  views: number;
  likes: number;
  comments: number;
  hashtags: string[];
  upload_date: string;
  duration_seconds: number;
  engagement_rate: number;
  thumbnail_url?: string | null;
};

type Source = {
  video_id: string;
  chunk_index: number;
  source_type: string;
  title: string;
  excerpt: string;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

const PROMPTS = [
  "Why did Video A get more engagement than Video B?",
  "What's the engagement rate of each?",
  "Compare the hooks in the first 5 seconds.",
  "Who's the creator of Video B and what's their follower count?",
  "Suggest improvements for B based on what worked in A.",
];

function formatNum(n: number) {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function thumbSrc(url: string | null | undefined) {
  if (!url) return undefined;
  return `${API_BASE}/api/thumbnail?url=${encodeURIComponent(url)}`;
}

function VideoCard({ v }: { v: VideoMeta }) {
  const isA = v.video_id === "A";
  const viewsLabel = v.views > 0 ? formatNum(v.views) : v.platform === "instagram" ? "Hidden by IG" : "0";
  const engagementLabel =
    v.views > 0 ? `${v.engagement_rate}%` : v.platform === "instagram" ? "N/A" : `${v.engagement_rate}%`;
  return (
    <div className={`video-card ${isA ? "a" : "b"}`}>
      <span className="badge">Video {v.video_id}</span>
      <span className="badge">{v.platform}</span>
      {v.thumbnail_url && (
        <img
          src={thumbSrc(v.thumbnail_url)}
          alt=""
          width={320}
          height={180}
          loading="lazy"
          style={{ width: "100%", maxHeight: 140, objectFit: "cover", borderRadius: 8, marginBottom: 8 }}
        />
      )}
      <h3>{v.title}</h3>
      <div className="stat-row">
        <span>
          Creator: <strong>{v.creator}</strong>
        </span>
        {v.follower_count != null && (
          <span>
            Followers: <strong>{formatNum(v.follower_count)}</strong>
          </span>
        )}
      </div>
      <div className="stat-row">
        <span>
          Views: <strong>{viewsLabel}</strong>
        </span>
        <span>
          Likes: <strong>{formatNum(v.likes)}</strong>
        </span>
        <span>
          Comments: <strong>{formatNum(v.comments)}</strong>
        </span>
        <span className="engagement">Engagement: {engagementLabel}</span>
      </div>
      <div className="stat-row">
        <span>Uploaded: {v.upload_date || "—"}</span>
        <span>Duration: {v.duration_seconds}s</span>
      </div>
      {v.hashtags?.length > 0 && (
        <div className="stat-row">
          {v.hashtags.slice(0, 8).map((h) => (
            <span key={h}>#{h.replace(/^#/, "")}</span>
          ))}
        </div>
      )}
      <a href={v.url} target="_blank" rel="noreferrer" style={{ fontSize: "0.8rem", color: "var(--accent)" }}>
        Open video
      </a>
    </div>
  );
}

export default function CreatorApp() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [videos, setVideos] = useState<VideoMeta[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const pollIndexStatus = useCallback(async (sid: string) => {
    for (let i = 0; i < 200; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const res = await fetch(`${API_BASE}/api/ingest/status/${sid}`);
        if (!res.ok) continue;
        const data = await res.json();
        if (data.chat_ready === true || data.status === "ready") {
          setIndexing(false);
          setStatus(`Chat ready. Click a question below. Session: ${sid}`);
          return;
        }
        if (typeof data.status === "string" && data.status.startsWith("error")) {
          setIndexing(false);
          setStatus(data.status);
          return;
        }
        setStatus(`Indexing for chat… (${(i + 1) * 3}s) — cards are ready below`);
      } catch {
        setStatus("Checking index status… (keep backend terminal open)");
      }
    }
    // indexing likely done but status poll missed — allow chat try
    setIndexing(false);
    setStatus("Indexing should be done — try chat. If error, Analyze once more.");
  }, []);

  const ingest = useCallback(async () => {
    if (!youtubeUrl.trim() || !instagramUrl.trim()) {
      setStatus("Both URLs are required.");
      return;
    }
    setLoading(true);
    setIndexing(false);
    setStatus("Fetching video data (1–3 min)…");
    setMessages([]);
    try {
      const res = await fetch(`${API_BASE}/api/ingest`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          youtube_url: youtubeUrl.trim(),
          instagram_url: instagramUrl.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const detail = data.detail;
        const msg = Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg).join(", ")
          : detail || "Ingest failed";
        throw new Error(msg);
      }
      setSessionId(data.session_id);
      setVideos(data.videos || []);
      setLoading(false);
      if (data.index_status === "indexing") {
        setIndexing(true);
        setStatus("Two videos loaded. Indexing for chat… (~5–15 min). Chat unlocks when ready.");
        void pollIndexStatus(data.session_id);
        // safety unlock so chat is not blocked forever
        setTimeout(() => {
          setIndexing((prev) => {
            if (prev) setStatus("Try chat now — indexing should be finished.");
            return false;
          });
        }, 2 * 60 * 1000);
      } else {
        setStatus(`Indexed ${data.chunk_count} chunks. Session: ${data.session_id}`);
      }
    } catch (e) {
      const err = e as Error;
      if (err.name === "AbortError") {
        setStatus("Request cancelled. Try again.");
      } else {
        setStatus(err.message || "Ingest failed");
      }
      setLoading(false);
    }
  }, [youtubeUrl, instagramUrl, pollIndexStatus]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!sessionId || !text.trim() || streaming || indexing) return;

      const userMsg: ChatMessage = { role: "user", content: text.trim() };
      setMessages((m) => [...m, userMsg]);
      setInput("");
      setStreaming(true);
      setStatus("Ollama is thinking… first reply can take 1–3 minutes. Please wait.");

      abortRef.current?.abort();
      const ac = new AbortController();
      abortRef.current = ac;

      let assistant = "";
      let sources: Source[] = [];

      setMessages((m) => [...m, { role: "assistant", content: "" }]);

      try {
        const res = await fetch(`${API_BASE}/api/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId, message: text.trim() }),
          signal: ac.signal,
        });
        if (!res.ok) {
          let detail = `Chat failed (${res.status})`;
          try {
            const errJson = await res.json();
            detail = typeof errJson.detail === "string" ? errJson.detail : detail;
          } catch {
            /* ignore */
          }
          throw new Error(detail);
        }
        if (!res.body) throw new Error("Chat request failed — no response body");

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.trim()) continue;
            const evt = JSON.parse(line);
            if (evt.type === "status") {
              setStatus(evt.content || "Thinking…");
            } else if (evt.type === "sources") {
              sources = evt.sources || [];
            } else if (evt.type === "token") {
              assistant += evt.content;
              setMessages((prev) => {
                const copy = [...prev];
                copy[copy.length - 1] = {
                  role: "assistant",
                  content: assistant,
                  sources,
                };
                return copy;
              });
            } else if (evt.type === "error") {
              throw new Error(evt.message);
            }
          }
        }
        setStatus("Ready");
      } catch (e) {
        if ((e as Error).name !== "AbortError") {
          const msg = e instanceof Error ? e.message : "Chat error";
          setStatus(msg);
          setMessages((prev) => {
            const copy = [...prev];
            if (copy.length && copy[copy.length - 1].role === "assistant") {
              copy[copy.length - 1] = { role: "assistant", content: `Error: ${msg}` };
            }
            return copy;
          });
        }
      } finally {
        setStreaming(false);
      }
    },
    [sessionId, streaming, indexing]
  );

  return (
    <main suppressHydrationWarning>
      <h1>Creator Video Compare</h1>
      <p className="subtitle">
        YouTube (A) vs Instagram Reel (B) — RAG chat with citations & memory
      </p>

      <div className="panel ingest-form">
        <label>YouTube URL (Video A)</label>
        <input
          value={youtubeUrl}
          onChange={(e) => setYoutubeUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={loading}
          suppressHydrationWarning
        />
        <label>Instagram Reel URL (Video B)</label>
        <input
          value={instagramUrl}
          onChange={(e) => setInstagramUrl(e.target.value)}
          placeholder="https://www.instagram.com/reel/..."
          disabled={loading}
          suppressHydrationWarning
        />
        <button type="button" onClick={ingest} disabled={loading} suppressHydrationWarning>
          {loading ? "Ingesting…" : "Analyze & Index"}
        </button>
        {status && (
          <p
            className={`status ${status.includes("fail") || status.includes("error") ? "error" : sessionId ? "ok" : ""}`}
          >
            {status}
          </p>
        )}
      </div>

      {videos.length === 2 && (
        <div className="video-grid">
          {videos.map((v) => (
            <VideoCard key={v.video_id} v={v} />
          ))}
        </div>
      )}

      <div className="panel chat-panel">
        <h2 style={{ margin: "0 0 0.5rem", fontSize: "1.1rem" }}>Chat</h2>
        <div className="suggestions">
          {PROMPTS.map((p) => (
            <button key={p} type="button" disabled={!sessionId || streaming || indexing} onClick={() => sendMessage(p)}>
              {p}
            </button>
          ))}
        </div>
        <div className="messages">
          {messages.length === 0 && (
            <p className="status">Ingest two videos, then ask comparison questions.</p>
          )}
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role}`}>
              {m.content}
              {m.sources && m.sources.length > 0 && (
                <ul className="sources">
                  {m.sources.map((s, j) => (
                    <li key={j}>
                      [Video {s.video_id}] {s.source_type}
                      {s.chunk_index >= 0 ? ` · chunk ${s.chunk_index}` : ""}: {s.excerpt}…
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
        <div className="chat-input-row">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && sendMessage(input)}
            placeholder={
              indexing ? "Wait — indexing for chat…" : sessionId ? "Ask about engagement, hooks, creators…" : "Ingest videos first"
            }
            disabled={!sessionId || streaming || indexing}
            suppressHydrationWarning
          />
          <button type="button" onClick={() => sendMessage(input)} disabled={!sessionId || streaming || indexing}>
            Send
          </button>
        </div>
      </div>
    </main>
  );
}
