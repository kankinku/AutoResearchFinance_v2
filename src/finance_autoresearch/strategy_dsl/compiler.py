from __future__ import annotations

from typing import Any

from finance_autoresearch.strategy.base_contract import IndicatorRegistry

from .models import GenomeCompileResult, StrategyGenomeV1


ALLOWED_TARGET_PATH = "src/finance_autoresearch/strategy/mutable/strategy_candidate.py"
MAX_INDICATOR_COUNT = 4
MAX_NEW_CLAUSES = 2
MAX_REGIME_BRANCHES = 2
MAX_EXIT_FAMILIES = 2
_ALLOWED_OPERATORS = {
    "greater_than",
    "less_than",
    "cross_over",
    "cross_under",
    "threshold_band",
    "regime_gate",
    "volatility_filter",
}
_CONTEXT_OPERANDS = {"close", "open", "high", "low", "volume"}
_DIRECTION_MODE = "mirrored_long_short"
_SUPPORTED_INDICATORS = {
    name
    for name in dir(IndicatorRegistry)
    if not name.startswith("_")
    and callable(getattr(IndicatorRegistry, name))
    and name != "rolling_corr"
}


def compile_strategy_genome(artifact: dict[str, Any]) -> GenomeCompileResult:
    if not isinstance(artifact, dict):
        raise ValueError("genome artifact must be an object")
    if artifact.get("kind") != "strategy_genome_v1":
        raise ValueError("artifact kind must be strategy_genome_v1")
    target_path = str(artifact.get("target_path", ""))
    if target_path != ALLOWED_TARGET_PATH:
        raise ValueError("target_path must exactly match the mutable strategy candidate")

    genome = StrategyGenomeV1.from_mapping(artifact)
    if genome.regime_policy == "consider_split_bull_bear":
        raise ValueError("consider_split_bull_bear requires the raw strategy path")
    indicator_count = len(genome.indicator_specs)
    if indicator_count > MAX_INDICATOR_COUNT:
        raise ValueError("indicator budget exceeded")
    new_clause_count = len(genome.entry_clauses) + len(genome.risk_clauses)
    if new_clause_count > MAX_NEW_CLAUSES:
        raise ValueError("new clause budget exceeded")
    regime_branch_count = _regime_branch_count(genome.regime_policy)
    if regime_branch_count > MAX_REGIME_BRANCHES:
        raise ValueError("regime branch budget exceeded")
    exit_family_count = max(1, len(genome.exit_clauses)) if genome.exit_clauses else 1
    if exit_family_count > MAX_EXIT_FAMILIES:
        raise ValueError("exit family budget exceeded")
    validated_indicator_ids, validated_clause_refs = _validate_genome_semantics(genome)

    full_file_contents = _render_strategy_source(genome)
    return GenomeCompileResult(
        target_path=target_path,
        full_file_contents=full_file_contents,
        compile_status="compiled",
        indicator_count=indicator_count,
        new_clause_count=new_clause_count,
        regime_branch_count=regime_branch_count,
        exit_family_count=exit_family_count,
        direction_mode=_DIRECTION_MODE,
        supports_true_regime_split=False,
        validated_indicator_ids=validated_indicator_ids,
        validated_clause_refs=validated_clause_refs,
    )


def _render_strategy_source(genome: StrategyGenomeV1) -> str:
    lines: list[str] = [
        "import pandas as pd",
        "",
        "from finance_autoresearch.strategy.base_contract import StrategyContext, StrategyDefinition",
        "",
        "",
        "def build_strategy(context: StrategyContext) -> StrategyDefinition:",
        "    regime = context.regimes.classify_ema200_regime(context.close)",
        "    regime_valid = context.indicators.ema(context.close, 200).notna()",
        "    bull = context.regimes.is_bull(context.close) & regime_valid",
        "    bear = context.regimes.is_bear(context.close) & regime_valid",
    ]

    for spec in genome.indicator_specs:
        lines.append(_render_indicator(spec))

    entry_names: list[str] = []
    for index, clause in enumerate(genome.entry_clauses):
        name = f"entry_clause_{index}"
        lines.append(f"    {name} = {_render_clause(clause)}")
        entry_names.append(name)
    risk_names: list[str] = []
    for index, clause in enumerate(genome.risk_clauses):
        name = f"risk_clause_{index}"
        lines.append(f"    {name} = {_render_clause(clause)}")
        risk_names.append(name)
    exit_names: list[str] = []
    for index, clause in enumerate(genome.exit_clauses):
        name = f"exit_clause_{index}"
        lines.append(f"    {name} = {_render_clause(clause)}")
        exit_names.append(name)

    long_entry_expr = _combine_and(entry_names + risk_names)
    long_exit_expr = _combine_or(exit_names)
    regime_lines = _render_regime_policy(genome.regime_policy)
    lines.extend(regime_lines)
    lines.extend(
        [
            f"    long_entries = long_entry_regime & ({long_entry_expr})",
            f"    long_exits = regime_valid & (long_exit_regime | ({long_exit_expr}))",
            f"    short_entries = short_entry_regime & ({long_exit_expr})",
            f"    short_exits = regime_valid & (short_exit_regime | ({long_entry_expr}))",
            "    return StrategyDefinition(",
            "        long_entries=long_entries,",
            "        long_exits=long_exits,",
            "        short_entries=short_entries,",
            "        short_exits=short_exits,",
            "        regime=regime,",
            f"        params={_render_literal(dict(genome.params))},",
            "        diagnostics={",
        ]
    )
    for spec in genome.indicator_specs:
        lines.append(f"            {spec['id']!r}: {spec['id']},")
    lines.extend(
        [
            "            'regime_valid': regime_valid,",
            f"            'family_id': {genome.family_id!r},",
            f"            'rationale': {genome.rationale!r},",
            f"            'direction_mode': {_DIRECTION_MODE!r},",
            "            'supports_true_regime_split': False,",
            "        },",
            "    )",
            "",
        ]
    )
    return "\n".join(lines)


