from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FINAL_HOST_DOC = ROOT / "docs" / "operations" / "mcp-phase3-7-8-final-host-acceptance.md"
COMPLETION_DOC = ROOT / "docs" / "operations" / "mcp-phase3-7-completion.md"

EXPECTED_FLAGS = (
    "--check-build-context",
    "--build-image",
    "--check-only",
    "--prepare-fixture",
    "--verify-timeout",
    "--verify-retry-exhaustion",
    "--verify-controller-restart",
)


def test_phase3_7_final_host_runbook_covers_acceptance_in_execution_order() -> None:
    text = FINAL_HOST_DOC.read_text(encoding="utf-8")

    ordered_markers = (
        "--check-build-context",
        "--build-image",
        "--prepare-fixture",
        "--verify-timeout",
        "--verify-retry-exhaustion",
        "--verify-controller-restart",
    )
    offsets = [text.index(marker) for marker in ordered_markers]
    assert offsets == sorted(offsets)

    for phase in range(1, 8):
        assert f"mcp-phase3-7-{phase}" in text

    for expected in (
        "orders_enabled=false",
        "Docker CLI is not available",
        "ENVIRONMENT_BLOCKED",
        "SUCCEEDED",
        "TIMED_OUT",
        "RETRY_EXHAUSTED",
        "CANCELLED",
        "STOPPED",
    ):
        assert expected in text


def test_phase3_7_documented_flags_match_acceptance_cli() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "verify_docker_evaluation.py"),
            "--help",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    for flag in EXPECTED_FLAGS:
        assert flag in completed.stdout
        assert flag in FINAL_HOST_DOC.read_text(encoding="utf-8")


def test_phase3_7_completion_keeps_external_host_evidence_explicit() -> None:
    text = COMPLETION_DOC.read_text(encoding="utf-8")

    assert "implementation_status = COMPLETE" in text
    assert "host_acceptance_status = PENDING_EXTERNAL" in text
    assert "Moon" in text
    assert "Docker Desktop" in text
    assert "orders_enabled=false" in text
