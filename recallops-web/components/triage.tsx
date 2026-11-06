"use client";
// The pieces of the triage screen: alert strip, agent timeline, memory panel,
// suggestion with accept/reject/correct, and the resolve form.
import { useState } from "react";
import type { Incident, MemoryHit, Suggestion, Verdict } from "@/lib/types";
import type { Step } from "@/lib/useTriage";
import { ago } from "@/lib/time";
import { Button, Chip, OutcomeBadge, Skeleton } from "./ui";

export function AlertStrip({ incident }: { incident: Incident }) {
  const a = incident.alert;
  const cells: [string, string, boolean?][] = [
    ["Service", incident.service],
    ["Metric", a?.metric ?? "–"],
    ["Value", a?.value ?? "–", true],
    ["Threshold", a?.threshold ?? "–"],
    ["Fired", a?.fired_at ?? ago(incident.opened_at)],
  ];
  return (
    <div className="mb-8 grid grid-cols-2 gap-4 rounded-lg border border-line bg-panel px-5 py-4 sm:grid-cols-5">
      {cells.map(([k, v, hot]) => (
        <div key={k}>
          <div className="text-xs text-muted">{k}</div>
          <div className={`font-mono text-code ${hot ? "text-danger" : "text-ink"}`}>{v}</div>
        </div>
      ))}
    </div>
  );
}

const stepLabel = { thought: "Thinking", tool: "Tool", memory: "Memory" } as const;

export function Timeline({ steps, running }: { steps: Step[]; running: boolean }) {
  return (
    <ol className="relative ml-1 border-l border-line">
      {steps.map((s) => (
        <li key={s.id} className="step-in relative grid grid-cols-[96px_1fr] gap-4 py-2 pl-6">
          <span aria-hidden className="absolute -left-[4px] top-[15px] h-2 w-2 rounded-full bg-line" />
          <span className="pt-0.5 text-xs text-muted">{stepLabel[s.kind]}</span>
          <StepBody step={s} />
        </li>
      ))}
      {running && (
        <li className="relative grid grid-cols-[96px_1fr] gap-4 py-2 pl-6" aria-live="polite">
          <span aria-hidden className="absolute -left-[4px] top-[15px] h-2 w-2 rounded-full bg-accent motion-safe:animate-pulse" />
          <span className="pt-0.5 text-xs text-muted">Working</span>
          <span className="text-muted">…</span>
        </li>
      )}
    </ol>
  );
}

function StepBody({ step }: { step: Step }) {
  const [open, setOpen] = useState(false);
  if (step.kind === "thought") return <p>{step.text}</p>;
  if (step.kind === "memory")
    return <p>Recalled <span className="font-mono text-code">{step.incident_id}</span> from {ago(step.occurred_at)}.</p>;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-3">
        <code className="rounded bg-hover px-2 py-0.5 font-mono text-code">{step.tool}</code>
        {step.output && (
          <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}
            className="-my-2 min-h-[32px] px-1 text-xs font-medium text-accent hover:underline">
            {open ? "Hide output" : "Show output"}
          </button>
        )}
      </div>
      {open && step.output && (
        <pre className="mt-2 overflow-x-auto rounded border border-line bg-panel p-3 font-mono text-xs leading-5 text-ink-2">{step.output}</pre>
      )}
    </div>
  );
}

export function MemoryPanel({ memories, loading, error, memoryOff, onRetry }: {
  memories: MemoryHit[]; loading: boolean; error?: string; memoryOff: boolean; onRetry: () => void;
}) {
  return (
    <section aria-labelledby="mem-h">
      <h2 id="mem-h" className="text-base font-semibold">Memory used</h2>
      <p className="mb-4 text-xs text-muted">What the agent recalled from past incidents</p>

      {memoryOff && <Note>Memory is off for this run. The agent is answering without past incidents.</Note>}

      {!memoryOff && error && (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line bg-panel p-4">
          <p>Couldn’t reach incident memory.</p>
          <p className="-mt-2 text-muted">Triage continues without past incidents.</p>
          <Button onClick={onRetry}>Retry</Button>
        </div>
      )}

      {!memoryOff && !error && (
        <div className="flex flex-col gap-3">
          {memories.map((m) => <MemoryCard key={m.id} m={m} />)}
          {loading && memories.length === 0 && [0, 1, 2].map((i) => (
            <div key={i} role="status" aria-label="Loading past incidents" className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-4">
              <div className="flex justify-between"><Skeleton className="h-4 w-20" /><Skeleton className="h-4 w-16" /></div>
              <Skeleton className="h-4 w-full" /><Skeleton className="h-4 w-3/4" />
            </div>
          ))}
          {!loading && memories.length === 0 && (
            <Note>No similar past incidents found. The agent will remember this one once it’s resolved.</Note>
          )}
        </div>
      )}
    </section>
  );
}

function MemoryCard({ m }: { m: MemoryHit }) {
  return (
    <article className="step-in rounded-lg border border-line bg-panel p-4">
      <header className="mb-2 flex items-center justify-between gap-3">
        <span className="font-mono text-code font-medium">{m.incident_id}</span>
        <span className="text-xs text-muted">{ago(m.occurred_at)}</span>
      </header>
      {m.summary && <p className="mb-2 text-muted">{m.summary}</p>}
      <ul className="flex flex-col gap-2">
        {m.actions.map((a, i) => (
          <li key={i} className="flex items-start justify-between gap-3">
            <span>{a.text}</span>
            <OutcomeBadge o={a.outcome} />
          </li>
        ))}
      </ul>
    </article>
  );
}

const Note = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-lg border border-line bg-panel p-4 text-muted">{children}</div>
);

