import { useEffect, useState } from "react";
import { fetchEval } from "./api";
import { pct, seconds, shortDate } from "./format";
import type { EvalData, Run } from "./types";

const SETS: Record<string, { name: string; note: string }> = {
  final: { name: "Final set", note: "24 questions, written last and run once" },
  "held-out": { name: "Held-out set", note: "32 questions kept out of prompt tuning" },
  tuned: { name: "Tuned set", note: "66 questions used while developing" },
};
const MODES: Record<string, string> = {
  dense: "Dense (bge-m3)",
  dense_rewrite: "Dense with query rewrite",
  bm25: "Keyword only (BM25)",
  hybrid: "Hybrid, fused",
  hybrid_rerank: "Hybrid with reranker",
  hybrid_blend: "Hybrid, blended",
};

function latest(runs: Run[], set: string): Run | undefined {
  return [...runs].filter((r) => r.set === set && !r.judge_only).sort((a, b) => a.timestamp.localeCompare(b.timestamp)).pop();
}

function Figure({ label, value, tone }: { label: string; value: string; tone?: "good" | "bad" }) {
  return (
    <div className={`figure${tone ? ` ${tone}` : ""}`}>
      <dd>{value}</dd>
      <dt>{label}</dt>
    </div>
  );
}

export default function Ledger() {
  const [data, setData] = useState<EvalData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetchEval().then(setData).catch(() => setError(true));
  }, []);

  if (error) return <section className="ledger"><p className="empty">The evaluation results could not be loaded.</p></section>;
  if (!data) return <section className="ledger"><p className="empty">Loading the ledger...</p></section>;

  const full = data.runs.filter((r) => !r.judge_only);
  const modes = Object.entries(data.retrieval.modes).sort((a, b) => b[1].mrr - a[1].mrr);

  return (
    <section className="ledger" aria-label="Evaluation ledger">
      <header className="chat-head"><p className="eyebrow">Evaluation ledger</p></header>
      <div className="ledger-body">
        <h2>What the numbers say.</h2>
        <p className="lede">Every figure here is read from the result files in <code>eval/results</code>, written by the evaluation scripts. Nothing is typed in by hand.</p>

        <div className="set-cards">
          {Object.entries(SETS).map(([key, meta]) => {
            const run = latest(data.runs, key);
            if (!run) return null;
            const s = run.summary;
            return (
              <article className="set-card" key={key}>
                <header>
                  <h3>{meta.name}</h3>
                  <span className="run-tag">{run.label}</span>
                </header>
                <p className="set-note">{meta.note}</p>
                <dl className="figures">
                  <Figure label="questions answered" value={pct(s.answered_rate)} />
                  <Figure label="refusals correct" value={pct(s.correct_refusal_rate)} />
                  <Figure label="citations valid" value={pct(s.citation_valid)} />
                  <Figure label="restricted leaks" value={String(s.leaks)} tone={s.leaks === 0 ? "good" : "bad"} />
                </dl>
              </article>
            );
          })}
        </div>

        <h3 className="section-h">Every full run</h3>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Run</th><th>Set</th><th>Date</th><th>Answered</th><th>Cite valid</th><th>Recall</th><th>Facts</th><th>Flagged</th><th>Refusal</th><th>Leaks</th><th>Mean</th></tr>
            </thead>
            <tbody>
              {[...full].reverse().map((r) => (
                <tr key={r.label}>
                  <th scope="row">{r.label}</th>
                  <td>{SETS[r.set]?.name ?? r.set}</td>
                  <td>{shortDate(r.timestamp)}</td>
                  <td>{pct(r.summary.answered_rate)}</td>
                  <td>{pct(r.summary.citation_valid)}</td>
                  <td>{pct(r.summary.citation_recall)}</td>
                  <td>{r.summary.fact_checks_n ? `${pct(r.summary.fact_checks)} of ${r.summary.fact_checks_n}` : "n/a"}</td>
                  <td>{pct(r.summary.flagged_rate)}</td>
                  <td>{pct(r.summary.correct_refusal_rate)}</td>
                  <td>{r.summary.leaks}</td>
                  <td>{seconds(r.summary.mean_seconds)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {modes.length > 0 && (
          <>
            <h3 className="section-h">Retrieval ablation <span className="muted">on {data.retrieval.n} answerable questions</span></h3>
            <ul className="bars">
              {modes.map(([mode, m]) => (
                <li key={mode}>
                  <span className="bar-name">{MODES[mode] ?? mode}</span>
                  <span className="bar" role="img" aria-label={`Reciprocal rank ${m.mrr.toFixed(2)}`}><i style={{ width: `${m.mrr * 100}%` }} /></span>
                  <span className="bar-val">MRR {m.mrr.toFixed(2)}</span>
                  <span className="bar-sub">top 1 {pct(m["hit@1"])}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
