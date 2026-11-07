"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getIncident, resolveIncident, sendFeedback } from "@/lib/api";
import type { Incident } from "@/lib/types";
import { useTriage } from "@/lib/useTriage";
import { PageHeader, SeverityBadge, Skeleton, StatusBadge, Button } from "@/components/ui";
import { AlertStrip, MemoryPanel, ResolveForm, SuggestionBlock, Timeline } from "@/components/triage";

export default function TriagePage() {
  const { id } = useParams<{ id: string }>();
  const [incident, setIncident] = useState<Incident | null>();
  const [memoryOn, setMemoryOn] = useState(true);
  const [resolved, setResolved] = useState(false);
  const t = useTriage(id, memoryOn);

  useEffect(() => {
    document.title = `${id} triage – RecallOps`;
    getIncident(id).then((i) => setIncident(i ?? null)).catch(() => setIncident(null));
  }, [id]);

  if (incident === undefined) return <Skeleton className="h-8 w-80" />;
  if (incident === null)
    return (
      <PageHeader title="Incident not found" sub={`No incident with id ${id}.`}
        crumbs={<Link href="/incidents" className="hover:text-ink">Incidents</Link>} />
    );

  const status = resolved ? "resolved" : incident.status;

  return (
    <>
      <PageHeader
        crumbs={<><Link href="/incidents" className="hover:text-ink">Incidents</Link> / <span className="font-mono text-code">{id}</span></>}
        title={<span className="flex flex-wrap items-center gap-3">{titleFor(incident)} <SeverityBadge s={incident.severity} /> <StatusBadge s={status} /></span>}
        actions={<>
          <label className="toggle flex cursor-pointer items-center gap-2 text-sm">
            Memory
            <input type="checkbox" role="switch" className="peer sr-only" checked={memoryOn} onChange={(e) => setMemoryOn(e.target.checked)} />
            <span aria-hidden className="relative h-5 w-9 rounded-full bg-line transition-colors peer-checked:bg-accent after:absolute after:left-0.5 after:top-0.5 after:h-4 after:w-4 after:rounded-full after:bg-panel after:transition-transform peer-checked:after:translate-x-4" />
          </label>
          <Link href={`/incidents/${id}/compare`}
            className="inline-flex h-9 items-center rounded-md border border-line bg-panel px-4 text-sm font-medium hover:bg-hover">
            Compare with memory off
          </Link>
        </>}
      />

      <AlertStrip incident={incident} />

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
        <div className="flex flex-col gap-8 lg:col-span-7">
          <section aria-labelledby="act-h">
            <h2 id="act-h" className="mb-3 text-base font-semibold">Agent activity</h2>
            <Timeline steps={t.steps} running={t.status === "running"} />
            {t.fatalError && (
              <div role="alert" className="mt-4 flex flex-col items-start gap-3 rounded-lg border border-line bg-panel p-4">
                <p>The agent stopped before finishing.</p>
                <p className="-mt-2 text-sm text-muted">{t.fatalError}</p>
                <Button onClick={t.retry}>Run triage again</Button>
              </div>
            )}
          </section>

          {t.suggestion && (
            <SuggestionBlock
              key={t.suggestion.id}
              s={t.suggestion}
              onVerdict={(verdict, extra) => sendFeedback(id, { suggestion_id: t.suggestion!.id, verdict, ...extra })}
            />
          )}

          <section aria-labelledby="res-h">
            <h2 id="res-h" className="mb-3 text-base font-semibold">Resolve incident</h2>
            <ResolveForm resolved={resolved || incident.status?.toLowerCase() === "resolved"} onResolve={async (r) => { await resolveIncident(id, r); setResolved(true); }} />
          </section>
        </div>

        <div className="lg:col-span-5">
          <MemoryPanel
            memories={t.memories}
            loading={t.status === "running" && !t.suggestion}
            error={t.memoryError}
            memoryOff={!memoryOn}
            onRetry={t.retry}
          />
        </div>
      </div>
    </>
  );
}

function titleFor(i: Incident) {
  const t = i.title ?? i.summary;
  return t.charAt(0).toUpperCase() + t.slice(1);
}
