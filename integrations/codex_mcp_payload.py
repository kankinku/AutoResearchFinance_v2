from __future__ import annotations

import json


def encode_tool_payload(payload: object) -> str:
    """Encode an MCP tool payload with the repository's stable JSON text contract."""

    return json.dumps(payload, ensure_ascii=True, sort_keys=True)


def text_content_payload(payload: object) -> list[dict[str, str]]:
    """Return transport-neutral MCP text content for a JSON payload."""

    return [{"type": "text", "text": encode_tool_payload(payload)}]
