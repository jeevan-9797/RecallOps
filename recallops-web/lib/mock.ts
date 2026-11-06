// Built-in demo data. Used when NEXT_PUBLIC_API_BASE is empty.
// Mirrors the Kartly story from the pitch: INC-2041 repeats INC-1987.
import type { Incident, LearningCurve, Pattern, TriageEvent } from "./types";
import { daysAgo, minutesAgo } from "./time";

export function mockIncidents(): Incident[] {
  return [
    { id: "INC-2041", severity: 1, service: "checkout-api", title: "Checkout p99 latency above 2s", summary: "p99 latency above 2s on checkout", opened_at: minutesAgo(4), status: "investigating",
      alert: { metric: "p99_latency", value: "6.2s", threshold: "2s", fired_at: "03:14 IST" } },
    { id: "INC-2040", severity: 2, service: "payments-svc", summary: "Gateway webhook retry queue backlog over threshold", opened_at: minutesAgo(28), status: "investigating" },
    { id: "INC-2039", severity: 2, service: "inventory-svc", summary: "Redis node failover causing intermittent 503s", opened_at: minutesAgo(180), status: "resolved" },
    { id: "INC-2038", severity: 3, service: "search-svc", summary: "Catalog index sync lagging behind updates", opened_at: minutesAgo(420), status: "resolved" },
    { id: "INC-2037", severity: 1, service: "delivery-eta-svc", summary: "Geocoding rate limits hit, ETAs fell back to 45 min", opened_at: daysAgo(1), status: "resolved" },
    { id: "INC-2036", severity: 2, service: "auth-gateway", summary: "Token cache expiry race during pod rotation", opened_at: daysAgo(2), status: "resolved" },
    { id: "INC-2035", severity: 3, service: "notification-svc", summary: "Push worker throttled during flash sale campaign", opened_at: daysAgo(4), status: "resolved" },
    { id: "INC-2034", severity: 3, service: "cart-sync-svc", summary: "Guest cart merge memory leak under high concurrency", opened_at: daysAgo(6), status: "resolved" },
  ];
}

const DEPLOYS_OUTPUT = `#4412  checkout-api  2026-11-05 18:40  rahul.menon   config: db.pool.max 40 -> 10
#4409  checkout-api  2026-11-05 11:02  ananya.rao    feat: coupon stacking (flag off)
#4401  checkout-api  2026-11-04 16:25  kiran.shetty  chore: bump http client`;

// One triage run, as the backend would stream it.
export function mockTriage(incidentId: string, memory: boolean): TriageEvent[] {
  const svc = mockIncidents().find((i) => i.id === incidentId)?.service ?? "checkout-api";
  const opening: TriageEvent[] = [
    { type: "thought", data: { id: "s1", text: `Checking deploys to ${svc} in the last 24 hours.` } },
    { type: "tool_call", data: { id: "s2", tool: "get_recent_deploys", args: { service: svc, hours: 24 }, output: DEPLOYS_OUTPUT } },
  ];
  if (!memory) {
    return [
      ...opening,
      { type: "thought", data: { id: "s3", text: "No past incidents available. Falling back to common causes of latency." } },
      { type: "suggestion", data: {
        id: "sug_off", root_cause: "Possible causes: high CPU, traffic spike, database slowness.",
        steps: ["Check CPU usage.", `Restart ${svc} pods.`, "Scale up replicas."] } },
      { type: "done", data: { memory: "off", time_to_hypothesis_s: 2280 } },
    ];
  }
  return [
    ...opening,
    { type: "memory_hit", data: { id: "m1", incident_id: "INC-1987", occurred_at: daysAgo(43),
      actions: [
        { text: "Restarted pods twice. Latency got worse.", outcome: "failed" },
        { text: "Rolled back pool config from deploy #3980. Recovered in 6 min.", outcome: "worked" },
      ] } },
    { type: "memory_hit", data: { id: "m2", incident_id: "INC-1902", occurred_at: daysAgo(63),
      actions: [{ text: "Rolled back pool config. Recovered in 8 min.", outcome: "worked" }] } },
    { type: "memory_hit", data: { id: "m3", incident_id: "INC-1755", occurred_at: daysAgo(122),
      actions: [{ text: "Scaled replicas from 6 to 12. No effect.", outcome: "failed" }] } },
    { type: "thought", data: { id: "s4", text: "Deploy #4412 changed the database connection pool size. INC-1987 had the same pattern." } },
    { type: "suggestion", data: {
      id: "sug_on", root_cause: "Connection pool limit reduced in deploy #4412.", confidence: "high",
      fix: "Roll back the pool config from #4412.",
      avoid: [{ text: `Restarting ${svc} pods. This failed in INC-1987 and made latency worse.`, source_incident: "INC-1987" }],
      owner: { team: "Payments platform team", person: "Rahul Menon" },
      memory_refs: ["INC-1987", "INC-1902", "INC-1755"] } },
    { type: "done", data: { memory: "on", time_to_hypothesis_s: 120 } },
  ];
}

export function mockPatterns(): Pattern[] {
  return [
    { id: "p1", statement: "Checkout latency spikes usually follow connection pool config changes deployed on Fridays.",
      support: "Seen in 4 of the last 5 checkout latency incidents", last_seen_at: daysAgo(6), incidents: ["INC-1987", "INC-2003", "INC-2019", "INC-2041"] },
    { id: "p2", statement: "Search timeouts during sale traffic are caused by Redis evictions, not the search service itself.",
      support: "Seen in 3 of 3 sale-day search incidents", last_seen_at: daysAgo(21), incidents: ["INC-1820", "INC-1911", "INC-2010"] },
    { id: "p3", statement: "Payment gateway timeouts above 5% clear on their own within 15 minutes. Restarting payments-svc does not help.",
      support: "Seen in 5 incidents", last_seen_at: daysAgo(12), incidents: ["INC-1702", "INC-1788", "INC-1866", "INC-1950", "INC-2031"] },
    { id: "p4", statement: "Disk-full alerts on inventory-svc come from log rotation failing after node restarts.",
      support: "Seen in 3 incidents", last_seen_at: daysAgo(35), incidents: ["INC-1690", "INC-1843", "INC-1977"] },
    { id: "p5", statement: "Feature flags rolled out to 100% without a canary caused 3 Sev 2 incidents this quarter.",
      support: "Seen in 3 incidents", last_seen_at: daysAgo(14), incidents: ["INC-1899", "INC-1958", "INC-2025"] },
  ];
}

// Placeholder curve. Stats are derived from the last point so the cards and chart always agree.
export function mockLearningCurve(): LearningCurve {
  const points = Array.from({ length: 40 }, (_, i) => {
    const n = i + 1;
    const wobble = Math.sin(n * 1.7) * 0.025;
    return { n, on: +(0.3 + 0.48 * (1 - Math.exp(-n / 14)) / (1 - Math.exp(-40 / 14)) + wobble * (n < 40 ? 1 : 0)).toFixed(3),
                off: +(0.31 + Math.sin(n * 2.3) * 0.02 * (n < 40 ? 1 : 0)).toFixed(3) };
  });
  const last = points[points.length - 1];
  return { points, stats: { top1_on: last.on, top1_off: last.off, repeated_failed_fixes_on: 0 }, sample: true };
}
