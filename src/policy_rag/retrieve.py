"""Filtered hybrid retrieval: vector search + BM25 keyword search, fused, then reranked."""

import re
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from . import config
from .filters import is_allowed

MODES = ("dense", "bm25", "hybrid", "hybrid_rerank", "hybrid_blend")
TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")


STOPWORDS = set("""a an and are as at be but by can do does for from has have how i if in is it its my me of on or so
that the their them then there these they this to was we what when where which who why will with would you your""".split())


def tokenize(text):
    return TOKEN_RE.findall(text.lower())


def keyword_tokens(text):
    """Tokens for BM25. Common words are dropped so they cannot outweigh the rare, meaningful ones."""
    return [t for t in tokenize(text) if t not in STOPWORDS]


def rrf(rankings, k=config.RRF_K):
    """Reciprocal rank fusion. rankings is a list of ranked id lists. Returns ids sorted by fused score."""
    scores = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: scores[i], reverse=True), scores


@dataclass
class Hit:
    chunk: object
    score: float
    dense_rank: int = 0
    bm25_rank: int = 0
    rerank_score: float = None


class Retriever:
    def __init__(self, index, embedder, reranker=None):
        self.index = index
        self.embedder = embedder
        self.reranker = reranker
        self._bm25_cache = {}

    def _allowed_ids(self, role, as_of):
        return [i for i, c in enumerate(self.index.chunks) if is_allowed(c, role, as_of)]

    def _bm25(self, allowed, key):
        # Built on the allowed subset only, so word statistics never come from forbidden text.
        if key not in self._bm25_cache:
            docs = [keyword_tokens(self.index.chunks[i].index_text) for i in allowed]
            self._bm25_cache[key] = BM25Okapi(docs)
        return self._bm25_cache[key]

    def search(self, query, role="employee", k=config.DEFAULT_K, mode="hybrid_rerank", as_of=None):
        assert mode in MODES, f"mode must be one of {MODES}"
        allowed = self._allowed_ids(role, as_of)
        if not allowed:
            return []

        dense_order, bm25_order = [], []
        if mode != "bm25":
            q = self.embedder.embed([query])[0]
            sims = self.index.vectors[allowed] @ q
            order = np.argsort(-sims)[: config.DENSE_POOL]
            dense_order = [allowed[i] for i in order]
        if mode != "dense":
            bm = self._bm25(allowed, (role, as_of))
            scores = bm.get_scores(keyword_tokens(query))
            order = np.argsort(-scores)[: config.BM25_POOL]
            bm25_order = [allowed[i] for i in order if scores[i] > 0]

        d_rank = {cid: r for r, cid in enumerate(dense_order, 1)}
        b_rank = {cid: r for r, cid in enumerate(bm25_order, 1)}

        if mode == "dense":
            ranked, score = dense_order, {c: 1 / (r) for c, r in d_rank.items()}
        elif mode == "bm25":
            ranked, score = bm25_order, {c: 1 / (r) for c, r in b_rank.items()}
        else:
            ranked, score = rrf([dense_order, bm25_order])

        hits = [Hit(self.index.chunks[i], score[i], d_rank.get(i, 0), b_rank.get(i, 0)) for i in ranked]

        if mode in ("hybrid_rerank", "hybrid_blend") and self.reranker and hits:
            pool = hits[: config.RERANK_POOL]
            rr = self.reranker.score(query, [h.chunk.index_text for h in pool])
            for h, s in zip(pool, rr):
                h.rerank_score = s
            by_rerank = sorted(pool, key=lambda h: h.rerank_score, reverse=True)
            if mode == "hybrid_blend":
                # Keep the reranker's opinion but let the first-stage ranking vote too. This protects
                # clauses a cross-encoder undervalues, such as "this policy does not provide for X".
                order, _ = rrf([[id(h) for h in by_rerank], [id(h) for h in pool]])
                lookup = {id(h): h for h in pool}
                by_rerank = [lookup[i] for i in order]
            hits = by_rerank + hits[config.RERANK_POOL:]
        return hits[:k]

    def search_multi(self, queries, role="employee", k=config.DEFAULT_K, mode="dense", as_of=None):
        """Search with several phrasings of one question and fuse the rankings.

        Keeping the original question in the mix protects against a bad rewrite.
        """
        lists = [self.search(q, role, 20, mode, as_of) for q in queries]
        first = {}
        for hits in lists:
            for h in hits:
                first.setdefault(h.chunk.chunk_id, h)
        order, scores = rrf([[h.chunk.chunk_id for h in hits] for hits in lists])
        out = []
        for cid in order[:k]:
            h = first[cid]
            out.append(Hit(h.chunk, scores[cid], h.dense_rank, h.bm25_rank, h.rerank_score))
        return out
