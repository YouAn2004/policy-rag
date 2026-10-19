export type Piece = { kind: "text"; text: string } | { kind: "cite"; label: string };

const GROUP = /\[([^[\]]*POL-\d{2}[^[\]]*)\]/g;

/** "POL-02 v3.1 §1.1" and "pol-02 §1.1" both become "POL-02 §1.1", the form the server uses. */
export function normaliseLabel(label: string): string {
  return label.trim().replace(/^pol-/i, "POL-").replace(/(POL-\d{2})\s*(?:v[\d.]+\s*)?§\s*(\d+\.\d+)/, "$1 §$2");
}

/** Splits one line of an answer into plain text and citation labels. A bracket may hold several labels. */
export function splitLine(line: string): Piece[] {
  const out: Piece[] = [];
  let last = 0;
  for (const m of line.matchAll(GROUP)) {
    const start = m.index ?? 0;
    if (start > last) out.push({ kind: "text", text: line.slice(last, start) });
    const labels = m[1].split(/\s*,\s*/).map(normaliseLabel).filter((l) => /^POL-\d{2}/.test(l));
    if (labels.length) labels.forEach((label) => out.push({ kind: "cite", label }));
    else out.push({ kind: "text", text: m[0] });
    last = start + m[0].length;
  }
  if (last < line.length) out.push({ kind: "text", text: line.slice(last) });
  return out;
}

export function splitAnswer(text: string): Piece[][] {
  return text.split(/\n+/).map((l) => l.trim()).filter(Boolean).map(splitLine);
}

export const pct = (v: number | null | undefined): string => (v == null ? "n/a" : `${Math.round(v * 100)}%`);

export const seconds = (v: number | null | undefined): string => (v == null ? "n/a" : `${v.toFixed(1)}s`);

export function shortDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

/** Problems that explain why an answer was flagged, in plain words. */
export function flagReasons(v: {
  invalid_citations: string[];
  uncited: boolean;
  unsupported_numbers: string[];
  llm_support?: { supported: boolean; problems: string[] } | null;
}): string[] {
  const out: string[] = [];
  if (v.uncited) out.push("The answer does not cite any clause.");
  if (v.invalid_citations.length) out.push(`It cites clauses that were not provided: ${v.invalid_citations.join(", ")}.`);
  if (v.unsupported_numbers.length) out.push(`These figures are not in the cited clauses or your question: ${v.unsupported_numbers.join(", ")}.`);
  if (v.llm_support && !v.llm_support.supported) out.push(...v.llm_support.problems.map(String));
  return out;
}

const EMAIL = /([\w.+-]+@[\w-]+(?:\.[\w-]+)+)/g;

/** Splits text around e-mail addresses so they can be rendered as links. */
export function splitEmails(text: string): Array<{ text: string; email: boolean }> {
  return text.split(EMAIL).map((part, i) => ({ text: part, email: i % 2 === 1 })).filter((p) => p.text);
}

const ROLE_LABELS: Record<string, string> = { employee: "Employee", manager: "Manager", hr: "HR", finance: "Finance", executive: "Executive" };
export const roleLabel = (id: string): string => ROLE_LABELS[id] ?? id;
