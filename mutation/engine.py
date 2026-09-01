from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from strategy_ir.schema import StrategyIR
from strategy_ir.validator import validate_strategy


class MutationError(ValueError):
    """Raised when a mutation cannot be applied to a Strategy IR."""


@dataclass(frozen=True)
class MutationOperation:
    op: str
    path: str | None = None
    value: Any = None
    other: StrategyIR | None = None


_RISK_PATHS = {
    "CHANGE_STOP": "risk.stop_loss_pct",
    "CHANGE_TAKE_PROFIT": "risk.take_profit_pct",
    "CHANGE_TRAILING_STOP": "risk.trailing_stop_pct",
    "CHANGE_POSITION_SIZE": "risk.position_size_pct",
}


def apply_operations(
    parent: StrategyIR,
    operations: list[MutationOperation],
    *,
    validate: bool = True,
) -> StrategyIR:
    data = parent.model_dump(mode="python", by_alias=False)
    for operation in operations:
        _apply_one(data, operation)
    try:
        child = StrategyIR.model_validate(data)
    except Exception as exc:
        raise MutationError(f"mutated IR is invalid: {exc}") from exc
    return validate_strategy(child) if validate else child


def _apply_one(data: dict[str, Any], operation: MutationOperation) -> None:
    op = operation.op
    if op == "SET_PARAMETER":
        _set_path(data, _required_path(operation), operation.value)
    elif op == "ADD_RULE":
        _append_path(data, _required_path(operation), operation.value)
    elif op == "REMOVE_RULE":
        _delete_path(data, _required_path(operation))
    elif op == "REPLACE_RULE":
        _set_path(data, _required_path(operation), operation.value)
    elif op in {"ENABLE_RULE", "DISABLE_RULE"}:
        _set_path(data, _required_path(operation) + ".enabled", op == "ENABLE_RULE")
    elif op == "CHANGE_AND_OR":
        if operation.value not in {"AND", "OR"}:
            raise MutationError("CHANGE_AND_OR value must be AND or OR")
        _set_path(data, _required_path(operation), operation.value)
    elif op == "ADD_INDICATOR":
        _set_path(data, _required_path(operation), operation.value, allow_new=True)
    elif op in {"REMOVE_INDICATOR", "REMOVE_REGIME_FILTER"}:
        _delete_path(data, _required_path(operation))
    elif op == "SWAP_INDICATOR":
        _set_path(data, _required_path(operation), operation.value)
    elif op in {"CHANGE_ENTRY", "CHANGE_EXIT"}:
        _set_path(data, _required_path(operation), operation.value)
    elif op in _RISK_PATHS:
        _set_path(data, _RISK_PATHS[op], operation.value)
    elif op == "ADD_REGIME_FILTER":
        _append_path(data, operation.path or "regime_filters", operation.value)
    elif op in {"CROSSOVER", "COMBINE_STRATEGY"}:
        _combine_strategy(data, operation)
    else:
        raise MutationError(f"unsupported operation: {op}")


def _combine_strategy(data: dict[str, Any], operation: MutationOperation) -> None:
    if operation.other is None:
        raise MutationError(f"{operation.op} requires other strategy")
    other = operation.other.model_dump(mode="python", by_alias=False)
    if operation.op == "CROSSOVER":
        data["exit"] = other["exit"]
    else:
        for name, spec in other["indicators"].items():
            if name in data["indicators"] and data["indicators"][name] != spec:
                raise MutationError(f"indicator collision: {name}")
            data["indicators"][name] = spec
        data["entry"]["conditions"].extend(other["entry"]["conditions"])
        data["exit"]["conditions"].extend(other["exit"]["conditions"])
    data["parents"] = list(dict.fromkeys([*data["parents"], other["strategy_id"]]))


def _required_path(operation: MutationOperation) -> str:
    if not operation.path:
        raise MutationError(f"{operation.op} requires path")
    return operation.path


def _parts(path: str) -> list[str]:
    parts = path.split(".")
    if not parts or any(not part for part in parts):
        raise MutationError(f"invalid path: {path}")
    return parts


def _container(data: Any, parts: list[str]) -> tuple[Any, str]:
    current = data
    for part in parts[:-1]:
        try:
            current = current[int(part)] if isinstance(current, list) else current[part]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise MutationError(f"path not found: {'.'.join(parts)}") from exc
    return current, parts[-1]


def _set_path(
    data: dict[str, Any], path: str, value: Any, *, allow_new: bool = False
) -> None:
    container, key = _container(data, _parts(path))
    try:
        if isinstance(container, list):
            container[int(key)] = value
        else:
            if key not in container and not allow_new:
                raise MutationError(f"path not found: {path}")
            container[key] = value
    except (IndexError, TypeError, ValueError) as exc:
        raise MutationError(f"path not found: {path}") from exc


def _append_path(data: dict[str, Any], path: str, value: Any) -> None:
    container, key = _container(data, _parts(path))
    try:
        target = container[int(key)] if isinstance(container, list) else container[key]
        if not isinstance(target, list):
            raise MutationError(f"path is not a list: {path}")
        target.append(value)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MutationError(f"path is not a list: {path}") from exc


def _delete_path(data: dict[str, Any], path: str) -> None:
    container, key = _container(data, _parts(path))
    try:
        if isinstance(container, list):
            del container[int(key)]
        else:
            del container[key]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise MutationError(f"path not found: {path}") from exc
