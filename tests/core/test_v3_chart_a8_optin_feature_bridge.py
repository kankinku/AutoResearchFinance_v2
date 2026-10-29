"""A8: opt-in chart research FeatureRef scalar vectors, causal overlay parity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from core.features.calculators import calculate_feature
from core.features.registry import research_feature_specs
from research.chart_pattern_bridge import (
    calculate_chart_research,
    chart_research_feature_specs,
    overlay_payload,
)
from research.llm.inherited_feature_compiler import (
    InheritedFeatureBindingError,
    _new_feature_vector,
)
from strategy_ir.schema import FeatureRef
from tests.core.test_v3_chart_a7_classical_lifecycle import EXAMPLES, interpolate_ohlc


def long_sample(
    name: str = "double_top",
    n: int = 192,
    zone: DataZone = DataZone.DEVELOPMENT,
) -> MarketDataSet:
    example = interpolate_ohlc(EXAMPLES[name])
    prefix = (example["close"][0],) * (n - len(example["close"]))
    bars = []
    for i, price in enumerate(prefix + example["close"]):
        bars.append(
            Bar(
                timestamp=datetime(2020, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
                symbol="TEST",
                open=price,
                high=price,
                low=price,
                close=price,
                volume=100.0,
            )
        )
    return MarketDataSet("a8-synthetic", zone, tuple(bars))


def data_inputs(market: MarketDataSet) -> dict[str, tuple[float, ...]]:
    return {
        key: tuple(float(getattr(row, key)) for row in market.bars)
        for key in ("high", "low", "close")
    }


def test_registry_447_unchanged_and_44_research_spec_outputs_opt_in_only() -> None:
    vanilla = research_feature_specs()
    research = chart_research_feature_specs()
    enabled = research_feature_specs(chart_research_opt_in=True)
    assert len(vanilla) == 447
    assert len(research) == 44
    assert len(enabled) == 491
    assert not set(s.name for s in research) & set(s.name for s in vanilla)
    assert all(s.status == "REGISTERED" and s.implementation_hash for s in research)
    assert all(s.source_licenses == ("original-research-only",) for s in research)
    assert all(s.inputs == ("high", "low", "close") for s in research)
    assert len({s.canonical_id for s in research}) == len(research)


@pytest.mark.parametrize("name", tuple(EXAMPLES))  # type: ignore[untyped-decorator]
def test_end_to_end_classical_channels_match_causal_confirmed_event(name: str) -> None:
    m = long_sample(name)
    inputs = data_inputs(m)
    prefix = "chart_research_" + name + "_"
    specs = {s.name: s for s in chart_research_feature_specs()}
    channels = {
        k: calculate_feature(specs[prefix + k], inputs)
        for k in (
            "detected",
            "stage",
            "quality",
            "neckline_distance",
            "distance_to_invalidation",
            "bars_since_confirmation",
        )
    }
    assert all(len(x) == len(m.bars) for x in channels.values())
    events = overlay_payload(m, patterns=(name,), allow_research=True)
    assert events["overlay_hash"]
    matches = [e for e in events["events"] if e["name"] == name]
    stages = [e["stage"] for e in matches]
    assert stages == ["CANDIDATE", "CONFIRMED"]
    candidate, confirmed = matches
    assert candidate["event_at"] < confirmed["event_at"]
    assert candidate["eligible_from"] == candidate["event_at"] + 1
    assert confirmed["eligible_from"] == confirmed["event_at"] + 1
    assert channels["stage"][candidate["event_at"]] == 1.0
    assert channels["stage"][confirmed["event_at"]] == 2.0
    assert channels["detected"][confirmed["event_at"]] == confirmed["direction"]
    assert sum(x != 0.0 for x in channels["detected"]) == 1
    assert channels["bars_since_confirmation"][confirmed["event_at"]] == 0.0
    assert all(x == 0.0 for x in channels["detected"][: confirmed["event_at"]])


@pytest.mark.parametrize("name", tuple(EXAMPLES))  # type: ignore[untyped-decorator]
def test_feature_ref_vector_parity_and_default_off(name: str) -> None:
    market = long_sample(name)
    key = f"chart_research_{name}_detected"
    ref = FeatureRef(feature_id=key, timeframe="1d", lag_bars=0)
    with pytest.raises(InheritedFeatureBindingError):
        _new_feature_vector(ref, market)
    direct = calculate_chart_research(name, "detected", data_inputs(market))
    assert _new_feature_vector(ref, market, allow_chart_research=True) == direct
    delayed = FeatureRef(feature_id=key, timeframe="1d", lag_bars=1)
    delayed_series = _new_feature_vector(delayed, market, allow_chart_research=True)
    assert delayed_series[0] is None and delayed_series[1:] == direct[:-1]


def test_research_zone_guard_and_unregistered_params_rejected() -> None:
    m = long_sample()
    spec = next(s for s in chart_research_feature_specs() if s.name.endswith("double_top_detected"))
    with pytest.raises(InheritedFeatureBindingError):
        _new_feature_vector(
            FeatureRef(feature_id=spec.name),
            long_sample(zone=DataZone.SEALED_OOS),
            allow_chart_research=True,
        )
    with pytest.raises(InheritedFeatureBindingError):
        _new_feature_vector(
            FeatureRef(feature_id=spec.name, parameters={"confirmation_bars": 0}),
            m,
            allow_chart_research=True,
        )
    with pytest.raises(PermissionError):
        overlay_payload(m, patterns=("double_top",), allow_research=False)
    with pytest.raises(PermissionError):
        overlay_payload(
            long_sample(zone=DataZone.SEALED_OOS),
            patterns=("double_top",),
            allow_research=True,
        )


def test_overlay_known_at_never_backdated_and_prefix_hash_reproducible() -> None:
    m = long_sample()
    full = overlay_payload(m, patterns=("double_top",), allow_research=True)
    assert all(e["event_at"] >= e["last_pivot_index"] for e in full["events"])
    assert all(e["known_at"] == e["event_at"] for e in full["events"])
    assert all(p["known_at"] >= p["pivot_at"] for p in full["pivots"])
    assert full == overlay_payload(m, patterns=("double_top",), allow_research=True)
    for cutoff in range(len(m.bars) - 33, len(m.bars) + 1):
        partial = MarketDataSet(m.version, m.zone, m.bars[:cutoff])
        snap = overlay_payload(partial, patterns=("double_top",), allow_research=True)
        assert snap["events"] == [event for event in full["events"] if event["event_at"] < cutoff]
        assert snap["pivots"] == [pivot for pivot in full["pivots"] if pivot["known_at"] < cutoff]


def test_harmonic_and_elliott_auxiliary_research_channels_have_finite_values() -> None:
    m = long_sample()
    src = data_inputs(m)
    channels = [
        ("harmonic_gartley", "detected"),
        ("harmonic_gartley", "stage"),
        ("harmonic_gartley", "distance_to_prz"),
        ("elliott_impulse_5", "detected"),
        ("elliott_impulse_5", "stage"),
    ]
    for pattern, channel in channels:
        result = calculate_chart_research(pattern, channel, src)
        assert len(result) == len(m.bars)
        assert all(isinstance(x, float) for x in result)


def test_overlay_has_separate_chart_generation_date_symbol_labels() -> None:
    m = long_sample()
    result = overlay_payload(
        m,
        patterns=("double_top",),
        allow_research=True,
        generation="G124",
        date_window=(160, len(m.bars)),
    )
    assert result["generation"] == "G124"
    assert result["symbol"] == "TEST"
    assert result["visible_window"] == [160, len(m.bars)]
    assert all(e["event_at"] >= 160 for e in result["events"])
    assert all(p["known_at"] >= 160 for p in result["pivots"])


@pytest.mark.parametrize("key", [s.name for s in chart_research_feature_specs()])  # type: ignore[untyped-decorator]
def test_all_44_named_feature_ref_outputs_equal_direct_replay(key: str) -> None:
    market = long_sample()
    spec = next(item for item in chart_research_feature_specs() if item.name == key)
    direct = calculate_feature(spec, data_inputs(market))
    ref = FeatureRef(feature_id=key, timeframe="1d")
    replay = _new_feature_vector(ref, market, allow_chart_research=True)
    assert replay == direct
    assert len(direct) == len(market.bars)
    assert all(isinstance(value, float) for value in direct)


def test_new_features_are_not_inserted_into_default_strategy_registry() -> None:
    old = research_feature_specs()
    new = research_feature_specs(chart_research_opt_in=True)
    assert old == tuple(x for x in new if x.family != "chart_research")
    assert {x.name for x in new if x.family == "chart_research"} == {
        x.name for x in chart_research_feature_specs()
    }


def test_full_prefix_parity_event_channels_on_each_pattern() -> None:
    for name in EXAMPLES:
        market = long_sample(name)
        src = data_inputs(market)
        total = calculate_chart_research(name, "detected", src)
        stage = calculate_chart_research(name, "stage", src)
        for cutoff in range(160, len(total) + 1):
            truncated = {key: vec[:cutoff] for key, vec in src.items()}
            assert calculate_chart_research(name, "detected", truncated) == total[:cutoff]
            assert calculate_chart_research(name, "stage", truncated) == stage[:cutoff]


def test_overlay_for_multiple_pattern_families_preserves_default_research_only() -> None:
    m = long_sample()
    names = ("double_top", "harmonic_gartley", "elliott_abc")
    payload = overlay_payload(m, patterns=names, allow_research=True)
    assert payload["source"] == "DEVELOPMENT_ONLY"
    assert payload["execution_trades"] == []
    assert payload["feature_source_hash"]
    assert payload["overlay_hash"]
    assert all(e["known_at"] >= e["last_pivot_index"] for e in payload["events"])
    with pytest.raises(ValueError):
        overlay_payload(m, patterns=names, generation="../bad", allow_research=True)
    with pytest.raises(ValueError):
        overlay_payload(m, patterns=("double_top", "double_top"), allow_research=True)


def test_actual_inherited_strategyir_bind_requires_opt_in_and_next_bar_stamps() -> None:
    from dataclasses import replace

    from core.integrity.hashes import content_hash
    from research.indicator_engine.bridge import ResearchSignalReplay
    from research.llm.inherited_feature_compiler import bind_inherited_features
    from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture

    ancestor, _ = _warmup_fixture()
    market = long_sample()
    count = len(market.bars)
    values = {"fast": (1.0,) * count, "slow": (0.0,) * count}
    stamps = tuple(row.timestamp for row in market.bars)
    replay = ResearchSignalReplay(
        hypothesis_hash=ancestor.hypothesis_hash,
        data_hash=market.dataset_hash,
        signals=tuple(sorted(values.items())),
        timestamps=stamps,
        execution_not_before=stamps[1:] + (None,),
        entry_regime_observations=0,
        replay_hash=content_hash({"a8": "pre-existing-fixture", "data": market.dataset_hash}),
    )
    parent = replace(
        ancestor,
        dataset_hash=market.dataset_hash,
        replay=replay,
        feature_values=values,
    )
    name = "chart_research_double_top_detected"
    child_ir = parent.strategy.model_copy(
        update={
            "features": {
                **parent.strategy.features,
                "research_neckline": FeatureRef(feature_id=name),
            }
        }
    )
    with pytest.raises(InheritedFeatureBindingError):
        bind_inherited_features(parent, child_ir, market)
    child = bind_inherited_features(
        parent,
        child_ir,
        market,
        allow_chart_research=True,
    )
    vector = child.feature_values["research_neckline"]
    assert vector == calculate_chart_research("double_top", "detected", data_inputs(market))
    assert child.replay.execution_not_before == stamps[1:] + (None,)
    assert child.replay.replay_hash != parent.replay.replay_hash
    assert bind_inherited_features(parent, child_ir, market, allow_chart_research=True) == child
