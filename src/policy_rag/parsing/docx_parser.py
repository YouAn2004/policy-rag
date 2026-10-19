"""Parse a policy DOCX into chunks, using heading styles, the control table and clause numbers."""

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from .common import CLAUSE_RE, SCHEDULE_RE, SECTION_RE, assemble, normalise_meta, table_to_text


def _iter_blocks(doc):
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def parse_docx(path):
    path = Path(path)
    doc = Document(str(path))
    raw = {}
    items = []
    title = ""
    section_no, section_title = "", ""

    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            text = block.text.strip()
            style = block.style.name
            if not text:
                continue
            if style == "Heading 1":
                title = text
            elif style == "Heading 2":
                m = SECTION_RE.match(text)
                s = SCHEDULE_RE.match(text)
                if m:
                    section_no, section_title = m.group(1), m.group(2)
                elif s:
                    section_no, section_title = "S", s.group(1)
                else:
                    section_no, section_title = "", text
            else:
                m = CLAUSE_RE.match(text)
                if m:
                    items.append(dict(kind="clause", section_no=m.group(1), section_title=section_title,
                                      clause=f"{m.group(1)}.{m.group(2)}", text=m.group(3).strip(), page=0))
        else:  # table
            rows = [[c.text.strip() for c in r.cells] for r in block.rows]
            if rows and rows[0][0] == "Document ID" or (rows and rows[0][0] in {"Document ID"}):
                raw = {r[0]: r[1] for r in rows}
            elif len(rows) > 1:
                items.append(dict(kind="table", section_no=section_no, section_title=section_title,
                                  clause="", text=table_to_text(rows[0], rows[1:]), page=0))

    # The title heading reads "POL-xx Title" in PDFs but plain "Title" in DOCX.
    raw["_title"] = title
    meta = normalise_meta(raw, path.name)
    return meta, assemble(meta, items)
