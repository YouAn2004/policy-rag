"""Ask a question end to end. Needs Ollama running (bge-m3 and the answer model) and a built index.

Usage:
    python src/policy_rag/cli_ask.py "can i wfh everyday?"
    python src/policy_rag/cli_ask.py "what bonus does a grade 5 get?" --role hr
    python src/policy_rag/cli_ask.py "..." --no-rewrite
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_rag import config  # noqa: E402
from policy_rag.assistant import PolicyAssistant  # noqa: E402
from policy_rag.cli_search import load_retriever  # noqa: E402
from policy_rag.llm import OllamaLLM  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--role", default="employee", choices=config.ROLES)
    ap.add_argument("--no-rewrite", action="store_true")
    a = ap.parse_args()

    bot = PolicyAssistant(load_retriever(config.DEFAULT_MODE), OllamaLLM(), config.DEFAULT_MODE, not a.no_rewrite)
    r = bot.ask(a.question, a.role)

    print(f"[{r.status.upper()}] role={r.role}")
    if r.rewritten:
        print(f"rewritten query: {r.rewritten}")
    print(f"\n{r.text}\n")
    for c in r.citations:
        print(f"  [{c['label']}] {c['title']} v{c['version']} (effective {c['effective_date']})\n      {c['text']}")
    if r.status == "refused":
        print(f"  reason: {r.refusal_reason}")
    elif r.verification:
        v = r.verification
        print(f"\nchecks: invalid citations={v['invalid_citations']} uncited={v['uncited']} "
              f"unsupported numbers={v['unsupported_numbers']} llm support={v['llm_support']}")
    print("\ntimings: " + ", ".join(f"{k} {t:.1f}s" for k, t in r.timings.items()))


if __name__ == "__main__":
    main()
