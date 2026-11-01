"""A16 indicator/chart unified, read-only catalog acceptance gates."""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.service import DashboardService

pytest_plugins = ("tests.dashboard.test_v3_a15_hermetic_p9_lab",)


def test_integrated_catalog_exposes_counts_without_enabling_trading(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))
    base = client.get("/api/features/catalog")
    integrated = client.get("/api/chart-research/catalog")
    assert base.status_code == 200 and integrated.status_code == 200
    body = integrated.json()
    assert body["baseline_feature_count"] == len(base.json()) == 487
    assert body["feature_count"] == 44
    assert body["combined_feature_count"] == 531
    assert body["registration_is_profitability_proof"] is False
    assert body["published_development_overlay"] is False
    assert body["enabled_by_default"] is False
    assert all("canonical_id" in item for item in base.json())
    assert client.get("/api/chart-research/overlay").json()["status"] == "DISABLED"


def test_chart_view_links_baseline_indicators_to_opt_in_pattern_view(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))
    page = client.get("/chart-research")
    assert page.status_code == 200
    html = page.text
    assert 'id="indicatorSearch"' in html
    assert 'id="indicatorList"' in html
    assert 'id="indicatorInfo"' in html
    assert '/api/features/catalog' in html
    assert '등록이 수익성·실사용을 보증하지 않습니다' in html
    assert '지표 시계열은 검증·발행 전 표시하지 않습니다' in html
    assert '/backtest' in html


def test_verified_p9_development_candles_render_in_readonly_chart(
    tmp_path: Path, isolated_original_p9_lab: str,
) -> None:
    """Join *actual* P9 original G94 candles to causal chart, without sealed OOS."""
    import json
    import urllib.request
    from datetime import datetime

    from core.data.contracts import Bar, DataZone, MarketDataSet
    from research.chart_pattern_bridge import overlay_payload

    source = isolated_original_p9_lab + "/api/backtest/runs/LAB_REPLAY_14626d55_G094"

    def fetch(path: str) -> dict[str, object]:
        with urllib.request.urlopen(source + path, timeout=15) as response:
            return json.load(response)

    verified = fetch("/verification")
    assert verified["status"] == "VERIFIED"
    assert verified["zone"] == "development"
    assert verified["candles"] == 1508
    assert verified["orders_enabled"] is False
    from scripts.v3_chart_verified_p9_bridge import collect_verified_p9_overlay

    checked = collect_verified_p9_overlay(isolated_original_p9_lab)
    assert checked["external_verification"]["original_dataset_hash"] == verified["dataset_hash"]
    assert len(checked["series"]["close"]) == 1508
    assert checked["execution_trades"] == []

    rows = []
    for offset in range(0, 1508, 500):
        page = fetch(f"/candles?offset={offset}&limit=500")
        assert page["status"] == "VERIFIED" and page["total"] == 1508
        assert page["offset"] == offset
        rows.extend(page["items"])
    assert len(rows) == 1508
    bars = tuple(
        Bar(
            timestamp=datetime.fromisoformat(item["timestamp"]),
            symbol=item["symbol"],
            open=item["open"], high=item["high"], low=item["low"],
            close=item["close"], volume=item["volume"],
        )
        for item in rows
    )
    market = MarketDataSet("lab-p9-readonly-candles", DataZone.DEVELOPMENT, bars)
    payload = overlay_payload(
        market, patterns=("double_top", "elliott_abc"),
        allow_research=True, data_kind="RESEARCH_DEVELOPMENT",
    )
    assert payload["data_kind"] == "RESEARCH_DEVELOPMENT"
    assert payload["execution_trades"] == []
    assert payload["symbol"] == "QQQ"
    assert len(payload["series"]["close"]) == 1508
    assert all(item["eligible_from"] == item["event_at"] + 1 for item in payload["events"])

    # Only this disposable state directory gets a read-only published overlay.
    target = tmp_path / "chart-research-overlay-a8.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    client = TestClient(create_app(DashboardService(tmp_path)))
    catalog = client.get("/api/chart-research/catalog").json()
    assert catalog["published_development_overlay"] is True
    observed = client.get("/api/chart-research/overlay?enabled=true")
    assert observed.status_code == 200
    assert observed.json()["overlay_hash"] == payload["overlay_hash"]
    assert client.get("/api/chart-research/overlay").json()["status"] == "DISABLED"


def test_p9_bridge_rejects_non_loopback_and_unverified_source() -> None:
    import pytest

    from scripts.v3_chart_verified_p9_bridge import validated_lab_url, verify_trace

    for source in (
        "http://example.com:8096", "https://127.0.0.1:8096",
        "http://127.0.0.1:8096@evil.test", "http://localhost:8096",
        "http://127.0.0.1:8096/private", "http://127.0.0.1:8096?token=foo",
    ):
        with pytest.raises(ValueError):
            validated_lab_url(source)
    assert validated_lab_url("http://127.0.0.1:8096") == "http://127.0.0.1:8096"
    with pytest.raises(ValueError):
        verify_trace({"status": "VERIFIED", "zone": "sealed_oos"})
    with pytest.raises(ValueError):
        verify_trace({"status": "UNVERIFIED", "zone": "development"})
