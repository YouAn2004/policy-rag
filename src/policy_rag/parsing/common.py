"""Shared helpers for turning raw lines into structured chunks."""

import re

from ..models import Chunk, DocMeta

CLAUSE_RE = re.compile(r"^(\d+)\.(\d+)\s+(\S.*)$")
SECTION_RE = re.compile(r"^(\d+)\.\s+(\S.*)$")
SCHEDULE_RE = re.compile(r"^Schedule:\s*(\S.*)$")


def join_wrapped(parts):
    """Join wrapped PDF lines. 'POL-' + '04' becomes 'POL-04', otherwise a space joins them."""
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
        elif out.endswith("-") and part[0].isdigit():
            out += part
        else:
            out += " " + part
    return re.sub(r"\s+", " ", out).strip()


def table_to_text(header, rows):
    """Render a table as one sentence-like line per row, so retrieval and the LLM can read it."""
    clean = lambda x: re.sub(r"\s+", " ", x or "").strip()
    header = [clean(h) for h in header]
    lines = []
    for row in rows:
        cells = [f"{h}: {clean(c)}" for h, c in zip(header, row) if clean(c)]
        lines.append("; ".join(cells))
    return "\n".join(lines)


def clean_title(title):
    """'POL-10 Compensation Policy (RESTRICTED to HR)' -> 'Compensation Policy'. DOCX and PDF headings differ."""
    title = re.sub(r"^POL-\d+\s+", "", title.strip())
    return re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()


def normalise_meta(raw, source_file):
    """Build DocMeta from the key/value pairs of the document control table."""
    get = lambda k: raw.get(k, "").strip()
    audience = [a.strip().lower() for a in get("Audience").split(",") if a.strip()]
    return DocMeta(
        doc_id=get("Document ID"),
        title=clean_title(raw.get("_title", "")),
        version=get("Version"),
        effective_date=get("Effective date"),
        status=get("Status").lower(),
        owner=get("Policy owner"),
        classification=get("Classification"),
        audience=audience,
        supersedes=get("Supersedes"),
        superseded_by=get("Superseded by"),
        source_file=source_file,
    )


def assemble(meta, items):
    """Turn parsed items into Chunks.

    items: list of dicts with keys kind, section_no, section_title, clause, text, page.
    Each chunk also receives the full text of its section, for small-to-big answering.
    """
    by_section = {}
    for it in items:
        by_section.setdefault((it["section_no"], it["section_title"]), []).append(it)

    chunks = []
    for it in items:
        siblings = by_section[(it["section_no"], it["section_title"])]
        if it["kind"] == "table":
            section_text = it["text"]
        else:
            section_text = "\n".join(
                f"{s['clause']} {s['text']}" for s in siblings if s["kind"] == "clause"
            )
        ident = it["clause"] or f"T{it['section_title'].lower().replace(' ', '-')}"
        chunks.append(
            Chunk(
                chunk_id=f"{meta.doc_id}@v{meta.version}#{ident}",
                kind=it["kind"],
                clause=it["clause"],
                section_no=it["section_no"],
                section_title=it["section_title"],
                text=it["text"],
                section_text=section_text,
                page=it["page"],
                meta=meta,
            )
        )
    return chunks
