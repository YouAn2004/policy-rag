"""Find out why answerable questions are refused.

For each question it shows what the judge was given, then repeats the judge with only the correct
clause ("oracle" context). Comparing the two separates retrieval problems from judge problems.

Usage (project root, Ollama running, index built):
    python src/policy_rag/diagnose.py
    python src/policy_rag/diagnose.py --ids g04 g13 --no-rewrite
"""

import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_rag import config  # noqa: E402
from policy_rag.evaluate import GOLDEN, resolve  # noqa: E402
from policy_rag.judge import find_clause  # noqa: E402
from policy_rag.thresholds import threshold_hints  # noqa: E402

# the answerable questions that were wrongly refused, then the unanswerable ones that must stay refused
DEFAULT_IDS = ["g04", "g08", "g13", "g16", "g38", "s01", "s03",
               "g43", "g44", "g45", "g46", "g47", "g48", "g49", "g50"]


def diagnose(real_ok, in_context, oracle_ok, answerable=True):
    if not answerable:
        return "BAD: an unanswerable question got through the judge" if real_ok else "OK, refused as it should be"
    if real_ok:
        return "OK, now answered"
    if not in_context:
        return ("RETRIEVAL: the correct clause was not in the context, but the judge accepts it when shown"
                if oracle_ok else
                "BOTH: the correct clause was missing and the judge rejects it even when shown")
    return ("DISTRACTION: the correct clause was shown but the judge still refused (other sections interfered)"
            if oracle_ok else
            "JUDGE: the judge rejects the correct clause even when it is the only context")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", nargs="+", default=DEFAULT_IDS)
    ap.add_argument("--no-rewrite", action="store_true")
    a = ap.parse_args()

    from policy_rag.assistant import PolicyAssistant
    from policy_rag.cli_search import load_retriever
    from policy_rag.llm import OllamaLLM
    from policy_rag.rewrite import rewrite_query

    golden = [q for q in json.loads(GOLDEN.read_text(encoding="utf-8"))["questions"] if q["id"] in a.ids]
    llm = OllamaLLM()
    retriever = load_retriever(config.DEFAULT_MODE)
    bot = PolicyAssistant(retriever, llm, config.DEFAULT_MODE, not a.no_rewrite)
    chunks = retriever.index.chunks
    summary = []

    for q in golden:
        question, role = q["question"], q["role"]
        queries, rewritten = [question], ""
        if not a.no_rewrite:
            rewritten = rewrite_query(llm, question)
            if rewritten.strip().lower() != question.strip().lower():
                queries.append(rewritten)
        if len(queries) > 1:
            hits = retriever.search_multi(queries, role, config.CONTEXT_HITS, config.DEFAULT_MODE)
        else:
            hits = retriever.search(question, role, config.CONTEXT_HITS, config.DEFAULT_MODE)

        context, available = bot.build_context(hits)
        expected_ids = set().union(*[resolve(chunks, r) for r in q["expected"]]) if q["expected"] else set()
        expected = [c for c in chunks if c.chunk_id in expected_ids]
        in_context = any(c.cite_key.lower() in available for c in expected)

        print("=" * 100)
        print(f"{q['id']} ({role}) {question}")
        print(f"rewritten : {rewritten or '(none)'}")
        print(f"expected  : {', '.join(c.cite_key for c in expected)}")
        print("top hits  :")
        for i, h in enumerate(hits, 1):
            mark = "*" if h.chunk.chunk_id in expected_ids else " "
            print(f"  {i}{mark} {h.chunk.cite_key}  [{h.chunk.section_title}]")
        print(f"context   : {len(context)} characters" + (f", correct clause in context = {in_context}" if expected else ""))

        checks = (threshold_hints(question, [(c.cite_key, c.text) for c in available.values()])
                  if config.THRESHOLD_HINTS else "")
        if checks:
            print("checked   :\n" + "\n".join("  " + l for l in checks.split("\n")))
        v = find_clause(llm, question, context, available, checks)
        real_ok = v.answerable
        print(f"judge (real context)   answerable={real_ok}  clause={v.clause!r}  raw={v.raw[:160]!r}")

        oracle_ok = None
        if expected and q["answerable"]:
            octx, oavail = bot.build_context([SimpleNamespace(chunk=c) for c in expected])
            ov = find_clause(llm, question, octx, oavail,
                             threshold_hints(question, [(c.cite_key, c.text) for c in oavail.values()])
                             if config.THRESHOLD_HINTS else "")
            oracle_ok = ov.answerable
            print(f"judge (correct clause) answerable={oracle_ok}  clause={ov.clause!r}  raw={ov.raw[:160]!r}")

        verdict = diagnose(real_ok, in_context, bool(oracle_ok), q["answerable"])
        print(f"diagnosis : {verdict}")
        summary.append((q["id"], verdict.split(":")[0].split(",")[0]))

    print("\n" + "=" * 100)
    print("Summary")
    for qid, v in summary:
        print(f"  {qid:<5} {v}")


if __name__ == "__main__":
    main()
