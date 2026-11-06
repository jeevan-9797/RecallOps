// Hand-drawn SVG line chart: two series, thin gridlines, no fills or markers.
import type { LearningCurve } from "@/lib/types";

const W = 960, H = 380, L = 56, R = 16, T = 16, B = 48;

export function LearningChart({ points }: { points: LearningCurve["points"] }) {
  const max = Math.max(...points.map((p) => p.n), 1);
  const x = (n: number) => L + ((n - 1) / Math.max(max - 1, 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const line = (k: "on" | "off") => points.map((p) => `${x(p.n).toFixed(1)},${y(p[k]).toFixed(1)}`).join(" ");
  const xTicks = [1, ...Array.from({ length: Math.floor(max / 5) }, (_, i) => (i + 1) * 5)].filter((n) => n <= max);

  return (
    <figure className="rounded-lg border border-line bg-panel p-6">
      <figcaption className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-muted">Top suggestion accuracy (rolling)</span>
        <span className="flex gap-6 text-sm">
          <span className="flex items-center gap-2"><span aria-hidden className="h-0.5 w-5 bg-accent" />Memory on</span>
          <span className="flex items-center gap-2 text-muted"><span aria-hidden className="h-0.5 w-5 bg-chart-off" />Memory off</span>
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
        aria-label={`Accuracy over ${max} incidents. Memory on ends at ${pct(points.at(-1)?.on)}, memory off at ${pct(points.at(-1)?.off)}.`}>
        {[0, 0.2, 0.4, 0.6, 0.8, 1].map((v) => (
          <g key={v}>
            <line x1={L} x2={W - R} y1={y(v)} y2={y(v)} className="stroke-line" strokeWidth={1} />
            <text x={L - 10} y={y(v) + 4} textAnchor="end" className="fill-muted font-mono text-[12px]">{v * 100}%</text>
          </g>
        ))}
        {xTicks.map((n) => (
          <text key={n} x={x(n)} y={H - B + 22} textAnchor="middle" className="fill-muted font-mono text-[12px]">{n}</text>
        ))}
        <text x={(L + W - R) / 2} y={H - 6} textAnchor="middle" className="fill-muted text-[13px]">Incident #</text>
        <polyline points={line("off")} fill="none" className="stroke-chart-off" strokeWidth={2} strokeLinejoin="round" />
        <polyline points={line("on")} fill="none" className="stroke-accent" strokeWidth={2.5} strokeLinejoin="round" />
      </svg>
    </figure>
  );
}

export const pct = (v?: number) => (v == null ? "–" : `${Math.round(v * 100)}%`);
