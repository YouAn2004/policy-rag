"""Embedding and reranking back ends. Both are small interfaces so tests can swap in fakes."""

import numpy as np


class OllamaEmbedder:
    def __init__(self, model, batch=16, cpu=False):
        self.model = model
        self.batch = batch
        # num_gpu 0 runs the embedding model on the CPU, so it never competes with the language model for GPU memory
        self.options = {"num_gpu": 0} if cpu else None

    def embed(self, texts):
        import ollama

        out = []
        for i in range(0, len(texts), self.batch):
            resp = ollama.embed(model=self.model, input=texts[i : i + self.batch],
                              keep_alive="30m", options=self.options)
            out.extend(resp["embeddings"])
        arr = np.asarray(out, dtype=np.float32)
        return arr / np.linalg.norm(arr, axis=1, keepdims=True)


class FastembedReranker:
    """Cross-encoder reranker. Reads query and clause together, so it judges relevance more sharply."""

    def __init__(self, model):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model = TextCrossEncoder(model_name=model)

    def score(self, query, passages):
        return [float(s) for s in self.model.rerank(query, passages)]
