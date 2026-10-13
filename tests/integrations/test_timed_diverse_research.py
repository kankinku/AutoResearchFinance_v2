"""Time-budgeted diverse research plans remain bounded and paper-only."""

from __future__ import annotations

from scripts.run_timed_diverse_research import (
    ORDER,
    build_request,
    domains_for,
)


def _source(*paths: str) -> dict:
    return {
        "strategy_id": "dummy",
        "source_path": "strategies/normalized/dummy.json",
        "family": "trend",
        "numeric_parameter_paths": list(paths),
    }


def test_campaign_picks_ten_distinct_registered_source_ids() -> None:
    assert len(ORDER) == 10
    assert len(set(ORDER)) == 10
    assert {"mean_reversion", "momentum", "golden_cross", "volatility"} <= set(ORDER)


def test_parameter_domains_always_have_distinct_allowed_names_and_values() -> None:
    for paths in (
        (),
        ("indicators.fast.period",),
        ("indicators.sma_fast.period", "indicators.sma_slow.period"),
    ):
        for index in range(10):
            plan = domains_for(_source(*paths), cycle=index, index=index)
            assert 1 <= len(plan) <= 4
            assert len({item["name"] for item in plan}) == len(plan)
            for domain in plan:
                assert 1 <= len(domain["values"]) <= 24
                assert len(set(domain["values"])) == len(domain["values"])
                assert domain["name"].startswith(("indicators.", "risk."))


def test_domain_rotation_explores_indicator_and_risk_differences() -> None:
    golden = _source("indicators.sma_fast.period", "indicators.sma_slow.period")
    first = domains_for(golden, cycle=0, index=0)
    second = domains_for(golden, cycle=1, index=10)
    assert first != second
    assert first[0]["values"] != second[0]["values"]
    assert first[1]["values"] != second[1]["values"]
    assert all(v >= 24 for v in first[1]["values"])


def test_campaign_request_has_no_orders_or_unavailable_benchmark_gate() -> None:
    source = _source("indicators.sma_fast.period", "indicators.sma_slow.period")
    source["strategy_id"] = "golden_cross"
    first = build_request(source, index=0, batch_generations=14, candidates=6)
    later = build_request(source, index=10, batch_generations=14, candidates=6)
    assert first["generations"] == later["generations"] == 14
    assert first["count"] == 6
    assert first["min_annual_trades"] == 5
    assert "min_qqq_cagr_delta" not in first
    assert "series_data_path" not in first
    assert not any("order" in k.lower() for k in first)
    assert first["intent"]["parent_ids"] == ["golden_cross"]
    assert first["intent"]["mode"] == "mixed"
    assert later["intent"]["mode"] == "parameter"
    assert first["seed"] != later["seed"]


def test_wall_deadline_finishes_without_starting_another_batch(tmp_path, monkeypatch) -> None:
    from scripts import run_timed_diverse_research as runner

    class FakeService:
        def __init__(self, **kwargs):
            pass

        def describe_inputs(self):
            return {
                "sources": [
                    {
                        "strategy_id": key,
                        "source_path": "strategies/normalized/" + key + ".json",
                        "family": "synthetic",
                        "numeric_parameter_paths": [],
                    }
                    for key in ORDER
                ],
                "datasets": [{"data_path": runner.DATA_PATH}],
            }

        def preflight(self, request):
            return {"status": "READY"}

        def start(self, request):
            raise AssertionError("deadline must prevent launching a new batch")

    monkeypatch.setattr(runner, "ResearchBatchService", FakeService)
    result = runner.run(
        project_root=tmp_path,
        state_dir=tmp_path / "state",
        duration_seconds=0.01,
        batch_generations=14,
        candidates=6,
        campaign_id="short-deadline",
    )
    assert result["status"] == "COMPLETED_TIME_BUDGET"
    assert result["batches_started"] == 0
    assert result["orders_enabled"] is False
    assert len(result["preflight"]) == 10
    assert not (tmp_path / "state/system/timed-diverse-research/active.lock").exists()
