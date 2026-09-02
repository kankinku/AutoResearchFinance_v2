from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, cast

from strategy_import.models import AnalysisResult, AnalysisStatus
from strategy_ir.schema import Condition, IndicatorSpec, Provenance, RiskConfig, RuleSet, StrategyIR
from strategy_ir.validator import StrategyValidationError, validate_strategy


def analyze_python_source(path: Path) -> AnalysisResult:
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    source = raw.decode("utf-8")
    try:
        tree = ast.parse(source, filename=str(path), mode="exec")
    except (UnicodeDecodeError, SyntaxError) as exc:
        return AnalysisResult(
            AnalysisStatus.REVIEW_REQUIRED,
            source_hash,
            "python",
            profile={"detected_constructs": ["python_module"]},
            reason=f"static Python analysis failed: {type(exc).__name__}",
        )

    literal = _find_named_literal(tree, {"STRATEGY", "STRATEGY_IR"})
    if literal is not None:
        try:
            strategy = _with_provenance(validate_strategy(literal), path, source_hash, "python")
            return AnalysisResult(AnalysisStatus.NORMALIZED, source_hash, "python", strategy)
        except StrategyValidationError as exc:
            return AnalysisResult(
                AnalysisStatus.REVIEW_REQUIRED,
                source_hash,
                "python",
                profile={"detected_constructs": ["strategy_literal"]},
                reason=f"Strategy IR validation failed: {exc}",
            )

    builder_state = _find_named_literal(tree, {"builder_state"})
    if builder_state is not None:
        try:
            strategy = _kis_builder_state_to_ir(builder_state, path, source_hash)
            return AnalysisResult(
                AnalysisStatus.NORMALIZED,
                source_hash,
                "kis_builder_state",
                strategy,
                profile={
                    "detected_constructs": ["kis_builder_state"],
                    "metadata": _metadata(builder_state),
                },
            )
        except (TypeError, ValueError, StrategyValidationError) as exc:
            return AnalysisResult(
                AnalysisStatus.REVIEW_REQUIRED,
                source_hash,
                "kis_builder_state",
                profile={"detected_constructs": ["kis_builder_state"]},
                reason=f"KIS builder_state conversion failed: {type(exc).__name__}",
            )

    constructs = ["python_module"]
    if any(isinstance(node, ast.ClassDef) for node in ast.walk(tree)):
        constructs.append("python_class")
    if any(
        isinstance(node, ast.Name) and node.id == "StrategyDefinition" for node in ast.walk(tree)
    ):
        constructs.append("strategy_definition")
    return AnalysisResult(
        AnalysisStatus.REVIEW_REQUIRED,
        source_hash,
        "python",
        profile={"detected_constructs": constructs},
        reason=(
            "Python source must expose a literal STRATEGY mapping or a static KIS builder_state; "
            "dynamic execution is not allowed"
        ),
    )


def analyze_source_file(path: Path) -> AnalysisResult:
    suffix = path.suffix.lower()
    if suffix == ".py":
        return analyze_python_source(path)
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    try:
        if suffix == ".json":
            document = json.loads(raw.decode("utf-8"))
        elif suffix in {".yaml", ".yml"}:
            import yaml  # type: ignore[import-untyped]

            document = yaml.safe_load(raw.decode("utf-8"))
        else:
            return AnalysisResult(
                AnalysisStatus.REVIEW_REQUIRED,
                source_hash,
                suffix.lstrip(".") or "unknown",
                profile={"detected_constructs": ["unknown_source"]},
                reason="source format requires a dedicated static analyzer",
            )
        strategy = _with_provenance(
            validate_strategy(document), path, source_hash, suffix.lstrip(".")
        )
        return AnalysisResult(AnalysisStatus.NORMALIZED, source_hash, suffix.lstrip("."), strategy)
    except (UnicodeDecodeError, ValueError, TypeError, StrategyValidationError) as exc:
        return AnalysisResult(
            AnalysisStatus.REVIEW_REQUIRED,
            source_hash,
            suffix.lstrip(".") or "unknown",
            profile={"detected_constructs": ["structured_source"]},
            reason=f"structured source validation failed: {type(exc).__name__}",
        )


def _find_named_literal(tree: ast.AST, names: set[str]) -> dict[str, Any] | None:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id in names for target in node.targets):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError, SyntaxError):
            return None
        return value if isinstance(value, dict) else None
    return None


