import type { Answer, EvalData, RoleInfo, Stage } from "./types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return (await res.json()) as T;
}

export const fetchRoles = () => getJson<{ roles: RoleInfo[]; stages: Stage[] }>("/api/roles");
export const fetchEval = () => getJson<EvalData>("/api/eval");

/** One server sent event block: "event: name" then "data: json". */
export function parseBlock(block: string): { event: string; data: unknown } | null {
  const lines = block.split("\n");
  const event = lines.find((l) => l.startsWith("event: "))?.slice(7);
  const data = lines.find((l) => l.startsWith("data: "))?.slice(6);
  return event && data ? { event, data: JSON.parse(data) } : null;
}

/** Sends a question and reports each pipeline stage as it starts. Resolves with the final answer. */
export async function askStream(
  question: string,
  role: string,
  onStage: (stage: Stage) => void,
  signal?: AbortSignal,
): Promise<Answer> {
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, role }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(res.status === 422 ? "That question could not be sent." : `The server answered ${res.status}.`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer: Answer | null = null;
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const parsed = parseBlock(buffer.slice(0, cut));
      buffer = buffer.slice(cut + 2);
      if (!parsed) continue;
      if (parsed.event === "step") onStage((parsed.data as { stage: Stage }).stage);
      else if (parsed.event === "result") answer = parsed.data as Answer;
      else if (parsed.event === "error") throw new Error((parsed.data as { message: string }).message);
    }
  }
  if (!answer) throw new Error("The connection closed before an answer arrived.");
  return answer;
}
