"""Independent benchmark and PIT evidence gates never authorize promotions."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet, MarketSourceProvenance
from research.indicator_engine.benchmark_pit import (
    BarReleaseEvidence,
    audit_pit_metadata,
    compare_independent_qqq,
)
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.risk_replay import AcademicRiskReplayResult

START = datetime(2021, 1, 4, 21, tzinfo=timezone.utc)


def _dataset(
    source: str,
    *,
    revision: str = "latest",
    adjustment: str = "raw",
    delta: float = 0.0,
    zone: DataZone = DataZone.DEVELOPMENT,
) -> MarketDataSet:
    bars = tuple(
        Bar(
            timestamp=START + timedelta(days=i),
            symbol="QQQ",
            open=100.0 + 5 * i + delta,
            high=101.0 + 5 * i + delta,
            low=99.0 + 5 * i + delta,
            close=100.5 + 5 * i + delta,
            volume=10000,
        )
        for i in range(3)
    )
    provenance = MarketSourceProvenance(
        source_id=source,
        retrieved_at=START + timedelta(days=30),
        revision_policy=revision,
        universe_policy="single_symbol",
        corporate_action_policy=adjustment,
        corporate_action_reference="archive:v1" if adjustment != "raw" else None,
        includes_delisted=False,
    )
    return MarketDataSet("fixture", zone, bars, provenance=provenance)


def _replay(data: MarketDataSet) -> AcademicRiskReplayResult:
    return AcademicRiskReplayResult(
        dataset_hash=data.dataset_hash,
        hypothesis_hash="hypothesis",
        replay_hash="replay",
        model_hash="model",
        equity_hash="equity",
        initial_cash=10000.0,
        final_equity=10000.0,
        equity_curve=(10000.0, 10000.0, 10000.0),
        fractions_at_close=(0.0, 0.0, 0.0),
        target_fractions_at_open=(0.0, 0.0, 0.0),
        trades=(),
        trades_count=0,
        total_paid_costs=0.0,
    )


def _releases(data: MarketDataSet):
    observations = tuple(
        BarReleaseEvidence(
            bar_timestamp=b.timestamp,
            price_available_at=b.timestamp + timedelta(minutes=1),
            vintage_captured_at=b.timestamp + timedelta(minutes=2),
            vintage_id=f"archive-{i}",
        )
        for i, b in enumerate(data.bars)
    )
    sessions = tuple(b.timestamp - timedelta(hours=6, minutes=30) for b in data.bars)
    return observations, sessions


def test_independent_qqq_is_costed_and_does_not_claim_alpha() -> None:
    primary = _dataset("provider-A")
    independent = _dataset("provider-B", delta=0.1)
    replay = _replay(primary)
    first = compare_independent_qqq(replay, primary, independent)
    second = compare_independent_qqq(replay, primary, independent)
    assert first == second
    assert first.benchmark_buy_cost > 0
    assert first.benchmark_final_equity > replay.final_equity
    assert first.benchmark_total_return > 0
    assert first.strategy_total_return == 0
    assert first.return_spread_percentage_points < 0
    assert first.status == "NON_PIT_DEVELOPMENT_COMPARISON"
    assert first.independently_verified_benchmark is False
    assert first.verified_alpha is False
    assert first.candidate_promotable is False
    assert first.broker_executable is False
    assert first.out_of_sample_approved is False


def test_rejects_self_benchmark_forged_replay_and_misaligned_data() -> None:
    primary = _dataset("provider-A")
    alternative = _dataset("provider-B", delta=0.2)
    report = _replay(primary)
    with pytest.raises(ResearchCatalogError, match="independent"):
        compare_independent_qqq(report, primary, primary)
    with pytest.raises(ResearchCatalogError, match="independent"):
        compare_independent_qqq(report, primary, _dataset("provider-A", delta=0.2))
    with pytest.raises(ResearchCatalogError, match="bound to different"):
        compare_independent_qqq(replace(report, dataset_hash="forged"), primary, alternative)
    with pytest.raises(ResearchCatalogError, match="timestamps"):
        shifted = tuple(
            replace(bar, timestamp=bar.timestamp + timedelta(hours=1))
            for bar in alternative.bars
        )
        compare_independent_qqq(
            report, primary, replace(alternative, bars=shifted),
        )
    with pytest.raises(ResearchCatalogError, match="adjustment"):
        compare_independent_qqq(
            report, primary, _dataset("provider-B", adjustment="split_adjusted"),
        )
    with pytest.raises(ResearchCatalogError, match="development-only"):
        compare_independent_qqq(report, primary, replace(alternative, zone=DataZone.SEALED_OOS))
    with pytest.raises(ResearchCatalogError, match="equity"):
        compare_independent_qqq(
            replace(report, final_equity=float("nan")), primary, alternative,
        )


def test_asof_pit_audit_only_accepts_pre_open_archived_vintages() -> None:
    dataset = _dataset("archive-A", revision="as_of")
    releases, sessions = _releases(dataset)
    audit = audit_pit_metadata(dataset, releases, sessions)
    assert audit.examined_bars == 3
    assert audit.dataset_hash == dataset.dataset_hash
    assert audit.status == "METADATA_CONSISTENT_NOT_CERTIFIED"
    assert not audit.independently_certified
    assert audit == audit_pit_metadata(dataset, releases, sessions)
    with pytest.raises(ResearchCatalogError, match="historical as-of"):
        audit_pit_metadata(_dataset("latest-A"), releases, sessions)
    late_release = list(releases)
    late_release[0] = replace(
        late_release[0], price_available_at=sessions[1] + timedelta(minutes=1),
        vintage_captured_at=sessions[1] + timedelta(minutes=2),
    )
    with pytest.raises(ResearchCatalogError, match="unavailable"):
        audit_pit_metadata(dataset, tuple(late_release), sessions)
    late_vintage = list(releases)
    late_vintage[0] = replace(
        late_vintage[0], vintage_captured_at=sessions[1] + timedelta(minutes=1),
    )
    with pytest.raises(ResearchCatalogError, match="not captured"):
        audit_pit_metadata(dataset, tuple(late_vintage), sessions)
    with pytest.raises(ResearchCatalogError, match="alignment"):
        audit_pit_metadata(dataset, (releases[1], releases[0], releases[2]), sessions)


def test_pit_audits_are_source_bound_and_still_not_certification() -> None:
    primary = _dataset("archived-A", revision="as_of")
    benchmark = _dataset("archived-B", revision="as_of", delta=0.2)
    evidence1, opens1 = _releases(primary)
    evidence2, opens2 = _releases(benchmark)
    audit1 = audit_pit_metadata(primary, evidence1, opens1)
    audit2 = audit_pit_metadata(benchmark, evidence2, opens2)
    comparison = compare_independent_qqq(
        _replay(primary), primary, benchmark,
        strategy_audit=audit1, benchmark_audit=audit2,
    )
    assert comparison.strategy_pit_audit_hash == audit1.evidence_hash
    assert comparison.benchmark_pit_audit_hash == audit2.evidence_hash
    assert not comparison.verified_alpha
    assert not comparison.independently_verified_benchmark
    with pytest.raises(ResearchCatalogError, match="asymmetric"):
        compare_independent_qqq(
            _replay(primary), primary, benchmark, strategy_audit=audit1,
        )
    with pytest.raises(ResearchCatalogError, match="do not match"):
        compare_independent_qqq(
            _replay(primary), primary, benchmark,
            strategy_audit=replace(audit1, dataset_hash="f" * 64),
            benchmark_audit=audit2,
        )


def test_invalid_metadata_timestamps_and_action_lineage_fail_closed() -> None:
    dataset = _dataset("archive-A", revision="as_of")
    evidence, sessions = _releases(dataset)
    with pytest.raises(ResearchCatalogError, match="opens"):
        audit_pit_metadata(dataset, evidence, sessions[:-1])
    with pytest.raises(ResearchCatalogError, match="precede completed"):
        audit_pit_metadata(dataset, evidence, (dataset.bars[0].timestamp, *sessions[1:]))
    with pytest.raises(ValueError, match="timezone"):
        BarReleaseEvidence(
            dataset.bars[0].timestamp, datetime(2021, 1, 4),
            dataset.bars[1].timestamp, "archive",
        )
    raw_provenance = dataset.provenance
    assert raw_provenance is not None
    unsupported = replace(
        raw_provenance,
        corporate_action_policy="split_adjusted",
        corporate_action_reference=None,
    )
    with pytest.raises(ResearchCatalogError, match="corporate-action lineage"):
        audit_pit_metadata(replace(dataset, provenance=unsupported), evidence, sessions)
