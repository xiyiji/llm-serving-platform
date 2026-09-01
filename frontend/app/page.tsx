"use client";

import Link from "next/link";
import { demoTrend, ThroughputLatencyChart } from "@/components/Charts";

const LAYERS = [
  "OpenAI-compatible chat API with SSE streaming",
  "Model selection and request configuration for backend engines",
  "Health, latency, QPS and utilisation observability panels",
  "Backend routing, canary controls and rollout visibility",
];

const CAPABILITIES = [
  { name: "Adaptive routing", desc: "Latency- and health-aware backend selection per request" },
  { name: "Dynamic batching", desc: "Micro-batch formation (time window + queue depth) for engine saturation" },
  { name: "KV-cache reuse", desc: "Prefix caching so repeated system prompts skip prefill" },
  { name: "Safe rollout controls", desc: "Canary, blue-green and rolling releases with auto-rollback" },
];

const METRICS = [
  { label: "Request throughput", value: "1,032 QPS", hint: "Sustained across active models", icon: "〰" },
  { label: "GPU utilization", value: "86.8%", hint: "Cluster average", icon: "▣" },
  { label: "KV-cache hit rate", value: "68.2%", hint: "Repeated system prefixes", icon: "◫" },
  { label: "Cold start", value: "2.6s", hint: "Average time to model ready", icon: "⚡" },
];

export default function Home() {
  return (
    <>
      <div className="card">
        <div className="grid cols-2">
          <div>
            <span className="pill neutral">Production-shaped LLM platform</span>
            <h1 style={{ fontSize: 34, margin: "14px 0 10px", lineHeight: 1.15 }}>
              A serving platform for your LLM infra stack.
            </h1>
            <p className="sub" style={{ fontSize: 14.5 }}>
              A landing page, a real chat playground wired to{" "}
              <code>/v1/chat/completions</code>, and an admin dashboard for
              observability, routing, health and release workflows.
            </p>
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Link href="/chat"><button className="btn">Open Chat</button></Link>
              <Link href="/admin"><button className="btn secondary">Admin Dashboard</button></Link>
            </div>
          </div>
          <div>
            <h2>▤ Platform Layers</h2>
            <p className="sub">What this frontend is designed to show.</p>
            {LAYERS.map((l) => (
              <div className="list-tile" key={l}>{l}</div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid cols-4">
        {METRICS.map((m) => (
          <div className="card metric" key={m.label}>
            <div className="label">
              <span>{m.label}</span>
              <span className="icon-chip">{m.icon}</span>
            </div>
            <div className="value">{m.value}</div>
            <div className="hint">{m.hint}</div>
          </div>
        ))}
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>◔ Live Performance Snapshot</h2>
          <p className="sub">Representative infra metrics for demos and walkthroughs.</p>
          <ThroughputLatencyChart data={demoTrend()} />
        </div>
        <div className="card">
          <h2>≡ Core Capabilities</h2>
          <p className="sub">The system design pillars behind the platform.</p>
          {CAPABILITIES.map((c) => (
            <div className="list-tile" key={c.name}>
              <div className="name">{c.name}</div>
              <div className="desc">{c.desc}</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
