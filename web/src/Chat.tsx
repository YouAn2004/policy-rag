import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Note, Progress } from "./Note";
import { roleLabel } from "./format";
import type { Citation, Turn } from "./types";

const EXAMPLES = [
  "How many days of annual leave do I get after 6 years?",
  "can i wfh everyday?",
  "A supplier gave me a gift worth RM 350. What should I do?",
  "What is the target bonus for a Grade 5 employee?",
];

interface Props {
  turns: Turn[];
  busy: boolean;
  role: string;
  onSend: (q: string) => void;
  onReset: () => void;
  onOpenSource: (c: Citation) => void;
  selected: string | null;
}

export default function Chat({ turns, busy, role, onSend, onReset, onOpenSource, selected }: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const fieldRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    endRef.current?.scrollIntoView({ behavior: calm ? "auto" : "smooth", block: "end" });
  }, [turns]);

  useEffect(() => {
    const el = fieldRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [draft]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = draft.trim();
    if (!q || busy) return;
    setDraft("");
    onSend(q);
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const empty = turns.length === 0;

  return (
    <section className="chat" aria-label="Conversation">
      <header className="chat-head">
        <p className="eyebrow">Policy assistant</p>
        {!empty && <button className="link" onClick={onReset}>New conversation</button>}
      </header>

      <div className="thread">
        {empty ? (
          <div className="welcome">
            <h2>Ask the handbook.</h2>
            <p>
              Answers quote the clause they rely on, and anything the handbook does not cover is declined instead of guessed.
              You are reading as <b>{roleLabel(role)}</b>.
            </p>
            <ul className="examples">
              {EXAMPLES.map((q) => (
                <li key={q}><button onClick={() => onSend(q)} disabled={busy}>{q}</button></li>
              ))}
            </ul>
          </div>
        ) : (
          turns.map((t) => {
            if (t.kind === "user") return <div key={t.id} className="turn user"><p>{t.text}</p></div>;
            if (t.kind === "divider") return <div key={t.id} className="divider"><span>Now reading as {roleLabel(t.role)}</span></div>;
            return (
              <div key={t.id} className="turn bot">
                {t.error ? (
                  <article className="note error" role="alert"><p className="para">{t.error}</p></article>
                ) : t.answer ? (
                  <Note answer={t.answer} role={t.role} onOpen={onOpenSource} selected={selected} />
                ) : (
                  <Progress stages={t.stages} />
                )}
              </div>
            );
          })
        )}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={submit}>
        <label htmlFor="q" className="sr">Your question</label>
        <textarea
          id="q"
          ref={fieldRef}
          value={draft}
          rows={1}
          maxLength={1000}
          placeholder="Ask about leave, expenses, travel, security..."
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKey}
        />
        <button type="submit" disabled={busy || !draft.trim()}>{busy ? "Working" : "Ask"}</button>
        <p className="hint">Enter to send, Shift+Enter for a new line.{draft.length > 850 && ` ${1000 - draft.length} characters left.`}</p>
      </form>
    </section>
  );
}
