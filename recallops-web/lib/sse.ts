import type { TriageEvent } from "./types";

// Reads a text/event-stream response body and yields parsed events.
// Used instead of EventSource because triage is a POST.
export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<TriageEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const chunk = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const ev = parseChunk(chunk);
        if (ev) yield ev;
      }
    }
    const tail = parseChunk(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}

function parseChunk(chunk: string): TriageEvent | null {
  let type = "message";
  const data: string[] = [];
  for (const line of chunk.split("\n")) {
    if (line.startsWith(":")) continue; // comment / keep-alive
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) data.push(line.slice(5).replace(/^ /, ""));
  }
  if (!data.length) return null;
  try {
    return { type, data: JSON.parse(data.join("\n")) } as TriageEvent;
  } catch {
    return null;
  }
}
