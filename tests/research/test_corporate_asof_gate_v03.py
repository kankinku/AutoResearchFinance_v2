"""V03 corporate action as-of: fail-closed dates, provenance and adjustments."""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from core.data.contracts import DataZone
from core.data.parquet import ParquetDataProvider
from research.indicator_engine import cli
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.corporate_actions import (
    parse_nasdaq_dividend_snapshot,
    record_nasdaq_dividend_snapshot,
)
from research.indicator_engine.corporate_asof_gate import audit_qqq_corporate_asof
from tests.research.test_qqq_split_residual_audit import _pair


def _inputs():
    raw_market, adjusted = _pair(
        ["2025-03-21", "2025-03-24", "2025-03-25"], [0, 0.71571, 0],
    )
    distribution = {
        "exOrEffDate": "03/24/2025", "recordDate": "03/25/2025",
        "paymentDate": "03/28/2025", "declarationDate": "N/A",
        "amount": "$0.71571", "currency": "USD", "type": "Cash",
    }
    body = json.dumps({
        "data": {"dividends": {"rows": [distribution]}},
        "status": {"rCode": 200},
    }).encode()
    observed = datetime(2026, 10, 15, tzinfo=timezone.utc)
    events = parse_nasdaq_dividend_snapshot(
        body, date(2025, 3, 21), date(2025, 3, 31), observed,
    )
    return raw_market, adjusted, events, body, observed


def test_historical_decision_before_source_capture_blocks_signal_and_payout() -> None:
    raw, _, dividends, _, _ = _inputs()
    report = audit_qqq_corporate_asof(
        raw, dividends, decision_at=datetime(2025, 3, 24, 21, tzinfo=timezone.utc),
    )
    assert report["status"] == "HISTORICAL_DECISION_PRECEDES_SOURCE_CAPTURE"
    assert report["issuer_amounts_matched"] == 1
    assert report["dividends_ex_date_on_or_before_decision"] == 1
    assert report["dividends_paid_on_or_before_decision"] == 0
    assert report["dividends_ex_prior_but_payment_after_decision"] == 1
    assert not report["dividend_snapshot_retrieved_by_decision"]
    assert not report["raw_market_retrieved_by_decision"]
    assert report["dividend_declaration_date_missing_count"] == 1
    assert report["independently_verified_announcement_timestamps"] == 0
    assert report["latest_adjusted_pair_available"] is False
    assert "matching_adjusted_raw_price_pair_missing" in report["blocking_reasons"]
    assert report["historical_point_in_time_verified"] is False
    assert report["broker_executable"] is False
    assert report == audit_qqq_corporate_asof(
        raw, dividends, decision_at=datetime(2025, 3, 24, 21, tzinfo=timezone.utc),
    )


def test_after_retrieval_does_not_establish_old_publication_or_primary_splits() -> None:
    raw, _, dividends, _, _ = _inputs()
    checked = audit_qqq_corporate_asof(
        raw, dividends, decision_at=datetime(2026, 10, 16, tzinfo=timezone.utc),
    )
    assert checked["status"] == "HISTORICAL_PUBLICATION_EVIDENCE_UNATTESTED"
    assert checked["raw_market_retrieved_by_decision"]
    assert checked["dividend_snapshot_retrieved_by_decision"]
    assert checked["dividends_paid_on_or_before_decision"] == 1
    assert checked["historically_verified_split_events"] == 0
    assert checked["split_catalog_evidence_class"] == "SECONDARY_AGGREGATOR_ONLY"
    assert checked["split_events_in_price_window_secondary"] == []
    assert not checked["historical_point_in_time_verified"]
    assert not checked["asof_dividend_signal_approved"]


def test_adjusted_pair_is_only_latest_revision_diagnostic() -> None:
    raw, adjusted, dividends, _, _ = _inputs()
    checked = audit_qqq_corporate_asof(
        raw, dividends,
        decision_at=datetime(2025, 3, 24, 21, tzinfo=timezone.utc),
        adjusted=adjusted,
    )
    assert checked["latest_adjusted_pair_available"]
    assert checked["adjusted_issuer_cash_check"]["matched_events"] == 1
    assert checked["adjusted_split_residual_check"]["cash_events_matched"] == 1
    assert checked["historical_point_in_time_verified"] is False
    assert checked["adjusted_asof_execution_approved"] is False


@pytest.mark.parametrize("change", ["sealed", "source", "wrong_adjusted", "naive"])
def test_dangerous_provenance_and_missing_timezone_fail_closed(change: str) -> None:
    raw, adjusted, dividends, _, _ = _inputs()
    cutoff = datetime(2025, 3, 24, 21, tzinfo=timezone.utc)
    if change == "sealed":
        raw = replace(raw, zone=DataZone.SEALED_OOS)
    if change == "source":
        raw = replace(raw, provenance=replace(raw.provenance, revision_policy="as_of"))
    if change == "wrong_adjusted":
        adjusted = replace(adjusted, provenance=replace(
            adjusted.provenance, source_id="other_vendor",
        ))
    if change == "naive":
        cutoff = cutoff.replace(tzinfo=None)
    with pytest.raises(ResearchCatalogError):
        audit_qqq_corporate_asof(
            raw, dividends, decision_at=cutoff,
            adjusted=adjusted if change == "wrong_adjusted" else None,
        )


def test_cli_replays_actual_dividend_manifest_and_is_readonly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    raw, _, _, payload, stamp = _inputs()
    par = tmp_path / "raw.parquet"
    raw_div = tmp_path / "cash.raw.json"
    manifest = tmp_path / "cash.manifest.json"
    ParquetDataProvider.write(par, raw)
    record_nasdaq_dividend_snapshot(
        payload, date(2025, 3, 21), date(2025, 3, 31), stamp,
        raw_div, manifest,
    )
    command = [
        "indicator-research", "audit-qqq-corporate-asof",
        "--raw-parquet", str(par),
        "--dividend-raw", str(raw_div),
        "--dividend-manifest", str(manifest),
        "--decision-at", "2025-03-24T21:00:00+00:00",
    ]
    monkeypatch.setattr(sys, "argv", command)
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["issuer_amounts_matched"] == 1
    assert result["historical_point_in_time_verified"] is False
    assert result["broker_executable"] is False
    assert raw_div.exists() and manifest.exists()
    raw_div.write_bytes(b"LEAK MY SECRET")
    assert cli.main() == 2
    refused = json.loads(capsys.readouterr().out)
    assert refused["status"] == "CORPORATE_ASOF_AUDIT_REJECTED"
    assert "LEAK MY SECRET" not in json.dumps(refused)
    assert refused["broker_executable"] is False
