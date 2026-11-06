"use client";
import { useCallback, useEffect, useState } from "react";
import { getLearningCurve } from "@/lib/api";
import type { LearningCurve } from "@/lib/types";
import { Button, PageHeader, Skeleton, Stat } from "@/components/ui";
import { LearningChart, pct } from "@/components/LearningChart";

export default function LearningCurvePage() {
  const [data, setData] = useState<LearningCurve | null>(null);
  const [error, setError] = useState<string>();
  const load = useCallback(() => {
    setError(undefined);
    getLearningCurve().then(setData).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { document.title = "Learning curve – RecallOps"; load(); }, [load]);

  const n = data?.points.length ?? 40;
  return (
    <>
      <PageHeader title="Learning curve" sub={`${n} past incidents replayed in order. Same agent, with and without memory.`} />
      {error && (
        <div role="alert" className="flex flex-col items-start gap-3 rounded-lg border border-line bg-panel p-6">
          <p>Couldn’t load the replay results.</p><p className="-mt-2 text-sm text-muted">{error}</p>
          <Button onClick={load}>Retry</Button>
        </div>
      )}
      {!error && (
        <>
          <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
            <Stat value={data ? pct(data.stats.top1_on) : "–"} label="Top suggestion correct, memory on" />
            <Stat value={data ? pct(data.stats.top1_off) : "–"} label="Top suggestion correct, memory off" />
            <Stat value={data ? data.stats.repeated_failed_fixes_on : "–"} label="Previously failed fixes repeated, memory on" />
          </div>
          {data ? <LearningChart points={data.points} /> : <Skeleton className="h-[420px] w-full" />}
          <p className="mt-4 text-muted">The replay set is held out from the agent’s memory before the run starts.</p>
          {data?.sample && <p className="mt-1 text-sm text-warn">Sample numbers. Replace with the real replay results before the demo.</p>}
        </>
      )}
    </>
  );
}
