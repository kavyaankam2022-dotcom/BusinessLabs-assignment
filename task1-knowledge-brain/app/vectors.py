from functools import cached_property
from typing import Sequence

import numpy as np


class Embedder:
    """Lazy sentence-transformer embeddings; model loading is deferred until needed."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @cached_property
    def model(self):
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(self.model_name)

    def encode(self, text: str) -> list[float]:
        vector = self.model.encode(text, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32).tolist()

    @staticmethod
    def similarity(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            return 0.0
        return max(0.0, min(1.0, float(np.dot(left, right))))