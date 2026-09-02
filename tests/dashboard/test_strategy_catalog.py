from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import create_app
from dashboard.service import DashboardService


def _write_catalog(state_dir: Path) -> None:
    strategies = state_dir / "strategies"
    strategies.mkdir()
    (strategies / "catalog.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "records": [
                    {
                        "record_id": "one",
                        "status": "NORMALIZED",
                        "source": {"origin": "KIS", "source_path": "preset/golden_cross.py"},
                        "strategy_id": "golden_cross",
                        "strategy_hash": "a" * 64,
                        "semantic_fingerprint": "b" * 64,
                        "duplicate_kind": "NEW",
                        "duplicate_of": None,
                        "reason": "",
                        "profile": {},
                        "strategy": {"id": "golden_cross", "family": "trend"},
                    },
                    {
                        "record_id": "two",
                        "status": "REVIEW_REQUIRED",
                        "source": {"origin": "external", "source_path": "other.py"},
                        "strategy_id": None,
                        "strategy_hash": None,
                        "semantic_fingerprint": None,
                        "duplicate_kind": "NOT_APPLICABLE",
                        "duplicate_of": None,
                        "reason": "dynamic execution is not allowed",
                        "profile": {"detected_constructs": ["python_class"]},
                        "strategy": None,
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_strategy_catalog_returns_normalized_and_review_records_without_secrets(
    tmp_path: Path,
) -> None:
    _write_catalog(tmp_path)
    client = TestClient(create_app(DashboardService(tmp_path)))

    response = client.get("/api/strategies/catalog")

    assert response.status_code == 200
    payload = response.json()
    assert {item["strategy_id"] for item in payload} == {"golden_cross", None}
    assert "api_key" not in response.text.lower()
    assert "app_secret" not in response.text.lower()
