"""End to end evaluation of the full assistant (rewrite, retrieval, refusal, answer, checks).

Slow, because each question makes 3 to 5 calls to the local model.
Usage (project root, Ollama running, index built):
    python src/policy_rag/evaluate_e2e.py --label p3
    python src/policy_rag/evaluate_e2e.py --label quick --limit 10
    python src/policy_rag/evaluate_e2e.py --label tricky --ids g02 g03 g19 g08 g43 g47 --no-rewrite
Reports
    answered rate          answerable questions that got an answer, not a refusal
    correct refusal rate   unanswerable or blocked questions that were refused
    citation valid         answers whose citations all point at clauses given to the model
    citation recall        answers that cite at least one expected clause
    fact checks            answers containing the required figures and none of the superseded ones
    flagged                answers that failed a check (invalid citation, invented number, unsupported claim)
Read eval/results/e2e_<label>.json to see every answer in full. Numbers alone do not replace reading them.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_rag import config  # noqa: E402
from policy_rag.evaluate import GOLDEN, resolve  # noqa: E402


def fact_check(q, text):
    """None when the question has no check, otherwise True or False."""
    must = q.get("must_contain", [])
    any_of = q.get("must_contain_any", [])
    must_not = q.get("must_not_contain", [])
    if not (must or any_of or must_not):
        return None
    low = text.lower()
    return (all(m.lower() in low for m in must)
            and all(any(x.lower() in low for x in group) for group in any_of)
            and not any(m.lower() in low for m in must_not))


def judge_row(q, ans, chunks, judge_only=False):
    expected = set().union(*[resolve(chunks, r) for r in q["expected"]]) if q["expected"] else set()
    forbidden = set().union(*[resolve(chunks, r) for r in q["forbidden"]]) if q["forbidden"] else set()
    cited_ids = {c["chunk_id"] for c in ans.citations}
    leak = [c["chunk_id"] for c in ans.citations if c["chunk_id"] in forbidden or c["doc_id"] in q["forbidden_docs"]]
    return dict(
        id=q["id"], type=q["type"], set=q.get("set", "standard"), role=q["role"], question=q["question"],
        answerable=q["answerable"], status=ans.status, rewritten=ans.rewritten, answer=ans.text,
        cited=[c["label"] for c in ans.citations], refusal_reason=ans.refusal_reason,
        cited_expected=bool(cited_ids & expected) if expected else None,
        citation_valid=(not ans.verification.get("invalid_citations") and not ans.verification.get("uncited"))
        if ans.status != "refused" else None,
        fact_ok=None if judge_only else (fact_check(q, ans.text) if ans.status != "refused"
                                         else (False if fact_check(q, "") is not None else None)),
        verification=ans.verification, leak=leak, seconds=ans.timings.get("total", 0.0))


def summarize(rows):
    ans = [r for r in rows if r["answerable"]]
    non = [r for r in rows if not r["answerable"]]
    given = [r for r in ans if r["status"] != "refused"]
    rate = lambda xs, f: (sum(1 for x in xs if f(x)) / len(xs)) if xs else None
    checks = [r for r in rows if r["fact_ok"] is not None and r["answerable"]]
    return {
        "answerable_n": len(ans), "unanswerable_n": len(non),
        "answered_rate": rate(ans, lambda r: r["status"] != "refused"),
        "correct_refusal_rate": rate(non, lambda r: r["status"] == "refused"),
        "citation_valid": rate(given, lambda r: r["citation_valid"]),
        "citation_recall": rate([r for r in given if r["cited_expected"] is not None], lambda r: r["cited_expected"]),
        "fact_checks": rate(checks, lambda r: r["fact_ok"]), "fact_checks_n": len(checks),
        "flagged_rate": rate(given, lambda r: r["status"] == "flagged"),
        "leaks": sum(len(r["leak"]) for r in rows),
        "mean_seconds": sum(r["seconds"] for r in rows) / len(rows) if rows else 0,
    }


def pct(x):
    return "n/a" if x is None else f"{x:.0%}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--golden", default=str(GOLDEN), help="question file, for example eval/golden_holdout.json")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--ids", nargs="+")
    ap.add_argument("--no-rewrite", action="store_true")
    ap.add_argument("--judge-only", action="store_true", help="stop after the answerability check (about 5 minutes)")
    a = ap.parse_args()

    from policy_rag.assistant import PolicyAssistant
    from policy_rag.cli_search import load_retriever
    from policy_rag.llm import OllamaLLM

    golden = json.loads(Path(a.golden).read_text(encoding="utf-8"))["questions"]
    if a.ids:
        golden = [q for q in golden if q["id"] in a.ids]
    if a.limit:
        golden = golden[: a.limit]

    retriever = load_retriever(config.DEFAULT_MODE)
    bot = PolicyAssistant(retriever, OllamaLLM(), config.DEFAULT_MODE, not a.no_rewrite)
    rows, t0 = [], time.time()
    for i, q in enumerate(golden, 1):
        ans = bot.ask(q["question"], q["role"], judge_only=a.judge_only)
        row = judge_row(q, ans, retriever.index.chunks, a.judge_only)
        rows.append(row)
        print(f"{i:>3}/{len(golden)} {q['id']:<4} {ans.status:<9} {ans.timings.get('total', 0):>5.1f}s  {q['question'][:60]}", flush=True)

    s = summarize(rows)
    print(f"\nFinished in {(time.time() - t0) / 60:.1f} min. Rewrite {'off' if a.no_rewrite else 'on'}, model {config.LLM_MODEL}\n")
    print(f"Answerable questions ({s['answerable_n']})")
    print(f"  answered rate        {pct(s['answered_rate'])}")
    if not a.judge_only:
        print(f"  citation valid       {pct(s['citation_valid'])}")
        print(f"  citation recall      {pct(s['citation_recall'])}")
        print(f"  fact checks          {pct(s['fact_checks'])} of {s['fact_checks_n']}")
        print(f"  flagged              {pct(s['flagged_rate'])}")
    print(f"Unanswerable or blocked ({s['unanswerable_n']})")
    print(f"  correct refusal rate {pct(s['correct_refusal_rate'])}")
    print(f"Leaks (restricted or forbidden clause cited): {s['leaks']}")
    print(f"Mean time per question: {s['mean_seconds']:.1f}s")

    bad = [r for r in rows if (r["answerable"] and (r["status"] != "answered" or r["fact_ok"] is False))
           or (not r["answerable"] and r["status"] != "refused")]
    if bad:
        print("\nWorth reading")
        for r in bad:
            why = f"  (judge: {r['refusal_reason']})" if r["refusal_reason"] else ""
            print(f"  {r['id']} [{r['status']}] {r['question']}\n      -> {r['answer'][:230]}{why}")

    config.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out = config.RESULTS_DIR / f"e2e_{a.label}.json"
    out.write_text(json.dumps(dict(label=a.label, timestamp=datetime.now().isoformat(timespec="seconds"),
                                   llm=config.LLM_MODEL, rewrite=not a.no_rewrite, judge_only=a.judge_only, summary=s, rows=rows),
                              indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved to {out.relative_to(config.ROOT)}")


if __name__ == "__main__":
    main()