def _render_indicator(spec: dict[str, Any]) -> str:
    indicator_id = _require_identifier(spec.get("id"), field_name="indicator id")
    indicator_name = str(spec.get("indicator", "")).strip()
    if not indicator_name:
        raise ValueError("indicator name is required")
    if indicator_name not in _SUPPORTED_INDICATORS:
        raise ValueError(f"indicator {indicator_name!r} is not supported by the genome compiler")
    input_name = str(spec.get("input", "close")).strip()
    args = {
        "close": "context.close",
        "open": "context.open",
        "high": "context.high",
        "low": "context.low",
        "volume": "context.volume",
    }
    if indicator_name == "atr":
        call = (
            "context.indicators.atr("
            "context.high, context.low, context.close"
            f"{_render_kwargs(spec.get('params', {}))})"
        )
    else:
        if input_name not in args:
            raise ValueError("unsupported indicator input")
        call = f"context.indicators.{indicator_name}({args[input_name]}{_render_kwargs(spec.get('params', {}))})"
    return f"    {indicator_id} = {call}"


def _render_clause(clause: dict[str, Any]) -> str:
    operator = str(clause.get("operator", "")).strip()
    if operator not in _ALLOWED_OPERATORS:
        raise ValueError(f"unsupported genome operator: {operator}")
    if operator == "regime_gate":
        regime_name = str(clause.get("regime", "")).strip().lower()
        if regime_name == "bull":
            return "bull"
        if regime_name == "bear":
            return "bear"
        raise ValueError("regime_gate must target bull or bear")

    left = _render_operand(clause.get("left"))
    right = _render_threshold_right(clause)
    if operator == "greater_than":
        return f"{left} > {right}"
    if operator == "less_than":
        return f"{left} < {right}"
    if operator == "cross_over":
        base = f"{left} > {right}"
        return f"({base}) & ~({base}).shift(1, fill_value=False)"
    if operator == "cross_under":
        base = f"{left} < {right}"
        return f"({base}) & ~({base}).shift(1, fill_value=False)"
    if operator == "threshold_band":
        lower = clause.get("lower")
        upper = clause.get("upper")
        if lower is None or upper is None:
            raise ValueError("threshold_band requires lower and upper")
        return f"({left} >= {_render_literal(lower)}) & ({left} <= {_render_literal(upper)})"
    if operator == "volatility_filter":
        mode = str(clause.get("mode", "below")).strip().lower()
        comparator = "<=" if mode == "below" else ">="
        return f"{left} {comparator} {right}"
    raise ValueError(f"unsupported genome operator: {operator}")


def _render_regime_policy(regime_policy: str) -> list[str]:
    if regime_policy == "preserve_current_regime_model":
        return [
            "    long_entry_regime = bull",
            "    long_exit_regime = bear",
            "    short_entry_regime = bear",
            "    short_exit_regime = bull",
        ]
    raise ValueError("unsupported regime policy")


def _render_threshold_right(clause: dict[str, Any]) -> str:
    if "right" in clause:
        return _render_operand(clause.get("right"))
    if "value" in clause:
        return _render_literal(clause["value"])
    raise ValueError("clause must provide either right or value")


def _render_operand(value: Any) -> str:
    if isinstance(value, (int, float, bool)):
        return _render_literal(value)
    if not isinstance(value, str):
        raise ValueError("clause operands must be strings or scalar values")
    normalized = value.strip()
    if not normalized:
        raise ValueError("clause operands must not be empty")
    if normalized in _CONTEXT_OPERANDS:
        return f"context.{normalized}"
    return _require_identifier(normalized, field_name="clause reference")


