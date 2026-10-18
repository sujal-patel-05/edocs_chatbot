"""
PII detection and redaction module for Symitar eDocs assistant.

Detects and redacts member account numbers, SSNs, credit card numbers,
phone numbers, and email addresses from queries, responses, and logs.
"""

from __future__ import annotations

import logging
import re
from typing import Tuple

logger = logging.getLogger("edocs.rag.pii")

# SSN: 3-2-4 or 9 consecutive digits
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

# Account / Member numbers: 6 to 12 digits preceded by account/mbr keywords
_ACCOUNT_PATTERN = re.compile(
    r"\b(?:acct|account|mbr|member)(?:\s*(?:#|no|num|number)?\s*[:=]?\s*)(\d{6,12})\b",
    re.IGNORECASE,
)

# Email pattern
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# Phone pattern
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b")

# 16-digit card pattern
_CARD_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")


def _luhn_check(card_str: str) -> bool:
    """Validate credit card number using Luhn algorithm."""
    digits = [int(d) for d in re.sub(r"\D", "", card_str)]
    if len(digits) not in (15, 16):
        return False
    checksum = 0
    reverse_digits = digits[::-1]
    for i, d in enumerate(reverse_digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def redact_pii(text: str) -> Tuple[str, bool]:
    """
    Scan and replace any detected personal/member PII with safe placeholders.
    Returns: (redacted_text, has_pii)
    """
    has_pii = False
    result = text

    # Redact SSN
    if _SSN_PATTERN.search(result):
        has_pii = True
        result = _SSN_PATTERN.sub("[REDACTED_SSN]", result)

    # Redact Cards (with Luhn check)
    for m in _CARD_PATTERN.finditer(result):
        matched_str = m.group(0)
        if _luhn_check(matched_str):
            has_pii = True
            result = result.replace(matched_str, "[REDACTED_CARD]")

    # Redact Account Numbers
    if _ACCOUNT_PATTERN.search(result):
        has_pii = True
        result = _ACCOUNT_PATTERN.sub("[REDACTED_ACCOUNT]", result)

    # Redact Email
    if _EMAIL_PATTERN.search(result):
        has_pii = True
        result = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", result)

    # Redact Phone
    if _PHONE_PATTERN.search(result):
        has_pii = True
        result = _PHONE_PATTERN.sub("[REDACTED_PHONE]", result)

    if has_pii:
        logger.info("PII detected and redacted from text")

    return result, has_pii
