"use client";

import { useCallback, useEffect, useState } from "react";
import { DEFAULT_API_BASE, getJson, postJson } from "@/lib/api";
import { demoTrend, GpuAreaChart, ThroughputLatencyChart, TrafficBarChart } from "@/components/Charts";

interface Health { status: string; uptime_s: number; version: string; details: Record<string, unknown>; }
interface Backends { default_backend: string; backends: any[]; model_mapping: Record<string, string>; }
interface Deployment {
  deployment_id: string; model: string; version: string; strategy: string;
  phase: string; traffic_pct: number; rollback_reason?: string | null;
}

function usePoll<T>(fn: () => Promise<T>, intervalMs: number): [T | null, string | null, () => void] {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const tick = useCallback(() => {
    fn().then((d) => { setData(d); setError(null); })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [fn]);
  useEffect(() => {
    tick();
    const id = setInterval(tick, intervalMs);
    return () => clearInterval(id);
  }, [tick, intervalMs]);
  return [data, error, tick];
}

export default function AdminPage() {
  const [apiBase, setApiBase] = useState(DEFAULT_API_BASE);
  const [apiKey, setApiKey] = useState("");

  const [health, healthErr] = usePoll<Health>(
    useCallback(() => getJson(apiBase, "/health", apiKey), [apiBase, apiKey]), 5000);
  const [backends, backendsErr] = usePoll<Backends>(
    useCallback(() => getJson(apiBase, "/v1/backends", apiKey), [apiBase, apiKey]), 5000);
  const [batch] = usePoll<any>(
    useCallback(() => getJson(apiBase, "/v1/batch/stats", apiKey), [apiBase, apiKey]), 5000);
  const [kv] = usePoll<any>(
    useCallback(() => getJson(apiBase, "/v1/kv-cache/stats", apiKey), [apiBase, apiKey]), 5000);
  const [alerts] = usePoll<any>(
    useCallback(() => getJson(apiBase, "/v1/alerts", apiKey), [apiBase, apiKey]), 6000);
  const [deployments, , refreshDeps] = usePoll<any>(
    useCallback(() => getJson(apiBase, "/v1/deployments", apiKey), [apiBase, apiKey]), 6000);
  const [registry] = usePoll<any>(
    useCallback(() => getJson(apiBase, "/v1/registry", apiKey), [apiBase, apiKey]), 10000);
  const [pool] = usePoll<any>(
    useCallback(() => getJson(apiBase, "/v1/cold-start/pool", apiKey), [apiBase, apiKey]), 6000);

  const [version, setVersion] = useState("v1.2.0");
  const [trafficPct, setTrafficPct] = useState(10);
  const [opMsg, setOpMsg] = useState<string | null>(null);

  const offline = !!healthErr;
  const trend = demoTrend();
  const traffic = (backends?.backends ?? []).map((b: any) => ({
    name: b.name, value: b.request_count ?? 0,
  }));

  async function startCanary() {
    try {
      const model = Object.keys(backends?.model_mapping ?? {})[0] ?? "llama-3.1-8b-instruct";
      const d = await postJson<Deployment>(apiBase, "/v1/deployments", {
        model, version, strategy: "canary", traffic_pct: trafficPct,
      }, apiKey);
      setOpMsg(`Canary ${d.deployment_id} started at ${d.traffic_pct}% traffic.`);
      refreshDeps();
    } catch (e) { setOpMsg(`Deploy failed: ${e instanceof Error ? e.message : e}`); }
  }

  async function act(id: string, action: "advance" | "rollback") {
    try {
      const d = await postJson<Deployment>(apiBase, `/v1/deployments/${id}/${action}`, {}, apiKey);
      setOpMsg(`${d.deployment_id}: ${d.phase} (${d.traffic_pct}% traffic)` +
               (d.rollback_reason ? ` — ${d.rollback_reason}` : ""));
      refreshDeps();
    } catch (e) { setOpMsg(`${action} failed: ${e instanceof Error ? e.message : e}`); }
  }

  return (
    <>
      <div className="card">
        <div className="grid cols-2eq">
          <div>
            <h2>⚙ Admin Dashboard</h2>
            <p className="sub">Observability, backend routing and serving controls.</p>
          </div>
          <div>
            <input className="text" value={apiBase} onChange={(e) => setApiBase(e.target.value)} />
            <input
              className="text" style={{ marginTop: 8 }} type="password"
              placeholder="API key (optional)"
              value={apiKey} onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
        </div>
        {offline && (
          <div className="list-tile" style={{ background: "var(--crit)", borderColor: "#fecaca", marginTop: 10 }}>
            <div className="name">Backend unreachable</div>
            <div className="desc">{healthErr} — panels show placeholders until the server responds.</div>
          </div>
        )}
      </div>

      <div className="grid cols-4">
        <div className="card metric">
          <div className="label"><span>Platform health</span><span className="icon-chip">♥</span></div>
          <div className="value">{health?.status ?? "—"}</div>
          <div className="hint">/health · v{health?.version ?? "?"} · up {Math.round(health?.uptime_s ?? 0)}s</div>
        </div>
        <div className="card metric">
          <div className="label"><span>Batch size</span><span className="icon-chip">→</span></div>
          <div className="value">{batch?.avg_batch_size ?? "—"}</div>
          <div className="hint">Average requests per micro-batch</div>
        </div>
        <div className="card metric">
          <div className="label"><span>KV hit rate</span><span className="icon-chip">◫</span></div>
          <div className="value">{kv ? `${Math.round((kv.hit_rate ?? 0) * 100)}%` : "—"}</div>
          <div className="hint">Prefix cache effectiveness</div>
        </div>
        <div className="card metric">
          <div className="label"><span>Default backend</span><span className="icon-chip">≡</span></div>
          <div className="value" style={{ fontSize: 22 }}>{backends?.default_backend ?? "—"}</div>
          <div className="hint">Backend adapter default</div>
        </div>
      </div>

      <div className="grid cols-2">
        <div className="card">
          <h2>◔ Serving Performance</h2>
          <p className="sub">Latency, throughput and GPU trend visualization.</p>
          <ThroughputLatencyChart data={trend} />
          <div style={{ height: 12 }} />
          <GpuAreaChart data={trend} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div className="card">
            <h2>⚠ Active Alerts</h2>
            <p className="sub">Rule engine over live platform state.</p>
            {(alerts?.active?.length ?? 0) === 0 && (
              <div className="list-tile">
                <div className="row">
                  <div className="name">No alerts firing</div>
                  <span className="pill ok">healthy</span>
                </div>
                <div className="desc">Latency, error rate, queue depth and cold starts inside thresholds.</div>
              </div>
            )}
            {(alerts?.active ?? []).map((a: any) => (
              <div className="list-tile" key={a.rule_name}>
                <div className="row">
                  <div className="name">{a.rule_name}</div>
                  <span className={`pill ${a.severity === "critical" ? "crit" : a.severity === "warning" ? "warn" : "info"}`}>
                    {a.severity}
                  </span>
                </div>
                <div className="desc">{a.message}</div>
              </div>
            ))}
            {(alerts?.history ?? []).slice(-2).reverse().filter((a: any) => a.status === "resolved").map((a: any, i: number) => (
              <div className="list-tile" key={`h${i}`}>
                <div className="row">
                  <div className="name">{a.rule_name}</div>
                  <span className="pill ok">resolved</span>
                </div>
                <div className="desc">{a.message}</div>
              </div>
            ))}
          </div>

          <div className="card">
            <h2>▷ Deployment Controls</h2>
            <p className="sub">Canary releases with auto-rollback on error-rate breach.</p>
            <label className="field">Version</label>
            <input className="text" value={version} onChange={(e) => setVersion(e.target.value)} />
            <label className="field">Canary traffic %</label>
            <input
              className="text" type="number" min={1} max={100}
              value={trafficPct} onChange={(e) => setTrafficPct(Number(e.target.value))}
            />
            <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
              <button className="btn" onClick={startCanary} disabled={offline}>Start canary</button>
            </div>
            {opMsg && <p className="sub" style={{ marginTop: 10 }}>{opMsg}</p>}
          </div>
        </div>
      </div>

      <div className="grid cols-2eq">
        <div className="card">
          <h2>≡ Backend Adapter</h2>
          <p className="sub">Live backend routing and health.</p>
          {backendsErr && <div className="list-tile"><div className="desc">Unavailable: {backendsErr}</div></div>}
          {(backends?.backends ?? []).map((b: any) => (
            <div className="list-tile" key={b.name}>
              <div className="row">
                <div>
                  <div className="name">{b.name}</div>
                  <div className="desc">{b.kind} · routed {b.routed} time(s)</div>
                </div>
                <span className={`pill ${b.healthy ? "ok" : "crit"}`}>{b.healthy ? "healthy" : "down"}</span>
              </div>
              <div className="badge-row" style={{ marginTop: 10 }}>
                <span className="chip">Avg latency {b.avg_latency_ms} ms</span>
                <span className="chip">Requests {b.request_count}</span>
                <span className="chip">Errors {b.error_count}</span>
              </div>
            </div>
          ))}
          <h2 style={{ marginTop: 18 }}>◫ Warm Pool</h2>
          <p className="sub">
            {pool ? `${pool.pool_size}/${pool.pool_capacity} warm · ${pool.eviction_policy} eviction` : "—"}
          </p>
          {(pool?.models ?? []).map((m: any) => (
            <div className="list-tile" key={m.id}>
              <div className="row">
                <div className="name">{m.id}</div>
                <span className={`pill ${m.status === "warm" ? "ok" : "neutral"}`}>{m.status}</span>
              </div>
              <div className="desc">load {m.load_time_s}s · used {m.use_count}×</div>
            </div>
          ))}
        </div>

        <div className="card">
          <h2>→ Route Distribution</h2>
          <p className="sub">Requests handled per backend.</p>
          <TrafficBarChart data={traffic.length ? traffic : [{ name: "primary", value: 0 }]} />
          <h2 style={{ marginTop: 18 }}>⟳ Releases & Registry</h2>
          <p className="sub">Deployment history and governed model versions.</p>
          {(deployments?.deployments ?? []).slice(0, 4).map((d: Deployment) => (
            <div className="list-tile" key={d.deployment_id}>
              <div className="row">
                <div className="name">{d.model} → {d.version}</div>
                <span className={`pill ${d.phase === "live" ? "ok" : d.phase === "rolled_back" ? "crit" : "info"}`}>
                  {d.phase}
                </span>
              </div>
              <div className="desc">
                {d.strategy} · {d.traffic_pct}% traffic
                {d.rollback_reason ? ` · ${d.rollback_reason}` : ""}
              </div>
              {d.phase !== "live" && d.phase !== "rolled_back" && (
                <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
                  <button className="btn secondary" onClick={() => act(d.deployment_id, "advance")}>Advance</button>
                  <button className="btn danger" onClick={() => act(d.deployment_id, "rollback")}>Rollback</button>
                </div>
              )}
            </div>
          ))}
          {(registry?.models ?? []).slice(0, 3).map((m: any) => (
            <div className="list-tile" key={`${m.model_id}:${m.version}`}>
              <div className="row">
                <div className="name">{m.model_id}:{m.version}</div>
                <span className="pill neutral">{m.stage}</span>
              </div>
              <div className="desc">{m.deployment_history?.length ?? 0} deployment event(s)</div>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
