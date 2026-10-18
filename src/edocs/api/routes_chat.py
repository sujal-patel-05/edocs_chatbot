"""
Chat API route with SSE streaming.
"""

from __future__ import annotations

import time
import uuid
from typing import Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.edocs.api.auth import get_current_user
from src.edocs.api.sse import format_sse
from src.edocs.rag.orchestrator import Orchestrator

router = APIRouter(prefix="/api/v1", tags=["Chat"])
orchestrator = Orchestrator()


class ChatRequest(BaseModel):
    conversation_id: Optional[str] = None
    message: str
    release: Optional[str] = "2023.00"
    product_area: Optional[str] = None
    user_role: Optional[str] = "general"


@router.post("/chat")
def chat_stream(req: ChatRequest, user: str = Depends(get_current_user)):
    """
    Stream question answer as Server-Sent Events (SSE).
    """
    t_start = time.time()
    conv_id = req.conversation_id or str(uuid.uuid4())
    msg_id = str(uuid.uuid4())

    def event_generator():
        try:
            # 1. Process query with orchestrator
            result = orchestrator.process_query(
                message=req.message,
                release=req.release,
                user_role=req.user_role or "general",
            )

            # 2. Emit 'meta' event
            yield format_sse(
                "meta",
                {
                    "conversation_id": conv_id,
                    "message_id": msg_id,
                    "intent": result["intent"],
                    "release": req.release or "2023.00",
                },
            )

            # 3. Stream 'token' events with exact whitespace preservation
            import re
            tokens = re.findall(r"\S+|\n+| +", result["answer"])
            for t in tokens:
                yield format_sse("token", {"text": t})
                if t.strip():
                    time.sleep(0.008)

            # 4. Emit 'answer_final' event
            yield format_sse(
                "answer_final",
                {
                    "text": result["answer"],
                    "verification": result["verification"],
                },
            )

            # 5. Emit 'citations' event
            yield format_sse("citations", result["citations"])

            # 6. Emit 'done' event
            latency_ms = int((time.time() - t_start) * 1000)
            yield format_sse("done", {"latency_ms": latency_ms})

        except Exception as e:
            yield format_sse("error", {"code": "INTERNAL_ERROR", "message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
