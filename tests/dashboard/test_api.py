from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.service import DashboardService
from integrations.kis.client import KISAccountSnapshot, KISHolding


class FakeKIS:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.health_calls = 0
        self.account_calls = 0

    def health(self) -> dict[str, str]:
        self.health_calls += 1
        if self.fail:
            raise RuntimeError("response contained secret-like diagnostic")
        return {"status": "ONLINE", "mode": "paper", "checked_at": "2026-09-01T12:00:00+00:00"}

    def account_snapshot(self) -> KISAccountSnapshot:
        self.account_calls += 1
        return KISAccountSnapshot(
            account_number="******78-01",
            equity=10000,
            cash=8000,
            buying_power=7500,
            holdings=(KISHolding("AAPL", 2, 400, 10),),
            captured_at="2026-09-01T12:00:00+00:00",
        )


def test_api_exposes_paper_health_and_sanitized_dashboard(tmp_path: Path) -> None:
    fake = FakeKIS()
    service = DashboardService(tmp_path, kis_client=fake)
    client = TestClient(create_app(service))

    health = client.get("/api/health")
    dashboard = client.get("/api/dashboard")

    assert health.status_code == 200
    assert health.json()["effective_mode"] == "paper"
    assert health.json()["live_enabled"] is False
    assert dashboard.status_code == 200
    assert dashboard.json()["mode"]["safety_status"] == "PAPER_ONLY"
    assert "secret-like" not in dashboard.text


def test_refresh_calls_only_paper_read_only_client_and_persists_account(tmp_path: Path) -> None:
    fake = FakeKIS()
    service = DashboardService(tmp_path, kis_client=fake)
    client = TestClient(create_app(service))

    response = client.post("/api/refresh")

    assert response.status_code == 200
    assert response.json()["account"]["equity"] == 10000
    assert response.json()["account"]["holdings"][0]["symbol"] == "AAPL"
    assert fake.health_calls == 1
    assert fake.account_calls == 1
    assert (tmp_path / "dashboard.json").is_file()


def test_refresh_failure_preserves_previous_snapshot_and_returns_degraded_status(
    tmp_path: Path,
) -> None:
    good = DashboardService(tmp_path, kis_client=FakeKIS())
    good.refresh()
    failing = DashboardService(tmp_path, kis_client=FakeKIS(fail=True))
    client = TestClient(create_app(failing))

    response = client.post("/api/refresh")

    assert response.status_code == 200
    payload = response.json()
    assert payload["account"]["equity"] == 10000
    assert payload["health"]["status"] == "DEGRADED"
    assert payload["health"]["kis_status"] == "OFFLINE"
    assert "KIS_REFRESH_FAILED" in payload["warning_codes"]
    assert "secret-like" not in response.text


def test_feature_catalog_exposes_sanitized_sources_aliases_and_timeframes(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))

    response = client.get("/api/features/catalog")

    assert response.status_code == 200
    item = next(row for row in response.json() if row["canonical_name"] == "rsi")
    assert "relative_strength_index" in item["aliases"]
    assert item["verification_status"] == "REGISTERED"
    assert "1w" in item["supported_timeframes"]
    assert "1mo" in item["supported_timeframes"]
    assert "api_key" not in response.text.lower()
    assert "app_secret" not in response.text.lower()


def test_feature_catalog_includes_optional_macro_and_rate_features(tmp_path: Path) -> None:
    client = TestClient(create_app(DashboardService(tmp_path)))

    response = client.get("/api/features/catalog")

    names = {item["canonical_name"] for item in response.json()}
    assert {"vix_percentile", "us_20y_change", "japan_2y_change", "korea_10y_change"} <= names
