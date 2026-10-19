"""Central settings. Change models here, nowhere else."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HANDBOOK_DIR = ROOT / "data" / "handbook"
INDEX_DIR = ROOT / "build" / "index"
RESULTS_DIR = ROOT / "eval" / "results"

EMBED_MODEL = "bge-m3"  # served by Ollama
EMBED_ON_CPU = True  # queries are short, and this keeps the GPU free so the language model is never evicted
RERANK_MODEL = "BAAI/bge-reranker-base"  # cross-encoder, runs locally through fastembed (ONNX)

ROLES = ["employee", "manager", "hr", "finance", "executive"]

DENSE_POOL = 20  # candidates taken from vector search
BM25_POOL = 20  # candidates taken from keyword search
RRF_K = 60  # reciprocal rank fusion constant
RERANK_POOL = 15  # fused candidates passed to the cross-encoder
DEFAULT_K = 5

# Answering
LLM_MODEL = "qwen2.5:7b"  # served by Ollama
LLM_NUM_CTX = 8192
DEFAULT_MODE = "dense"  # best retrieval mode in the v2b ablation
USE_REWRITE = True  # rewrite casual questions into handbook wording before retrieval
THRESHOLD_HINTS = True  # code compares the employee's figures with clause thresholds and tells the model
CONTEXT_HITS = 5  # retrieved clauses used to pick sections for the prompt
MAX_SECTIONS = 4  # at most this many policy sections go into the prompt
MAX_RETRIES = 1  # one regeneration if the answer fails the structural checks

# Who to point people to when the handbook cannot answer. Matched against the policy owner.
CONTACTS = {
    "Human Resources": "hr@meridianworks.example",
    "Finance": "finance@meridianworks.example",
    "IT Security": "security@meridianworks.example",
    "Legal and Compliance": "compliance@meridianworks.example",
    "Facilities": "safety@meridianworks.example",
}
DEFAULT_CONTACT = ("Human Resources", "hr@meridianworks.example")
