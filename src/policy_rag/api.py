"""HTTP API for the chat interface.

    POST /api/ask      question + role in, server sent events out (one "step" event per pipeline stage,
                       then one "result" event with the full answer)
    GET  /api/roles    roles with how much of the handbook each can see
    GET  /api/eval     saved evaluation runs and the retrieval ablation
    GET  /api/health   liveness and model names

The built interface in web/dist is served from the same process when it exists.
"""

import json
import queue
import threading
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .filters import is_allowed

WEB_DIST = config.ROOT / "web" / "dist"
STAGES = ["rewrite", "search", "judge", "answer", "verify"]
SET_BY_PREFIX = {"g": "tuned", "s": "tuned", "h": "held-out", "f": "final"}


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    role: str = "employee"


def load_assistant():
    """Build the real assistant: index from disk, Ollama for embeddings and answers."""
    from .assistant import PolicyAssistant
    from .cli_search import load_retriever
    from .llm import OllamaLLM

    return PolicyAssistant(load_retriever(config.DEFAULT_MODE), OllamaLLM(), config.DEFAULT_MODE, config.USE_REWRITE)


def sse(event, data):
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def role_summary(chunks, role):
    today = date.today().isoformat()
    allowed = [c for c in chunks if is_allowed(c, role, today)]
    return {"id": role, "documents": len({c.meta.doc_id for c in allowed}), "clauses": len(allowed)}


def set_name(rows):
    names = {SET_BY_PREFIX.get(r["id"][:1], "other") for r in rows}
    return names.pop() if len(names) == 1 else "mixed"


def read_results(folder):
    """Summaries of every saved end to end run and the best retrieval ablation. Rows are left out."""
    runs, retrieval = [], {}
    best_n = 0
    for path in sorted(folder.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if path.name.startswith("e2e_") and "summary" in data:
            runs.append({"label": data.get("label", path.stem), "timestamp": data.get("timestamp", ""),
                         "set": set_name(data.get("rows", [])), "judge_only": bool(data.get("judge_only")),
                         "summary": data["summary"]})
        elif isinstance(data.get("results"), dict):
            for mode, res in data["results"].items():
                summary = res.get("summary", {})
                if summary.get("n", 0) >= best_n:
                    if summary["n"] > best_n:
                        retrieval, best_n = {}, summary["n"]
                    retrieval[mode] = {**summary, "run": data.get("label", path.stem)}
    runs.sort(key=lambda r: r["timestamp"])
    return {"runs": runs, "retrieval": {"n": best_n, "modes": retrieval}}


def create_app(assistant=None, results_dir=None, web_dist=None):
    """assistant may be a ready PolicyAssistant (tests pass one with fake models). Otherwise it loads at startup."""
    state = {"bot": assistant}
    lock = threading.Lock()  # Ollama handles one request at a time anyway
    results_dir = results_dir or config.RESULTS_DIR

    @asynccontextmanager
    async def lifespan(app):
        if state["bot"] is None:
            state["bot"] = load_assistant()
        yield

    app = FastAPI(title="Policy RAG", lifespan=lifespan)

    @app.get("/api/health")
    def health():
        return {"ok": state["bot"] is not None, "llm": config.LLM_MODEL, "embeddings": config.EMBED_MODEL}

    @app.get("/api/roles")
    def roles():
        chunks = state["bot"].retriever.index.chunks
        return {"roles": [role_summary(chunks, r) for r in config.ROLES], "stages": STAGES}

    @app.get("/api/eval")
    def evaluation():
        return read_results(results_dir)

    @app.post("/api/ask")
    def ask(req: AskRequest):
        question = req.question.strip()
        if not question:
            raise HTTPException(422, "The question is empty.")
        if req.role not in config.ROLES:
            raise HTTPException(422, f"Unknown role. Use one of {', '.join(config.ROLES)}.")
        bot = state["bot"]
        events = queue.Queue()

        def work():
            try:
                with lock:
                    answer = bot.ask(question, req.role, progress=lambda stage: events.put(("step", {"stage": stage})))
                events.put(("result", answer.to_dict()))
            except Exception as exc:  # the browser gets a readable message instead of a dropped stream
                events.put(("error", {"message": f"The assistant could not finish. Is Ollama running? ({str(exc)[:160]})"}))
            finally:
                events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def stream():
            while (item := events.get()) is not None:
                yield sse(*item)

        return StreamingResponse(stream(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    dist = web_dist if web_dist is not None else WEB_DIST
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


app = create_app()
