import { useEffect, useRef } from "react";
import type { Citation } from "./types";

export default function SourceDrawer({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (citation) closeRef.current?.focus();
  }, [citation]);

  return (
    <aside className="drawer" aria-label="Source clause">
      {citation && (
        <div className="drawer-inner" key={citation.chunk_id}>
          <header>
            <p className="eyebrow">Source clause</p>
            <button ref={closeRef} className="icon-btn" onClick={onClose} aria-label="Close source">Close</button>
          </header>
          <h2 className="clause-label">{citation.label}</h2>
          <p className="doc-title">{citation.title}</p>
          <dl className="facts">
            <div><dt>Version</dt><dd>{citation.version}</dd></div>
            <div><dt>In force from</dt><dd>{citation.effective_date}</dd></div>
            <div><dt>Section</dt><dd>{citation.section}</dd></div>
            <div className="wide"><dt>File</dt><dd>{citation.source_file}{citation.page ? `, page ${citation.page}` : ""}</dd></div>
          </dl>
          <blockquote className="clause-text">{citation.text}</blockquote>
          <p className="drawer-note">This is the exact text the assistant was given. If the answer says something this clause does not, do not rely on it.</p>
        </div>
      )}
    </aside>
  );
}
