// Small building blocks shared by every page.
import type { ButtonHTMLAttributes, ReactNode } from "react";
import type { IncidentStatus, Outcome, Severity } from "@/lib/types";

type Tone = "danger" | "warn" | "ok" | "neutral";
const toneClass: Record<Tone, string> = {
  danger: "border-danger text-danger",
  warn: "border-warn text-warn",
  ok: "border-ok text-ok",
  neutral: "border-line text-muted",
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span className={`inline-flex shrink-0 items-center rounded border px-2 py-px text-xs font-medium ${toneClass[tone]}`}>
      {children}
    </span>
  );
}

export const SeverityBadge = ({ s }: { s: Severity }) => (
  <Badge tone={s === 1 ? "danger" : s === 2 ? "warn" : "neutral"}>Sev {s}</Badge>
);

const statusLabel: Record<IncidentStatus, [string, Tone]> = {
  open: ["Open", "danger"],
  investigating: ["Investigating", "warn"],
  resolved: ["Resolved", "ok"],
};
export const StatusBadge = ({ s }: { s: IncidentStatus }) => <Badge tone={statusLabel[s][1]}>{statusLabel[s][0]}</Badge>;

const outcomeLabel: Record<Outcome, [string, Tone]> = {
  worked: ["Worked", "ok"],
  failed: ["Failed", "danger"],
  partial: ["Partly worked", "warn"],
};
export const OutcomeBadge = ({ o }: { o: Outcome }) => <Badge tone={outcomeLabel[o][1]}>{outcomeLabel[o][0]}</Badge>;

type Variant = "primary" | "outline" | "quiet";
const variantClass: Record<Variant, string> = {
  primary: "bg-accent text-white border-accent hover:bg-accent-hover hover:border-accent-hover",
  outline: "bg-panel text-ink border-line hover:bg-hover hover:border-field",
  quiet: "bg-transparent text-muted border-transparent hover:text-ink hover:bg-hover",
};
export function Button({ variant = "outline", className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      type="button"
      {...p}
      className={`inline-flex h-9 items-center justify-center rounded-md border px-4 text-sm font-medium transition-colors ${variantClass[variant]} ${className}`}
    />
  );
}

export function Chip({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center rounded border border-line bg-hover px-2 py-0.5 font-mono text-xs text-ink">{children}</span>;
}

export function PageHeader({ title, sub, crumbs, actions }: { title: ReactNode; sub?: ReactNode; crumbs?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-8">
      {crumbs && <nav aria-label="Breadcrumb" className="mb-2 text-sm text-muted">{crumbs}</nav>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-ink">{title}</h1>
        {actions && <div className="flex flex-wrap items-center gap-3">{actions}</div>}
      </div>
      {sub && <p className="mt-1 text-base text-muted">{sub}</p>}
    </div>
  );
}

export function Stat({ value, label }: { value: ReactNode; label: string }) {
  return (
    <div className="rounded-lg border border-line bg-panel p-5">
      <div className="text-3xl font-semibold tabular-nums text-ink">{value}</div>
      <div className="mt-1 text-xs text-muted">{label}</div>
    </div>
  );
}

export function Skeleton({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div aria-hidden style={style} className={`rounded bg-skeleton motion-safe:animate-pulse ${className}`} />;
}
