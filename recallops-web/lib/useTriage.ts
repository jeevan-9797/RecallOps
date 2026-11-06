"use client";
import { useCallback, useEffect, useState } from "react";
import { streamTriage } from "./api";
import type { MemoryHit, Suggestion, TriageEvent } from "./types";

export type Step =
  | { kind: "thought"; id: string; text: string }
  | { kind: "tool"; id: string; tool: string; output?: string }
  | { kind: "memory"; id: string; incident_id: string; occurred_at: string };

export interface TriageState {
  status: "running" | "done" | "failed";
  steps: Step[];
  memories: MemoryHit[];
  suggestion?: Suggestion;
  memoryError?: string;     // memory unreachable; triage continues
  fatalError?: string;      // stream itself broke
  timeToHypothesis?: number;
}

const initial: TriageState = { status: "running", steps: [], memories: [] };

// Runs one triage stream and folds the events into screen state.
export function useTriage(incidentId: string, memory: boolean) {
  const [state, setState] = useState<TriageState>(initial);
  const [run, setRun] = useState(0);
  const retry = useCallback(() => setRun((r) => r + 1), []);

  useEffect(() => {
    const ctrl = new AbortController();
    setState(initial);
    (async () => {
      try {
        for await (const ev of streamTriage(incidentId, memory, ctrl.signal)) {
          setState((s) => reduce(s, ev));
        }
        setState((s) => (s.status === "running" ? { ...s, status: "done" } : s));
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        setState((s) => ({ ...s, status: "failed", fatalError: (e as Error).message }));
      }
    })();
    return () => ctrl.abort();
  }, [incidentId, memory, run]);

  return { ...state, retry };
}

// Pure: React may call it twice in dev, so no side effects here.
function reduce(s: TriageState, ev: TriageEvent): TriageState {
  switch (ev.type) {
    case "thought":
      return { ...s, steps: [...s.steps, { kind: "thought", id: ev.data.id, text: ev.data.text }] };
    case "tool_call":
      return { ...s, steps: [...s.steps, { kind: "tool", id: ev.data.id, tool: ev.data.tool, output: ev.data.output }] };
    case "memory_hit": {
      if (s.memories.some((m) => m.id === ev.data.id)) return s; // ignore duplicate events
      return {
        ...s,
        memories: [...s.memories, ev.data],
        steps: [...s.steps, { kind: "memory", id: `mem-${ev.data.id}`, incident_id: ev.data.incident_id, occurred_at: ev.data.occurred_at }],
      };
    }
    case "suggestion":
      return { ...s, suggestion: ev.data };
    case "error":
      // A memory failure is shown in the memory panel; triage keeps going.
      if (ev.data.stage === "memory") return { ...s, memoryError: ev.data.message };
      return { ...s, status: "failed", fatalError: ev.data.message };
    case "done":
      return { ...s, status: "done", timeToHypothesis: ev.data.time_to_hypothesis_s };
    default:
      return s;
  }
}
