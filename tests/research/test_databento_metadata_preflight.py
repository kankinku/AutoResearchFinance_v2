"""Databento authenticated METADATA preflight never purchases, downloads or certifies PIT."""
from __future__ import annotations

import json

import httpx
import pytest

from research.indicator_engine.databento_metadata_preflight import probe_qqq_xnas_metadata


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)


def _metadata(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    assert request.url.host == "hist.databento.com"
    assert request.url.path.startswith("/v0/metadata.")
    assert request.headers.get("authorization", "").startswith("Basic ")
    assert "top-secret" not in str(request.url)
    if request.url.path.endswith("get_dataset_range"):
        assert request.url.params["dataset"] == "XNAS.ITCH"
        return httpx.Response(200, json={
            "start": "2018-05-01T00:00:00Z",
            "end": "2026-10-15T00:00:00Z",
            "schema": {"trades": {
                "start": "2018-05-01T00:00:00Z",
                "end": "2026-10-15T00:00:00Z",
            }},
        })
    if request.url.path.endswith("get_cost"):
        assert request.url.params["dataset"] == "XNAS.ITCH"
        assert request.url.params["symbols"] == "QQQ"
        assert request.url.params["schema"] == "trades"
        assert request.url.params["start"] == "2020-01-02T00:00:00Z"
        assert request.url.params["end"] == "2026-01-01T00:00:00Z"
        return httpx.Response(200, json=28.75)
    if request.url.path.endswith("get_dataset_condition"):
        return httpx.Response(200, json=[
            {"date": "2020-01-02", "condition": "available",
             "last_modified_date": "2026-09-30"},
            {"date": "2020-01-03", "condition": "available",
             "last_modified_date": "2026-09-30"},
        ])
    raise AssertionError("unexpected, potentially billable endpoint")


def test_no_key_no_requests_and_no_false_cost():
    def fail(_request):
        raise AssertionError("should never make HTTP request")
    with _client(fail) as client:
        result = probe_qqq_xnas_metadata(api_key=None, client=client)
    assert result.status == "AUTH_REQUIRED"
    assert result.quoted_cost_usd is None
    assert result.schema_coverage_verified is False
    assert result.historical_pit_verified is False
    assert result.broker_executable is False


def test_authed_metadata_yields_quote_not_pit_and_revisions_warning():
    with _client(_metadata) as client:
        result = probe_qqq_xnas_metadata(api_key="top-secret", client=client)
    assert result.status == "METADATA_QUOTED_NOT_PIT"
    assert result.quoted_cost_usd == 28.75
    assert result.schema_coverage_verified is True
    assert result.condition_records_inspected == 2
    assert result.condition_recently_modified == 2
    assert result.historical_pit_verified is False
    assert result.publisher_release_authentication_verified is False
    assert result.licensing_verified is False
    assert result.broker_executable is False
    assert "2026-10-31" in result.record()["retroactive_revision_alert"]
    assert "top-secret" not in json.dumps(result.record())


@pytest.mark.parametrize("issue", ["bad_range", "bad_cost", "degraded", "forbidden"])
def test_missing_coverage_expensive_or_bad_metadata_never_approves(issue):
    def handler(request):
        if issue == "forbidden":
            return httpx.Response(403, json={"message": "not entitled"})
        response = _metadata(request)
        if issue == "bad_range" and request.url.path.endswith("get_dataset_range"):
            response = httpx.Response(200, json={
                "start": "2024-01-01T00:00:00Z",
                "end": "2026-10-15T00:00:00Z",
                "schema": {"trades": {
                    "start": "2024-01-01T00:00:00Z",
                    "end": "2026-10-15T00:00:00Z",
                }},
            })
        if issue == "bad_cost" and request.url.path.endswith("get_cost"):
            return httpx.Response(200, json=-3)
        if issue == "degraded" and request.url.path.endswith("get_dataset_condition"):
            return httpx.Response(200, json=[
                {"date": "2020-01-02", "condition": "degraded",
                 "last_modified_date": "2026-09-30"},
            ])
        return response
    with _client(handler) as client:
        result = probe_qqq_xnas_metadata(api_key="top-secret", client=client)
    assert result.status != "METADATA_QUOTED_NOT_PIT"
    assert result.historical_pit_verified is False
    assert result.broker_executable is False
    assert "top-secret" not in json.dumps(result.record())


def test_metadata_transport_failure_never_exposes_auth_header():
    def fail(request):
        raise httpx.ReadTimeout("simulated timeout", request=request)
    with _client(fail) as client:
        result = probe_qqq_xnas_metadata(api_key="top-secret", client=client)
    assert result.status == "METADATA_UNAVAILABLE"
    assert result.quoted_cost_usd is None
    assert "top-secret" not in json.dumps(result.record())


def test_cli_without_key_is_dry_and_reports_access_required(monkeypatch, capsys):
    import sys

    from research.indicator_engine.cli import main

    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    monkeypatch.setattr(sys, "argv", [
        "research-cli", "probe-databento-qqq-metadata",
    ])
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "AUTH_REQUIRED"
    assert report["historical_pit_verified"] is False
    assert report["quoted_cost_usd"] is None
