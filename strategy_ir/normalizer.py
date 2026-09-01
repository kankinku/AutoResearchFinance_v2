from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

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
            document = _python_literal(raw.decode("utf-8"))
            if document is not None:
                strategy = _with_provenance(
                    validate_strategy(document), path, source_hash, "python"
                )
                return ImportResult(ImportStatus.NORMALIZED, source_hash, "python", strategy)
            regex_strategy = _regex_cross_strategy(raw.decode("utf-8"), path, source_hash, "python")
            if regex_strategy is not None:
                return ImportResult(ImportStatus.NORMALIZED, source_hash, "python", regex_strategy)
            return _unsupported(
                source_hash, "python", "Python source must expose a literal STRATEGY mapping"
            )
        if suffix in {".pine", ".pinescript"}:
            regex_strategy = _regex_cross_strategy(
                raw.decode("utf-8"), path, source_hash, "pinescript"
            )
            if regex_strategy is not None:
                return ImportResult(
                    ImportStatus.NORMALIZED, source_hash, "pinescript", regex_strategy
                )
            return _unsupported(
                source_hash, "pinescript", "cross-over mapping was not recognized"
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


def _regex_cross_strategy(
    source: str, path: Path, source_hash: str, source_type: str
) -> StrategyIR | None:
    periods = [
        int(value)
        for value in re.findall(r"(?:SMA|EMA|ta\.sma|ta\.ema)[^\d]{0,20}(\d+)", source)
    ]
    has_cross = "crossover" in source.lower() or "cross_above" in source.lower()
    has_exit = "crossunder" in source.lower() or "cross_below" in source.lower()
    if len(periods) < 2 or not has_cross or not has_exit:
        return None
    document: dict[str, Any] = {
        "schema_version": 1,
        "id": path.stem,
        "family": "imported",
        "generation": 0,
        "indicators": {
            "fast": {"type": "SMA", "period": periods[0]},
            "slow": {"type": "SMA", "period": periods[1]},
        },
        "entry": {
            "logic": "AND",
            "conditions": [{"op": "cross_above", "left": "fast", "right": "slow"}],
        },
        "exit": {
            "logic": "OR",
            "conditions": [{"op": "cross_below", "left": "fast", "right": "slow"}],
        },
        "risk": {"stop_loss_pct": 2.0, "take_profit_pct": 5.0},
    }
    strategy = _with_provenance(validate_strategy(document), path, source_hash, source_type)
    return strategy


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
