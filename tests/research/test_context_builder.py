from __future__ import annotations

from research.llm.context_builder import build_context, should_call_llm


def test_context_builder_is_compact_and_excludes_raw_or_sealed_data() -> None:
    context = build_context(
        generation=3,
        champion={"id": "S1", "score": 0.7},
        frontier=[{"id": "S2", "family": "trend"}],
        observations=[{"parameter": "rsi", "value": 34, "score": 0.8}],
        raw_market_rows=[{"close": 100}],
        sealed_oos=[{"close": 200}],
    )

    assert context["generation"] == 3
    assert "raw_market_rows" not in context
    assert "sealed_oos" not in context
    assert "close" not in str(context)


def test_llm_trigger_skips_when_local_improvement_is_ongoing() -> None:
    assert should_call_llm(
        generation_start=True, plateau=False, new_family=False, new_primitive=False
    )
    assert should_call_llm(
        generation_start=False, plateau=True, new_family=False, new_primitive=False
    )
    assert not should_call_llm(
        generation_start=False, plateau=False, new_family=False, new_primitive=False
    )


def test_context_builder_can_expose_registry_catalog_without_raw_market_data() -> None:
    context = build_context(
        generation=2,
        champion=None,
        frontier=[],
        observations=[],
        feature_catalog=[{"name": "vix_percentile", "family": "macro"}],
        raw_market_rows=[{"close": 123}],
    )

    assert context["feature_catalog"] == [{"name": "vix_percentile", "family": "macro"}]
    assert "raw_market_rows" not in context


def test_context_builder_preserves_indicator_selection_contract_fields() -> None:
    context = build_context(
        generation=1,
        champion=None,
        frontier=[],
        observations=[],
        feature_catalog=[
            {
                "name": "us10y_weekly_rsi",
                "canonical_id": "canonical-rsi",
                "inputs": ["US10Y.close"],
                "timeframe": "1w",
                "supported_timeframes": ["1d", "1w"],
                "status": "REGISTERED",
                "implementation_hash": "impl-hash",
            }
        ],
    )

    feature = context["feature_catalog"][0]
    assert feature["canonical_id"] == "canonical-rsi"
    assert feature["inputs"] == ["US10Y.close"]
    assert feature["supported_timeframes"] == ["1d", "1w"]
    assert feature["implementation_hash"] == "impl-hash"
