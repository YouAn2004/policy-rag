"""Build the search index from the handbook. Needs Ollama running with bge-m3 pulled.

Usage (project root):  python src/policy_rag/cli_index.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from policy_rag import config  # noqa: E402
from policy_rag.embeddings import OllamaEmbedder  # noqa: E402
from policy_rag.index import PolicyIndex  # noqa: E402
from policy_rag.parsing import parse_folder  # noqa: E402


def main():
    chunks = [c for _, cs in parse_folder(config.HANDBOOK_DIR) for c in cs]
    print(f"Embedding {len(chunks)} chunks with {config.EMBED_MODEL} ...")
    index = PolicyIndex.build(chunks, OllamaEmbedder(config.EMBED_MODEL), config.EMBED_MODEL)
    index.save(config.INDEX_DIR)
    print(f"Saved index to {config.INDEX_DIR}")


if __name__ == "__main__":
    main()
