"use client";

import { useMemo, useRef, useState } from "react";
import {
  DEFAULT_API_BASE,
  getJson,
  postJson,
  streamChat,
  type ChatMessage,
  type CompletionResponse,
} from "@/lib/api";

const MODELS = ["llama-3.1-8b-instruct", "mistral-7b-instruct"];

interface UiMessage extends ChatMessage {
  meta?: string;
  error?: boolean;
}

export default function ChatPage() {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState(MODELS[0]);
  const [systemPrompt, setSystemPrompt] = useState(
    "You are a helpful assistant for debugging infrastructure and system design questions."
  );
  const [temperature, setTemperature] = useState(0.7);
  const [streaming, setStreaming] = useState(true);
  const [connection, setConnection] = useState<"idle" | "checking" | "healthy" | "down">("idle");
  const [input, setInput] = useState(
    "Explain how adaptive routing, batching, and KV-cache work together in an LLM serving platform."
  );
  const [messages, setMessages] = useState<UiMessage[]>([
    {
      role: "assistant",
      content:
        "Console ready. Set your base URL and send a real request to /v1/chat/completions.",
    },
  ]);
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const curl = useMemo(() => {
    const body = {
      model,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: input },
      ],
      temperature,
      stream: streaming,
    };
    const auth = apiKey ? `  -H 'Authorization: Bearer ${apiKey}' \\\n` : "";
    return `curl -X POST ${apiBase}/v1/chat/completions \\\n  -H 'Content-Type: application/json' \\\n${auth}  -d '${JSON.stringify(body, null, 2)}'`;
  }, [apiBase, apiKey, model, systemPrompt, input, temperature, streaming]);

  async function checkConnection() {
    setConnection("checking");
    try {
      await getJson(apiBase, "/health", apiKey);
      setConnection("healthy");
    } catch {
      setConnection("down");
    }
  }

  function scrollDown() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });
  }

  async function send() {
    if (!input.trim() || busy) return;
    const userMsg: UiMessage = { role: "user", content: input };
    const history = [...messages.filter((m) => !m.error), userMsg];
    setMessages([...history, { role: "assistant", content: streaming ? "" : "…" }]);
    setBusy(true);
    setInput("");
    scrollDown();

    const payload = {
      model,
      messages: [
        { role: "system", content: systemPrompt },
        ...history
          .filter((m) => m.role !== "system")
          .map(({ role, content }) => ({ role, content })),
      ],
      temperature,
      stream: streaming,
    };

    const started = performance.now();
    try {
      if (streaming) {
        let acc = "";
        await streamChat(
          apiBase,
          payload,
          (delta) => {
            acc += delta;
            setMessages((cur) => [
              ...cur.slice(0, -1),
              { role: "assistant", content: acc },
            ]);
            scrollDown();
          },
          apiKey
        );
        const ms = Math.round(performance.now() - started);
        setMessages((cur) => [
          ...cur.slice(0, -1),
          { role: "assistant", content: acc, meta: `${model} · streamed · ${ms} ms` },
        ]);
      } else {
        const res = await postJson<CompletionResponse>(
          apiBase, "/v1/chat/completions", payload, apiKey
        );
        setMessages((cur) => [
          ...cur.slice(0, -1),
          {
            role: "assistant",
            content: res.text,
            meta: `${res.model} · ${res.latency_ms} ms · ${res.usage.total_tokens} tokens${res.cached ? " · cache hit" : ""}`,
          },
        ]);
      }
    } catch (e) {
      setMessages((cur) => [
        ...cur.slice(0, -1),
        {
          role: "assistant",
          content: `Request failed: ${e instanceof Error ? e.message : String(e)}`,
          error: true,
        },
      ]);
    } finally {
      setBusy(false);
      scrollDown();
    }
  }

  return (
    <div className="grid cols-2" style={{ gridTemplateColumns: "420px 1fr", alignItems: "start" }}>
      <div className="card">
        <h2>▢ Configuration</h2>
        <p className="sub">Wire the console directly to your backend.</p>

        <label className="field">API Base</label>
        <input className="text" value={apiBase} onChange={(e) => setApiBase(e.target.value)} />

        <label className="field">API Key</label>
        <input
          className="text" type="password" placeholder="Optional bearer token"
          value={apiKey} onChange={(e) => setApiKey(e.target.value)}
        />

        <div className="list-tile" style={{ marginTop: 14 }}>
          <div className="row">
            <div>
              <div className="name">Connection</div>
              <div className="desc">Checks /health on your server</div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span className={`pill ${connection === "healthy" ? "ok" : connection === "down" ? "crit" : "neutral"}`}>
                {connection}
              </span>
              <button className="btn secondary" onClick={checkConnection}>Check</button>
            </div>
          </div>
        </div>

        <label className="field">Model</label>
        <select className="text" value={model} onChange={(e) => setModel(e.target.value)}>
          {MODELS.map((m) => <option key={m}>{m}</option>)}
        </select>

        <label className="field">System Prompt</label>
        <textarea
          className="text" rows={3}
          value={systemPrompt} onChange={(e) => setSystemPrompt(e.target.value)}
        />

        <div style={{ display: "flex", gap: 14, alignItems: "flex-end" }}>
          <div style={{ flex: 1 }}>
            <label className="field">Temperature</label>
            <input
              className="text" type="number" step="0.1" min="0" max="2"
              value={temperature}
              onChange={(e) => setTemperature(Number(e.target.value))}
            />
          </div>
          <div className="list-tile" style={{ flex: 1, marginBottom: 0 }}>
            <div className="row">
              <div>
                <div className="name">Streaming</div>
                <div className="desc">Streams via SSE</div>
              </div>
              <button
                className={`toggle ${streaming ? "on" : ""}`}
                onClick={() => setStreaming(!streaming)}
                aria-label="toggle streaming"
              />
            </div>
          </div>
        </div>

        <label className="field">cURL Preview</label>
        <div className="code-block">{curl}</div>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <h2>▷ Chat Playground</h2>
            <p className="sub">Calls your real <code>/v1/chat/completions</code> endpoint.</p>
          </div>
          <div className="badge-row">
            <span className="chip">Model: {model}</span>
            <span className="chip">Stream {streaming ? "on" : "off"}</span>
          </div>
        </div>

        <div className="chat-scroll" ref={scrollRef}>
          {messages.map((m, i) => (
            <div key={i} className={`msg ${m.role} ${m.error ? "error" : ""}`}>
              <div className="role">{m.role}</div>
              <div>{m.content}</div>
              {m.meta && <div className="meta">{m.meta}</div>}
            </div>
          ))}
        </div>

        <div style={{ marginTop: 14 }}>
          <textarea
            className="text" rows={3} value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: 10, alignItems: "center" }}>
            <div className="badge-row">
              <span className="chip">OpenAI-compatible</span>
              <span className="chip">Bearer auth supported</span>
            </div>
            <button className="btn" onClick={send} disabled={busy}>
              {busy ? "Generating…" : "Send"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
