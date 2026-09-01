from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, TextIO


def success(request_id: object, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def text_content(payload: object) -> list[dict[str, str]]:
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]


def serve_lines(server: Any, lines: Iterable[str], output: TextIO) -> None:
    for line in lines:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = server.handle(request)
        except (TypeError, ValueError, json.JSONDecodeError):
            response = error(None, -32700, "invalid JSON-RPC request")
        if response is not None:
            output.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            output.flush()
