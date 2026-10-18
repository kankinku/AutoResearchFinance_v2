"""Bound ChatGPT MCP transport context without modifying immutable research evidence.

Only read-only overview tools are summarized. Any research write, checkpoint,
strategy proof and error result is delivered unmodified. Explicit `full` reads
remain possible, and only non-sensitive sizes/hashes are recorded for diagnosis.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CONTEXT_LIMIT_BYTES = 24 * 1024
COMPACTABLE_TOOLS = frozenset(
    {"get_dashboard_status", "get_research_brief", "get_research_batch_report"}
)
_LIST_PREVIEW_LENGTHS = {
    "tests": 3,
    "trend": 8,
    "workers": 3,
    "generations": 4,
    "observations": 4,
    "failure_knowledge": 4,
    "frontier": 5,
}
_ID_FIELDS = (
    "name",
    "id",
    "feature_id",
    "indicator_id",
    "key",
    "type",
    "status",
    "available",
    "category",
    "group",
    "source",
)


def encoded_size(payload: object) -> int:
    """Use the same default JSON escaping as the actual MCP transport."""
    return len(json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8"))


def _short_tree(value: object, depth: int = 0) -> object:
    """Summarize aggregate metadata only, never infer missing experimental facts."""
    if isinstance(value, dict):
        if depth >= 3:
            return {"entry_count": len(value)}
        return {
            str(k): _short_tree(v, depth + 1)
            for k, v in value.items()
            if isinstance(v, (str, int, float, bool))
            or v is None
            or (depth < 2 and isinstance(v, dict))
        }
    if isinstance(value, list):
        return {"total_items": len(value)}
    if isinstance(value, str) and len(value) > 240:
        return {"text_chars": len(value)}
    return value


def _recent(value: object, count: int) -> object:
    if not isinstance(value, list):
        return _short_tree(value)
    return value[-count:]


def _catalog_ids(items: object) -> object:
    if not isinstance(items, list):
        return _short_tree(items)
    names: list[object] = []
    for item in items:
        if isinstance(item, dict):
            row = {
                key: item[key]
                for key in _ID_FIELDS
                if key in item and isinstance(item[key], (str, int, float, bool))
            }
            names.append(row if row else {"fields": len(item)})
        else:
            names.append(item if isinstance(item, (str, int, float, bool)) else None)
    return names


def compact_mcp_context(
    tool: str,
    original: dict[str, Any],
    *,
    response_mode: str = "summary",
    limit_bytes: int = CONTEXT_LIMIT_BYTES,
) -> dict[str, Any]:
    """Summarize expensive, read-only overview replies; never mutate inputs.

    Full detail is always available with response_mode=full. In the compact
    projection, sampled rows are actual records; no fabricated metrics are added.
    """
    if tool not in COMPACTABLE_TOOLS or response_mode == "full":
        return original
    source = json.dumps(original, ensure_ascii=True, sort_keys=True).encode("utf-8")
    if len(source) <= limit_bytes:
        return original
    view = dict(original)
    shortened: dict[str, dict[str, int]] = {}
    keys: tuple[str, ...]
    if tool == "get_dashboard_status":
        keys = ("tests", "trend", "workers")
    elif tool == "get_research_brief":
        keys = (
            "feature_catalog",
            "research_trial_inventory",
            "observations",
            "failure_knowledge",
            "frontier",
        )
    else:
        keys = ("generations", "failure_analysis")
    for key in keys:
        if key not in view:
            continue
        item = view[key]
        if isinstance(item, list):
            if key == "feature_catalog":
                view[key] = _catalog_ids(item)
            else:
                view[key] = _recent(item, _LIST_PREVIEW_LENGTHS.get(key, 4))
            if len(view[key]) < len(item):
                shortened[key] = {"total": len(item), "returned": len(view[key])}
            elif view[key] != item:
                shortened[key] = {"total": len(item), "returned": len(view[key])}
        elif isinstance(item, dict):
            view[key] = _short_tree(item)
            shortened[key] = {
                "original_bytes": encoded_size(item),
                "returned_bytes": encoded_size(view[key]),
            }
    meta: dict[str, Any] = {
        "mode": "summary",
        "original_bytes": len(source),
        "original_sha256": hashlib.sha256(source).hexdigest(),
        "stored_records_unchanged": True,
        "shortened_fields": shortened,
        "full_detail": "For full details, call the same tool with response_mode='full'.",
    }
    view["_context_budget"] = meta
    # Even unusually large individual stored events must not escape the bound.
    # Only optional history/lookup fields may be further reduced. Key research
    # policy, champion, health, progress and access-control fields remain intact.
    for key in keys:
        if encoded_size(view) <= limit_bytes:
            break
        if key not in view:
            continue
        val = view[key]
        if isinstance(val, list):
            if key == "feature_catalog":
                view[key] = val[:40]
            else:
                view[key] = []
            entry = shortened.setdefault(key, {})
            entry["returned"] = len(view[key])
            if "total" not in entry and isinstance(original[key], list):
                entry["total"] = len(original[key])
        elif isinstance(val, dict):
            view[key] = {"omitted_details": True}
            shortened[key]["returned_bytes"] = encoded_size(view[key])
    if encoded_size(view) > limit_bytes:
        # Fail visibly instead of silently truncating security, checkpoints,
        # provenance or policy. The original is never echoed accidentally.
        return {
            "status": "CONTEXT_BUDGET_EXCEEDED",
            "error_code": "OVERVIEW_REQUIRES_FILTER",
            "orders_enabled": False,
            "_context_budget": meta,
        }
    meta["returned_bytes"] = encoded_size(view)
    return view


def append_context_metrics(
    state_dir: Path,
    *,
    tool: str,
    original_bytes: int,
    returned_bytes: int,
    mode: str,
) -> None:
    """Best-effort bounded telemetry: no tokens, inputs, logs or research rows."""
    if tool not in COMPACTABLE_TOOLS:
        return
    try:
        directory = state_dir / "logs"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / "mcp-context-metrics.jsonl"
        if path.exists() and path.stat().st_size > 1024 * 1024:
            path.replace(path.with_suffix(".previous"))
        row = {
            "utc": datetime.now(timezone.utc).isoformat(),
            "tool": tool,
            "original_bytes": original_bytes,
            "returned_bytes": returned_bytes,
            "mode": mode,
        }
        with os.fdopen(
            os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600), "a", encoding="utf-8"
        ) as handle:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    except OSError:
        # Operational observability cannot break safe read-only operations.
        pass
