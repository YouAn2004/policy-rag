"""Start the web server: API plus the built chat interface if web/dist exists.

Usage (project root, Ollama running, index built):
    python src/policy_rag/serve.py
    python src/policy_rag/serve.py --port 8001

The server listens on 127.0.0.1 only, so it is reachable from this computer and nowhere else.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    a = ap.parse_args()

    import uvicorn

    uvicorn.run("policy_rag.api:app", host=a.host, port=a.port)


if __name__ == "__main__":
    main()