export function SuggestionBlock({ s, onVerdict }: {
  s: Suggestion;
  onVerdict: (v: Verdict, extra?: { actual_cause: string; fix_that_worked: string }) => Promise<void>;
}) {
  const [mode, setMode] = useState<"idle" | "correcting" | "sending">("idle");
  const [sent, setSent] = useState<Verdict | null>(null);
  const [cause, setCause] = useState("");
  const [fix, setFix] = useState("");

  async function send(v: Verdict) {
    setMode("sending");
    await onVerdict(v, v === "correct" ? { actual_cause: cause, fix_that_worked: fix } : undefined);
    setSent(v);
    setMode("idle");
  }

  return (
    <div className="step-in rounded-lg border border-l-2 border-line border-l-accent bg-panel p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-semibold">{s.steps ? s.root_cause : `Likely root cause: ${lower(s.root_cause)}`}</p>
        {s.confidence && <span className="text-xs text-muted">{cap(s.confidence)} confidence</span>}
      </div>
      {s.fix && <p className="mt-2">Recommended fix: {lower(s.fix)}</p>}
      {s.steps && (
        <ol className="mt-2 list-decimal pl-5">{s.steps.map((x) => <li key={x}>{x}</li>)}</ol>
      )}
      {s.avoid?.map((a) => <p key={a.text} className="mt-2 text-danger">Avoid {lower(a.text)}</p>)}
      {s.owner && <p className="mt-2 text-sm text-muted">Owner: {s.owner.team}{s.owner.person ? ` (${s.owner.person})` : ""}</p>}

      {sent ? (
        <p className="mt-5 text-sm text-ok" role="status">
          {sent === "accept" ? "Accepted. Saved to incident memory." : sent === "reject" ? "Rejected. The agent will weigh this lower next time." : "Correction saved. The agent will check this first next time."}
        </p>
      ) : (
        <div className="mt-5 flex flex-wrap gap-3">
          <Button variant="primary" onClick={() => send("accept")} disabled={mode === "sending"}>Accept</Button>
          <Button onClick={() => send("reject")} disabled={mode === "sending"}>Reject</Button>
          <Button variant={mode === "correcting" ? "primary" : "outline"} aria-expanded={mode === "correcting"}
            onClick={() => setMode(mode === "correcting" ? "idle" : "correcting")} disabled={mode === "sending"}>Correct</Button>
        </div>
      )}

      {mode !== "idle" && !sent && mode === "correcting" && (
        <form className="mt-5 flex flex-col gap-4 border-t border-line pt-5" onSubmit={(e) => { e.preventDefault(); send("correct"); }}>
          <Field label="What was the actual cause?">
            <textarea required rows={2} value={cause} onChange={(e) => setCause(e.target.value)}
              placeholder="e.g. Redis evictions on the session cache under sale traffic" className={inputCls} />
          </Field>
          <Field label="Fix that worked">
            <input value={fix} onChange={(e) => setFix(e.target.value)} placeholder="e.g. Raised Redis maxmemory" className={inputCls} />
          </Field>
          <p className="text-xs text-muted">The agent will check this first next time it sees a similar alert.</p>
          <div className="flex gap-3">
            <Button variant="primary" type="submit">Save correction</Button>
            <Button variant="quiet" onClick={() => setMode("idle")}>Cancel</Button>
          </div>
        </form>
      )}
    </div>
  );
}

export function ResolveForm({ onResolve, resolved }: {
  onResolve: (r: { root_cause: string; fix: string; failed_fixes: string; duration_min: number }) => Promise<void>;
  resolved: boolean;
}) {
  const [f, setF] = useState({ root_cause: "", fix: "", failed_fixes: "", duration_min: "" });
  const [saving, setSaving] = useState(false);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });

  if (resolved)
    return <div role="status" className="rounded-lg border border-line bg-panel p-5 text-ok">Resolved and saved to the team’s incident memory.</div>;

  return (
    <form
      className="flex flex-col gap-4 rounded-lg border border-line bg-panel p-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        await onResolve({ ...f, duration_min: Number(f.duration_min) || 0 });
        setSaving(false);
      }}
    >
      <Field label="Root cause"><input required value={f.root_cause} onChange={set("root_cause")} placeholder="e.g. Pool limit reduced in deploy #4412" className={inputCls} /></Field>
      <Field label="Fix applied"><input required value={f.fix} onChange={set("fix")} placeholder="e.g. Rolled back the pool config" className={inputCls} /></Field>
      <Field label="Fixes that did not work"><textarea rows={3} value={f.failed_fixes} onChange={set("failed_fixes")} placeholder="e.g. Restarted pods, no change" className={inputCls} /></Field>
      <Field label="Time to resolve">
        <span className="flex items-center gap-2">
          <input type="number" min={0} inputMode="numeric" value={f.duration_min} onChange={set("duration_min")} className={inputCls.replace("w-full", "w-24")} />
          <span className="text-muted">min</span>
        </span>
      </Field>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <p className="text-xs text-muted">Saved to the team’s incident memory.</p>
        <Button variant="primary" type="submit" disabled={saving}>{saving ? "Saving…" : "Resolve and save"}</Button>
      </div>
    </form>
  );
}

const inputCls = "w-full rounded-md border bg-panel px-3 py-2 text-base placeholder:text-muted/70 hover:border-ink-2 disabled:bg-hover";
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="flex flex-col gap-1.5"><span className="text-sm font-medium">{label}</span>{children}</label>;
}
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);
const lower = (s: string) => s[0].toLowerCase() + s.slice(1);

export function MemoryRefs({ ids }: { ids: string[] }) {
  return <div className="flex flex-wrap gap-2">{ids.map((i) => <Chip key={i}>{i}</Chip>)}</div>;
}
