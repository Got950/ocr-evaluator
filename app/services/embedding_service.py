from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


@dataclass(frozen=True)
class EmbeddingService:
    model: SentenceTransformer

    @classmethod
    def load(cls) -> "EmbeddingService":
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return cls(model=model)

    def embed(self, text: str) -> np.ndarray:
        vec = self.model.encode([text], convert_to_numpy=True, normalize_embeddings=False)[0]
        return np.asarray(vec, dtype=np.float32)

    def similarity(self, text_a: str, text_b: str) -> float:
        va = self.embed(text_a)
        vb = self.embed(text_b)
        return _cosine_similarity(va, vb)

