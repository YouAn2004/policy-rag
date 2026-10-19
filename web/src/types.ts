export type Status = "answered" | "flagged" | "refused";
export type Stage = "rewrite" | "search" | "judge" | "answer" | "verify";

export interface Citation {
  label: string;
  chunk_id: string;
  doc_id: string;
  title: string;
  version: string;
  effective_date: string;
  section: string;
  source_file: string;
  page: number | null;
  text: string;
}

export interface Verification {
  cited: string[];
  invalid_citations: string[];
  uncited: boolean;
  unsupported_numbers: string[];
  llm_support?: { supported: boolean; problems: string[] } | null;
}

export interface Answer {
  status: Status;
  text: string;
  question: string;
  role: string;
  rewritten: string;
  citations: Citation[];
  verification: Verification;
  retrieved: string[];
  refusal_reason: string;
  contact: string;
  timings: Record<string, number>;
  checks: string;
}

export interface RoleInfo {
  id: string;
  documents: number;
  clauses: number;
}

export interface RunSummary {
  answerable_n: number;
  unanswerable_n: number;
  answered_rate: number | null;
  correct_refusal_rate: number | null;
  citation_valid: number | null;
  citation_recall: number | null;
  fact_checks: number | null;
  fact_checks_n: number;
  flagged_rate: number | null;
  leaks: number;
  mean_seconds: number | null;
}

export interface Run {
  label: string;
  timestamp: string;
  set: string;
  judge_only: boolean;
  summary: RunSummary;
}

export interface RetrievalMode {
  n: number;
  "hit@1": number;
  "hit@3": number;
  "hit@5": number;
  mrr: number;
  violations: number;
  run: string;
}

export interface EvalData {
  runs: Run[];
  retrieval: { n: number; modes: Record<string, RetrievalMode> };
}

export type Turn =
  | { kind: "user"; id: string; text: string }
  | { kind: "divider"; id: string; role: string }
  | { kind: "bot"; id: string; role: string; stages: Stage[]; answer: Answer | null; error: string | null };
