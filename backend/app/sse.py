"""
Server-Sent Events (SSE) formatting for streaming API responses.
"""
from __future__ import annotations

import json
from typing import Any, Dict


def format_sse_event(event: str, data: Dict[str, Any]) -> str:
    """
    Format one SSE message block.

    Args:
        event: Event name (meta, token, done, error).
        data: JSON-serializable payload.

    Returns:
        SSE-formatted string ending with a blank line.
    """
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
