"""
Field lookup, release catalog, and user feedback routes.
"""

from __future__ import annotations

import logging
from typing import List, Literal, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from src.edocs.api.auth import get_current_user
from src.edocs.config import load_settings
from src.edocs.models import FieldRecord
from src.edocs.store.pg import PostgresStore

logger = logging.getLogger("edocs.api.routes_fields")
router = APIRouter(prefix="/api/v1", tags=["Fields & Meta"])

settings = load_settings()
store = PostgresStore(dsn=settings.postgres.dsn)


class FeedbackRequest(BaseModel):
    message_id: str
    rating: Literal["up", "down"]
    reason: Optional[Literal["wrong", "incomplete", "not_found", "irrelevant", "other"]] = None
    comment: Optional[str] = None


@router.get("/fields", response_model=List[FieldRecord])
def search_fields(
    q: str = "",
    record: Optional[str] = None,
    release: str = "2023.00",
    limit: int = 20,
    user: str = Depends(get_current_user),
):
    """Structured field lookup panel for developers."""
    return store.search_fields(query=q, record=record, release=release, limit=limit)


@router.get("/releases")
def get_releases(user: str = Depends(get_current_user)):
    """Available releases and the default release."""
    return {
        "default_release": settings.app.default_release,
        "available_releases": [settings.app.default_release],
    }


@router.post("/feedback")
def submit_feedback(fb: FeedbackRequest, user: str = Depends(get_current_user)):
    """Record user feedback (thumbs up / down)."""
    logger.info(
        "User feedback: user=%s, message_id=%s, rating=%s, reason=%s",
        user,
        fb.message_id,
        fb.rating,
        fb.reason,
    )
    return {"status": "ok", "message": "Feedback recorded."}