def _render_kwargs(params: Any) -> str:
    if not params:
        return ""
    if not isinstance(params, dict):
        raise ValueError("indicator params must be an object")
    ordered = ", ".join(f"{key}={_render_literal(value)}" for key, value in sorted(params.items()))
    return f", {ordered}"


def _combine_and(names: list[str]) -> str:
    if not names:
        return "regime_valid"
    return " & ".join(names)


def _combine_or(names: list[str]) -> str:
    if not names:
        return "bear"
    return " | ".join(names)


def _render_literal(value: Any) -> str:
    return repr(value)


def _require_identifier(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized.replace("_", "").isalnum():
        raise ValueError(f"{field_name} must be a simple identifier")
    return normalized


def _regime_branch_count(regime_policy: str) -> int:
    if regime_policy == "preserve_current_regime_model":
        return 2
    raise ValueError("unsupported regime policy")


def _validate_genome_semantics(genome: StrategyGenomeV1) -> tuple[tuple[str, ...], tuple[str, ...]]:
    declared_indicator_ids: list[str] = []
    declared_indicator_set: set[str] = set()
    validated_clause_refs: list[str] = []
    validated_clause_ref_set: set[str] = set()

    for spec in genome.indicator_specs:
        indicator_id = _require_identifier(spec.get("id"), field_name="indicator id")
        indicator_name = str(spec.get("indicator", "")).strip()
        if not indicator_name:
            raise ValueError("indicator name is required")
        if not hasattr(IndicatorRegistry, indicator_name):
            raise ValueError(f"unknown indicator name: {indicator_name}")
        if indicator_name not in _SUPPORTED_INDICATORS:
            raise ValueError(f"indicator {indicator_name!r} is not supported by the genome compiler")
        declared_indicator_set.add(indicator_id)
        if indicator_id not in declared_indicator_ids:
            declared_indicator_ids.append(indicator_id)

    for clause in (*genome.entry_clauses, *genome.exit_clauses, *genome.risk_clauses):
        _validate_clause_operands(
            clause=clause,
            declared_indicator_ids=declared_indicator_set,
            validated_clause_refs=validated_clause_refs,
            validated_clause_ref_set=validated_clause_ref_set,
        )

    return tuple(declared_indicator_ids), tuple(validated_clause_refs)


def _validate_clause_operands(
    *,
    clause: dict[str, Any],
    declared_indicator_ids: set[str],
    validated_clause_refs: list[str],
    validated_clause_ref_set: set[str],
) -> None:
    operator = str(clause.get("operator", "")).strip()
    if operator == "regime_gate":
        return
    _validate_clause_operand(
        clause.get("left"),
        declared_indicator_ids=declared_indicator_ids,
        validated_clause_refs=validated_clause_refs,
        validated_clause_ref_set=validated_clause_ref_set,
    )
    if "right" in clause:
        _validate_clause_operand(
            clause.get("right"),
            declared_indicator_ids=declared_indicator_ids,
            validated_clause_refs=validated_clause_refs,
            validated_clause_ref_set=validated_clause_ref_set,
        )
    if "value" in clause:
        _validate_clause_operand(
            clause.get("value"),
            declared_indicator_ids=declared_indicator_ids,
            validated_clause_refs=validated_clause_refs,
            validated_clause_ref_set=validated_clause_ref_set,
        )
    if operator == "threshold_band":
        _validate_clause_operand(
            clause.get("lower"),
            declared_indicator_ids=declared_indicator_ids,
            validated_clause_refs=validated_clause_refs,
            validated_clause_ref_set=validated_clause_ref_set,
        )
        _validate_clause_operand(
            clause.get("upper"),
            declared_indicator_ids=declared_indicator_ids,
            validated_clause_refs=validated_clause_refs,
            validated_clause_ref_set=validated_clause_ref_set,
        )


def _validate_clause_operand(
    value: Any,
    *,
    declared_indicator_ids: set[str],
    validated_clause_refs: list[str],
    validated_clause_ref_set: set[str],
) -> None:
    if value is None:
        raise ValueError("clause operands must not be empty")
    if isinstance(value, (int, float, bool)):
        return
    if not isinstance(value, str):
        raise ValueError("clause operands must be strings or scalar values")
    normalized = _require_identifier(value, field_name="clause reference")
    if normalized not in _CONTEXT_OPERANDS and normalized not in declared_indicator_ids:
        raise ValueError(f"unknown clause reference: {normalized}")
    if normalized not in validated_clause_ref_set:
        validated_clause_ref_set.add(normalized)
        validated_clause_refs.append(normalized)
