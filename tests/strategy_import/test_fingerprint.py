from __future__ import annotations

from strategy_import.fingerprint import DuplicateKind, classify_duplicate, strategy_fingerprint
from strategy_ir.schema import StrategyIR


def _strategy(*, stop_loss: float = 5.0) -> StrategyIR:
    return StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "sample",
            "family": "trend",
            "generation": 0,
            "indicators": {
                "fast": {"type": "SMA", "period": 5},
                "slow": {"type": "SMA", "period": 20},
            },
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "cross_above", "left": "fast", "right": "slow"}],
            },
            "exit": {
                "logic": "OR",
                "conditions": [{"op": "cross_below", "left": "fast", "right": "slow"}],
            },
            "risk": {"stop_loss_pct": stop_loss, "take_profit_pct": 10},
        }
    )


def test_fingerprint_ignores_strategy_id_and_provenance() -> None:
    left = _strategy()
    right = left.model_copy(
        update={
            "strategy_id": "other",
            "provenance": {"source_path": "other.py", "source_hash": "different"},
        }
    )

    assert strategy_fingerprint(left) == strategy_fingerprint(right)
    assert classify_duplicate(left, [right]).kind == DuplicateKind.EXACT_DUPLICATE.value


def test_fingerprint_marks_risk_only_change_as_partial_duplicate() -> None:
    assert (
        classify_duplicate(_strategy(stop_loss=5), [_strategy(stop_loss=3)]).kind
        == DuplicateKind.PARTIAL_DUPLICATE.value
    )
