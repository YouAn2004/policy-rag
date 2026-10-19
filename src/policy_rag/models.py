"""Data structures shared across the pipeline."""

from dataclasses import asdict, dataclass, field


@dataclass
class DocMeta:
    doc_id: str
    title: str
    version: str
    effective_date: str  # ISO date, e.g. 2026-01-01
    status: str  # "current" or "superseded"
    owner: str
    classification: str  # "Internal" or "Restricted"
    audience: list  # roles allowed to read, e.g. ["all"] or ["hr", "finance"]
    supersedes: str = ""
    superseded_by: str = ""
    source_file: str = ""


@dataclass
class Chunk:
    """One retrievable unit. A clause or one table, plus the context needed to cite it."""

    chunk_id: str
    kind: str  # "clause" or "table"
    clause: str  # e.g. "4.1" (empty for tables)
    section_no: str  # e.g. "4"
    section_title: str
    text: str  # the clause text itself
    section_text: str  # full text of the parent section, for answer generation
    page: int  # 1-based page for PDFs, 0 for DOCX
    meta: DocMeta = field(default=None)

    @property
    def citation(self):
        if self.kind == "table":
            return f"{self.meta.doc_id} v{self.meta.version} {self.section_title}"
        return f"{self.meta.doc_id} v{self.meta.version} §{self.clause}"

    @property
    def cite_key(self):
        """The label the language model must use when citing this chunk."""
        if self.kind == "table":
            return f"{self.meta.doc_id} Table: {self.section_title}"
        return f"{self.meta.doc_id} §{self.clause}"

    @property
    def index_text(self):
        """Text that gets embedded and keyword indexed. Context first, so short clauses are findable."""
        return f"{self.meta.title}. {self.section_title}. {self.text}"

    @classmethod
    def from_dict(cls, d):
        d = dict(d)
        d.pop("citation", None)
        d["meta"] = DocMeta(**d["meta"])
        return cls(**d)

    def to_dict(self):
        d = asdict(self)
        d["citation"] = self.citation
        return d
