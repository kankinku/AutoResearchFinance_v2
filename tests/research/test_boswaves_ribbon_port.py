"""Causal BOSWaves indicator semantic-port tests (not TradingView parity)."""
import pytest

from research.pine_import.boswaves_ribbon import RibbonParams, compute_ribbon


def _series():
    close = [100 + i * 0.3 for i in range(75)] + [
        122.5 - i * 1.2 for i in range(55)
    ]
    return [p + 1 for p in close], [p - 1 for p in close], close


def test_both_alert_flips_and_bounded_history():
    high, low, close = _series()
    report = compute_ribbon(high, low, close)
    assert any(bar.flip == 1 for bar in report.bars)
    assert any(bar.flip == -1 for bar in report.bars)
    assert all(bar.trend == 0 for bar in report.bars[:33])
    assert report.tradingview_parity == "NOT_VERIFIED"
    assert report.execution_semantics.startswith("NO_ORDERS")


def test_prefix_causality():
    high, low, close = _series()
    full = compute_ribbon(high, low, close)
    for n in (38, 50, 90, 125):
        prefix = compute_ribbon(high[:n], low[:n], close[:n])
        assert prefix.bars == full.bars[:n]


def test_visual_position_stop_targets_and_no_same_bar_hit():
    high, low, close = _series()
    result = compute_ribbon(
        high, low, close, params=RibbonParams(keep_positions=5)
    )
    assert len(result.visual_positions) >= 2
    first = result.visual_positions[0]
    assert first.entry_price == close[first.entry_bar]
    assert first.stop_price == pytest.approx(
        first.entry_price - first.direction * first.risk_distance
    )
    assert first.zone_half_width == pytest.approx(
        first.risk_distance * 0.06
    )
    for i, target in enumerate(first.targets):
        assert target == pytest.approx(
            first.entry_price + first.direction * first.risk_distance * (i + 1)
        )
    assert not result.bars[first.entry_bar].stopped_now


def test_reject_misaligned_prices_nan_and_unsupported_params():
    with pytest.raises(ValueError):
        compute_ribbon([1], [2], [1.5])
    with pytest.raises(ValueError):
        compute_ribbon([2], [1], [])
    with pytest.raises(ValueError):
        compute_ribbon([2], [1], [1.5], source=[float("nan")])
    with pytest.raises(ValueError):
        compute_ribbon([2], [1], [1.5], params=RibbonParams(alma_length=2))
    with pytest.raises(ValueError):
        compute_ribbon([2], [1], [1.5], params=RibbonParams(keep_positions=9))
    with pytest.raises(ValueError):
        compute_ribbon([2], [1], [1.5], params=RibbonParams(alma_sigma=float("nan")))


def test_indicator_does_not_pretend_to_trade():
    high, low, close = _series()
    result = compute_ribbon(high, low, close)
    assert not hasattr(result, "trades")
    assert not hasattr(result, "orders")
    assert result.source_license == "MPL-2.0"
    assert all(
        position.end_reason in ("REVERSED", "STOP_VISUAL", None)
        for position in result.visual_positions
    )
