"""
Reranker module using BAAI/bge-reranker-v2-m3.

Scores (query, chunk_text) pairs and filters results below min_score threshold.
"""

from __future__ import annotations

import logging
from typing import List, Tuple
from src.edocs.models import Chunk

logger = logging.getLogger("edocs.rag.rerank")


class Reranker:
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        top_n_in: int = 40,
        top_n_out: int = 6,
        min_score: float = 0.30,
    ):
        self.model_name = model_name
        self.top_n_in = top_n_in
        self.top_n_out = top_n_out
        self.min_score = min_score
        self._model = None
        self._is_loaded = False

    def load_model(self):
        if self._is_loaded:
            return
        try:
            from FlagEmbedding import FlagReranker
            logger.info("Loading reranker %s...", self.model_name)
            self._model = FlagReranker(self.model_name, use_fp16=False)
            self._is_loaded = True
        except Exception as e:
            logger.warning(
                "FlagReranker unavailable (%s). Using lexical overlap scorer for test/dev.", e
            )
            self._model = None
            self._is_loaded = False

    def rerank(
        self, query: str, candidates: List[Chunk]
    ) -> List[Tuple[Chunk, float]]:
        """
        Rerank candidates against query.
        Returns top_n_out (Chunk, score) pairs with score >= min_score.
        """
        if not candidates:
            return []

        candidates = candidates[: self.top_n_in]

        if self._model is not None:
            pairs = [[query, c.text] for c in candidates]
            scores = self._model.compute_score(pairs)
            if isinstance(scores, (int, float)):
                scores = [float(scores)]
            else:
                scores = [float(s) for s in scores]
        else:
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
            q_terms = set(content_words if content_words else [w for w in raw_words if len(w) >= 2])
            
            # Extract adjacent bigrams
            phrases = []
            if len(content_words) >= 2:
                for i in range(len(content_words) - 1):
                    phrases.append(f"{content_words[i]} {content_words[i+1]}")

            is_procedural = any(w in raw_words for w in ["how", "create", "steps", "procedure", "add", "setup"])

            scores = []
            for c in candidates:
                text_lower = c.text.lower()
                path_lower = " > ".join(c.section_path).lower()
                matches = sum(1 for t in q_terms if t in text_lower)
                title_matches = sum(1 for t in q_terms if t in path_lower)
                
                raw_score = (matches / (len(q_terms) or 1)) * 0.45 + (title_matches / (len(q_terms) or 1)) * 0.35
                
                # Phrase bonus
                for p in phrases:
                    if p in text_lower:
                        raw_score += 0.15
                    if p in path_lower:
                        raw_score += 0.25
                
                # Procedure bonus for step-by-step documentation
                if is_procedural and ("1." in c.text and "2." in c.text):
                    raw_score += 0.15

                scores.append(raw_score)

        # Pair candidates with scores and sort descending
        scored = list(zip(candidates, scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        # Filter by min_score and truncate to top_n_out
        filtered = [
            (c, s) for c, s in scored if s >= self.min_score
        ][: self.top_n_out]

        # If everything fell below min_score but we had candidates, keep the top 1 if score > 0
        if not filtered and scored and scored[0][1] > 0.05:
            filtered = [scored[0]]

        return filtered
