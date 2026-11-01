"""A8 read-only chart dashboard research view, defaults off and digest verified."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from core.integrity.hashes import content_hash
from dashboard.app import create_app
from dashboard.service import DashboardService
from research.chart_pattern_bridge import overlay_payload
from tests.core.test_v3_chart_a8_optin_feature_bridge import long_sample


def test_research_catalog_is_opt_in_without_deleting_default_catalog(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))
    index = client.get("/api/features/catalog")
    assert index.status_code == 200
    extra = client.get("/api/chart-research/catalog")
    assert extra.status_code == 200
    body = extra.json()
    assert body["enabled_by_default"] is False
    assert body["research_only"] is True
    assert body["feature_count"] == 44
    assert len(body["patterns"]) == 12
    assert all(x["implementation_hash"] for x in body["features"])


def test_research_dashboard_is_disabled_until_explicitly_requested(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))
    off = client.get("/api/chart-research/overlay")
    assert off.status_code == 200 and off.json()["status"] == "DISABLED"
    none = client.get("/api/chart-research/overlay?enabled=true")
    assert none.status_code == 200 and none.json()["status"] == "NOT_PUBLISHED"
    page = client.get("/chart-research")
    assert page.status_code == 200
    assert "chart-research" in page.text


def test_readonly_published_overlay_rejects_tampering_or_sealed_markers(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))
    data = overlay_payload(long_sample(), patterns=("double_top",), allow_research=True)
    storage = tmp_path / "chart-research-overlay-a8.json"
    storage.write_text(json.dumps(data), encoding="utf8")
    live = client.get("/api/chart-research/overlay?enabled=true")
    assert live.status_code == 200
    assert live.json()["overlay_hash"] == data["overlay_hash"]
    data["events"][0]["stage"] = "HACKED"
    storage.write_text(json.dumps(data), encoding="utf8")
    compromised = client.get("/api/chart-research/overlay?enabled=true")
    assert compromised.status_code == 409
    assert compromised.json()["status"] == "INTEGRITY_ERROR"
    data["source"] = "SEALED_OOS"
    data["overlay_hash"] = content_hash({k: v for k, v in data.items() if k != "overlay_hash"})
    storage.write_text(json.dumps(data), encoding="utf8")
    refused = client.get("/api/chart-research/overlay?enabled=true")
    assert refused.status_code == 403


def test_demo_route_is_labeled_synthetic_and_has_no_trade_markers(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))
    body = client.get("/api/chart-research/overlay?enabled=true&demo=true")
    assert body.status_code == 200, body.text
    payload = body.json()
    assert payload["data_kind"] == "SYNTHETIC"
    assert payload["source"] == "DEVELOPMENT_ONLY"
    assert payload["execution_trades"] == []
    assert all(x["known_at"] >= x["last_pivot_index"] for x in payload["events"])
