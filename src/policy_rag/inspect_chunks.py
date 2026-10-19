"""Parse the handbook and print what the parser found.

Usage (from the project root):
    python src/policy_rag/inspect_chunks.py
    python src/policy_rag/inspect_chunks.py --show POL-05
Also writes build/chunks.jsonl as a debugging dump.
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from policy_rag.parsing import parse_folder  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default=str(ROOT / "data" / "handbook"))
    ap.add_argument("--show", help="print every chunk of this doc id, e.g. POL-05")
    args = ap.parse_args()

    parsed = parse_folder(args.folder)
    out = ROOT / "build" / "chunks.jsonl"
    out.parent.mkdir(exist_ok=True)

    print(f"{'file':<42}{'ver':<5}{'status':<11}{'audience':<28}{'clauses':>8}{'tables':>7}")
    total = 0
    with out.open("w", encoding="utf-8") as fh:
        for meta, chunks in parsed:
            nc = sum(c.kind == "clause" for c in chunks)
            nt = sum(c.kind == "table" for c in chunks)
            total += len(chunks)
            print(f"{meta.source_file:<42}{meta.version:<5}{meta.status:<11}{','.join(meta.audience):<28}{nc:>8}{nt:>7}")
            for c in chunks:
                fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
            if args.show and meta.doc_id == args.show and meta.status == "current":
                for c in chunks:
                    print(f"  [{c.citation}] ({c.section_title}) {c.text[:110]}")
    print(f"\n{len(parsed)} files, {total} chunks written to {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
