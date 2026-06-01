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

function VideoCard({ v }: { v: VideoMeta }) {
  const isA = v.video_id === "A";
  return (
    <div className={`video-card ${isA ? "a" : "b"}`}>
      <span className="badge">Video {v.video_id}</span>
      <span className="badge">{v.platform}</span>
      {v.thumbnail_url && (
        <img
          src={v.thumbnail_url}
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
          Views: <strong>{formatNum(v.views)}</strong>
        </span>
        <span>
          Likes: <strong>{formatNum(v.likes)}</strong>
        </span>
        <span>
          Comments: <strong>{formatNum(v.comments)}</strong>
        </span>
        <span className="engagement">Engagement: {v.engagement_rate}%</span>
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

export default function Home() {
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [instagramUrl, setInstagramUrl] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [videos, setVideos] = useState<VideoMeta[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const ingest = useCallback(async () => {
    if (!youtubeUrl.trim() || !instagramUrl.trim()) {
      setStatus("Both URLs are required.");
      return;
    }
    setLoading(true);
    setStatus("Fetching transcripts & metadata…");
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
      setStatus(`Indexed ${data.chunk_count} chunks. Session: ${data.session_id}`);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "Ingest failed");
    } finally {
      setLoading(false);
    }
  }, [youtubeUrl, instagramUrl]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!sessionId || !text.trim() || streaming) return;

      const userMsg: ChatMessage = { role: "user", content: text.trim() };
      setMessages((m) => [...m, userMsg]);
      setInput("");
      setStreaming(true);
      setStatus("Streaming answer…");

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
        if (!res.ok || !res.body) throw new Error("Chat request failed");

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
            if (evt.type === "sources") {
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
          setStatus(e instanceof Error ? e.message : "Chat error");
        }
      } finally {
        setStreaming(false);
      }
    },
    [sessionId, streaming]
  );

  return (
    <main>
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
        />
        <label>Instagram Reel URL (Video B)</label>
        <input
          value={instagramUrl}
          onChange={(e) => setInstagramUrl(e.target.value)}
          placeholder="https://www.instagram.com/reel/..."
          disabled={loading}
        />
        <button onClick={ingest} disabled={loading}>
          {loading ? "Ingesting…" : "Analyze & Index"}
        </button>
        {status && <p className={`status ${status.includes("fail") || status.includes("error") ? "error" : sessionId ? "ok" : ""}`}>{status}</p>}
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
            <button key={p} type="button" disabled={!sessionId || streaming} onClick={() => sendMessage(p)}>
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
            placeholder={sessionId ? "Ask about engagement, hooks, creators…" : "Ingest videos first"}
            disabled={!sessionId || streaming}
          />
          <button onClick={() => sendMessage(input)} disabled={!sessionId || streaming}>
            Send
          </button>
        </div>
      </div>
    </main>
  );
}
