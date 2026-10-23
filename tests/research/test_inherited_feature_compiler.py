"""Regression: new registered indicators really execute and reconstitute the same replay."""

from __future__ import annotations

from dataclasses import replace

import pytest

from core.data.contracts import MarketDataSet
from core.integrity.hashes import content_hash
from research.indicator_engine.inherited_decision_audit import audit_inherited_decisions
from research.indicator_engine.strategy_adapter import evaluate_compiled_development
from research.llm.inherited_execution_identity import inherited_effective_signal_hash
from research.llm.inherited_feature_compiler import (
    InheritedFeatureBindingError,
    _new_feature_vector,
    bind_inherited_features,
)
from strategy_ir.schema import Condition, FeatureRef
from tests.research.test_v3_inherited_audit_warmup import _warmup_fixture


def _atr_mutation(*, lag: int = 0, lookback: int = 2):
    original, market = _warmup_fixture()
    reference = FeatureRef(
        feature_id="normalized_atr_percent",
        timeframe="1d",
        lookback=lookback,
        inputs=("high", "low", "close"),
        lag_bars=lag,
    )
    amended = original.strategy.model_copy(
        update={
            "features": {**original.strategy.features, "natr_pct_20": reference},
            "regime_filters": [
                *original.strategy.regime_filters,
                Condition(op="less_than", left="natr_pct_20", value=0.035),
            ],
        }
    )
    return original, market, amended, reference


def test_new_atr_vector_is_actually_computed_signed_and_s2_audited():
    original, market, amended, _ = _atr_mutation()
    child = bind_inherited_features(original, amended, market)
    assert "natr_pct_20" in child.feature_values
    assert child.feature_values["natr_pct_20"][0] is None
    assert child.feature_values["natr_pct_20"][2] is not None
    assert child.replay.replay_hash != original.replay.replay_hash
    assert dict(child.replay.signals) == child.feature_values
    assert child.strategy_hash == content_hash(amended.model_dump(mode="json", by_alias=True))
    assert inherited_effective_signal_hash(child, market)
    evaluated = evaluate_compiled_development(child, market)
    audited = audit_inherited_decisions(child, market)
    assert evaluated.final_equity == audited.evaluation.final_equity
    assert evaluated.equity_hash == audited.evaluation.equity_hash
    rebuilt = bind_inherited_features(original, amended, market)
    assert rebuilt == child


def test_atr_series_is_causal_on_prefix_and_explicit_lag():
    _, market, _, reference = _atr_mutation(lag=2)
    delayed = _new_feature_vector(reference, market)
    assert delayed[:2] == (None, None)
    assert delayed[3] is not None
    past = MarketDataSet("s2-regression-v3", "development", market.bars[:4])
    assert delayed[:4] == _new_feature_vector(reference, past)


def test_only_registered_OHLCV_same_timeframe_allowed():
    original, market, amended, _ = _atr_mutation()
    for feature_ref in (
        FeatureRef(feature_id="not-a-registered-feature"),
        FeatureRef(feature_id="normalized_atr_percent", timeframe="1h"),
        FeatureRef(feature_id="normalized_atr_percent", inputs=("VIX.close",)),
    ):
        bad = amended.model_copy(
            update={"features": {**original.strategy.features, "natr_pct_20": feature_ref}}
        )
        with pytest.raises(InheritedFeatureBindingError):
            bind_inherited_features(original, bad, market)


def test_existing_replay_unchanged_when_no_feature_mutation():
    original, market = _warmup_fixture()
    descendant = original.strategy.model_copy(update={"strategy_id": "changed-id"})
    actual = bind_inherited_features(original, descendant, market)
    assert actual.replay == original.replay
    assert actual.hypothesis_hash == original.hypothesis_hash
    assert actual.feature_values == original.feature_values


def test_invalid_feature_tamper_has_no_replay_proof():
    original, market, amended, _ = _atr_mutation()
    signed = bind_inherited_features(original, amended, market)
    assert audit_inherited_decisions(signed, market)
    altered = replace(
        signed,
        feature_values={
            **signed.feature_values,
            "natr_pct_20": tuple(None for _ in market.bars),
        },
    )
    with pytest.raises(ValueError, match="precomputed feature mismatch"):
        evaluate_compiled_development(altered, market)


