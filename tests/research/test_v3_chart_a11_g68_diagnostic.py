"""A11 proven provenance/control limits. Real ledger is always snapshotted.

This is a development-only, scripted measurement, not a complete A11/GPT
generation or independent PIT/OOS benchmark. Locked B4 is intentionally red.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import scripts.v3_chart_a11_g68_preregistered as a11
from core.backtest.engine import _feature_values
from core.data.contracts import Bar, DataZone, MarketDataSet
from core.integrity.hashes import content_hash
from strategy_ir.schema import StrategyIR

PREREG = Path("docs/operations/quant-v3-chart-A11-preregistration-20261029.json")
REPORT = Path("docs/operations/quant-v3-chart-A11-G68-diagnostic-results-20261029.json")


def test_A11_preregistered_policy_cannot_be_modified_after_result(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    frozen = json.loads(PREREG.read_text())
    assert (
        content_hash({k: v for k, v in frozen.items() if k != "freeze_hash"})
        == frozen["freeze_hash"]
    )
    assert frozen["source_generation"] == 68
    assert frozen["market_zone"] == "DEVELOPMENT_NON_PIT"
    assert frozen["market_bars"] == 1508
    assert frozen["model_calls"] == 0
    assert frozen["candidates_per_arm"] == 1
    assert frozen["maximum_arms"] == len(frozen["arms"]) == 6
    assert frozen["parent_strategy_sha"] == (
        "12be5bc19a1aaff9d70fd527e315a3e0a62f7bd7b6854d4addf4272f3453306b"
    )
    changed = dict(frozen)
    changed["seed"] = 9999
    path = tmp_path / "altered-prereg.json"
    path.write_text(json.dumps(changed))
    monkeypatch.setattr(a11, "PREREG", path)
    with pytest.raises(ValueError, match="preregistered"):
        a11.read_prereg()


def test_G68_actual_five_arm_costed_results_and_B4_failure_are_unambiguous() -> None:
    report = json.loads(REPORT.read_text())
    frozen = json.loads(PREREG.read_text())
    assert report["preregistration_hash"] == frozen["freeze_hash"]
    assert report["scope"] == "A11_PHASE1_SCRIPTED_DEVELOPMENT_NOT_AUTONOMOUS_GPT"
    assert report["arm_count"] == 6
    assert report["valid_costed_arm_count"] == 5
    assert report["blocked_arm_count"] == 1
    assert report["all_preregistered_arms_completed"] is False
    assert report["real_G68_parent_audited"] is True
    assert report["independent_OOS_accessed"] is False
    assert report["gpt_calls_performed"] == 0
    assert report["model_generated_candidates"] == 0
    assert report["release_authorized"] is False
    assert report["alpha_improvement_proved"] is False
    assert report["statistical_significance_established"] is False
    assert report["original_ledger_modified"] is False
    assert report["no_new_counted_generations"] is True
    assert report["parent_source"]["parent_dataset_hash"] == frozen["dataset_sha"]
    assert len({r["strategy_sha"] for r in report["candidate_arms"] if r.get("strategy_sha")}) == 5
    arms = {r["arm"]: r for r in report["candidate_arms"]}
    assert list(arms) == [arm["id"] for arm in frozen["arms"]]
    assert all(row["candidate_budget"] == 1 for row in arms.values())
    parent = arms["B0_PARENT"]
    assert parent["total_return"] == pytest.approx(0.6067529662408822)
    assert parent["closed_trades"] == 35
    assert parent["trading_costs"] > 0
    assert set(parent["development_calendar_year_returns"]) == {
        "2020",
        "2021",
        "2022",
        "2023",
        "2024",
        "2025",
    }
    assert report["QQQ_same_snapshot_price_only_reference"] > 0.0
    assert all(
        "delta_vs_QQQ_price_only_pp" in row
        for row in arms.values()
        if row["counted_as_valid_evaluation"]
    )
    assert arms["B1_CLASSICAL"]["closed_trades"] == 23
    assert arms["B1_CLASSICAL"]["max_drawdown"] < parent["max_drawdown"]
    assert arms["B1_CLASSICAL"]["total_return"] < parent["total_return"]
    assert arms["B40_PINNED"]["closed_trades"] == 35
    assert arms["B40_PINNED"]["total_return"] < parent["total_return"]
    assert arms["B2_ELLIOTT"]["closed_trades"] == 0
    assert arms["B3_COMBINED"]["closed_trades"] == 0
    assert all(
        row["total_return"] <= parent["total_return"]
        for row in arms.values()
        if row["counted_as_valid_evaluation"]
    )
    invalid = arms["B4_DELAYED_CONTROL"]
    assert invalid["status"] == "BLOCKED_DOUBLE_LAG_PROVENANCE"
    assert invalid["research_feature_ref_lag_bars"] == 35
    assert invalid["counted_as_valid_evaluation"] is False
    assert "valid close decision" in invalid["reason"]


def test_duplicate_lag_is_a_real_canonical_boundary_bug_not_alpha() -> None:
    """Inherited compiler prelags, but the core engine re-applies reference lag."""
    observed = [
        Bar(
            timestamp=datetime(2021, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
            symbol="ZZZ",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=10.0,
        )
        for i in range(12)
    ]
    market = MarketDataSet(
        version="synthetic-timing-negative",
        zone=DataZone.DEVELOPMENT,
        bars=tuple(observed),
    )
    strategy = StrategyIR.model_validate(
        {
            "schema_version": 1,
            "id": "a11-lag-provenance-negative",
            "family": "a11_test",
            "generation": 0,
            "indicators": {"unused_sma": {"type": "SMA", "period": 2}},
            "features": {"a": {"feature_id": "synthetic-not-registered", "lag_bars": 3}},
            "entry": {
                "logic": "AND",
                "conditions": [{"op": "greater_than", "left": "a", "value": 0}],
            },
            "exit": {"logic": "OR", "conditions": [{"op": "less_equal", "left": "a", "value": 0}]},
            "risk": {"stop_loss_pct": 0.0, "take_profit_pct": 0.0},
        }
    )
    # The research inherited binder has already applied lag=3 to the
    # source event at index 2: this should be available at index 5.
    prelagged = (None, None, None, None, None, 1.0) + (0.0,) * 6
    executed = _feature_values(market, strategy, {"a": prelagged}, None, None)
    assert len(executed["a"]) == 12
    assert executed["a"][5] is None
    assert executed["a"][8] == 1.0  # erroneous second lag, 6 bars instead of 3
    assert executed["a"] != list(prelagged)


def test_A11_original_evidence_preserved_and_five_arms_replay_after_A12() -> None:
    needed = ("cycles.sqlite", "gateway.sqlite", "catalog-s6-v2.sqlite")
    if (
        not all((a11.ORIGINAL / f).is_file() for f in needed)
        or not (a11.SOURCE / "session-id.txt").is_file()
    ):
        pytest.skip("G452 source checkpoint is an intentionally external, non-CI data fixture")
    reported = json.loads(REPORT.read_text())
    replayed = a11.run_a11(save=False)
    # The historical 5+1 failure must not be overwritten after A12 repairs
    # the execution boundary. Only B4's post-fix result differs.
    for key in ("preregistration_hash", "arm_count", "parent_source"):
        assert replayed[key] == reported[key]
    assert reported["valid_costed_arm_count"] == 5
    assert reported["blocked_arm_count"] == 1
    assert replayed["valid_costed_arm_count"] == 6
    assert replayed["blocked_arm_count"] == 0
    old = {arm["arm"]: arm for arm in reported["candidate_arms"]}
    new = {arm["arm"]: arm for arm in replayed["candidate_arms"]}
    for name in ("B0_PARENT", "B1_CLASSICAL", "B2_ELLIOTT", "B3_COMBINED", "B40_PINNED"):
        assert new[name] == old[name]
    assert old["B4_DELAYED_CONTROL"]["status"] == "BLOCKED_DOUBLE_LAG_PROVENANCE"
    assert new["B4_DELAYED_CONTROL"]["status"] == "VALID_COSTED_DEVELOPMENT_REPLAY"
