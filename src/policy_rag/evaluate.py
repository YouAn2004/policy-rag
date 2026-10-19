"""Measure retrieval quality and policy safety against eval/golden_policy.json.

Usage (project root, Ollama running, index built):
    python src/policy_rag/evaluate.py --label baseline
    python src/policy_rag/evaluate.py --label baseline --modes hybrid hybrid_rerank

Per mode it reports
    Hit@k     share of answerable questions with at least one expected clause in the top k
    Cover@5   average share of the expected clauses found in the top 5 (matters for multi-clause answers)
    MRR       mean of 1 / rank of the first expected clause (top 10)
    Violations  returned clauses that are forbidden, restricted for the role, or superseded. Must be 0.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_rag import config  # noqa: E402
from policy_rag.filters import is_allowed  # noqa: E402

GOLDEN = config.ROOT / "eval" / "golden_policy.json"
DEPTH = 10
KS = (1, 3, 5)


def resolve(chunks, ref):
    """'POL-04#2.1' -> chunk ids of the current version. A full chunk id passes through."""
    if "@" in ref:
        return {c.chunk_id for c in chunks if c.chunk_id == ref}
    doc, ident = ref.split("#", 1)
    return {c.chunk_id for c in chunks
            if c.meta.doc_id == doc and c.meta.status == "current" and c.chunk_id.split("#", 1)[1] == ident}


def top_score(hit):
    return hit.rerank_score if hit.rerank_score is not None else hit.score


def run_mode(retriever, questions, mode, rewriter=None):
    """mode may end in _rewrite (for example dense_rewrite). The question is then searched in its
    original wording and in the rewritten wording, and the two rankings are fused."""
    chunks = retriever.index.chunks
    rows = []
    for q in questions:
        rewritten = ""
        if mode.endswith("_rewrite"):
            base = mode[: -len("_rewrite")]
            rewritten = rewriter(q["question"])
            hits = retriever.search_multi([q["question"], rewritten], q["role"], DEPTH, base)
        else:
            hits = retriever.search(q["question"], q["role"], DEPTH, mode)
        ids = [h.chunk.chunk_id for h in hits]
        expected = set().union(*[resolve(chunks, r) for r in q["expected"]]) if q["expected"] else set()
        forbidden = set().union(*[resolve(chunks, r) for r in q["forbidden"]]) if q["forbidden"] else set()
        violations = [h.chunk.chunk_id for h in hits
                      if h.chunk.chunk_id in forbidden
                      or h.chunk.meta.doc_id in q["forbidden_docs"]
                      or not is_allowed(h.chunk, q["role"])]
        rank = next((r for r, i in enumerate(ids, 1) if i in expected), None)
        rows.append(dict(
            id=q["id"], type=q["type"], set=q.get("set", "standard"), rewrite=rewritten, answerable=q["answerable"], rank=rank,
            cover5=(len(expected & set(ids[:5])) / len(expected)) if expected else None,
            violations=violations, top_score=top_score(hits[0]) if hits else None,
            top=[h.chunk.citation for h in hits[:3]]))
    return rows


def summarize(rows):
    ans = [r for r in rows if r["answerable"]]
    n = len(ans)
    out = {"n": n}
    for k in KS:
        out[f"hit@{k}"] = sum(1 for r in ans if r["rank"] and r["rank"] <= k) / n if n else 0
    out["cover@5"] = sum(r["cover5"] for r in ans) / n if n else 0
    out["mrr"] = sum(1 / r["rank"] for r in ans if r["rank"]) / n if n else 0
    out["violations"] = sum(len(r["violations"]) for r in rows)
    return out


def fmt(s):
    return (f"Hit@1 {s['hit@1']:.2f} | @3 {s['hit@3']:.2f} | @5 {s['hit@5']:.2f} | "
            f"Cover@5 {s['cover@5']:.2f} | MRR {s['mrr']:.3f} | Violations {s['violations']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--golden", default=str(GOLDEN), help="question file, for example eval/golden_holdout.json")
    ap.add_argument("--modes", nargs="+", default=["dense", "bm25", "hybrid", "hybrid_rerank", "hybrid_blend", "dense_rewrite"])
    ap.add_argument("--show-misses", action="store_true")
    a = ap.parse_args()

    from policy_rag.cli_search import load_retriever

    rewriter = None
    if any(m.endswith("_rewrite") for m in a.modes):
        from policy_rag.llm import OllamaLLM
        from policy_rag.rewrite import rewrite_query

        llm, cache = OllamaLLM(), {}
        rewriter = lambda text: cache.setdefault(text, rewrite_query(llm, text))
    needs_rerank = any(m in a.modes for m in ("hybrid_rerank", "hybrid_blend"))
    retriever = load_retriever("hybrid_rerank" if needs_rerank else "hybrid")
    golden = json.loads(Path(a.golden).read_text(encoding="utf-8"))["questions"]
    print(f"Run {a.label}: {sum(q['answerable'] for q in golden)} answerable "
          f"({sum(q.get('set') == 'stress' for q in golden)} of them stress questions), "
          f"{sum(not q['answerable'] for q in golden)} unanswerable or blocked\n")

    results = {}
    for mode in a.modes:
        rows = run_mode(retriever, golden, mode, rewriter)
        s = summarize(rows)
        results[mode] = dict(summary=s, rows=rows)
        print(f"{mode:<14} {fmt(summarize([r for r in rows if r['set'] == 'standard']))}")
        stress = [r for r in rows if r["set"] == "stress"]
        if stress:
            print(f"{'  stress set':<14} {fmt(summarize(stress))}")
        if a.show_misses:
            for r in rows:
                if r["answerable"] and (r["rank"] is None or r["rank"] > 3):
                    print(f"    miss {r['id']} rank={r['rank']} got {r['top']}")

    best = [r for r in results[a.modes[-1]]["rows"] if r["set"] == "standard"]
    types = sorted({r["type"] for r in best})
    print(f"\nBy question type ({a.modes[-1]})")
    for t in types:
        sub = [r for r in best if r["type"] == t]
        if any(r["answerable"] for r in sub):
            print(f"  {t:<18} n={sum(r['answerable'] for r in sub):<3} {fmt(summarize(sub))}")

    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS_DIR / f"{a.label}.json"
    out.write_text(json.dumps(dict(label=a.label, timestamp=datetime.now().isoformat(timespec="seconds"),
                                   embed_model=config.EMBED_MODEL, rerank_model=config.RERANK_MODEL,
                                   results=results), indent=2), encoding="utf-8")
    print(f"\nSaved to {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
