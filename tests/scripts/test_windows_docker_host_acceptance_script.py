from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_windows_docker_host_acceptance.ps1"


def test_windows_host_acceptance_wrapper_pins_remote_and_requires_windows_docker() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert 'RemoteBranch = "feat/autoresearch-runtime-mcp-sdk"' in text
    assert 'real Windows host required' in text
    assert 'Docker Desktop Linux engine required' in text
    assert 'working tree must be clean before acceptance' in text
    assert 'origin/$RemoteBranch' in text
    assert 'local HEAD $localHead does not match' in text


def test_windows_host_acceptance_wrapper_runs_canonical_steps() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    for marker in (
        "--check-build-context",
        "--build-image",
        "--prepare-fixture",
        "--verify-timeout",
        "--verify-retry-exhaustion",
        "--verify-controller-restart",
        "ruff",
        "mypy",
        "pytest",
        "verify_mcp_sdk_runtime.py",
        "verify_mcp_runtime.py",
    ):
        assert marker in text


def test_windows_host_acceptance_wrapper_requires_safe_json_contract() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "orders_enabled must be false" in text
    assert 'status = "PASS"' in text
    assert "report.json" in text
    assert "WINDOWS_DOCKER_HOST_ACCEPTANCE=PASS" in text
    assert "WINDOWS_DOCKER_HOST_ACCEPTANCE=$($report.status)" in text
    assert "state/windows-docker-host-acceptance/" in gitignore


def test_windows_host_acceptance_wrapper_handles_windows_powershell_native_stderr() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert '$ErrorActionPreference = "Continue"' in text
    assert "$exitCode = $LASTEXITCODE" in text
    assert "if ($exitCode -ne 0)" in text
    assert "$ErrorActionPreference = $previousPreference" in text


def test_windows_host_acceptance_wrapper_does_not_merge_or_mutate_branch() -> None:
    text = SCRIPT.read_text(encoding="utf-8").lower()

    forbidden = (
        "git merge ",
        "git rebase ",
        "git reset ",
        "git clean ",
        "git checkout ",
        "git switch ",
        "git push ",
    )
    assert not any(token in text for token in forbidden)
