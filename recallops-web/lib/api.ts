// Every call to the backend goes through this file.
// No NEXT_PUBLIC_API_BASE set → built-in mock data, so the UI runs without a backend.
import type { Feedback, Incident, LearningCurve, Pattern, Resolution, TriageEvent } from "./types";
import { mockIncidents, mockLearningCurve, mockPatterns, mockTriage } from "./mock";
import { readSSE } from "./sse";

const BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");
export const isMock = BASE === "";

const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((res, rej) => {
    const t = setTimeout(res, ms);
    signal?.addEventListener("abort", () => { clearTimeout(t); rej(new DOMException("aborted", "AbortError")); });
  });

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status}`);
  return res.status === 204 ? (undefined as T) : res.json();
}

// In-memory state for mock mode (resets on page reload).
const mockState = { resolved: new Set<string>() };

export async function getIncidents(): Promise<Incident[]> {
  if (isMock) return mockIncidents().map((i) => (mockState.resolved.has(i.id) ? { ...i, status: "resolved" } : i));
  return http("/api/incidents");
}

export async function getIncident(id: string): Promise<Incident | undefined> {
  if (isMock) return (await getIncidents()).find((i) => i.id === id);
  return http(`/api/incidents/${encodeURIComponent(id)}`);
}

export async function getPatterns(): Promise<Pattern[]> {
  if (isMock) return mockPatterns();
  return http("/api/observations");
}

export async function getLearningCurve(): Promise<LearningCurve> {
  if (isMock) return mockLearningCurve();
  return http("/api/metrics/learning-curve");
}

export async function fireDemoAlert(): Promise<{ id: string }> {
  if (isMock) return { id: "INC-2041" };
  return http("/api/alerts", {
    method: "POST",
    body: JSON.stringify({ service: "checkout-api", metric: "p99_latency", value: 6.2, threshold: 2, unit: "s", demo: true }),
  });
}

export async function resetDemo(): Promise<void> {
  if (isMock) { mockState.resolved.clear(); return; }
  await http("/api/demo/reset", { method: "POST" });
}

export async function sendFeedback(id: string, fb: Feedback): Promise<void> {
  if (isMock) { await sleep(300); return; }
  await http(`/api/incidents/${encodeURIComponent(id)}/feedback`, { method: "POST", body: JSON.stringify(fb) });
}

export async function resolveIncident(id: string, r: Resolution): Promise<void> {
  if (isMock) { await sleep(400); mockState.resolved.add(id); return; }
  await http(`/api/incidents/${encodeURIComponent(id)}/resolve`, { method: "POST", body: JSON.stringify(r) });
}

// Streams the agent's triage. Real mode: POST + text/event-stream. Mock: the same events, paced.
export async function* streamTriage(id: string, memory: boolean, signal?: AbortSignal): AsyncGenerator<TriageEvent> {
  if (isMock) {
    for (const ev of mockTriage(id, memory)) {
      await sleep(ev.type === "memory_hit" ? 550 : ev.type === "suggestion" ? 900 : 700, signal);
      yield ev;
    }
    return;
  }
  const res = await fetch(`${BASE}/api/incidents/${encodeURIComponent(id)}/triage${memory ? "" : "?memory=off"}`, {
    method: "POST",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Triage stream failed: ${res.status}`);
  yield* readSSE(res.body);
}
