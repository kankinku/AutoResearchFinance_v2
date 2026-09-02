from __future__ import annotations

from pathlib import Path

from strategy_import.analyzers import AnalysisStatus, analyze_python_source


def test_kis_builder_state_is_converted_to_strategy_ir(tmp_path: Path) -> None:
    source = tmp_path / "golden_cross.py"
    source.write_text(
        """
from strategy_core.registry import register

@register('golden_cross', '추세추종')
class GoldenCrossPreset:
    builder_state = {
        'metadata': {'id': 'golden_cross', 'category': 'trend'},
        'indicators': [
            {'indicatorId': 'sma', 'alias': 'sma_fast', 'params': {'period': 5}},
            {'indicatorId': 'sma', 'alias': 'sma_slow', 'params': {'period': 20}},
        ],
        'entry': {'logic': 'AND', 'conditions': [{
            'left': {'type': 'indicator', 'indicatorAlias': 'sma_fast'},
            'operator': 'cross_above',
            'right': {'type': 'indicator', 'indicatorAlias': 'sma_slow'},
        }]},
        'exit': {'logic': 'AND', 'conditions': [{
            'left': {'type': 'indicator', 'indicatorAlias': 'sma_fast'},
            'operator': 'cross_below',
            'right': {'type': 'indicator', 'indicatorAlias': 'sma_slow'},
        }]},
        'risk': {'stopLoss': {'enabled': True, 'percent': 5},
                 'takeProfit': {'enabled': False, 'percent': 10}},
    }
""",
        encoding="utf-8",
    )

    result = analyze_python_source(source)

    assert result.status is AnalysisStatus.NORMALIZED
    assert result.strategy is not None
    assert result.strategy.strategy_id == "golden_cross"
    assert result.strategy.indicators["sma_fast"].type == "SMA"
    assert result.strategy.entry.conditions[0].op == "cross_above"
    assert result.strategy.risk.stop_loss_pct == 5


def test_dynamic_python_is_retained_for_review_without_execution(tmp_path: Path) -> None:
    source = tmp_path / "dynamic.py"
    source.write_text(
        "raise RuntimeError('must never execute')\nclass DynamicStrategy: pass\n",
        encoding="utf-8",
    )

    result = analyze_python_source(source)

    assert result.status is AnalysisStatus.REVIEW_REQUIRED
    assert result.strategy is None
    assert "execution" in result.reason.lower()
    assert "python_module" in result.profile["detected_constructs"]


def test_textual_sma_words_do_not_create_fake_strategy(tmp_path: Path) -> None:
    source = tmp_path / "comment_only.py"
    source.write_text(
        "# SMA(5) crossover and SMA(20) crossunder are discussed here\n",
        encoding="utf-8",
    )

    result = analyze_python_source(source)

    assert result.status is AnalysisStatus.REVIEW_REQUIRED
    assert result.strategy is None


def test_kis_price_operand_maps_to_strategy_ir_price_reference(tmp_path: Path) -> None:
    source = tmp_path / "price_condition.py"
    source.write_text(
        """
class Preset:
    builder_state = {
        'metadata': {'id': 'breakout', 'category': 'breakout'},
        'indicators': [{'indicatorId': 'highest', 'alias': 'prev_high', 'params': {'period': 20}}],
        'entry': {'logic': 'AND', 'conditions': [{
            'left': {'type': 'price', 'priceField': 'close'},
            'operator': 'less_than',
            'right': {'type': 'indicator', 'indicatorAlias': 'prev_high'},
        }]},
        'exit': {'logic': 'OR', 'conditions': [{
            'left': {'type': 'price', 'priceField': 'close'},
            'operator': 'greater_than',
            'right': {'type': 'indicator', 'indicatorAlias': 'prev_high'},
        }]},
        'risk': {
            'stopLoss': {'enabled': True, 'percent': 3},
            'takeProfit': {'enabled': False, 'percent': 10},
        },
    }
""",
        encoding="utf-8",
    )

    result = analyze_python_source(source)

    assert result.status is AnalysisStatus.NORMALIZED
    assert result.strategy is not None
    assert result.strategy.entry.conditions[0].left == "close"
