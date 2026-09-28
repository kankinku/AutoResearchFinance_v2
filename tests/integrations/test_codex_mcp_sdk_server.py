from __future__ import annotations

import importlib.metadata
import subprocess
import sys
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parents[2]


def test_phase5_2_declares_official_mcp_v2_dependency() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]

    assert "mcp>=2.2,<3" in dependencies

    version = importlib.metadata.version("mcp")
    major, minor, *_ = (int(part) for part in version.split("."))
    assert (major, minor) >= (2, 2)
    assert major < 3


def test_phase5_2_shadow_sdk_server_can_be_constructed_without_cutover(tmp_path: Path) -> None:
    from integrations.codex_mcp_sdk_server import (
        SDK_ADAPTER_STATUS,
        create_sdk_mcp_server,
    )

    adapter = create_sdk_mcp_server(
        state_dir=tmp_path / "state",
        project_root=tmp_path,
    )

    assert SDK_ADAPTER_STATUS == "SHADOW_SKELETON"
    assert adapter.state_dir == (tmp_path / "state").resolve()
    assert adapter.project_root == tmp_path.resolve()
    assert adapter.server.name == "quant-autoresearch"
    assert adapter.server.version == "0.1.0"

    options = adapter.server.create_initialization_options()
    assert options.server_name == "quant-autoresearch"
    assert options.server_version == "0.1.0"
    assert options.capabilities.tools is None


def test_phase5_2_shadow_module_has_separate_entrypoint_and_manual_server_remains_canonical(
) -> None:
    shadow = subprocess.run(
        [
            sys.executable,
            "-m",
            "integrations.codex_mcp_sdk_server",
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    manual = subprocess.run(
        [
            sys.executable,
            "-m",
            "integrations.codex_mcp_server",
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert shadow.returncode == 0
    assert "quant-autoresearch-sdk-shadow" in shadow.stdout
    assert manual.returncode == 0
    assert "quant-autoresearch-codex-mcp" in manual.stdout
