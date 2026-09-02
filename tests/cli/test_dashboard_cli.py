from __future__ import annotations

import json
from pathlib import Path

import pytest

from cli import main


def test_dashboard_status_is_paper_only(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "dashboard-status",
                "--state-dir",
                str(tmp_path),
                "--env-file",
                str(tmp_path / "missing.env"),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["effective_mode"] == "paper"
    assert payload["live_enabled"] is False
    assert "KIS_CONFIG_MISSING" in payload["warning_codes"]


def test_dashboard_refresh_reports_degraded_without_credentials(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "dashboard-refresh",
                "--state-dir",
                str(tmp_path),
                "--env-file",
                str(tmp_path / "missing.env"),
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["effective_mode"] == "paper"
    assert payload["live_enabled"] is False
    assert payload["status"] == "DEGRADED"


def test_dashboard_parser_rejects_non_local_host() -> None:
    with pytest.raises(ValueError, match="localhost"):
        main(["dashboard", "--host", "0.0.0.0"])
