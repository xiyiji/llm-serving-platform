export const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface CompletionResponse {
  request_id: string;
  model: string;
  text: string;
  usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number };
  latency_ms: number;
  finish_reason: string;
  backend?: string;
  cached?: boolean;
}

function headers(apiKey?: string): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  if (apiKey) h["Authorization"] = `Bearer ${apiKey}`;
  return h;
}

export async function getJson<T>(base: string, path: string, apiKey?: string): Promise<T> {
  const res = await fetch(`${base}${path}`, { headers: headers(apiKey) });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return res.json();
}

export async function postJson<T>(
  base: string, path: string, body: unknown, apiKey?: string
): Promise<T> {
  const res = await fetch(`${base}${path}`, {
    method: "POST",
    headers: headers(apiKey),
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data?.error?.message || `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data as T;
}

/** Consume the gateway's SSE stream, invoking onDelta per text chunk. */
export async function streamChat(
  base: string,
  body: unknown,
  onDelta: (text: string) => void,
  apiKey?: string
): Promise<void> {
  const res = await fetch(`${base}/v1/chat/completions`, {
    method: "POST",
    headers: headers(apiKey),
    body: JSON.stringify(body),
  });
  if (!res.ok || !res.body) {
    let msg = `HTTP ${res.status}`;
    try { msg = (await res.json())?.error?.message || msg; } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const evt of events) {
      const line = evt.trim();
      if (!line.startsWith("data:")) continue;
      const payload = line.slice(5).trim();
      if (payload === "[DONE]") return;
      try {
        const parsed = JSON.parse(payload);
        if (parsed.error) throw new Error(parsed.error.message);
        if (parsed.delta) onDelta(parsed.delta);
      } catch (e) {
        if (e instanceof Error && e.message && !e.message.startsWith("Unexpected")) throw e;
      }
    }
  }
}
