import { useState } from "react";
import { flagReasons, roleLabel, seconds, splitAnswer, splitEmails } from "./format";
import type { Answer, Citation, Stage, Status } from "./types";

const STEPS: Array<{ id: Stage; label: string }> = [
  { id: "rewrite", label: "Rewriting your question in handbook wording" },
  { id: "search", label: "Searching the clauses this role may read" },
  { id: "judge", label: "Finding the clause that settles it" },
  { id: "answer", label: "Drafting an answer with citations" },
  { id: "verify", label: "Checking citations and figures" },
];

export function Progress({ stages }: { stages: Stage[] }) {
  const current = stages[stages.length - 1];
  const index = STEPS.findIndex((s) => s.id === current);
  return (
    <ol className="progress" aria-live="polite" aria-label="Progress">
      {STEPS.map((s, i) => {
        const state = !current ? (i === 0 ? "active" : "todo") : i < index ? "done" : i === index ? "active" : "todo";
        return (
          <li key={s.id} className={`step ${state}`} aria-current={state === "active" ? "step" : undefined}>
            <span className="dot" aria-hidden="true" />
            {s.label}
          </li>
        );
      })}
    </ol>
  );
}

const STAMP: Record<Status, string> = { answered: "Checked", flagged: "Check this", refused: "Not covered" };

function Text({ text }: { text: string }) {
  return (
    <>
      {splitEmails(text).map((p, i) =>
        p.email ? <a key={i} href={`mailto:${p.text}`}>{p.text}</a> : <span key={i}>{p.text}</span>,
      )}
    </>
  );
}

function Body({ answer, onOpen, selected }: { answer: Answer; onOpen: (c: Citation) => void; selected: string | null }) {
  if (answer.status === "refused") return <p className="para"><Text text={answer.text} /></p>;
  const byLabel = new Map(answer.citations.map((c) => [c.label, c]));
  return (
    <>
      {splitAnswer(answer.text).map((pieces, i) => (
        <p className="para" key={i}>
          {pieces.map((p, j) => {
            if (p.kind === "text") return <span key={j}>{p.text}</span>;
            const c = byLabel.get(p.label);
            if (!c) return <span key={j} className="chip missing" title="This clause was not provided to the assistant">{p.label}</span>;
            return (
              <button key={j} className="chip" aria-pressed={selected === c.chunk_id} onClick={() => onOpen(c)} title={`${c.title}, version ${c.version}`}>
                {p.label}
              </button>
            );
          })}
        </p>
      ))}
    </>
  );
}

function Details({ answer }: { answer: Answer }) {
  const v = answer.verification;
  const support = v.llm_support;
  const refused = answer.status === "refused";
  return (
    <div className="details-body">
      {answer.rewritten && answer.rewritten.toLowerCase() !== answer.question.toLowerCase() && (
        <p><b>Searched for</b> {answer.rewritten}</p>
      )}
      {refused ? (
        answer.refusal_reason && <p><b>Why</b> {answer.refusal_reason}</p>
      ) : (
        <ul className="checklist">
          <li className={v.invalid_citations.length || v.uncited ? "bad" : "ok"}>Every citation points at a clause the assistant was given</li>
          <li className={v.unsupported_numbers.length ? "bad" : "ok"}>Every figure appears in the cited clauses or in your question</li>
          <li className={support == null ? "skip" : support.supported ? "ok" : "bad"}>
            {support == null ? "Support check was not run" : support.supported ? "A second model pass found the answer supported" : "A second model pass found a problem"}
          </li>
        </ul>
      )}
      {answer.checks && (
        <>
          <p><b>Checked facts</b> computed by code, not by the model</p>
          <pre className="facts-pre">{answer.checks}</pre>
        </>
      )}
      <p className="timing">
        {Object.entries(answer.timings).filter(([k]) => ["rewrite", "retrieve", "judge", "answer", "total"].includes(k)).map(([k, t]) => `${k} ${seconds(t)}`).join("  ·  ")}
      </p>
    </div>
  );
}

export function Note({ answer, role, onOpen, selected }: { answer: Answer; role: string; onOpen: (c: Citation) => void; selected: string | null }) {
  const [open, setOpen] = useState(false);
  const reasons = answer.status === "flagged" ? flagReasons(answer.verification) : [];
  const cited = answer.citations.length;
  return (
    <article className={`note ${answer.status}`}>
      <header className="note-head">
        <span className={`stamp ${answer.status}`}>{STAMP[answer.status]}</span>
        <span className="who">answering as {roleLabel(role)}</span>
      </header>
      <div className="note-body"><Body answer={answer} onOpen={onOpen} selected={selected} /></div>
      {answer.status === "flagged" && (
        <div className="warn" role="note">
          <strong>This answer failed an automatic check.</strong> Read the cited clauses yourself or ask the policy owner before acting on it.
          {reasons.length > 0 && <ul>{reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
        </div>
      )}
      {answer.status === "refused" && answer.contact && (
        <p className="contact">Policy owner <b>{answer.contact}</b></p>
      )}
      <footer className="note-foot">
        <span>{answer.status === "refused" ? "No clause cited" : `${cited} ${cited === 1 ? "clause" : "clauses"} cited`} · {seconds(answer.timings.total)}</span>
        <button className="link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>{open ? "Hide how it was checked" : "How it was checked"}</button>
      </footer>
      {open && <Details answer={answer} />}
    </article>
  );
}
