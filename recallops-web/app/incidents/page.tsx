"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { fireDemoAlert, getIncidents, resetDemo } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { ago } from "@/lib/time";
import { Button, PageHeader, SeverityBadge, Skeleton, Stat, StatusBadge } from "@/components/ui";

export default function IncidentsPage() {
  const router = useRouter();
  const [rows, setRows] = useState<Incident[] | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<"fire" | "reset" | null>(null);

  const load = useCallback(() => {
    setError(undefined);
    getIncidents().then(setRows).catch((e) => setError(e.message));
  }, []);
  useEffect(load, [load]);

  async function fire() {
    setBusy("fire");
    try {
      const { id } = await fireDemoAlert();
      router.push(`/incidents/${id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }
  async function reset() {
    setBusy("reset");
    try { await resetDemo(); load(); } catch (e) { setError((e as Error).message); }
    setBusy(null);
  }

  const open = rows?.filter((r) => r.status !== "resolved").length;
  const sev1 = rows?.filter((r) => r.status !== "resolved" && r.severity === 1).length;
  const resolvedWeek = rows?.filter((r) => r.status === "resolved" && Date.now() - +new Date(r.opened_at) < 7 * 864e5).length;

  return (
    <>
      <PageHeader
        title="Incidents"
        actions={<>
          <Button variant="quiet" onClick={reset} disabled={busy !== null}>{busy === "reset" ? "Resetting…" : "Reset demo"}</Button>
          <Button variant="primary" onClick={fire} disabled={busy !== null}>{busy === "fire" ? "Firing…" : "Fire demo alert"}</Button>
        </>}
      />

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Stat value={open ?? "–"} label="Open incidents" />
        <Stat value={sev1 ?? "–"} label="Sev 1 open" />
        <Stat value={resolvedWeek ?? "–"} label="Resolved in the last 7 days" />
      </div>

      <div className="overflow-x-auto rounded-lg border border-line bg-panel">
        <table className="w-full min-w-[840px] border-collapse text-left">
          <thead>
            <tr className="border-b border-line bg-page text-xs text-muted">
              <th className="w-24 px-4 py-3 font-medium">Severity</th>
              <th className="w-32 px-4 py-3 font-medium">Incident</th>
              <th className="w-44 px-4 py-3 font-medium">Service</th>
              <th className="px-4 py-3 font-medium">Summary</th>
              <th className="w-32 px-4 py-3 font-medium">Opened</th>
              <th className="w-36 px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {error && (
              <tr><td colSpan={6} className="px-4 py-8">
                <p>Couldn’t load incidents.</p>
                <p className="mt-1 text-sm text-muted">{error}</p>
                <Button className="mt-3" onClick={load}>Retry</Button>
              </td></tr>
            )}
            {!error && !rows && Array.from({ length: 6 }, (_, i) => (
              <tr key={i} className="border-b border-line last:border-0">
                {[14, 20, 28, 64, 16, 20].map((w, j) => (
                  <td key={j} className="px-4 py-4"><Skeleton className="h-4" style={{ maxWidth: w * 4 }} /></td>
                ))}
              </tr>
            ))}
            {!error && rows?.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-8">
                <p>No incidents yet.</p>
                <p className="mt-1 text-sm text-muted">Fire the demo alert to start a triage.</p>
              </td></tr>
            )}
            {rows?.map((r) => (
              <tr
                key={r.id}
                onClick={() => router.push(`/incidents/${r.id}`)}
                className="cursor-pointer border-b border-line transition-colors last:border-0 hover:bg-hover"
              >
                <td className="px-4 py-3.5"><SeverityBadge s={r.severity} /></td>
                <td className="px-4 py-3.5 font-mono text-code tabular-nums">
                  <Link href={`/incidents/${r.id}`} onClick={(e) => e.stopPropagation()} className="hover:underline">{r.id}</Link>
                </td>
                <td className="px-4 py-3.5 font-mono text-code text-muted">{r.service}</td>
                <td className="px-4 py-3.5">{r.summary}</td>
                <td className="px-4 py-3.5 text-muted tabular-nums">{ago(r.opened_at)}</td>
                <td className="px-4 py-3.5"><StatusBadge s={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
