"""Actual provider metadata vintages are unavailable; synthetic controls test fail-closed."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.databento_cutover_audit import (
    compare_condition_vintages,
    preserve_condition_snapshot,
)

EARLY = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
LATER = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
START, END = date(2020, 1, 2), date(2020, 1, 3)


def _conditions(*, revised: bool = False) -> bytes:
    rows = [
        {"date": "2020-01-02", "condition": "available",
         "last_modified_date": "2026-09-30"},
        {"date": "2020-01-03", "condition": "available",
         "last_modified_date": "2026-10-14" if revised else "2026-09-30"},
    ]
    return json.dumps(rows, sort_keys=True).encode("utf-8")


def _save(root: Path, when: datetime, *, preview: bool = False,
          revised: bool = False):
    return preserve_condition_snapshot(
        root, raw_conditions=_conditions(revised=revised),
        environment="preview" if preview else "production",
        start=START, end=END, captured_at=when,
    )


def test_two_archived_conditions_detect_modified_dates_without_pit(tmp_path: Path):
    first = _save(tmp_path, EARLY)
    second = _save(tmp_path, LATER, revised=True)
    result = compare_condition_vintages(first, second)
    assert result.status == "CONDITION_REVISIONS_OBSERVED"
    assert result.compared_days == 2
    assert result.changed_dates == ("2020-01-03",)
    assert result.changed_days == 1
    assert result.environment_pair == "production→production"
    assert result.source_bytes_reverified is True
    assert result.market_packet_revisions_verified is False
    assert result.historical_pit_verified is False
    assert result.broker_executable is False
    assert result.pair_hash


def test_preview_not_mislabeled_as_production_cutover(tmp_path: Path):
    first = _save(tmp_path, EARLY)
    preview = _save(tmp_path, LATER + timedelta(minutes=1),
                    preview=True, revised=True)
    result = compare_condition_vintages(first, preview)
    assert result.status == "CONDITION_REVISIONS_OBSERVED"
    assert result.environment_pair == "production→preview"
    assert result.post_cutover_production_verified is False
    assert result.historical_pit_verified is False


def test_no_conditions_changed_does_not_prove_itch_bytes_unchanged(tmp_path: Path):
    first = _save(tmp_path, EARLY)
    second = _save(tmp_path, LATER)
    result = compare_condition_vintages(first, second)
    assert result.status == "CONDITION_METADATA_UNCHANGED"
    assert result.changed_days == 0
    assert result.market_packet_revisions_verified is False
    assert not result.historical_pit_verified


@pytest.mark.parametrize("failure", ["tamper", "missing", "duplicate", "scope", "out_of_order"])
def test_bad_vintage_pair_is_refused(tmp_path: Path, failure: str):
    first = _save(tmp_path, EARLY)
    if failure == "duplicate":
        with pytest.raises(ResearchCatalogError, match="exists"):
            _save(tmp_path, EARLY)
        return
    second = _save(tmp_path, LATER)
    if failure == "tamper":
        (second / "conditions.json").write_bytes(b"{}")
    elif failure == "missing":
        (second / "conditions.json").unlink()
    elif failure == "scope":
        other = preserve_condition_snapshot(
            tmp_path, raw_conditions=_conditions(),
            environment="production",
            start=date(2020, 1, 1), end=END,
            captured_at=LATER + timedelta(minutes=1),
        )
        second = other
    elif failure == "out_of_order":
        first, second = second, first
    with pytest.raises(ResearchCatalogError):
        compare_condition_vintages(first, second)


@pytest.mark.parametrize("raw", [
    b'{"status":"ok"}',
    b'[{"date":"2020-01-02","condition":"available","last_modified_date":"2026-09-30"}]',
    b'[{"date":"2020-01-02","condition":"available","last_modified_date":"2026-09-30"},'
    b'{"date":"2020-01-02","condition":"available","last_modified_date":"2026-09-30"}]',
])
def test_bad_provider_condition_payload_is_rejected(tmp_path: Path, raw: bytes):
    with pytest.raises(ResearchCatalogError, match="condition"):
        preserve_condition_snapshot(
            tmp_path, raw_conditions=raw, environment="production",
            start=START, end=END, captured_at=EARLY,
        )


def test_offline_cli_report_and_unavailable_evidence(tmp_path: Path, monkeypatch, capsys):
    import sys

    from research.indicator_engine.cli import main
    a = _save(tmp_path, EARLY)
    b = _save(tmp_path, LATER, revised=True)
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "compare-databento-condition-vintages",
        "--earlier", str(a), "--later", str(b),
    ])
    assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["changed_days"] == 1
    assert result["historical_pit_verified"] is False
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "compare-databento-condition-vintages",
        "--earlier", str(tmp_path / "missing"), "--later", str(b),
    ])
    assert main() == 2
    failure = json.loads(capsys.readouterr().out)
    assert failure["status"] == "CONDITION_VINTAGE_UNVERIFIABLE"
    assert failure["broker_executable"] is False



def test_backdated_capture_cannot_claim_future_modified_dataset(tmp_path: Path):
    with pytest.raises(ResearchCatalogError, match="condition"):
        preserve_condition_snapshot(
            tmp_path, raw_conditions=_conditions(revised=True),
            environment="production", start=START, end=END,
            captured_at=EARLY,
        )


def test_untrusted_future_or_naive_capture_timestamp_fails_closed(tmp_path: Path):
    with pytest.raises(ResearchCatalogError, match="future"):
        preserve_condition_snapshot(
            tmp_path, raw_conditions=_conditions(), environment="production",
            start=START, end=END, captured_at=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
    with pytest.raises(ResearchCatalogError, match="timezone"):
        preserve_condition_snapshot(
            tmp_path, raw_conditions=_conditions(), environment="production",
            start=START, end=END, captured_at=datetime(2026, 10, 14),
        )


def test_preview_and_production_are_distinct_and_source_only(tmp_path: Path):
    first = _save(tmp_path, EARLY, preview=True)
    later = _save(tmp_path, LATER)
    checked = compare_condition_vintages(first, later)
    assert checked.environment_pair == "preview→production"
    assert checked.post_cutover_production_verified is False
    assert checked.market_packet_revisions_verified is False
