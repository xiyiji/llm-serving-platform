"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export interface TrendPoint {
  t: string;
  throughput: number;
  latency: number;
  gpu: number;
}

/** Representative trend series for demo panels when live history is thin. */
export function demoTrend(): TrendPoint[] {
  const points: TrendPoint[] = [];
  for (let i = 0; i <= 6; i++) {
    const minutes = i * 5;
    points.push({
      t: `12:${minutes.toString().padStart(2, "0")}`,
      throughput: Math.round(620 + i * 48 + Math.sin(i) * 12),
      latency: Math.round(58 + Math.sin(i * 1.7) * 9),
      gpu: Math.round(71 + i * 3.2 - Math.max(0, i - 4) * 1.5),
    });
  }
  return points;
}

export function ThroughputLatencyChart({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={230}>
      <LineChart data={data} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
        <CartesianGrid strokeDasharray="4 4" stroke="#e5eaf1" />
        <XAxis dataKey="t" tick={{ fontSize: 12, fill: "#64748b" }} />
        <YAxis tick={{ fontSize: 12, fill: "#64748b" }} />
        <Tooltip />
        <Line type="monotone" dataKey="throughput" name="tokens/s" stroke="#2563eb" strokeWidth={2} dot={false} />
        <Line type="monotone" dataKey="latency" name="p95 ms" stroke="#0ea5e9" strokeWidth={2} dot={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function GpuAreaChart({ data }: { data: TrendPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={190}>
      <AreaChart data={data} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
        <CartesianGrid strokeDasharray="4 4" stroke="#e5eaf1" />
        <XAxis dataKey="t" tick={{ fontSize: 12, fill: "#64748b" }} />
        <YAxis domain={[0, 100]} tick={{ fontSize: 12, fill: "#64748b" }} />
        <Tooltip />
        <Area type="monotone" dataKey="gpu" name="GPU %" stroke="#2563eb" fill="#dbeafe" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function TrafficBarChart({ data }: { data: { name: string; value: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 6, right: 12, left: -14, bottom: 0 }}>
        <CartesianGrid strokeDasharray="4 4" stroke="#e5eaf1" />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#64748b" }} />
        <YAxis tick={{ fontSize: 12, fill: "#64748b" }} />
        <Tooltip />
        <Bar dataKey="value" name="requests" fill="#101828" radius={[6, 6, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
