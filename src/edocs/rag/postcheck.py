"""
Post-generation verification and grounding check module.

Validates citations [n], verifies identifiers verbatim against retrieved context,
and enforces PII safety.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Tuple
from src.edocs.rag.pii import redact_pii

logger = logging.getLogger("edocs.rag.postcheck")

_CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def verify_and_clean_response(
    answer: str,
    context_text: str,
    num_excerpts: int,
) -> Tuple[str, Dict[str, object]]:
    """
    Perform post-generation verification:
    1. Validate citation numbers [n] (must be 1 <= n <= num_excerpts).
    2. Check that key uppercase identifiers appear in context.
    3. Redact any accidental PII in output.
    """
    removed_items: List[str] = []
    citations_ok = True
    identifiers_ok = True

    # 1. Validate citations
    def _check_citation(match: re.Match) -> str:
        nonlocal citations_ok
        n = int(match.group(1))
        if 1 <= n <= num_excerpts:
            return match.group(0)
        citations_ok = False
        removed_items.append(f"Invalid citation [{n}] (only {num_excerpts} excerpts)")
        return ""

    cleaned_answer = _CITATION_PATTERN.sub(_check_citation, answer)

    # 2. Identifier verification: find uppercase tokens that look like mnemonics
    context_upper = context_text.upper()
    tokens = set(re.findall(r"\b[A-Z0-9_]{3,20}\b", cleaned_answer))
    common_words = {
        "THE", "AND", "FOR", "THIS", "THAT", "WITH", "FROM", "WHEN", "NOTE",
        "STEP", "TYPE", "DATA", "CODE", "USER", "FILE", "VIEW", "ONLY",
        "EACH", "HAVE", "BEEN", "WILL", "MUST", "NAME", "HELP", "DATE",
        "TRUE", "FALSE", "NONE", "NULL", "WHAT", "SHOW", "FIND", "ITEM"
    }

    for tok in tokens:
        if tok not in common_words and not tok.isdigit():
            if tok not in context_upper:
                identifiers_ok = False
                removed_items.append(f"Unverified identifier: {tok}")

    # 3. Output PII check
    safe_text, has_pii = redact_pii(cleaned_answer)
    if has_pii:
        removed_items.append("PII removed from generated response")

    # Normalize line breaks and multiple consecutive horizontal spaces without destroying newlines
    safe_text = safe_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in safe_text.split("\n")]
    safe_text = "\n".join(lines).strip()
    safe_text = re.sub(r"\n{3,}", "\n\n", safe_text)

    verification_meta = {
        "citations_ok": citations_ok,
        "identifiers_ok": identifiers_ok,
        "removed": removed_items,
    }

    return safe_text, verification_meta
