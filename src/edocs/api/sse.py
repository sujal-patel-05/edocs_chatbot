"""
Server-Sent Events (SSE) formatter for streaming chat completions.
"""

from __future__ import annotations

import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    """Format event and payload as an SSE packet."""
    json_str = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {json_str}\n\n"