def test_parameter_position_sizing_has_distinct_costed_identity_without_legacy_change():
    original, market = _warmup_fixture()
    one_hundred = inherited_effective_signal_hash(original, market)
    assert one_hundred
    changed_risk = original.strategy.risk.model_copy(update={"position_size_pct": 75.0})
    altered_ir = original.strategy.model_copy(update={"risk": changed_risk})
    child = bind_inherited_features(original, altered_ir, market)
    assert child.replay == original.replay
    assert inherited_effective_signal_hash(child, market) != one_hundred
    assert child.strategy.risk.position_size_pct == 75
    original_eval = evaluate_compiled_development(original, market)
    child_eval = evaluate_compiled_development(child, market)
    assert original_eval.equity_hash != child_eval.equity_hash
    assert child_eval.broker_executable is False


def test_counted_descendant_replays_ancestor_feature_signature_without_rewriting_evidence(
    tmp_path, monkeypatch
):
    """The audited signature must survive an inherited threshold-only mutation."""
    from types import SimpleNamespace

    import application.academic_checkpoint_service as service_module
    from application.academic_checkpoint_service import (
        AcademicMCPCheckpointService,
        CycleStateError,
    )

    base, market = _warmup_fixture()
    ref = FeatureRef(
        feature_id="normalized_atr_percent",
        lookback=2,
        inputs=("high", "low", "close"),
    )
    initial_ir = base.strategy.model_copy(
        update={
            "features": {**base.strategy.features, "natr_pct_20": ref},
            "regime_filters": [
                *base.strategy.regime_filters,
                Condition(op="less_than", left="natr_pct_20", value=0.035),
            ],
        }
    )
    source = bind_inherited_features(base, initial_ir, market)
    source_audit = audit_inherited_decisions(source, market)
    child_ir = initial_ir.model_copy(
        update={
            "regime_filters": [
                *base.strategy.regime_filters,
                Condition(op="less_than", left="natr_pct_20", value=0.05),
            ],
        }
    )
    child = bind_inherited_features(source, child_ir, market)
    child_audit = audit_inherited_decisions(child, market)
    direct_child = bind_inherited_features(base, child_ir, market)
    assert audit_inherited_decisions(direct_child, market).trace_hash != child_audit.trace_hash
    source_record = {
        "generation": 1,
        "base_algorithm_plan": {},
        "inherited_strategy_ir": initial_ir.model_dump(mode="json"),
        "strategy_hash": source.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "audit_hash": source_audit.trace_hash,
        "measured_final_equity": source_audit.evaluation.final_equity,
        "evidence_hash": "1" * 64,
    }
    child_record = {
        "generation": 2,
        "base_algorithm_plan": {},
        "inherited_strategy_ir": child_ir.model_dump(mode="json"),
        "strategy_hash": child.strategy_hash,
        "dataset_hash": market.dataset_hash,
        "audit_hash": child_audit.trace_hash,
        "measured_final_equity": child_audit.evaluation.final_equity,
        "inherited_parent": {
            "schema": "p0-3b-counted-inheritance-input-v1",
            "source_generation": 1,
            "source_evidence_hash": source_record["evidence_hash"],
            "parent_strategy_hash": source.strategy_hash,
        },
    }
    monkeypatch.setattr(service_module.AlgorithmPlan, "model_validate", lambda _: object())
    monkeypatch.setattr(
        service_module, "compile_algorithm_plan", lambda *args: SimpleNamespace(compiled=base)
    )
    svc = AcademicMCPCheckpointService(project_root=tmp_path, state_dir=tmp_path / "state")
    rebuilt = svc._inherited_from_evidence(
        None, market, child_record, history=[source_record, child_record]
    )
    assert rebuilt.replay == source.replay
    assert rebuilt.strategy_hash == child.strategy_hash
    assert audit_inherited_decisions(rebuilt, market).trace_hash == child_audit.trace_hash
    altered = dict(child_record)
    altered["inherited_parent"] = {
        **child_record["inherited_parent"],
        "source_evidence_hash": "0" * 64,
    }
    with pytest.raises(CycleStateError, match="cannot replay"):
        svc._inherited_from_evidence(None, market, altered, history=[source_record, altered])
