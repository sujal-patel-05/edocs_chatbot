"""
Deduplication module for eDocs topics across and within CHM files.

Uses SHA-256 hash of normalized text to identify exact duplicates,
merging breadcrumbs and referencing CHM names into a single canonical Document.
"""

from __future__ import annotations

import hashlib
import re
from typing import Dict, List
from src.edocs.models import Document


def compute_content_hash(text: str) -> str:
    """Compute SHA-256 hash of whitespace-normalized lowercase text."""
    norm = re.sub(r"\s+", " ", text).strip().lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def deduplicate_documents(docs: List[Document]) -> List[Document]:
    """
    Deduplicate a list of Document objects by content_hash.
    When a duplicate is found, append breadcrumbs and CHM references to the canonical Document.
    """
    seen: Dict[str, Document] = {}
    result: List[Document] = []

    for doc in docs:
        if doc.content_hash in seen:
            canonical = seen[doc.content_hash]
            for bc in doc.breadcrumbs:
                if bc not in canonical.breadcrumbs:
                    canonical.breadcrumbs.append(bc)
            if doc.chm not in canonical.also_in and doc.chm != canonical.chm:
                canonical.also_in.append(doc.chm)
        else:
            seen[doc.content_hash] = doc
            result.append(doc)

    return result
