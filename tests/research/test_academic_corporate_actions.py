"""Retrospective cash dividend research must never masquerade as historical PIT."""

import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.data.contracts import Bar, DataZone, MarketDataSet
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.corporate_actions import (
    parse_nasdaq_dividend_snapshot,
    record_nasdaq_dividend_snapshot,
    retrospective_dividend_benchmark,
    verify_dividend_snapshot,
)

STAMP = datetime(2026, 10, 14, 6, 9, tzinfo=timezone.utc)


def _rows():
    return [
        {"exOrEffDate": "01/03/2023", "recordDate": "01/04/2023", "paymentDate": "01/05/2023",
         "declarationDate": "N/A", "amount": "$0.50", "currency": "USD", "type": "Cash"},
        {"exOrEffDate": "01/06/2023", "recordDate": "01/09/2023", "paymentDate": "01/10/2023",
         "declarationDate": "01/05/2023", "amount": "$1.00", "currency": "USD", "type": "Cash"},
    ]


def _raw(rows=None):
    rows = _rows() if rows is None else rows
    return json.dumps({"data": {"dividends": {"asOf": None, "rows": rows}},
                       "status": {"rCode": 200}}).encode()


def _market():
    start = datetime(2023, 1, 2, tzinfo=timezone.utc)
    bars = tuple(Bar(start + timedelta(days=i), "QQQ", 100, 101, 99, 100, 1000)
                 for i in range(12))
    return MarketDataSet("demo", DataZone.DEVELOPMENT, bars)


def test_retrospective_cash_paid_when_pay_date_not_at_ex_date():
    evidence = parse_nasdaq_dividend_snapshot(_raw(), date(2023, 1, 2),
                                               date(2023, 1, 13), STAMP)
    assert len(evidence.events) == 2
    assert evidence.events[0].ex_date == date(2023, 1, 3)
    assert evidence.events[0].pay_date == date(2023, 1, 5)
    assert evidence.events[0].known_at == STAMP
    assert not evidence.historically_tradeable
    assert evidence.missing_declaration_dates == 1
    result = retrospective_dividend_benchmark(_market(), evidence)
    assert result.status == "RETROSPECTIVE_DIVIDEND_SCENARIO_ONLY"
    assert result.payout_count == 2
    assert result.total_cash_distributions > 0
    assert result.price_only_final_equity < result.dividend_cash_final_equity
    assert not result.pit_verified and not result.candidate_promotable
    assert "corporate_split_history_unverified" in result.blockers
    assert "historical_declaration_availability_unverified" in result.blockers
    assert "dividend_latest_revision_not_as_of" in result.blockers


def test_first_day_ex_does_not_credit_dividend_to_new_purchase():
    data = parse_nasdaq_dividend_snapshot(_raw(), date(2023, 1, 2),
                                         date(2023, 1, 13), STAMP)
    original = _market()
    shortened = MarketDataSet("first-ex", DataZone.DEVELOPMENT, original.bars[1:])
    run = retrospective_dividend_benchmark(shortened, data)
    assert run.payout_count == 1


def test_rejects_missing_or_illogical_dividends():
    for bad in (
        _rows() + [_rows()[0]],
        [{**_rows()[0], "paymentDate": "01/02/2023"}],
        [{**_rows()[0], "currency": "CAD"}],
        [{**_rows()[0], "amount": "$NaN"}],
        [{**_rows()[0], "type": "Stock"}],
        [{**_rows()[0], "exOrEffDate": "12/21/2025"}],
        [{**_rows()[0], "declarationDate": "01/11/2023"}],
    ):
        with pytest.raises(ResearchCatalogError):
            parse_nasdaq_dividend_snapshot(_raw(bad), date(2023, 1, 2),
                                          date(2023, 1, 13), STAMP)
    with pytest.raises(ResearchCatalogError):
        parse_nasdaq_dividend_snapshot(b"<html>blocked</html>", date(2023, 1, 2),
                                      date(2023, 1, 13), STAMP)


def test_fail_closed_future_data_use_or_sealed_zone():
    evidence = parse_nasdaq_dividend_snapshot(_raw(), date(2023, 1, 2),
                                              date(2023, 1, 13), STAMP)
    assert evidence.is_available_for_decision(datetime(2023, 1, 9, tzinfo=timezone.utc)) is False
    assert evidence.is_available_for_decision(STAMP) is True
    dataset = _market()
    with pytest.raises(ResearchCatalogError, match="development"):
        retrospective_dividend_benchmark(MarketDataSet("sealed", DataZone.SEALED_OOS,
                                             dataset.bars), evidence)


def test_raw_and_manifest_are_append_only_and_detect_tampering(tmp_path: Path):
    raw = tmp_path / "source.json"
    proof = tmp_path / "manifest.json"
    evidence = record_nasdaq_dividend_snapshot(_raw(), date(2023, 1, 2),
                                                date(2023, 1, 13), STAMP, raw, proof)
    assert evidence.source_sha256 == hashlib.sha256(raw.read_bytes()).hexdigest()
    replay = verify_dividend_snapshot(raw, proof)
    assert replay.snapshot_hash == evidence.snapshot_hash
    with pytest.raises(ResearchCatalogError, match="exists"):
        record_nasdaq_dividend_snapshot(_raw(), date(2023, 1, 2),
                                        date(2023, 1, 13), STAMP, raw, proof)
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(ResearchCatalogError, match="digest"):
        verify_dividend_snapshot(raw, proof)


def test_dividends_after_last_market_day_are_not_fictitious_cash():
    rows = [{**_rows()[0], "paymentDate": "01/20/2023"}]
    evidence = parse_nasdaq_dividend_snapshot(
        _raw(rows), date(2023, 1, 2), date(2023, 1, 13), STAMP
    )
    result = retrospective_dividend_benchmark(_market(), evidence)
    assert result.payout_count == 0
    assert result.total_cash_distributions == 0.0
    assert result.dividend_cash_final_equity == result.price_only_final_equity


def test_manifest_tampering_never_grants_historical_certification(tmp_path: Path):
    raw = tmp_path / "source.json"
    proof = tmp_path / "manifest.json"
    record_nasdaq_dividend_snapshot(_raw(), date(2023, 1, 2),
                                    date(2023, 1, 13), STAMP, raw, proof)
    changed = json.loads(proof.read_text())
    changed["pit_verified"] = True
    proof.write_text(json.dumps(changed))
    with pytest.raises(ResearchCatalogError, match="cannot be verified"):
        verify_dividend_snapshot(raw, proof)
