from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.service import DashboardService
from integrations.kis.client import KISAccountSnapshot, KISHolding


class NoOrderFakeKIS:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def health(self) -> dict[str, object]:
        self.calls.append("health")
        return {"status": "ONLINE", "mode": "paper"}

    def account_snapshot(self) -> KISAccountSnapshot:
        self.calls.append("account_snapshot")
        return KISAccountSnapshot(
            account_number="******78-01",
            equity=12345.0,
            cash=10000.0,
            buying_power=9000.0,
            holdings=(KISHolding("QQQ", 1, 345.0, 5.0),),
            captured_at="2026-09-01T12:00:00+00:00",
        )


def test_local_dashboard_refresh_is_paper_read_only_end_to_end(tmp_path: Path) -> None:
    fake = NoOrderFakeKIS()
    client = TestClient(create_app(DashboardService(tmp_path, kis_client=fake)))

    response = client.post("/api/refresh")
    payload = response.json()

    assert response.status_code == 200
    assert fake.calls == ["health", "account_snapshot"]
    assert payload["mode"]["effective_mode"] == "paper"
    assert payload["mode"]["live_enabled"] is False
    assert payload["account"]["equity"] == 12345.0
    assert "authorization" not in response.text.lower()
    assert "appsecret" not in response.text.lower()
    assert "/trading/order" not in response.text
