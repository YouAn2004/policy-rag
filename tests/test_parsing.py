"""Check the parsers against the Markdown sources the handbook was generated from."""

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from policy_rag.parsing import parse_file  # noqa: E402

SRC = sorted((ROOT / "handbook_src").glob("*.md"))
FILES = sorted((ROOT / "data" / "handbook").iterdir())


def norm(t):
    return re.sub(r"\s+", " ", t).strip()


def source_for(meta):
    for f in SRC:
        text = f.read_text(encoding="utf-8")
        m = re.match(r"---\n(.*?)\n---\n", text, re.S)
        fm = yaml.safe_load(m.group(1))
        if fm["doc_id"] == meta.doc_id and str(fm["version"]) == meta.version:
            clauses = {}
            for line in text[m.end():].splitlines():
                c = re.match(r"^(\d+\.\d+) (.*)$", line)
                if c:
                    clauses[c.group(1)] = norm(c.group(2))
            return fm, clauses
    raise AssertionError(f"no source for {meta.doc_id} v{meta.version}")


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_clauses_and_metadata_match_source(path):
    meta, chunks = parse_file(path)
    fm, truth = source_for(meta)

    assert meta.status == fm["status"]
    assert meta.effective_date == str(fm["effective_date"])
    assert meta.audience == fm["access"]
    assert meta.owner == fm["owner"]
    assert meta.classification == ("Internal" if fm["access"] == ["all"] else "Restricted")

    got = {c.clause: norm(c.text) for c in chunks if c.kind == "clause"}
    assert got.keys() == truth.keys(), "clause numbers differ"
    for k in truth:
        assert got[k] == truth[k], f"clause {k} text differs"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_clause_has_section_context(path):
    _, chunks = parse_file(path)
    for c in chunks:
        assert c.section_title, f"{c.chunk_id} lost its section title"
        assert c.chunk_id.startswith(c.meta.doc_id)


def test_tables_found_only_where_expected():
    expected = {"POL-04": 1, "POL-05": 1, "POL-08": 1, "POL-12": 1}
    for path in FILES:
        meta, chunks = parse_file(path)
        n = sum(c.kind == "table" for c in chunks)
        assert n == expected.get(meta.doc_id, 0) if meta.status == "current" else n == 0


def test_table_content_is_readable():
    meta, chunks = parse_file(ROOT / "data" / "handbook" / "POL-04_expense_claims.pdf")
    table = [c for c in chunks if c.kind == "table"][0]
    assert "Claim amount (RM): Above 10,000; Approver: CFO" in table.text


def test_chunk_ids_unique_across_versions():
    ids = []
    for path in FILES:
        ids += [c.chunk_id for c in parse_file(path)[1]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_titles_are_clean_and_match_source(path):
    meta, _ = parse_file(path)
    fm, _ = source_for(meta)
    assert meta.title == fm["title"]
    assert "POL-" not in meta.title and "(" not in meta.title
