"""Retrieval logic tests with fake models. They check plumbing and safety, not semantic quality."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from policy_rag import config  # noqa: E402
from policy_rag.evaluate import resolve, run_mode, summarize  # noqa: E402
from policy_rag.filters import is_allowed  # noqa: E402
from policy_rag.index import PolicyIndex  # noqa: E402
from policy_rag.parsing import parse_folder  # noqa: E402
from policy_rag.retrieve import MODES, Retriever, rrf, tokenize  # noqa: E402


class FakeEmbedder:
    """Hashed bag of words. Deterministic, no model needed."""

    def embed(self, texts):
        out = np.zeros((len(texts), 256), dtype=np.float32)
        for r, t in enumerate(texts):
            for w in tokenize(t):
                out[r, int(hashlib.md5(w.encode()).hexdigest(), 16) % 256] += 1
        norm = np.linalg.norm(out, axis=1, keepdims=True)
        return out / np.where(norm == 0, 1, norm)


class FakeReranker:
    def score(self, query, passages):
        q = set(tokenize(query))
        return [len(q & set(tokenize(p))) / (1 + len(set(tokenize(p)))) for p in passages]


@pytest.fixture(scope="module")
def retriever():
    chunks = [c for _, cs in parse_folder(config.HANDBOOK_DIR) for c in cs]
    index = PolicyIndex.build(chunks, FakeEmbedder(), "fake")
    return Retriever(index, FakeEmbedder(), FakeReranker())


@pytest.fixture(scope="module", params=["golden_policy.json", "golden_holdout.json", "golden_final.json"])
def golden(request):
    return json.loads((ROOT / "eval" / request.param).read_text(encoding="utf-8"))["questions"]


def test_rrf_rewards_agreement():
    order, scores = rrf([["a", "b", "c"], ["b", "a", "d"]])
    assert order[:2] == ["a", "b"] or order[:2] == ["b", "a"]
    assert scores["a"] == scores["b"] > scores["c"]
    assert set(order) == {"a", "b", "c", "d"}


def test_golden_references_all_resolve(retriever, golden):
    chunks = retriever.index.chunks
    for q in golden:
        for ref in q["expected"] + q["forbidden"]:
            assert len(resolve(chunks, ref)) == 1, f"{q['id']}: {ref} does not resolve to exactly one chunk"
        for doc in q["forbidden_docs"]:
            assert any(c.meta.doc_id == doc for c in chunks)


def test_golden_expected_is_reachable_by_role(retriever, golden):
    chunks = {c.chunk_id: c for c in retriever.index.chunks}
    for q in golden:
        for ref in q["expected"]:
            for cid in resolve(retriever.index.chunks, ref):
                assert is_allowed(chunks[cid], q["role"]), f"{q['id']} expects {ref} but role {q['role']} cannot see it"


@pytest.mark.parametrize("role", config.ROLES)
@pytest.mark.parametrize("mode", MODES)
def test_no_forbidden_content_for_any_role(retriever, role, mode):
    for query in ["bonus percentage grade 5", "notice period", "annual leave days", "quotations purchase", "carry forward"]:
        for h in retriever.search(query, role, 10, mode):
            assert h.chunk.meta.status == "current"
            assert "all" in h.chunk.meta.audience or role in h.chunk.meta.audience


def test_employee_cannot_see_restricted_but_manager_can(retriever):
    emp = {h.chunk.meta.doc_id for h in retriever.search("quotations purchase tender", "employee", 10, "bm25")}
    mgr = {h.chunk.meta.doc_id for h in retriever.search("quotations purchase tender", "manager", 10, "bm25")}
    assert "POL-12" not in emp and "POL-12" in mgr


def test_superseded_version_never_returned(retriever):
    for h in retriever.search("14 days of paid annual leave carry forward 8 days", "employee", 10, "hybrid"):
        assert h.chunk.meta.version != "3.0"


def test_future_policy_not_returned(retriever):
    # Before POL-05 took effect (2026-03-01) it must not be searchable.
    hits = retriever.search("hotel cap per night", "employee", 10, "bm25", as_of="2026-02-01")
    assert all(h.chunk.meta.doc_id != "POL-05" for h in hits)
    hits = retriever.search("hotel cap per night", "employee", 10, "bm25", as_of="2026-03-01")
    assert any(h.chunk.meta.doc_id == "POL-05" for h in hits)


def test_rerank_mode_orders_by_rerank_score(retriever):
    hits = retriever.search("fire drills", "employee", 5, "hybrid_rerank")
    scores = [h.rerank_score for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_evaluation_runs_and_reports_zero_violations(retriever, golden):
    for mode in MODES:
        rows = run_mode(retriever, golden, mode)
        s = summarize(rows)
        assert s["violations"] == 0
        assert 0 <= s["mrr"] <= 1 and s["n"] == sum(q["answerable"] for q in golden)


def test_summarize_math():
    rows = [dict(answerable=True, rank=1, cover5=1.0, violations=[]),
            dict(answerable=True, rank=4, cover5=0.5, violations=[]),
            dict(answerable=True, rank=None, cover5=0.0, violations=[]),
            dict(answerable=False, rank=None, cover5=None, violations=["x"])]
    s = summarize(rows)
    assert s["hit@1"] == pytest.approx(1 / 3) and s["hit@5"] == pytest.approx(2 / 3)
    assert s["mrr"] == pytest.approx((1 + 0.25) / 3) and s["violations"] == 1


def test_blend_mode_keeps_same_candidates_as_rerank(retriever):
    a = retriever.search("fire drills", "employee", 15, "hybrid_rerank")
    b = retriever.search("fire drills", "employee", 15, "hybrid_blend")
    assert {h.chunk.chunk_id for h in a} == {h.chunk.chunk_id for h in b}


def test_bm25_ignores_stopwords(retriever):
    from policy_rag.retrieve import keyword_tokens
    assert keyword_tokens("How many days of leave do I get?") == ["many", "days", "leave", "get"]


@pytest.mark.parametrize("mode", MODES)
def test_every_mode_returns_results(retriever, mode):
    assert len(retriever.search("annual leave carry forward", "employee", 5, mode)) == 5


def test_question_files_are_well_formed():
    seen = set()
    for name in ("golden_policy.json", "golden_holdout.json", "golden_final.json"):
        for q in json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))["questions"]:
            assert q["id"] not in seen, f"duplicate id {q['id']}"
            seen.add(q["id"])
            assert q["role"] in config.ROLES, q["id"]
            assert bool(q["expected"]) == bool(q["answerable"]), f"{q['id']}: answerable questions need expected clauses and the others none"
            assert q["question"].strip()
    holdout = json.loads((ROOT / "eval" / "golden_holdout.json").read_text(encoding="utf-8"))["questions"]
    tuned = {q["question"].lower() for q in json.loads((ROOT / "eval" / "golden_policy.json").read_text(encoding="utf-8"))["questions"]}
    assert not any(q["question"].lower() in tuned for q in holdout), "held-out questions must differ from the tuned set"


def test_final_set_does_not_overlap_the_earlier_sets():
    def load(name):
        return json.loads((ROOT / "eval" / name).read_text(encoding="utf-8"))["questions"]
    earlier = {q["question"].lower() for name in ("golden_policy.json", "golden_holdout.json") for q in load(name)}
    assert not any(q["question"].lower() in earlier for q in load("golden_final.json"))
