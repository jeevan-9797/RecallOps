"use client";
import { useCallback, useEffect, useState } from "react";
import { getPatterns } from "@/lib/api";
import type { Pattern } from "@/lib/types";
import { ago } from "@/lib/time";
import { Button, Chip, PageHeader, Skeleton } from "@/components/ui";

export default function PatternsPage() {
  const [items, setItems] = useState<Pattern[] | null>(null);
  const [error, setError] = useState<string>();
  const load = useCallback(() => {
    setError(undefined);
    getPatterns().then(setItems).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { document.title = "Learned patterns – RecallOps"; load(); }, [load]);

  return (
    <>
      <PageHeader title="Learned patterns" sub="Recurring causes the agent has noticed across past incidents. Updated after each resolved incident." />
      <div className="flex flex-col gap-4">
        {error && (
          <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line bg-panel p-6">
            <p>Couldn’t load patterns.</p><p className="-mt-2 text-sm text-muted">{error}</p>
            <Button onClick={load}>Retry</Button>
          </div>
        )}
        {!error && !items && [0, 1, 2].map((i) => (
          <div key={i} className="flex flex-col gap-3 rounded-lg border border-line bg-panel p-6">
            <Skeleton className="h-5 w-3/4" /><Skeleton className="h-4 w-1/3" /><Skeleton className="h-6 w-1/2" />
          </div>
        ))}
        {items?.length === 0 && (
          <div className="rounded-lg border border-line bg-panel p-6 text-muted">
            No patterns yet. They appear once a few similar incidents have been resolved.
          </div>
        )}
        {items?.map((p) => (
          <article key={p.id} className="rounded-lg border border-line bg-panel p-6">
            <p className="text-lg font-medium">{p.statement}</p>
            <p className="mt-3 text-muted">{p.support}</p>
            <p className="text-muted">Last seen {ago(p.last_seen_at)}</p>
            <div className="mt-4 flex flex-wrap gap-2">{p.incidents.map((i) => <Chip key={i}>{i}</Chip>)}</div>
          </article>
        ))}
      </div>
    </>
  );
}
