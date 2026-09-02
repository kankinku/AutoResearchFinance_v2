from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from strategy_import.analyzers import analyze_python_source
from strategy_ir.schema import Provenance, StrategyIR
from strategy_ir.validator import StrategyValidationError, validate_strategy


class ImportStatus(str, Enum):
    NORMALIZED = "NORMALIZED"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class ImportResult:
    status: ImportStatus
    source_hash: str
    source_type: str
    strategy: StrategyIR | None = None
    reason: str = ""


def normalize_source(path: Path) -> ImportResult:
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    suffix = path.suffix.lower()
    try:
        if suffix in {".yaml", ".yml", ".json"}:
            document = json.loads(raw.decode("utf-8")) if suffix == ".json" else _yaml(raw)
            strategy = _with_provenance(validate_strategy(document), path, source_hash, suffix[1:])
            return ImportResult(ImportStatus.NORMALIZED, source_hash, suffix[1:], strategy)
        if suffix == ".py":
            analysis = analyze_python_source(path)
            if analysis.strategy is not None:
                return ImportResult(
                    ImportStatus.NORMALIZED,
                    source_hash,
                    analysis.source_type,
                    analysis.strategy,
                    analysis.reason,
                )
            return _unsupported(source_hash, "python", analysis.reason)
        if suffix in {".pine", ".pinescript"}:
            return _unsupported(
                source_hash,
                "pinescript",
                "Pine source requires an explicit static mapping; text patterns are not executed",
            )
        return _unsupported(
            source_hash, suffix.lstrip(".") or "unknown", "source type is unsupported"
        )
    except (UnicodeDecodeError, ValueError, SyntaxError, StrategyValidationError) as exc:
        return _unsupported(source_hash, suffix.lstrip(".") or "unknown", str(exc))


def _yaml(raw: bytes) -> dict[str, Any]:
    import yaml  # type: ignore[import-untyped]

    document: Any = yaml.safe_load(raw.decode("utf-8"))
    if not isinstance(document, dict):
        raise ValueError("YAML root must be a mapping")
    return document


def _python_literal(source: str) -> dict[str, Any] | None:
    tree = ast.parse(source, mode="exec")
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in {"STRATEGY", "STRATEGY_IR"}
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return value if isinstance(value, dict) else None
    return None


def _with_provenance(
    strategy: StrategyIR, path: Path, source_hash: str, source_type: str
) -> StrategyIR:
    return strategy.model_copy(
        update={
            "provenance": Provenance(
                source_path=path.as_posix(),
                source_hash=source_hash,
                source_type=source_type,
            )
        }
    )


def _unsupported(source_hash: str, source_type: str, reason: str) -> ImportResult:
    return ImportResult(ImportStatus.UNSUPPORTED, source_hash, source_type, reason=reason)
