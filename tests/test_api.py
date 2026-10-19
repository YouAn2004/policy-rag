import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from policy_rag import config  # noqa: E402
from policy_rag.api import create_app, read_results  # noqa: E402
from test_assistant import OK_JUDGE, OK_SUPPORT, ScriptedLLM, bot, retriever  # noqa: E402,F401


def parse_events(body):
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n", 1)
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


@pytest.fixture
def client(retriever, tmp_path):
    llm = ScriptedLLM(judge=OK_JUDGE, support=OK_SUPPORT, answer="You get 16 days [POL-02 §1.1].")
    return TestClient(create_app(bot(retriever, llm), results_dir=tmp_path, web_dist=tmp_path / "none"))


def test_ask_streams_each_stage_then_the_result(client):
    r = client.post("/api/ask", json={"question": "How many days of annual leave do I get?", "role": "employee"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_events(r.text)
    assert [e[0] for e in events] == ["step"] * 4 + ["result"]
    assert [e[1]["stage"] for e in events[:4]] == ["search", "judge", "answer", "verify"]
    result = events[-1][1]
    assert result["status"] == "answered" and result["citations"][0]["label"] == "POL-02 §1.1"
    assert "16 days" in result["citations"][0]["text"] or result["citations"][0]["text"]


def test_a_refusal_carries_the_contact(retriever, tmp_path):
    llm = ScriptedLLM(judge='{"clause": "none", "reason": "nothing"}')
    c = TestClient(create_app(bot(retriever, llm), results_dir=tmp_path, web_dist=tmp_path / "none"))
    events = parse_events(c.post("/api/ask", json={"question": "Can I bring my dog?", "role": "employee"}).text)
    assert events[-1][0] == "result" and events[-1][1]["status"] == "refused" and events[-1][1]["contact"]


@pytest.mark.parametrize("body", [{"question": "   ", "role": "employee"}, {"question": "hi", "role": "ceo"},
                                  {"question": "x" * 1001, "role": "employee"}, {"role": "employee"}])
def test_bad_requests_are_rejected(client, body):
    assert client.post("/api/ask", json=body).status_code == 422


def test_a_crash_inside_the_pipeline_becomes_an_error_event(retriever, tmp_path):
    class Broken:
        def complete(self, *a, **k):
            raise RuntimeError("connection refused")

    c = TestClient(create_app(bot(retriever, Broken()), results_dir=tmp_path, web_dist=tmp_path / "none"))
    events = parse_events(c.post("/api/ask", json={"question": "How many days of annual leave?", "role": "employee"}).text)
    assert events[-1][0] == "error" and "Ollama" in events[-1][1]["message"]


def test_roles_show_that_restricted_roles_see_more(client):
    roles = {r["id"]: r for r in client.get("/api/roles").json()["roles"]}
    assert set(roles) == set(config.ROLES)
    assert roles["employee"]["documents"] < roles["executive"]["documents"]
    assert roles["executive"]["clauses"] > roles["employee"]["clauses"]


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_eval_endpoint_summarises_saved_runs(tmp_path):
    rows = [{"id": "h01"}, {"id": "h20"}]
    (tmp_path / "e2e_x.json").write_text(json.dumps({"label": "x", "timestamp": "2026-01-02", "rows": rows,
                                                     "summary": {"answered_rate": 1.0}}), encoding="utf-8")
    (tmp_path / "v9.json").write_text(json.dumps({"label": "v9", "results": {
        "dense": {"summary": {"n": 58, "mrr": 0.9}}, "bm25": {"summary": {"n": 58, "mrr": 0.6}}}}), encoding="utf-8")
    (tmp_path / "old.json").write_text(json.dumps({"label": "old", "results": {"dense": {"summary": {"n": 42, "mrr": 0.5}}}}), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    out = read_results(tmp_path)
    assert out["runs"][0]["set"] == "held-out" and out["runs"][0]["summary"]["answered_rate"] == 1.0
    assert out["retrieval"]["n"] == 58 and set(out["retrieval"]["modes"]) == {"dense", "bm25"}


@pytest.mark.skipif(not any(config.RESULTS_DIR.glob("e2e_*.json")), reason="no saved evaluation runs in this checkout")
def test_eval_endpoint_reads_the_real_results_folder(retriever):
    c = TestClient(create_app(bot(retriever, ScriptedLLM(judge=OK_JUDGE))))
    data = c.get("/api/eval").json()
    assert data["runs"] and all(r["set"] in {"tuned", "held-out", "final", "mixed"} for r in data["runs"])
    assert data["retrieval"]["n"] >= 58
