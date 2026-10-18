"""
Authentication and rate limiting module for Symitar eDocs API.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import APIKeyHeader

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# In-memory rate limiter: user_id/key -> list of timestamp floats
_rate_limit_records: Dict[str, List[float]] = {}
RATE_LIMIT_PER_MINUTE = 30


def get_current_user(
    x_api_key: Optional[str] = Security(api_key_header),
    authorization: Optional[str] = Header(None),
) -> str:
    """
    Authenticate user via X-API-Key header or Authorization: Bearer <token>.
    For development/local use, defaults to 'dev_user' if no key provided.
    """
    token = x_api_key
    if not token and authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1]

    user_id = token or "dev_user"

    # Rate limiting check (30 requests per minute)
    now = time.time()
    timestamps = _rate_limit_records.setdefault(user_id, [])
    # Keep only timestamps in the last 60 seconds
    _rate_limit_records[user_id] = [t for t in timestamps if now - t < 60.0]

    if len(_rate_limit_records[user_id]) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded (30 requests per minute).",
        )

    _rate_limit_records[user_id].append(now)
    return user_id
