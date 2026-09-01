from __future__ import annotations

from pathlib import Path

from strategy_ir.normalizer import ImportStatus, normalize_source


def test_yaml_source_normalizes_with_hash_and_ir(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    source.write_text(
        """schema_version: 1
strategy:
  id: imported-yaml
  family: trend
  generation: 0
  indicators:
    fast: {type: SMA, period: 5}
    slow: {type: SMA, period: 20}
  entry: {logic: AND, conditions: [{op: cross_above, left: fast, right: slow}]}
  exit: {logic: OR, conditions: [{op: cross_below, left: fast, right: slow}]}
  risk: {stop_loss_pct: 2, take_profit_pct: 5}
""",
        encoding="utf-8",
    )

    result = normalize_source(source)

    assert result.status is ImportStatus.NORMALIZED
    assert result.strategy is not None
    assert result.strategy.strategy_id == "imported-yaml"
    assert len(result.source_hash) == 64


def test_python_source_uses_literal_ast_without_executing_code(tmp_path: Path) -> None:
    source = tmp_path / "strategy.py"
    source.write_text(
        "STRATEGY = {\n"
        " 'schema_version': 1,\n"
        " 'strategy': {\n"
        "  'id': 'py', 'family': 'trend', 'generation': 0,\n"
        "  'indicators': {'fast': {'type': 'SMA', 'period': 5}, "
        "'slow': {'type': 'SMA', 'period': 20}},\n"
        "  'entry': {'logic': 'AND', 'conditions': ["
        "{'op': 'cross_above', 'left': 'fast', 'right': 'slow'}]},\n"
        "  'exit': {'logic': 'OR', 'conditions': ["
        "{'op': 'cross_below', 'left': 'fast', 'right': 'slow'}]},\n"
        "  'risk': {'stop_loss_pct': 2, 'take_profit_pct': 5}\n"
        " }\n"
        "}\n",
        encoding="utf-8",
    )

    result = normalize_source(source)

    assert result.status is ImportStatus.NORMALIZED
    assert result.strategy is not None
    assert result.strategy.strategy_id == "py"


def test_unsupported_source_is_reported_without_silent_drop(tmp_path: Path) -> None:
    source = tmp_path / "strategy.py"
    source.write_text("import requests\nrequests.get('https://example.com')\n", encoding="utf-8")

    result = normalize_source(source)

    assert result.status is ImportStatus.UNSUPPORTED
    assert result.strategy is None
    assert "literal" in result.reason.lower()
