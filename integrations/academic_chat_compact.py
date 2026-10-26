"""Opt-in compact, phase-aware GPT checkpoint read for the existing ChatGPT MCP.

No model calls, SDK threads, database writes, new MCP tools, or changes to
canonical evidence. The canonical full checkpoint remains the authority.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from hashlib import sha256
from typing import Any


class ChatCheckpointCompressionError(ValueError):
    """A safe complete-enough read cannot be represented within the budget."""


# Strictly optional historical commentary lists; schemas, lineage selection,
# execution constraints, latest measurements and checkpoint remain untouched.
_OPTIONAL_RECENT_LISTS = {
    "experiment_learning": {"recent_evidence": 4},
    "cross_generation_memory": {
        "frequent_intervention_families": 5,
        "repeated_failure_families": 5,
        "recent_verified_results": 5,
    },
    "economic_feedback": {"review_candidates": 5},
}
_HEAD = re.compile(r"[0-9a-f]{64}\Z")


def _serialized(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False).encode("utf-8")


def compact_academic_checkpoint(
    source: dict[str, Any],
    *,
    max_bytes: int = 96 * 1024,
) -> dict[str, Any]:
    """Present a verified server checkpoint without duplicating all history.

    Only call with the actual canonical output of get_algorithm_research or
    the just-committed response. This view cannot authenticate raw inputs on
    its own; all mutations MUST use the original canonical checkpoint token.
    """
    if type(max_bytes) is not int or not 1024 <= max_bytes <= 256 * 1024:
        raise ChatCheckpointCompressionError("invalid checkpoint budget")
    if source.get("orders_enabled") is not False:
        raise ChatCheckpointCompressionError("orders are not proven disabled")
    if source.get("independent_oos_approved") is not False:
        raise ChatCheckpointCompressionError("sealed OOS scope invalid")
    completed = source.get("completed_generations")
    requested = source.get("requested_generations")
    if type(completed) is not int or type(requested) is not int or not 0 <= completed <= requested:
        raise ChatCheckpointCompressionError("invalid generation counter")
    history = source.get("history")
    if not isinstance(history, list) or len(history) != completed:
        raise ChatCheckpointCompressionError("canonical history count mismatch")
    head = history[-1].get("evidence_hash") if history else None
    if history and (not isinstance(head, str) or _HEAD.fullmatch(head) is None):
        raise ChatCheckpointCompressionError("canonical history head missing")
    phase = source.get("checkpoint_phase")
    actions = {
        "AWAITING_PLAN": "AUTHOR_AND_SUBMIT_PLAN",
        "AWAITING_DIAGNOSIS": "AUTHOR_AND_SUBMIT_DIAGNOSIS",
        "INTERRUPTED": "INSPECT_AND_EXPLICITLY_RESUME_IF_SAFE",
        "COMPLETED": "NO_MORE_GENERATIONS",
        "CANCELLED": "NO_MORE_GENERATIONS",
    }
    if phase not in actions:
        raise ChatCheckpointCompressionError("unknown research checkpoint phase")
    if phase in ("AWAITING_PLAN", "AWAITING_DIAGNOSIS"):
        if not isinstance(source.get("checkpoint_token"), str) or not re.fullmatch(
            r"[0-9a-f]{32}", source["checkpoint_token"]
        ):
            raise ChatCheckpointCompressionError("missing authenticated checkpoint token")
        if not isinstance(source.get("model_context"), dict):
            raise ChatCheckpointCompressionError("missing mandatory model decision context")
    original_bytes = _serialized(source)
    view = deepcopy(source)
    view["history"] = history[-1:]  # last raw record, not an invented summary
    omissions: dict[str, dict[str, int]] = {}
    context = view.get("model_context")
    if isinstance(context, dict):
        for section, keys in _OPTIONAL_RECENT_LISTS.items():
            item = context.get(section)
            if not isinstance(item, dict):
                continue
            for name, limit in keys.items():
                values = item.get(name)
                if isinstance(values, list) and len(values) > limit:
                    # Ranked families retain the highest-evidence entries;
                    # chronological observations retain the most recent.
                    item[name] = (
                        values[:limit]
                        if name
                        in (
                            "frequent_intervention_families",
                            "repeated_failure_families",
                            "review_candidates",
                        )
                        else values[-limit:]
                    )
                    omissions[section + "." + name] = {
                        "source_items": len(values),
                        "returned_items": limit,
                    }
    view["last_completed_evidence_hash"] = head
    view["history_window"] = {
        "source_generations": completed,
        "returned_generations": len(view["history"]),
        "more_history_requires_full_lookup": completed > len(view["history"]),
        "head_evidence_hash": head,
    }
    view["continuation"] = {
        "expected_generation": completed + 1 if completed < requested else None,
        "required_model_action": actions[phase],
        "submit_tool": {
            "AWAITING_PLAN": "submit_algorithm_plan",
            "AWAITING_DIAGNOSIS": "submit_algorithm_diagnosis",
        }.get(phase),
        "canonical_checkpoint_token_unchanged": True,
        "read_current_checkpoint_after_uncertain_write": True,
        "automatic_model_turns_started": 0,
        "model_decision_authored_by": "CURRENT_CHATGPT_CONVERSATION_NOT_CODEX_SDK",
    }
    view["compact_source"] = {
        "schema": "quant-chat-checkpoint-optin-compact-v1",
        "full_source_sha256": sha256(original_bytes).hexdigest(),
        "full_source_bytes": len(original_bytes),
        "complete_history_available_with_full": True,
        "full_read_tool": "get_algorithm_research",
        "full_read_response_mode": "full",
        "optional_history_lists_shortened": omissions,
        "historical_omissions_are_not_negative_evidence": True,
        "typed_model_schema_retained": True,
        "verified_canonical_source_required_for_submission": True,
        "independent_oos_approved": False,
        "orders_enabled": False,
    }
    compact_bytes = len(_serialized(view))
    if compact_bytes > max_bytes:
        raise ChatCheckpointCompressionError("compact checkpoint exceeds byte budget")
    view["compact_source"]["returned_bytes"] = compact_bytes
    for _ in range(4):
        size = len(_serialized(view))
        if size == view["compact_source"]["returned_bytes"]:
            break
        view["compact_source"]["returned_bytes"] = size
    if view["compact_source"]["returned_bytes"] > max_bytes:
        raise ChatCheckpointCompressionError("compact checkpoint exceeds byte budget")
    return view
