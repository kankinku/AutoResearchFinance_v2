"""Canonical vocabulary shared by LLM prompts and intent validation."""

from __future__ import annotations

import re

from strategy_ir.contracts import CANONICAL_CONDITION_OPERATORS, CANONICAL_TIMEFRAMES

__all__ = [
    "CANONICAL_CONDITION_OPERATORS",
    "CANONICAL_TIMEFRAMES",
    "canonical_intent_instruction",
    "require_canonical_dot_path",
]

_CANONICAL_PATH_PART = r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+"
_CANONICAL_PATH_RE = re.compile(
    rf"^(?:{_CANONICAL_PATH_PART})(?:\.(?:{_CANONICAL_PATH_PART}))*$"
)


def require_canonical_dot_path(path: str) -> str:
    """Validate the only path notation allowed after the compatibility ingress."""

    if not isinstance(path, str) or not path or not _CANONICAL_PATH_RE.fullmatch(path):
        raise ValueError(
            f"canonical path must use dotted names and integer indexes: {path!r}"
        )
    return path


def canonical_intent_instruction(*, repair: bool = False) -> str:
    """Return the single authoritative instruction for ResearchIntent output."""

    operators = ", ".join(CANONICAL_CONDITION_OPERATORS[:-1])
    operators += f", or {CANONICAL_CONDITION_OPERATORS[-1]}"
    prefix = (
        "Act as an independent intent repair agent. "
        if repair
        else ""
    )
    feature_scope = "Use only registered feature selections. " if repair else ""
    return (
        f"{prefix}Return exactly one ResearchIntent JSON object using only the canonical "
        "typed operation fields defined by the output schema. Never emit JSON Patch "
        "add/replace/remove operations; Never use JSON Patch add/replace/remove operations. "
        "ADD_RULE and ADD_REGIME_FILTER must use a "
        "condition object, SET_PARAMETER must use a scalar value, and ADD_FEATURE must "
        "use a typed feature object. "
        f"Use only the verified condition operators {operators}. Use Strategy IR-root "
        "dotted paths such as entry.conditions.<index> and indicators.<alias>; indicator "
        "changes must carry an indicator object at indicators.<alias>. Feature changes "
        "must use features.<alias>. "
        f"{feature_scope}Never use bracket or slash paths in output. Do not edit files, "
        "write Python, change evaluators, access credentials, or place orders."
    )
