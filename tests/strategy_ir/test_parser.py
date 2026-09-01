from __future__ import annotations

from pathlib import Path

from strategy_ir.parser import parse_strategy_yaml
from tests.strategy_ir.test_schema import example_document


def test_parser_normalizes_json_like_yaml_and_preserves_provenance(tmp_path: Path) -> None:
    source = tmp_path / "strategy.yaml"
    source.write_text(
        """schema_version: 1
strategy:
  id: S1
  family: trend
  generation: 1
  indicators:
    fast: {type: SMA, period: 5}
    slow: {type: SMA, period: 20}
  entry: {logic: AND, conditions: [{op: cross_above, left: fast, right: slow}]}
  exit: {logic: OR, conditions: [{op: cross_below, left: fast, right: slow}]}
  risk: {stop_loss_pct: 2, take_profit_pct: 5}
""",
        encoding="utf-8",
    )

    parsed = parse_strategy_yaml(source)

    assert parsed.strategy_id == "S1"
    assert parsed.provenance.source_path == source.as_posix()
    assert len(parsed.provenance.source_hash) == 64


def test_parser_produces_stable_canonical_dict() -> None:
    from strategy_ir.parser import parse_strategy_document

    first = parse_strategy_document(example_document()).model_dump(mode="json")
    second = parse_strategy_document(
        {"strategy": example_document()["strategy"], "schema_version": 1}
    ).model_dump(mode="json")
    assert first == second
