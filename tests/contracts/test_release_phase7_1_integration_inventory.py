from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "docs" / "operations" / "release-phase7-1-integration-inventory.json"
REPORT = ROOT / "docs" / "operations" / "release-phase7-1-integration-readiness.md"


def test_phase7_1_inventory_freezes_current_integration_state() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["phase"] == "7.1"
    assert payload["status"] == "INTERNAL_RELEASE_READY"
    assert payload["git"]["behind_origin_master"] == 0
    assert payload["git"]["ahead_origin_master"] == 43
    assert payload["git"]["merge_commits"] == 0
    assert payload["git"]["remote_contains_head"] is False
    assert payload["git"]["push_performed"] is False
    assert payload["git"]["merge_performed"] is False


def test_phase7_1_inventory_records_release_risks_without_mutating_them() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["change_scope"]["files_changed"] == 152
    assert payload["change_scope"]["insertions"] == 25700
    assert payload["change_scope"]["deletions"] == 935
    assert payload["protected_paths"]["changed_files"] == 5
    assert payload["protected_paths"]["commits"] == ["8b421c9"]
    assert payload["security_scan"]["secret_pattern_matches"] == 0
    assert payload["security_scan"]["tracked_runtime_artifacts"] == 0
    assert payload["security_scan"]["added_binary_files"] == 0


def test_phase7_1_inventory_preserves_external_and_user_owned_boundaries() -> None:
    payload = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert payload["external_pending"]["docker_host_acceptance"] is True
    assert payload["external_pending"]["push_requires_user_approval"] is True
    assert payload["external_pending"]["merge_requires_user_approval"] is True
    assert payload["other_worktree"]["path"].endswith("AutoResearchFinance_v2-analysis")
    assert payload["other_worktree"]["has_user_owned_changes"] is True
    assert payload["other_worktree"]["must_not_modify"] is True


def test_phase7_1_report_defines_next_non_mutating_release_step() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for marker in (
        "Phase 7.2",
        "PR-ready",
        "merge-auditor",
        "43",
        "152",
        "PENDING_EXTERNAL",
        "push하지 않는다",
        "merge하지 않는다",
    ):
        assert marker in text
