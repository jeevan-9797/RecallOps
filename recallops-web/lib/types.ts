// Shared data shapes. These match the API contract in README.md.

export type Severity = 1 | 2 | 3;
export type IncidentStatus = "open" | "investigating" | "resolved";
export type Outcome = "worked" | "failed" | "partial";

export interface Incident {
  id: string;               // "INC-2041"
  severity: Severity;
  service: string;          // "checkout-api"
  title?: string;           // display title; falls back to summary
  summary: string;
  opened_at: string;        // ISO timestamp
  status: IncidentStatus;
  alert?: { metric: string; value: string; threshold: string; fired_at: string };
}

export interface MemoryAction { text: string; outcome: Outcome }

export interface MemoryHit {
  id: string;
  incident_id: string;      // "INC-1987"
  occurred_at: string;      // ISO timestamp; the UI renders "6 weeks ago"
  summary?: string;
  actions: MemoryAction[];  // one outcome per action, never per incident
}

export interface Suggestion {
  id: string;
  root_cause: string;
  confidence?: "high" | "medium" | "low";
  fix?: string;
  steps?: string[];         // generic answers (memory off) come as steps
  avoid?: { text: string; source_incident?: string }[];
  owner?: { team: string; person?: string };
  memory_refs?: string[];
}

// SSE events from POST /api/incidents/{id}/triage
export type TriageEvent =
  | { type: "thought"; data: { id: string; text: string } }
  | { type: "tool_call"; data: { id: string; tool: string; args?: unknown; output?: string } }
  | { type: "memory_hit"; data: MemoryHit }
  | { type: "suggestion"; data: Suggestion }
  | { type: "error"; data: { stage: "memory" | "llm" | "tool"; message: string; retryable?: boolean } }
  | { type: "done"; data: { memory: "on" | "off"; time_to_hypothesis_s?: number } };

export interface Pattern {
  id: string;
  statement: string;
  support: string;          // "Seen in 4 of the last 5 checkout latency incidents"
  last_seen_at: string;     // ISO timestamp
  incidents: string[];
}

export interface LearningCurve {
  points: { n: number; on: number; off: number }[];  // rolling top-1 accuracy, 0..1
  stats: { top1_on: number; top1_off: number; repeated_failed_fixes_on: number };
  sample?: boolean;         // true while numbers are placeholders
}

export type Verdict = "accept" | "reject" | "correct";
export interface Feedback {
  suggestion_id: string;
  verdict: Verdict;
  actual_cause?: string;
  fix_that_worked?: string;
}

export interface Resolution {
  root_cause: string;
  fix: string;
  failed_fixes?: string;
  duration_min: number;
}
