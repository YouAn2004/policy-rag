"""Try a search from the terminal.

Usage:
    python src/policy_rag/cli_search.py "how many days of annual leave do I get?" --role employee
    python src/policy_rag/cli_search.py "bonus for grade 5" --role hr --mode dense --k 8
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_rag import config  # noqa: E402
from policy_rag.embeddings import FastembedReranker, OllamaEmbedder  # noqa: E402
from policy_rag.index import PolicyIndex  # noqa: E402
from policy_rag.retrieve import MODES, Retriever  # noqa: E402


def load_retriever(mode):
    index = PolicyIndex.load(config.INDEX_DIR)
    if index.embed_model != config.EMBED_MODEL:
        sys.exit(f"Index was built with {index.embed_model}, config says {config.EMBED_MODEL}. Rebuild with cli_index.py.")
    reranker = FastembedReranker(config.RERANK_MODEL) if mode == "hybrid_rerank" else None
    return Retriever(index, OllamaEmbedder(config.EMBED_MODEL, cpu=config.EMBED_ON_CPU), reranker)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--role", default="employee", choices=config.ROLES)
    ap.add_argument("--mode", default="hybrid_rerank", choices=MODES)
    ap.add_argument("--k", type=int, default=config.DEFAULT_K)
    a = ap.parse_args()

    hits = load_retriever(a.mode).search(a.query, a.role, a.k, a.mode)
    print(f"role={a.role} mode={a.mode}\n")
    for i, h in enumerate(hits, 1):
        extra = f" rerank={h.rerank_score:.2f}" if h.rerank_score is not None else ""
        print(f"{i}. {h.chunk.citation}  score={h.score:.4f} dense#{h.dense_rank} bm25#{h.bm25_rank}{extra}")
        print(f"   {h.chunk.text[:160]}")


if __name__ == "__main__":
    main()
