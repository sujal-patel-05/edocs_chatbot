"""
Hybrid retrieval module combining exact lookup, dense/sparse search, and RRF fusion.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Dict, List, Optional, Tuple
from src.edocs.models import Chunk, FieldRecord
from src.edocs.rag.rerank import Reranker
from src.edocs.rag.router import RouterDecision
from src.edocs.store.pg import PostgresStore
from src.edocs.store.qdrant import QdrantVectorStore

logger = logging.getLogger("edocs.rag.retrieve")


def rrf_fuse(
    rank_lists: List[List[str]], k: int = 60
) -> List[Tuple[str, float]]:
    """
    Reciprocal Rank Fusion over multiple ranked lists of chunk_ids.
    RRF_score(d) = sum_{l in rank_lists} 1 / (k + rank_l(d))
    """
    scores: Dict[str, float] = {}
    for r_list in rank_lists:
        for rank, chunk_id in enumerate(r_list, 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + (1.0 / (k + rank))

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_scores


class Retriever:
    def __init__(
        self,
        store: PostgresStore,
        reranker: Optional[Reranker] = None,
        qdrant: Optional[QdrantVectorStore] = None,
    ):
        self.store = store
        self.reranker = reranker or Reranker()
        self.qdrant = qdrant or QdrantVectorStore()

    def _fetch_chunks_by_ids(self, chunk_ids: List[str]) -> Dict[str, Chunk]:
        if not chunk_ids:
            return {}
        results: Dict[str, Chunk] = {}
        if self.store.use_sqlite:
            with sqlite3.connect(self.store.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                placeholders = ",".join("?" for _ in chunk_ids)
                cur.execute(
                    f"SELECT chunk_id, doc_id, release, text, section_path, anchor, topic_type, product_area, kind, token_count, content_hash FROM chunks WHERE chunk_id IN ({placeholders})",
                    chunk_ids,
                )
                for r in cur.fetchall():
                    c = Chunk(
                        chunk_id=r[0],
                        doc_id=r[1],
                        release=r[2],
                        text=r[3],
                        section_path=json.loads(r[4]),
                        anchor=r[5],
                        topic_type=r[6],
                        product_area=r[7],
                        kind=r[8],
                        token_count=r[9],
                        content_hash=r[10],
                    )
                    results[c.chunk_id] = c
        return results

    def _lexical_search_chunks(
        self, query: str, release: str = "2023.00", limit: int = 50
    ) -> List[str]:
        """Perform fast lexical keyword search in the store with weighted scoring."""
        import re

        stopwords = {
            "a", "an", "the", "and", "or", "but", "if", "then", "else", "when",
            "at", "by", "for", "with", "about", "against", "between", "into", "through",
            "during", "before", "after", "above", "below", "to", "from", "up", "down",
            "in", "out", "on", "off", "over", "under", "again", "further", "once",
            "here", "there", "where", "why", "how", "all", "any", "both", "each", "few",
            "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own",
            "same", "so", "than", "too", "very", "can", "will", "just", "should",
            "now", "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
            "your", "yours", "yourself", "yourselves", "he", "him", "his", "himself",
            "she", "her", "hers", "herself", "it", "its", "itself", "they", "them",
            "their", "theirs", "themselves", "what", "which", "who", "whom", "this",
            "that", "these", "those", "am", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "having", "do", "does", "did", "doing",
            "would", "could", "tell", "show", "give", "please", "help"
        }

        raw_words = re.findall(r'[a-zA-Z0-9_]+', query.lower())
        content_words = [w for w in raw_words if w not in stopwords and len(w) >= 2]
        terms = content_words if content_words else [w for w in raw_words if len(w) >= 2]
        terms = terms[:8]

        if not terms:
            return []

        # Build adjacent phrases
        phrases = []
        if len(terms) >= 2:
            for i in range(len(terms) - 1):
                phrases.append(f"{terms[i]} {terms[i+1]}")

        chunk_ids: List[str] = []
        if self.store.use_sqlite:
            with sqlite3.connect(self.store.sqlite_fallback_path) as conn:
                cur = conn.cursor()
                score_parts = []
                score_params = []
                where_parts = []
                where_params = []

                for t in terms:
                    # Match exact section/topic title (e.g. ["Payroll"])
                    score_parts.append("(CASE WHEN lower(section_path) LIKE ? THEN 15 WHEN lower(section_path) LIKE ? THEN 6 ELSE 0 END)")
                    score_params.extend([f'%"{t}"%', f'%{t}%'])
                    # Match filename/module in doc_id
                    score_parts.append("(CASE WHEN lower(doc_id) LIKE ? THEN 8 ELSE 0 END)")
                    score_params.append(f"%{t}%")
                    # Match text body
                    score_parts.append("(CASE WHEN lower(text) LIKE ? THEN 3 ELSE 0 END)")
                    score_params.append(f"%{t}%")

                    where_parts.append("lower(text) LIKE ? OR lower(section_path) LIKE ? OR lower(doc_id) LIKE ?")
                    where_params.extend([f"%{t}%", f"%{t}%", f"%{t}%"])

                for p in phrases:
                    score_parts.append("(CASE WHEN lower(section_path) LIKE ? THEN 20 ELSE 0 END)")
                    score_params.append(f'%"{p}"%')
                    score_parts.append("(CASE WHEN lower(text) LIKE ? THEN 6 ELSE 0 END)")
                    score_params.append(f"%{p}%")

                score_parts.append("(CASE WHEN kind = 'record_overview' THEN 5 WHEN kind = 'topic' THEN 4 ELSE 1 END)")

                score_sql = " + ".join(score_parts)
                where_sql = " OR ".join(where_parts)
                sql = f"""
                SELECT chunk_id, ({score_sql}) AS score
                FROM chunks
                WHERE ({where_sql}) AND release = ?
                ORDER BY score DESC, token_count ASC
                LIMIT ?
                """
                all_params = score_params + where_params + [release, limit]
                cur.execute(sql, all_params)
                chunk_ids = [r[0] for r in cur.fetchall()]
        return chunk_ids

    def retrieve(
        self,
        query: str,
        decision: RouterDecision,
        release: str = "2023.00",
        top_k: int = 6,
    ) -> List[Tuple[Chunk, float]]:
        """
        Execute full retrieval pipeline:
        1. Exact lookup for entities
        2. Lexical & vector search
        3. RRF fusion
        4. Cross-encoder rerank
        """
        exact_chunks: List[Chunk] = []

        # 1. Exact lookup
        # If entities contain records (e.g. LOAN, ACCOUNT), retrieve record topic chunk and core field cards
        import re
        for rec in decision.entities.records:
            fields = self.store.search_fields(query=rec, record=rec, release=release, limit=8)
            for f in fields:
                fld_key = f.poweron_mnemonic or f.field_number or re.sub(r'[^a-zA-Z0-9_]', '', f.field_name) or "0"
                field_chunk_id = f"{f.doc_id}#field_{fld_key}"
                overview_chunk_id = f"{f.doc_id}#record_overview"
                topic_chunk_id = f"{f.doc_id}#0"
                found = self._fetch_chunks_by_ids([overview_chunk_id, topic_chunk_id, field_chunk_id])
                for c in found.values():
                    if c not in exact_chunks:
                        exact_chunks.append(c)

        # If entities contain mnemonics or field names, find field cards
        for mnem in decision.entities.mnemonics + decision.entities.fields:
            fields = self.store.search_fields(query=mnem, release=release, limit=3)
            for f in fields:
                # Find the field card chunk or topic chunk
                fld_key = f.poweron_mnemonic or f.field_number or re.sub(r'[^a-zA-Z0-9_]', '', f.field_name) or "0"
                field_chunk_id = f"{f.doc_id}#field_{fld_key}"
                topic_chunk_id = f"{f.doc_id}#0"
                found = self._fetch_chunks_by_ids([field_chunk_id, topic_chunk_id])
                for c in found.values():
                    if c not in exact_chunks:
                        exact_chunks.append(c)

        # 2. Candidate generation
        lexical_ids = self._lexical_search_chunks(query, release=release, limit=40)

        # RRF ranking (with single or multiple candidate lists)
        fused = rrf_fuse([lexical_ids], k=60)
        candidate_ids = [cid for cid, _ in fused[:40]]

        candidate_map = self._fetch_chunks_by_ids(candidate_ids)
        candidate_chunks = [
            candidate_map[cid] for cid in candidate_ids if cid in candidate_map
        ]

        # Merge exact chunks at the top
        all_candidates = []
        seen_ids = set()
        for c in exact_chunks:
            if c.chunk_id not in seen_ids:
                all_candidates.append(c)
                seen_ids.add(c.chunk_id)

        for c in candidate_chunks:
            if c.chunk_id not in seen_ids:
                all_candidates.append(c)
                seen_ids.add(c.chunk_id)

        # 3. Rerank candidates
        reranked = self.reranker.rerank(query, all_candidates)

        return reranked[:top_k]
