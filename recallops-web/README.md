# RecallOps web

The frontend for RecallOps: on-call incident triage that remembers past outages, including the fixes that failed.
Built from the Hallmark-polished Stitch screens. Next.js 14 (App Router), TypeScript, Tailwind.

## Run it

You need **Node.js 18.18 or newer**. Check with `node -v`.

```bash
npm install
npm run dev
```

Open http://localhost:3000. With no backend configured, the app runs on **built-in mock data**,
and "Mock data" shows in the top bar. The full demo works offline:

1. **Incidents** → click **Fire demo alert**
2. Watch the agent's steps and the **Memory used** cards appear one by one
3. Click **Correct**, save a correction; fill **Resolve incident**
4. Flip the **Memory** toggle off to see the generic answer
5. **Compare with memory off** shows both answers side by side
6. **Learned patterns** and **Learning curve** in the top bar

## Connect the real backend

```bash
cp .env.example .env.local
# edit .env.local:
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Restart `npm run dev`. "Mock data" disappears from the top bar when it's using the real API.

The backend must allow CORS from `http://localhost:3000` (and the Vercel URL later),
including `POST` and the `Content-Type` header.

## Where things live

| Path | What it is |
|---|---|
| `lib/api.ts` | **Every backend call.** Mock vs real switch. Change endpoints here only. |
| `lib/types.ts` | Data shapes. Must match the backend. |
| `lib/useTriage.ts` | Turns the SSE stream into screen state. |
| `lib/sse.ts` | Reads `text/event-stream` from a POST (EventSource only supports GET). |
| `lib/mock.ts` | The demo story data (INC-2041 repeats INC-1987). |
| `components/triage.tsx` | Timeline, memory panel, suggestion, correct and resolve forms. |
| `components/ui.tsx` | Badges, buttons, stat blocks, skeletons. |
| `tailwind.config.ts` | Design tokens. One accent colour; change colours here only. |

## API contract (for the backend)

All timestamps are ISO 8601. The frontend writes "6 weeks ago" itself.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/incidents` | | `Incident[]` |
| GET | `/api/incidents/{id}` | | `Incident` |
| POST | `/api/alerts` | `{service, metric, value, threshold, unit, demo}` | `{id}` of the new incident |
| POST | `/api/incidents/{id}/triage` (`?memory=off`) | | SSE stream, see below |
| POST | `/api/incidents/{id}/feedback` | `{suggestion_id, verdict: "accept"\|"reject"\|"correct", actual_cause?, fix_that_worked?}` | 2xx |
| POST | `/api/incidents/{id}/resolve` | `{root_cause, fix, failed_fixes, duration_min}` | 2xx |
| GET | `/api/observations` | | `Pattern[]` |
| GET | `/api/metrics/learning-curve` | | `LearningCurve` |
| POST | `/api/demo/reset` | | 2xx |

`Incident`: `{id, severity: 1|2|3, service, title?, summary, opened_at, status: "open"|"investigating"|"resolved", alert?: {metric, value, threshold, fired_at}}`

`Pattern`: `{id, statement, support, last_seen_at, incidents: string[]}`

`LearningCurve`: `{points: [{n, on, off}], stats: {top1_on, top1_off, repeated_failed_fixes_on}, sample?}`. Accuracy values are 0 to 1.

### Triage stream events

Agreed contract: `thought`, `tool_call`, `memory_hit`, `suggestion`, `error`, `done`.

```text
event: thought
data: {"id":"s1","text":"Checking deploys to checkout-api in the last 24 hours."}

event: tool_call
data: {"id":"s2","tool":"get_recent_deploys","args":{},"output":"optional text for Show output"}

event: memory_hit
data: {"id":"m1","incident_id":"INC-1987","occurred_at":"2026-09-22T03:14:00Z","summary":"optional",
       "actions":[{"text":"Restarted pods twice. Latency got worse.","outcome":"failed"},
                  {"text":"Rolled back pool config. Recovered in 6 min.","outcome":"worked"}]}

event: suggestion
data: {"id":"sug_1","root_cause":"Connection pool limit reduced in deploy #4412.","confidence":"high",
       "fix":"Roll back the pool config from #4412.",
       "avoid":[{"text":"Restarting checkout-api pods. This failed in INC-1987.","source_incident":"INC-1987"}],
       "owner":{"team":"Payments platform team","person":"Rahul Menon"},
       "memory_refs":["INC-1987","INC-1902","INC-1755"]}

event: error
data: {"stage":"memory","message":"Couldn't reach incident memory.","retryable":true}

event: done
data: {"memory":"on","time_to_hypothesis_s":120}
```

Rules the UI relies on:
- **`outcome` is per action, not per incident.** One incident can have a failed and a worked action.
- **An `error` with `stage: "memory"` does not end the stream.** The memory panel shows the error and triage continues.
  Any other `error` stops the run and shows "Run triage again".
- **Memory-off answers** send `steps: string[]` instead of `fix`, and no `memory_refs`.
- Each event's `id` must be unique within a run. Duplicate `memory_hit` ids are ignored.

## Before the demo

- Replace the **sample learning-curve numbers** with the real replay results. The page shows a warning while
  the API sends `"sample": true`.
- Deploy: push to GitHub, import into Vercel, set `NEXT_PUBLIC_API_BASE` in Vercel's environment settings.
- Fonts are bundled from npm, so the app works on bad venue Wi-Fi once it's running.
