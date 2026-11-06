"""
RecallOps Server-Sent Events (SSE) Protocol Helpers.
Enforces deterministic newline-delimited SSE event framing for frontend streaming.
"""

import json
from typing import Any, Dict


class SSEEventTypes:
    """Standard event type constants for triage streaming."""
    THOUGHT = "thought"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    RECALLED_MEMORY = "recalled_memory"
    WARNING = "warning"
    SUGGESTION = "suggestion"
    DONE = "done"
    ERROR = "error"
    PING = "ping"


def format_sse(event: str, data: Any) -> str:
    """
    Formats a message as a compliant Server-Sent Event frame.
    Produces:
        event: <event_name>
        data: <json_string>
        \n
    """
    if isinstance(data, (dict, list)):
        payload = json.dumps(data)
    elif isinstance(data, str):
        payload = data
    else:
        payload = json.dumps(data, default=str)

    return f"event: {event}\ndata: {payload}\n\n"
