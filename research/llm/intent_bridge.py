from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping

from core.features.contracts import FeatureSpec
from mutation.engine import MutationOperation, apply_operations
from research.llm.director import FeatureSelection, IntentOperation, ResearchIntent
from strategy_ir.schema import FeatureRef, StrategyIR


class IntentEligibilityError(ValueError):
    """Raised when an LLM intent cannot enter the local experiment queue."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INTENT_INVALID",
        diagnostic: Mapping[str, object] | None = None,
    ) -> None:
        self.code = code
        self.diagnostic: dict[str, object] = {
            "code": code,
            "phase": "PREFLIGHT",
            **dict(diagnostic or {}),
        }
        super().__init__(f"{code}: {message}")


_ALLOWED_SERIES_PREFIXES = frozenset(
    {
        "VIX.",
        "GOLD.",
        "DXY.",
        "QQQ.",
        "NASDAQ.",
        "US2Y.",
        "US10Y.",
        "US20Y.",
        "JP2Y.",
        "JP10Y.",
        "JP20Y.",
        "KR2Y.",
        "KR10Y.",
        "KR20Y.",
    }
)
_ALLOWED_SERIES_FIELDS = frozenset({"open", "high", "low", "close", "volume"})
_PRIMARY_BAR_FIELDS = _ALLOWED_SERIES_FIELDS


def intent_to_operations(
    intent: ResearchIntent,
    feature_specs: Iterable[FeatureSpec] | Mapping[str, FeatureSpec],
) -> tuple[MutationOperation, ...]:
    """Convert a validated intent into typed, registry-backed IR mutations.

    A FeatureProposal remains in quarantine until separately verified and registered;
    it never becomes an experiment input merely because the LLM returned it.
    """

    if intent.feature_proposal is not None:
        raise IntentEligibilityError(
            "feature proposal requires verification before experiment eligibility",
            code="INTENT_FEATURE_PROPOSAL_UNVERIFIED",
        )
    specs = _index_specs(feature_specs)
    operations = tuple(
        operation
        for item in intent.operations
        for operation in (_operation_from_payload(item, specs),)
        if operation is not None
    )
    selected = tuple(
        _selection_operation(selection, specs)
        for selection in intent.feature_selections
    )
    return _order_operations(operations + selected)


def apply_intent(
    parent: StrategyIR,
    intent: ResearchIntent,
    feature_specs: Iterable[FeatureSpec] | Mapping[str, FeatureSpec],
) -> StrategyIR:
    """Apply an eligible intent and preserve generation/lineage in the IR."""

    if parent.strategy_id not in intent.parent_ids:
        raise IntentEligibilityError(
            f"intent parent does not match strategy: {parent.strategy_id}"
        )
    operations = intent_to_operations(intent, feature_specs)
    try:
        child = apply_operations(parent, list(operations))
    except ValueError as exc:
        raise IntentEligibilityError(str(exc), code="INTENT_MUTATION_INVALID") from exc
    mutation_names = [
        f"{operation.op}:{operation.path or ''}".rstrip(":")
        for operation in operations
    ]
    data = child.model_dump(mode="python", by_alias=False)
    data["generation"] = parent.generation + 1
    data["parents"] = list(dict.fromkeys([*parent.parents, parent.strategy_id]))
    data["research"]["mutation"] = [*parent.research.mutation, *mutation_names]
    return StrategyIR.model_validate(data)


def _index_specs(
    feature_specs: Iterable[FeatureSpec] | Mapping[str, FeatureSpec],
) -> dict[str, FeatureSpec]:
    values = feature_specs.values() if isinstance(feature_specs, Mapping) else feature_specs
    indexed: dict[str, FeatureSpec] = {}
    for spec in values:
        if spec.status != "REGISTERED":
            continue
        indexed[spec.name] = spec
        if spec.canonical_id:
            indexed[spec.canonical_id] = spec
        indexed.update({alias: spec for alias in spec.aliases})
    return indexed


def _selection_operation(
    selection: FeatureSelection, specs: Mapping[str, FeatureSpec]
) -> MutationOperation:
    spec = specs.get(selection.feature_id)
    if spec is None:
        raise IntentEligibilityError(
            f"feature is not registered: {selection.feature_id}",
            code="INTENT_UNREGISTERED_FEATURE",
        )
    inputs = selection.inputs or spec.inputs
    _validate_inputs(inputs)
    if selection.parameters:
        parameters = dict(spec.parameters)
        parameters.update(selection.parameters)
    else:
        parameters = dict(spec.parameters)
    reference = FeatureRef(
        feature_id=spec.name,
        timeframe=selection.timeframe,
        lag_bars=selection.lag_bars,
        lookback=selection.lookback,
        inputs=tuple(inputs),
        parameters=parameters,
    )
    return MutationOperation("ADD_FEATURE", f"features.{selection.alias}", reference)


def _validate_inputs(inputs: tuple[str, ...]) -> None:
    if not inputs:
        raise IntentEligibilityError("feature inputs cannot be empty")
    for input_name in inputs:
        if "." not in input_name:
            if input_name in _PRIMARY_BAR_FIELDS:
                continue
            raise IntentEligibilityError(f"feature input must identify a series: {input_name}")
        series_id, field = input_name.rsplit(".", 1)
        if field not in _ALLOWED_SERIES_FIELDS:
            raise IntentEligibilityError(f"unsupported feature input field: {input_name}")
        if f"{series_id}." not in _ALLOWED_SERIES_PREFIXES:
            raise IntentEligibilityError(f"feature input series is not allowed: {input_name}")


def _operation_from_payload(
    payload: IntentOperation | Mapping[str, object], specs: Mapping[str, FeatureSpec]
) -> MutationOperation | None:
    if isinstance(payload, IntentOperation):
        return _typed_operation_from_model(payload, specs)
    op = payload.get("op")
    if not isinstance(op, str) or not op:
        raise IntentEligibilityError("intent operation op is required")
    path = payload.get("path")
    if path is not None and not isinstance(path, str):
        raise IntentEligibilityError("intent operation path must be a string")
    if op.lower() == "retain":
        if path is not None or payload.get("value") is not None:
            raise IntentEligibilityError("retain operation cannot carry path or value")
        return None
    normalized_op, normalized_path = _normalize_operation(op, path)
    value = _decode_json_value(payload.get("value"))
    if normalized_op == "ADD_FEATURE":
        value = _feature_reference(value, specs)
    return MutationOperation(op=normalized_op, path=normalized_path, value=value)


def _typed_operation_from_model(
    operation: IntentOperation, specs: Mapping[str, FeatureSpec]
) -> MutationOperation | None:
    if operation.op == "RETAIN":
        return None
    path = _normalize_path(operation.path)
    if operation.op == "ADD_REGIME_FILTER":
        if path not in {None, "regime_filters"}:
            raise IntentEligibilityError(
                "regime filter additions must target the regime_filters list",
                code="INTENT_PATH_TARGET",
                diagnostic={
                    "path_received": path,
                    "path_expected": "regime_filters",
                    "repair_action": "target_regime_filter_list",
                    "retryable": True,
                },
            )
        return MutationOperation(operation.op, "regime_filters", _condition_value(operation))
    if operation.op == "ADD_RULE":
        if path not in {"entry.conditions", "exit.conditions"}:
            raise IntentEligibilityError(
                "rule additions must target entry.conditions or exit.conditions",
                code="INTENT_PATH_TARGET",
                diagnostic={
                    "path_received": path,
                    "path_expected": "entry.conditions|exit.conditions",
                    "repair_action": "target_rule_condition_list",
                    "retryable": True,
                },
            )
        return MutationOperation(operation.op, path, _condition_value(operation))
    if operation.op == "REPLACE_RULE" and operation.condition is not None:
        if path is None or not (path.endswith(".conditions") or ".conditions." in path):
            raise IntentEligibilityError(
                "condition replacement must target a rule condition",
                code="INTENT_PATH_TARGET",
                diagnostic={
                    "path_received": path,
                    "path_expected": "entry.conditions.<index>|exit.conditions.<index>",
                    "repair_action": "target_rule_condition",
                    "retryable": True,
                },
            )
        return MutationOperation(operation.op, path, _condition_value(operation))
    if operation.op == "ADD_FEATURE":
        if path is None or not path.startswith("features.") or path == "features.":
            raise IntentEligibilityError(
                "feature additions require a features.<alias> target",
                code="INTENT_PATH_TARGET",
                diagnostic={
                    "path_received": path,
                    "path_expected": "features.<alias>",
                    "repair_action": "set_canonical_target_path",
                    "retryable": True,
                },
            )
        return MutationOperation(operation.op, path, _feature_reference(operation.feature, specs))
    if operation.op == "ADD_INDICATOR":
        if path is None or not path.startswith("indicators.") or path == "indicators.":
            raise IntentEligibilityError(
                "indicator additions require an indicators.<alias> target",
                code="INTENT_PATH_TARGET",
                diagnostic={
                    "path_received": path,
                    "path_expected": "indicators.<alias>",
                    "repair_action": "set_canonical_target_path",
                    "retryable": True,
                },
            )
        if operation.indicator is None:
            raise IntentEligibilityError(
                "indicator additions require an indicator object",
                code="INTENT_VALUE_TYPE",
            )
        return MutationOperation(
            operation.op,
            path,
            operation.indicator.model_dump(mode="python", exclude_none=True),
        )
    if operation.op == "SWAP_INDICATOR":
        if path is None or not path.startswith("indicators.") or path == "indicators.":
            raise IntentEligibilityError(
                "indicator swaps require an indicators.<alias> target",
                code="INTENT_PATH_TARGET",
                diagnostic={
                    "path_received": path,
                    "path_expected": "indicators.<alias>",
                    "repair_action": "set_canonical_target_path",
                    "retryable": True,
                },
            )
        if operation.indicator is None:
            raise IntentEligibilityError(
                "indicator swaps require an indicator object",
                code="INTENT_VALUE_TYPE",
            )
        return MutationOperation(
            operation.op,
            path,
            operation.indicator.model_dump(mode="python", exclude_none=True),
        )
    if operation.op == "CHANGE_AND_OR":
        if path not in {"entry.logic", "exit.logic"}:
            raise IntentEligibilityError(
                "logic changes must target entry.logic or exit.logic",
                code="INTENT_PATH_TARGET",
            )
        return MutationOperation(operation.op, path, operation.logic)
    if operation.op == "SET_PARAMETER":
        if path is None or not _is_parameter_path(path):
            raise IntentEligibilityError(
                "parameter changes must target an indicator or risk parameter",
                code="INTENT_PATH_TARGET",
            )
        return MutationOperation(operation.op, path, operation.value)
    if operation.op in {
        "REMOVE_RULE",
        "REMOVE_FEATURE",
        "REMOVE_INDICATOR",
        "REMOVE_REGIME_FILTER",
        "ENABLE_RULE",
        "DISABLE_RULE",
    } and not path:
        raise IntentEligibilityError(
            f"{operation.op} requires a target path", code="INTENT_PATH_TARGET"
        )
    assert path is not None
    if operation.op == "REMOVE_REGIME_FILTER" and path == "regime_filters":
        raise IntentEligibilityError(
            "regime filter removal requires an item index",
            code="INTENT_PATH_TARGET",
        )
    if operation.op == "REMOVE_FEATURE" and not path.startswith("features."):
        raise IntentEligibilityError(
            "feature removal must target features.<alias>", code="INTENT_PATH_TARGET"
        )
    if operation.op == "REMOVE_INDICATOR" and not path.startswith("indicators."):
        raise IntentEligibilityError(
            "indicator removal must target indicators.<alias>",
            code="INTENT_PATH_TARGET",
        )
    if operation.op in {"ADD_RULE", "ADD_REGIME_FILTER"} and operation.condition is None:
        raise IntentEligibilityError(
            f"{operation.op} requires a condition object", code="INTENT_VALUE_TYPE"
        )
    return MutationOperation(operation.op, path, operation.value)


def _is_parameter_path(path: str) -> bool:
    if path.startswith("indicators."):
        return path.endswith(".period") or ".parameters." in path
    return path in {
        "risk.stop_loss_pct",
        "risk.take_profit_pct",
        "risk.trailing_stop_pct",
        "risk.position_size_pct",
        "risk.risk_appetite",
        "risk.loss_tolerance_pct",
        "risk.daily_loss_limit_pct",
        "risk.daily_loss_action",
        "risk.max_concurrent_positions",
        "risk.max_total_exposure_pct",
    }


def _condition_value(operation: IntentOperation) -> dict[str, object]:
    if operation.condition is None:
        raise IntentEligibilityError(
            f"{operation.op} requires a condition object", code="INTENT_VALUE_TYPE"
        )
    return operation.condition.model_dump(
        mode="python", exclude_none=True, exclude_defaults=True
    )


def _normalize_operation(op: str, path: str | None) -> tuple[str, str | None]:
    normalized_path = _normalize_path(path)
    lowered = op.lower()
    if lowered not in {"add", "replace", "remove"}:
        return op, normalized_path
    if normalized_path is None:
        raise IntentEligibilityError(f"{op} operation requires path")
    if lowered == "replace":
        if normalized_path.startswith("indicators.") and (
            normalized_path.endswith(".period") or ".parameters." in normalized_path
        ):
            return "SET_PARAMETER", normalized_path
        return "REPLACE_RULE", normalized_path
    if lowered == "remove":
        if normalized_path.startswith("features."):
            return "REMOVE_FEATURE", normalized_path
        return "REMOVE_RULE", normalized_path
    if normalized_path.startswith("features."):
        return "ADD_FEATURE", normalized_path
    if normalized_path.startswith("indicators."):
        return "ADD_INDICATOR", normalized_path
    if normalized_path.startswith("regime_filters"):
        return "ADD_REGIME_FILTER", _list_target_path(normalized_path)
    return "ADD_RULE", _list_target_path(normalized_path)


def _normalize_path(path: str | None) -> str | None:
    if path is None:
        return None
    if not path.startswith("/"):
        return _normalize_dot_path(path)
    parts = path.lstrip("/").split("/")
    if parts and parts[0] == "source_strategy":
        parts = parts[1:]
    if not parts or any(
        not part or (part == "-" and index != len(parts) - 1)
        for index, part in enumerate(parts)
    ):
        raise IntentEligibilityError(f"invalid intent operation path: {path}")
    decoded = [part.replace("~1", "/").replace("~0", "~") for part in parts]
    return _normalize_dot_path(".".join(decoded))


def _normalize_dot_path(path: str) -> str:
    normalized = re.sub(r"\[(\d+)\]", r".\1", path)
    if "[" in normalized or "]" in normalized:
        raise IntentEligibilityError(
            f"unsupported path notation: {path}", code="INTENT_PATH_FORMAT"
        )
    return normalized


def _order_operations(
    operations: tuple[MutationOperation, ...],
) -> tuple[MutationOperation, ...]:
    """Apply declarations before rules that may reference their aliases."""

    priority = {
        "ADD_INDICATOR": 0,
        "ADD_FEATURE": 0,
        "SET_PARAMETER": 1,
        "SWAP_INDICATOR": 1,
        "ADD_RULE": 2,
        "REPLACE_RULE": 2,
        "ADD_REGIME_FILTER": 2,
    }
    ordered = sorted(
        enumerate(operations), key=lambda item: (priority.get(item[1].op, 3), item[0])
    )
    return tuple(operation for _, operation in ordered)


def _list_target_path(path: str) -> str:
    return path[:-2] if path.endswith(".-") else path


def _decode_json_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped.startswith(("{", "[")):
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _feature_reference(value: object, specs: Mapping[str, FeatureSpec]) -> FeatureRef:
    if isinstance(value, FeatureRef):
        spec = specs.get(value.feature_id)
        if spec is None:
            raise IntentEligibilityError(
                f"feature is not registered: {value.feature_id}",
                code="INTENT_UNREGISTERED_FEATURE",
            )
        data = value.model_dump(mode="python")
        data["feature_id"] = spec.name
        if not data.get("inputs"):
            data["inputs"] = spec.inputs
        _validate_inputs(tuple(data["inputs"]))
        return FeatureRef.model_validate(data)
    if not isinstance(value, Mapping):
        raise IntentEligibilityError(
            "ADD_FEATURE value must be an object", code="INTENT_VALUE_TYPE"
        )
    feature_id = value.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id:
        raise IntentEligibilityError(
            "ADD_FEATURE value requires feature_id", code="INTENT_VALUE_TYPE"
        )
    spec = specs.get(feature_id)
    if spec is None:
        raise IntentEligibilityError(
            f"feature is not registered: {feature_id}",
            code="INTENT_UNREGISTERED_FEATURE",
        )
    allowed = {
        "feature_id",
        "timeframe",
        "lag_bars",
        "lookback",
        "inputs",
        "parameters",
    }
    data = {key: item for key, item in value.items() if key in allowed}
    data["feature_id"] = spec.name
    if not data.get("inputs"):
        data["inputs"] = spec.inputs
    try:
        reference = FeatureRef.model_validate(data)
    except (TypeError, ValueError) as exc:
        raise IntentEligibilityError(
            f"invalid ADD_FEATURE value: {exc}", code="INTENT_VALUE_TYPE"
        ) from exc
    _validate_inputs(tuple(reference.inputs))
    return reference
