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
