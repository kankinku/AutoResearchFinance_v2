from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "docs" / "operations" / "release-phase7-3-prepush-gate.json"
REPORT = ROOT / "docs" / "operations" / "release-phase7-3-prepush-publication.md"


def test_phase7_3_gate_freezes_non_mutating_publication_state() -> None:
    payload = json.loads(GATE.read_text(encoding="utf-8"))

    assert payload["phase"] == "7.3"
    assert payload["status"] == "PREPUSH_GATE_READY"
    assert payload["pre_gate_head"] == "4d4a88b"
    assert payload["pre_gate_ahead_origin_master"] == 45
    assert payload["behind_origin_master"] == 0
    assert payload["working_tree_clean"] is True


def test_phase7_3_gate_records_remote_dry_run_without_publication() -> None:
    payload = json.loads(GATE.read_text(encoding="utf-8"))

    assert payload["publication_target"] == "feat/autoresearch-runtime-mcp-sdk"
    assert payload["dry_run"]["status"] == "PASS"
    assert payload["dry_run"]["remote_branch_existed_before"] is False
    assert payload["dry_run"]["remote_branch_existed_after"] is False
    assert payload["remote_actions"] == {
        "branch_rename": "NOT_PERFORMED",
        "push": "NOT_PERFORMED",
        "pr_creation": "NOT_PERFORMED",
        "merge": "NOT_PERFORMED",
    }


def test_phase7_3_gate_requires_user_approval_and_external_docker_signoff() -> None:
    payload = json.loads(GATE.read_text(encoding="utf-8"))

    assert payload["approval_boundary"]["push_requires_user_approval"] is True
    assert payload["approval_boundary"]["pr_creation_requires_user_approval"] is True
    assert payload["approval_boundary"]["merge_requires_user_approval"] is True
    assert payload["external_pending"]["docker_host_acceptance"] == "PENDING_EXTERNAL"
    assert payload["orders_enabled"] is False


def test_phase7_3_report_contains_exact_publication_handoff() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for marker in (
        "feat/autoresearch-runtime-mcp-sdk",
        "git push origin HEAD:refs/heads/feat/autoresearch-runtime-mcp-sdk",
        "dry-run",
        "Docker Host Acceptance",
        "사용자 승인",
        "push하지 않았다",
        "PR을 생성하지 않았다",
        "merge하지 않았다",
    ):
        assert marker in text
