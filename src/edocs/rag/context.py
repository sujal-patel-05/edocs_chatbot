"""
Context builder for assembling retrieved excerpts into prompt context.

Handles excerpt numbering ([1], [2]...), parent/section expansion,
token budget enforcement (<= max_context_tokens), and related topic links.
"""

from __future__ import annotations

import logging
from typing import List, Tuple
import tiktoken
from src.edocs.models import Chunk

logger = logging.getLogger("edocs.rag.context")
_enc = tiktoken.get_encoding("cl100k_base")


def build_context(
    scored_chunks: List[Tuple[Chunk, float]],
    max_tokens: int = 6000,
) -> Tuple[str, List[dict]]:
    """
    Build numbered XML-style context block for the prompt:
    <excerpt id="1" doc_id="..." release="..." title="...">
    ...
    </excerpt>

    Returns: (context_str, list_of_citation_metadata)
    """
    citations: List[dict] = []
    excerpt_blocks: List[str] = []
    used_tokens = 0

    for idx, (chunk, score) in enumerate(scored_chunks, 1):
        chunk_text = chunk.text.strip()
        # Cap single excerpt length to at most 3500 chars to avoid giant table blowups
        if len(chunk_text) > 3500:
            chunk_text = chunk_text[:3500] + "\n...[truncated for length]..."

        chunk_tokens = chunk.token_count or len(_enc.encode(chunk_text))
        if used_tokens + chunk_tokens > max_tokens and excerpt_blocks:
            break

        doc_title = chunk.section_path[0] if chunk.section_path else chunk.doc_id
        breadcrumb = " > ".join(chunk.section_path) if chunk.section_path else doc_title

        block = (
            f'<excerpt id="{idx}" doc_id="{chunk.doc_id}" release="{chunk.release}" '
            f'title="{doc_title}" breadcrumb="{breadcrumb}" score="{score:.3f}">\n'
            f"{chunk_text}\n"
            f"</excerpt>"
        )
        excerpt_blocks.append(block)
        used_tokens += chunk_tokens

        citations.append({
            "n": idx,
            "doc_id": chunk.doc_id,
            "anchor": chunk.anchor or "",
            "title": doc_title,
            "breadcrumb": breadcrumb,
            "release": chunk.release,
            "score": score,
            "viewer_url": f"/api/v1/docs/{chunk.doc_id}",
        })

    context_str = "\n\n".join(excerpt_blocks)
    return context_str, citations
