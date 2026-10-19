from pathlib import Path

from .docx_parser import parse_docx
from .pdf_parser import parse_pdf


def parse_file(path):
    suffix = Path(path).suffix.lower()
    if suffix == ".docx":
        return parse_docx(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    raise ValueError(f"Unsupported file type: {path}")


def parse_folder(folder):
    """Parse every DOCX and PDF in a folder. Returns a list of (meta, chunks)."""
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in {".docx", ".pdf"})
    return [parse_file(f) for f in files]
