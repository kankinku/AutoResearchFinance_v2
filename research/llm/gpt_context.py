"""GPT-facing research context sanitization and audit records. No local model API."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

from research.llm.director import ResearchIntent


def _sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized.startswith("kis_") or any(
        term in normalized
        for term in (
            "secret",
            "token",
            "password",
            "credential",
            "api_key",
            "authorization",
            "raw_market",
            "sealed_oos",
        )
    )


def sanitize_context(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): sanitize_context(item)
            for key, item in value.items()
            if not _sensitive_key(str(key))
        }
    if isinstance(value, (list, tuple)):
        return [sanitize_context(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def record_intent(path: Path, intent: ResearchIntent) -> None:
    payload = sanitize_context(intent.model_dump(mode="json", exclude_none=True))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                {"timestamp": datetime.now(timezone.utc).isoformat(), "intent": payload},
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )


def write_provider_status(
    path: Path,
    provider: str,
    status: str,
    last_result: str,
    *,
    operation: str | None = None,
) -> None:
    payload = {
        "provider": provider,
        "status": status,
        "last_result": last_result,
        "last_call_at": datetime.now(timezone.utc).isoformat(),
    }
    if operation is not None:
        payload["operation"] = operation
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError:
        return
