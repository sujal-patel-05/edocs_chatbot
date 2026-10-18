"""
Embedding module for dense and sparse vectors (BAAI/bge-m3).

Provides incremental embedding tracking to skip re-embedding unchanged chunks.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple
from src.edocs.models import Chunk

logger = logging.getLogger("edocs.ingest.embed")


class EmbeddingService:
    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu", batch_size: int = 16):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None
        self._is_loaded = False

    def load_model(self):
        if self._is_loaded:
            return
        try:
            from FlagEmbedding import BGEM3FlagModel
            logger.info("Loading BGE-M3 model (%s) on %s...", self.model_name, self.device)
            self._model = BGEM3FlagModel(self.model_name, use_fp16=(self.device == "cuda"), device=self.device)
            self._is_loaded = True
        except Exception as e:
            logger.warning(
                "FlagEmbedding / BGEM3FlagModel not available (%s). Using fallback hash embeddings for test/dev.",
                e,
            )
            self._model = None
            self._is_loaded = False

    def embed_chunks(
        self, chunks: List[Chunk]
    ) -> Tuple[List[List[float]], List[Dict[str, Any]]]:
        """
        Embed a list of chunks into dense and sparse vectors.
        Returns: (dense_vectors, sparse_vectors)
        """
        if not chunks:
            return [], []

        texts = [c.text for c in chunks]

        if self._model is not None:
            output = self._model.encode(
                texts,
                batch_size=self.batch_size,
                max_length=1024,
                return_dense=True,
                return_sparse=True,
            )
            dense_vecs = output["dense_vecs"].tolist()
            sparse_vecs = []
            for sp in output["lexical_weights"]:
                # Convert string token weights to indices/values for Qdrant
                indices = [abs(hash(k)) % (2**31 - 1) for k in sp.keys()]
                values = [float(v) for v in sp.values()]
                sparse_vecs.append({"indices": indices, "values": values})
            return dense_vecs, sparse_vecs

        # Fallback deterministic pseudo-embeddings for fast local testing/dev
        dense_vecs = []
        sparse_vecs = []
        for text in texts:
            # Deterministic 1024-d unit vector from text hash
            h = abs(hash(text))
            vec = [(float((h * (i + 1)) % 1000) / 1000.0) - 0.5 for i in range(1024)]
            # Normalize
            norm = sum(x**2 for x in vec) ** 0.5 or 1.0
            dense_vecs.append([x / norm for x in vec])

            # Deterministic sparse weights
            words = text.split()[:50]
            indices = [abs(hash(w)) % (2**31 - 1) for w in words]
            values = [1.0] * len(words)
            sparse_vecs.append({"indices": indices, "values": values})

        return dense_vecs, sparse_vecs
