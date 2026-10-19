"""Build, save and load the search index: chunks plus one embedding vector per chunk."""

import json

import numpy as np

from .models import Chunk


class PolicyIndex:
    def __init__(self, chunks, vectors, embed_model):
        assert len(chunks) == len(vectors)
        self.chunks = chunks
        self.vectors = vectors
        self.embed_model = embed_model

    @classmethod
    def build(cls, chunks, embedder, embed_model):
        vectors = embedder.embed([c.index_text for c in chunks])
        return cls(chunks, vectors, embed_model)

    def save(self, folder):
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / "chunks.jsonl").open("w", encoding="utf-8") as fh:
            for c in self.chunks:
                fh.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        np.save(folder / "vectors.npy", self.vectors)
        (folder / "info.json").write_text(json.dumps({"embed_model": self.embed_model}), encoding="utf-8")

    @classmethod
    def load(cls, folder):
        chunks = [Chunk.from_dict(json.loads(l)) for l in (folder / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
        vectors = np.load(folder / "vectors.npy")
        info = json.loads((folder / "info.json").read_text(encoding="utf-8"))
        return cls(chunks, vectors, info["embed_model"])
