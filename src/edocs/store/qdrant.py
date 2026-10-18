"""
Qdrant vector store backend for eDocs chunks.

Implements hybrid search using named dense (1024-dim cosine) and named sparse vectors.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from src.edocs.models import Chunk

logger = logging.getLogger("edocs.store.qdrant")


class QdrantVectorStore:
    def __init__(self, url: str = "http://localhost:6333", collection_name: str = "edocs_chunks"):
        self.url = url
        self.collection_name = collection_name
        self.client = None
        self._is_available = False
        self._init_client()

    def _init_client(self):
        try:
            from qdrant_client import QdrantClient
            self.client = QdrantClient(url=self.url, timeout=2.0)
            # Test connectivity
            self.client.get_collections()
            self._is_available = True
            logger.info("Connected to Qdrant at %s", self.url)
            self.init_collection()
        except Exception as e:
            logger.warning(
                "Qdrant at %s unavailable (%s). Running in offline/mock mode for local dev.",
                self.url,
                e,
            )
            self._is_available = False

    @property
    def is_available(self) -> bool:
        return self._is_available

    def init_collection(self):
        if not self._is_available or self.client is None:
            return
        from qdrant_client.http import models

        collections = [c.name for c in self.client.get_collections().collections]
        if self.collection_name not in collections:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={
                    "dense": models.VectorParams(size=1024, distance=models.Distance.COSINE)
                },
                sparse_vectors_config={
                    "sparse": models.SparseVectorParams()
                },
            )
            # Create payload indexes
            for field in ["release", "product_area", "topic_type", "doc_id", "kind"]:
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            logger.info("Created Qdrant collection %s with hybrid vectors", self.collection_name)

    def upsert_chunks(
        self,
        chunks: List[Chunk],
        dense_vectors: List[List[float]],
        sparse_vectors: Optional[List[Dict[str, Any]]] = None,
    ):
        if not self._is_available or self.client is None:
            return
        from qdrant_client.http import models

        points = []
        for idx, chunk in enumerate(chunks):
            vector_dict: Dict[str, Any] = {"dense": dense_vectors[idx]}
            if sparse_vectors and idx < len(sparse_vectors):
                vector_dict["sparse"] = models.SparseVector(
                    indices=sparse_vectors[idx]["indices"],
                    values=sparse_vectors[idx]["values"],
                )

            payload = chunk.model_dump()
            points.append(
                models.PointStruct(
                    id=abs(hash(chunk.chunk_id)) % (2**63 - 1),
                    vector=vector_dict,
                    payload=payload,
                )
            )

        # Batch upsert
        self.client.upsert(collection_name=self.collection_name, points=points)
        logger.info("Upserted %d points into Qdrant", len(points))
