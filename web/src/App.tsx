import { useCallback, useEffect, useRef, useState } from "react";
import { askStream, fetchRoles } from "./api";
import Chat from "./Chat";
import { roleLabel } from "./format";
import Ledger from "./Ledger";
import SourceDrawer from "./SourceDrawer";
import type { Citation, RoleInfo, Stage, Turn } from "./types";

type Tab = "ask" | "ledger";
let counter = 0;
const uid = () => `t${++counter}`;

export default function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [role, setRole] = useState("employee");
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<Citation | null>(null);
  const [offline, setOffline] = useState(false);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    fetchRoles().then((r) => setRoles(r.roles)).catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setSource(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const totalDocs = Math.max(0, ...roles.map((r) => r.documents));

  const chooseRole = (next: string) => {
    if (next === role) return;
    setRole(next);
    setTurns((t) => {
      if (!t.length) return t;
      const last = t[t.length - 1];
      const base = last.kind === "divider" ? t.slice(0, -1) : t;
      return [...base, { kind: "divider", id: uid(), role: next }];
    });
  };

  const patchBot = (id: string, patch: (t: Extract<Turn, { kind: "bot" }>) => Partial<Turn>) =>
    setTurns((all) => all.map((t) => (t.kind === "bot" && t.id === id ? ({ ...t, ...patch(t) } as Turn) : t)));

  const send = useCallback(
    async (question: string) => {
      const id = uid();
      const ctrl = new AbortController();
      abort.current = ctrl;
      setSource(null);
      setBusy(true);
      setTurns((t) => [
        ...t,
        { kind: "user", id: uid(), text: question },
        { kind: "bot", id, role, stages: [], answer: null, error: null },
      ]);
      try {
        const answer = await askStream(
          question,
          role,
          (stage: Stage) => patchBot(id, (t) => ({ stages: [...t.stages, stage] })),
          ctrl.signal,
        );
        patchBot(id, () => ({ answer }));
      } catch (e) {
        if (!ctrl.signal.aborted) patchBot(id, () => ({ error: e instanceof Error ? e.message : "Something went wrong." }));
      } finally {
        if (abort.current === ctrl) setBusy(false);
      }
    },
    [role],
  );

  const reset = () => {
    abort.current?.abort();
    setTurns([]);
    setSource(null);
    setBusy(false);
  };

  return (
    <div className={`app${source ? " has-drawer" : ""}`}>
      <aside className="rail">
        <div className="brand">
          <span className="mark" aria-hidden="true">P</span>
          <div>
            <h1>Handbook Desk</h1>
            <p>Meridian Works policies. Runs on this computer.</p>
          </div>
        </div>

        <nav className="tabs" aria-label="Sections">
          <button aria-current={tab === "ask" ? "page" : undefined} onClick={() => setTab("ask")}>Ask</button>
          <button aria-current={tab === "ledger" ? "page" : undefined} onClick={() => setTab("ledger")}>Ledger</button>
        </nav>

        <section className="roles" aria-labelledby="roles-h">
          <h2 id="roles-h">Reading as</h2>
          <div role="radiogroup" aria-labelledby="roles-h" className="role-list">
            {(roles.length ? roles : ["employee", "manager", "hr", "finance", "executive"].map((id) => ({ id, documents: 0, clauses: 0 }))).map((r) => (
              <button key={r.id} role="radio" aria-checked={role === r.id} className="role" onClick={() => chooseRole(r.id)}>
                <span className="role-name">{roleLabel(r.id)}</span>
                {totalDocs > 0 && <span className="role-meta">{r.documents} of {totalDocs} policies</span>}
              </button>
            ))}
          </div>
          <p className="role-note">Restricted policies are removed before any search, so they cannot be quoted to a role that may not read them.</p>
        </section>
      </aside>

      <main className="main">
        {offline && (
          <div className="offline" role="alert">
            The server is not reachable. Start it with <code>python src\policy_rag\serve.py</code> and reload.
          </div>
        )}
        {tab === "ask" ? (
          <Chat turns={turns} busy={busy} role={role} onSend={send} onReset={reset} onOpenSource={setSource} selected={source?.chunk_id ?? null} />
        ) : (
          <Ledger />
        )}
      </main>

      <SourceDrawer citation={source} onClose={() => setSource(null)} />
    </div>
  );
}