def _kis_builder_state_to_ir(state: dict[str, Any], path: Path, source_hash: str) -> StrategyIR:
    metadata = state.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a mapping")
    strategy_id = str(metadata.get("id") or path.stem)
    indicators: dict[str, IndicatorSpec] = {}
    for index, item in enumerate(_list_of_mappings(state.get("indicators"))):
        alias = str(item.get("alias") or item.get("id") or f"indicator_{index + 1}")
        params = item.get("params", {})
        params = params if isinstance(params, dict) else {}
        period = params.get("period")
        numeric_period = int(period) if isinstance(period, (int, float)) and period > 0 else None
        extra = {str(k): v for k, v in params.items() if k != "period" and _scalar(v)}
        indicators[alias] = IndicatorSpec(
            type=str(item.get("indicatorId") or item.get("type") or "UNKNOWN").upper(),
            period=numeric_period,
            parameters=extra,
        )
    if not indicators:
        raise ValueError("builder_state has no indicators")
    entry = _rule_set(state.get("entry"), indicators)
    exit_rules = _rule_set(state.get("exit"), indicators)
    risk = _risk_config(state.get("risk"))
    document = {
        "schema_version": 1,
        "id": strategy_id,
        "family": str(metadata.get("category") or "imported"),
        "generation": 0,
        "indicators": {key: value.model_dump() for key, value in indicators.items()},
        "entry": entry.model_dump(),
        "exit": exit_rules.model_dump(),
        "risk": risk.model_dump(),
    }
    return _with_provenance(validate_strategy(document), path, source_hash, "kis_builder_state")


def _rule_set(raw: Any, indicators: dict[str, IndicatorSpec]) -> RuleSet:
    if not isinstance(raw, dict):
        raise TypeError("rule set must be a mapping")
    conditions: list[Condition] = []
    for item in _list_of_mappings(raw.get("conditions")):
        left = _operand(item.get("left"))
        operator = _operator(item.get("operator") or item.get("op"))
        right_raw = item.get("right")
        right = (
            _operand(right_raw)
            if isinstance(right_raw, dict) and right_raw.get("type") == "indicator"
            else None
        )
        value = (
            right_raw.get("value")
            if isinstance(right_raw, dict) and right_raw.get("type") == "value"
            else None
        )
        conditions.append(Condition(op=operator, left=left, right=right, value=value))
    logic = str(raw.get("logic") or "AND").upper()
    if logic not in {"AND", "OR"}:
        raise ValueError("unsupported rule logic")
    return RuleSet(logic=cast(Literal["AND", "OR"], logic), conditions=conditions)


def _operand(raw: Any) -> str:
    if not isinstance(raw, dict):
        raise ValueError("condition operand is not an indicator")
    if raw.get("type") == "price":
        price_field = raw.get("priceField")
        if price_field in {"open", "high", "low", "close", "volume"}:
            return str(price_field)
        raise ValueError("unsupported price field")
    if raw.get("type") != "indicator":
        raise ValueError("condition operand is not an indicator")
    alias = raw.get("indicatorAlias") or raw.get("alias")
    if not alias:
        raise ValueError("indicator alias is missing")
    return str(alias)


def _operator(value: Any) -> str:
    aliases = {
        "crosses_above": "cross_above",
        "crosses_below": "cross_below",
        ">": "greater_than",
        ">=": "greater_equal",
        "<": "less_than",
        "<=": "less_equal",
        "==": "equal",
    }
    result = aliases.get(str(value), str(value))
    if result not in {
        "cross_above",
        "cross_below",
        "less_than",
        "less_equal",
        "greater_than",
        "greater_equal",
        "equal",
    }:
        raise ValueError(f"unsupported operator {result}")
    return result


def _risk_config(raw: Any) -> RiskConfig:
    raw = raw if isinstance(raw, dict) else {}
    stop = _risk_percent(raw.get("stopLoss"))
    take = _risk_percent(raw.get("takeProfit"))
    trailing = _risk_percent(raw.get("trailingStop"))
    return RiskConfig(stop_loss_pct=stop, take_profit_pct=take, trailing_stop_pct=trailing)


def _risk_percent(raw: Any) -> float:
    if not isinstance(raw, dict) or not raw.get("enabled", False):
        return 0.0
    value = raw.get("percent", 0)
    return float(value) if isinstance(value, (int, float)) and value >= 0 else 0.0


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _metadata(state: dict[str, Any]) -> dict[str, Any]:
    metadata = state.get("metadata", {})
    return (
        {str(key): value for key, value in metadata.items() if _scalar(value)}
        if isinstance(metadata, dict)
        else {}
    )


def _scalar(value: Any) -> bool:
    return value is None or isinstance(value, (bool, int, float, str))


def _with_provenance(
    strategy: StrategyIR, path: Path, source_hash: str, source_type: str
) -> StrategyIR:
    return strategy.model_copy(
        update={
            "provenance": Provenance(
                source_path=path.as_posix(), source_hash=source_hash, source_type=source_type
            )
        }
    )
