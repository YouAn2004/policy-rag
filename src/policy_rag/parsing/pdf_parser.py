"""Parse a policy PDF. Tables are cut out of the text flow and read as tables."""

import re
from pathlib import Path

import pdfplumber

from .common import (CLAUSE_RE, SCHEDULE_RE, SECTION_RE, assemble, join_wrapped, normalise_meta,
                     table_to_text)

CONTROL_KEYS = ["Document ID", "Version", "Effective date", "Status", "Policy owner",
                "Classification", "Audience", "Supersedes", "Superseded by"]
CONTROL_RE = re.compile(r"^(" + "|".join(CONTROL_KEYS) + r")\s{2,}(.+)$")
FOOTER_RE = re.compile(r"^POL-\d+ v[\d.]+\s*\|\s*Page \d+$")
HEADER_RE = re.compile(r"^Meridian Works Sdn Bhd \|")


def _page_lines_and_tables(page):
    """Return (lines outside tables, list of tables as row lists)."""
    tables = page.find_tables()
    boxes = [t.bbox for t in tables]

    def outside(obj):
        if obj.get("object_type") != "char":
            return True
        x, y = (obj["x0"] + obj["x1"]) / 2, (obj["top"] + obj["bottom"]) / 2
        return not any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in boxes)

    text = page.filter(outside).extract_text(layout=False) or ""
    return text.splitlines(), [t.extract() for t in tables]


def parse_pdf(path):
    path = Path(path)
    raw, items = {}, []
    title = ""
    section_no, section_title = "", ""
    cur = None  # clause being built: dict with parts

    def flush():
        nonlocal cur
        if cur:
            items.append(dict(kind="clause", section_no=cur["sec_no"], section_title=cur["sec_title"],
                              clause=cur["clause"], text=join_wrapped(cur["parts"]), page=cur["page"]))
            cur = None

    with pdfplumber.open(str(path)) as pdf:
        for pno, page in enumerate(pdf.pages, start=1):
            lines, tables = _page_lines_and_tables(page)
            for line in lines:
                line = line.rstrip()
                s = line.strip()
                if not s or HEADER_RE.match(s) or FOOTER_RE.match(s):
                    continue
                if not title:
                    title = re.sub(r"^POL-\d+\s+", "", s)
                    continue
                c = CONTROL_RE.match(s) if not items else None
                if c and not section_no:
                    raw[c.group(1)] = c.group(2).strip()
                    continue
                m_cl = CLAUSE_RE.match(s)
                m_sec = SECTION_RE.match(s)
                m_sch = SCHEDULE_RE.match(s)
                if m_cl:
                    flush()
                    cur = dict(clause=f"{m_cl.group(1)}.{m_cl.group(2)}", parts=[m_cl.group(3)],
                               sec_no=section_no, sec_title=section_title, page=pno)
                elif m_sec:
                    flush()
                    section_no, section_title = m_sec.group(1), m_sec.group(2)
                elif m_sch:
                    flush()
                    section_no, section_title = "S", m_sch.group(1)
                elif cur:
                    cur["parts"].append(s)
            flush()
            for tb in tables:
                tb = [[(c or "").strip() for c in row] for row in tb if row]
                if tb and tb[0][0] == "Document ID":
                    raw.update({r[0]: r[1] for r in tb if len(r) > 1})
                elif len(tb) > 1:
                    items.append(dict(kind="table", section_no=section_no, section_title=section_title,
                                      clause="", text=table_to_text(tb[0], tb[1:]), page=pno))
    flush()
    raw["_title"] = title
    meta = normalise_meta(raw, path.name)
    return meta, assemble(meta, items)
