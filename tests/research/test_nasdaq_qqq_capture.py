"""Nasdaq observations must be captured with immutable bytes and remain non-PIT."""

import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from core.data.parquet import ParquetDataProvider
from research.indicator_engine.capture_integrity import verify_nasdaq_capture
from research.indicator_engine.catalog import ResearchCatalogError
from research.indicator_engine.nasdaq_capture import (
    capture_nasdaq_qqq,
    parse_nasdaq_qqq,
)

_START = date(2020, 1, 2)
_END = date(2020, 1, 6)
_CAPTURED = datetime(2026, 10, 14, 4, 20, tzinfo=timezone.utc)


def _body(
    rows: list[dict[str, str]] | None = None,
    *,
    count: int | None = None,
    as_of: str | None = None,
) -> bytes:
    if rows is None:
        rows = [
            {"date": "01/06/2020", "open": "216.00", "high": "219.00",
             "low": "215.00", "close": "218.00", "volume": "30,100,000"},
            {"date": "01/03/2020", "open": "213.30", "high": "215.47",
             "low": "213.28", "close": "214.18", "volume": "27,532,657"},
            {"date": "01/02/2020", "open": "214.40", "high": "216.16",
             "low": "213.98", "close": "216.16", "volume": "31,014,900"},
        ]
    return json.dumps({
        "data": {"symbol": "QQQ", "totalRecords": count if count is not None else len(rows),
                 "tradesTable": {"asOf": as_of, "rows": rows}},
        "status": {"rCode": 200}, "message": None,
    }).encode()


def test_parse_nasdaq_qqq_is_date_labeled_raw_and_non_pit():
    market = parse_nasdaq_qqq(_body(), _START, _END, _CAPTURED)
    assert len(market.bars) == 3
    assert market.bars[0].timestamp == datetime(2020, 1, 2, tzinfo=timezone.utc)
    assert market.bars[0].open == 214.4
    assert market.bars[0].volume == 31_014_900
    assert market.provenance is not None
    assert market.provenance.source_id == "nasdaq-public"
    assert market.provenance.revision_policy == "latest"
    assert market.provenance.corporate_action_policy == "raw"
    assert market.provenance.corporate_action_reference is None


@pytest.mark.parametrize("bad", [
    b"<html>challenge</html>",
    b"{}",
    _body(count=20),
    _body(as_of="2020-01-01"),
    _body(rows=[]),
    _body(rows=[{"date": "01/03/2020", "open": "1e309", "high": "2", "low": "1",
                 "close": "1", "volume": "10"}]),
    _body(rows=[{"date": "01/03/2020", "open": "210", "high": "211", "low": "209",
                 "close": "212", "volume": "10"}]),
])
def test_rejects_invalid_or_incomplete_source_payload(bad: bytes):
    with pytest.raises(ResearchCatalogError):
        parse_nasdaq_qqq(bad, _START, _END, _CAPTURED)


def test_append_only_snapshot_and_manifest_round_trip(tmp_path: Path):
    outfile = tmp_path / "data" / "qqq.parquet"
    rawfile = tmp_path / "state" / "raw.json"
    proof = tmp_path / "state" / "capture.json"
    report = capture_nasdaq_qqq(
        _START, _END, outfile, rawfile, proof,
        fetch_bytes=lambda _: _body(), captured_at=_CAPTURED,
    )
    dataset = ParquetDataProvider.read(outfile)
    evidence = json.loads(proof.read_text())
    assert dataset.dataset_hash == evidence["dataset_hash"]
    assert evidence["raw_sha256"] == hashlib.sha256(rawfile.read_bytes()).hexdigest()
    assert evidence["status"] == "NON_PIT_SOURCE_CAPTURE"
    assert evidence["point_in_time_verified"] is False
    assert evidence["independent_benchmark_verified"] is False
    assert report.dataset_hash == dataset.dataset_hash
    assert report.row_count == 3
    assert verify_nasdaq_capture(outfile, rawfile, proof).dataset_hash == report.dataset_hash
    with pytest.raises(ResearchCatalogError, match="exists"):
        capture_nasdaq_qqq(_START, _END, outfile, rawfile, proof,
                           fetch_bytes=lambda _: _body(), captured_at=_CAPTURED)


def test_no_partial_output_on_transport_error(tmp_path: Path):
    outfile = tmp_path / "qqq.parquet"
    raw = tmp_path / "raw.json"
    proof = tmp_path / "proof.json"

    def broken(_: str) -> bytes:
        raise OSError("blocked remote endpoint")

    with pytest.raises(ResearchCatalogError, match="fetch"):
        capture_nasdaq_qqq(_START, _END, outfile, raw, proof,
                           fetch_bytes=broken, captured_at=_CAPTURED)
    assert not any(p.exists() for p in (outfile, raw, proof))


def test_rejects_wrong_or_excessive_period():
    with pytest.raises(ResearchCatalogError):
        parse_nasdaq_qqq(_body(), date(2025, 1, 1), date(2020, 1, 1), _CAPTURED)
    with pytest.raises(ResearchCatalogError):
        parse_nasdaq_qqq(_body(), date(2010, 1, 1), date(2026, 1, 1), _CAPTURED)


