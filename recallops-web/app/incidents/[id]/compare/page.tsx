"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { useTriage, type TriageState } from "@/lib/useTriage";
import { duration } from "@/lib/time";
import { PageHeader, Skeleton } from "@/components/ui";
import { MemoryRefs } from "@/components/triage";

// Same alert, two runs side by side. Both panels share one style on purpose:
// the only difference the jury should notice is the content.
export default function ComparePage() {
  const { id } = useParams<{ id: string }>();
  const off = useTriage(id, false);
  const on = useTriage(id, true);
  useEffect(() => { document.title = `${id} compared – RecallOps`; }, [id]);

  return (
    <>
      <PageHeader
        crumbs={<><Link href="/incidents" className="hover:text-ink">Incidents</Link> / <Link href={`/incidents/${id}`} className="font-mono text-code hover:text-ink">{id}</Link> / Compare</>}
        title="Same alert, with and without memory"
      />
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2 md:divide-x md:divide-line">
        <Column label="Memory off" t={off} />
        <div className="md:pl-8"><Column label="Memory on" t={on} /></div>
      </div>
    </>
  );
}

function Column({ label, t }: { label: string; t: TriageState }) {
  const s = t.suggestion;
  const refs = s?.memory_refs ?? [];
  return (
    <section className="md:pr-8">
      <h2 className="mb-3 text-sm text-muted">{label}</h2>
      <div className="flex min-h-[220px] flex-col gap-3 rounded-lg border border-line bg-panel p-5">
        {!s && !t.fatalError && (
          <div role="status" aria-label="Agent is working" className="flex flex-col gap-3">
            <Skeleton className="h-4 w-5/6" /><Skeleton className="h-4 w-2/3" /><Skeleton className="h-4 w-3/4" />
          </div>
        )}
        {t.fatalError && <p className="text-muted">Couldn’t finish this run: {t.fatalError}</p>}
        {s && (
          <div className="step-in flex flex-col gap-3">
            <p>{s.steps ? s.root_cause : `Root cause: ${s.root_cause.charAt(0).toLowerCase() + s.root_cause.slice(1)}`}</p>
            {s.steps && (<><p className="font-medium">Suggested steps:</p><ol className="list-decimal pl-5">{s.steps.map((x) => <li key={x}>{x}</li>)}</ol></>)}
            {s.fix && <p>Fix: {s.fix.charAt(0).toLowerCase() + s.fix.slice(1)}</p>}
            {s.avoid?.map((a) => <p key={a.text} className="text-danger">Avoid {a.text.charAt(0).toLowerCase() + a.text.slice(1)}</p>)}
            {s.owner && <p>Owner: {s.owner.team}.</p>}
            {refs.length > 0 && <MemoryRefs ids={refs} />}
          </div>
        )}
      </div>
      {t.status === "done" && (
        <div className="mt-3 text-sm text-muted">
          <p>{refs.length ? `${refs.length} past incidents referenced.` : "No past incidents referenced."}</p>
          {t.timeToHypothesis != null && <p>Time to hypothesis: <span className="tabular-nums">{duration(t.timeToHypothesis)}</span></p>}
        </div>
      )}
    </section>
  );
}