def test_changed_capture_bytes_must_be_rejected(tmp_path: Path):
    outfile = tmp_path / "qqq.parquet"
    raw = tmp_path / "raw.json"
    manifest = tmp_path / "manifest.json"
    capture_nasdaq_qqq(_START, _END, outfile, raw, manifest,
                       fetch_bytes=lambda _: _body(), captured_at=_CAPTURED)
    raw.write_bytes(raw.read_bytes() + b" ")
    with pytest.raises(ResearchCatalogError, match="digest"):
        verify_nasdaq_capture(outfile, raw, manifest)


def test_concurrent_capture_preserves_winning_bundle(tmp_path: Path) -> None:
    """A late loser must not unlink files written after its existence precheck."""
    outfile = tmp_path / "data" / "qqq.parquet"
    rawfile = tmp_path / "state" / "raw.json"
    manifest = tmp_path / "state" / "capture.json"
    winner = None

    def competing_fetch(_: str) -> bytes:
        nonlocal winner
        # The outer capture already passed its initial exists check. This
        # simulates another process finishing the same bundle before the
        # original capture resumes publishing its raw bytes.
        winner = capture_nasdaq_qqq(
            _START, _END, outfile, rawfile, manifest,
            fetch_bytes=lambda _: _body(), captured_at=_CAPTURED,
        )
        return _body()

    with pytest.raises((ResearchCatalogError, FileExistsError), match="exists"):
        capture_nasdaq_qqq(
            _START, _END, outfile, rawfile, manifest,
            fetch_bytes=competing_fetch, captured_at=_CAPTURED,
        )

    assert winner is not None
    assert all(path.is_file() for path in (outfile, rawfile, manifest))
    assert rawfile.read_bytes() == _body()
    assert verify_nasdaq_capture(outfile, rawfile, manifest).dataset_hash == winner.dataset_hash


def _competing_capture_worker(
    paths: tuple[str, str, str], barrier: object, results: object
) -> None:
    from pathlib import Path

    output, raw, manifest = (Path(value) for value in paths)
    try:
        barrier.wait(timeout=20)  # type: ignore[attr-defined]
        report = capture_nasdaq_qqq(
            _START, _END, output, raw, manifest,
            fetch_bytes=lambda _: _body(), captured_at=_CAPTURED,
        )
        results.put(("winner", report.dataset_hash))  # type: ignore[attr-defined]
    except (FileExistsError, ResearchCatalogError) as exc:
        results.put(("collision", str(exc)))  # type: ignore[attr-defined]
    except BaseException as exc:
        results.put(("unexpected", repr(exc)))  # type: ignore[attr-defined]


def test_two_process_capture_contention_retains_one_complete_bundle(
    tmp_path: Path,
) -> None:
    import multiprocessing

    # Spawn avoids forking pytest's already-threaded process.
    context = multiprocessing.get_context("spawn")
    for trial in range(12):
        folder = tmp_path / str(trial)
        paths = (
            folder / "data" / "qqq.parquet",
            folder / "state" / "raw.json",
            folder / "state" / "capture.json",
        )
        barrier = context.Barrier(2)
        queue = context.Queue()
        processes = [
            context.Process(
                target=_competing_capture_worker,
                args=(tuple(str(path) for path in paths), barrier, queue),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        outcomes = [queue.get(timeout=35) for _ in processes]
        for process in processes:
            process.join(timeout=10)
            assert process.exitcode == 0
        assert sorted(kind for kind, _ in outcomes) == ["collision", "winner"]
        assert verify_nasdaq_capture(*paths).dataset_hash == next(
            value for kind, value in outcomes if kind == "winner"
        )
        assert all(path.is_file() for path in paths)
        assert not list(folder.rglob(".nasdaq-capture-*"))
        queue.close()


def test_late_manifest_collision_never_deletes_competitor_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    from research.indicator_engine import nasdaq_capture

    output = tmp_path / "data" / "qqq.parquet"
    raw = tmp_path / "state" / "raw.json"
    manifest = tmp_path / "state" / "capture.json"
    original_link = os.link
    owner_bytes = b"another capture already owns this manifest"

    def competing_manifest(source: str, destination: str) -> None:
        if Path(destination) == manifest:
            manifest.write_bytes(owner_bytes)
        original_link(source, destination)

    monkeypatch.setattr(nasdaq_capture.os, "link", competing_manifest)
    with pytest.raises(FileExistsError):
        capture_nasdaq_qqq(
            _START, _END, output, raw, manifest,
            fetch_bytes=lambda _: _body(), captured_at=_CAPTURED,
        )
    assert manifest.read_bytes() == owner_bytes
    assert not raw.exists() and not output.exists()
    assert not list(tmp_path.rglob(".nasdaq-capture-*"))


def test_parquet_stage_error_does_not_publish_any_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from research.indicator_engine import nasdaq_capture

    output = tmp_path / "data" / "qqq.parquet"
    raw = tmp_path / "state" / "raw.json"
    manifest = tmp_path / "state" / "capture.json"

    def failed_parquet(destination: Path, market: object) -> None:
        destination.write_bytes(b"partial data")
        raise OSError("disk write stopped")

    monkeypatch.setattr(nasdaq_capture.ParquetDataProvider, "write", failed_parquet)
    with pytest.raises(OSError, match="disk write stopped"):
        capture_nasdaq_qqq(
            _START, _END, output, raw, manifest,
            fetch_bytes=lambda _: _body(), captured_at=_CAPTURED,
        )
    assert not any(path.exists() for path in (output, raw, manifest))
    assert not list(tmp_path.rglob(".nasdaq-capture-*"))
