from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "docs" / "operations" / "release-phase7-2-pr-package.json"
REPORT = ROOT / "docs" / "operations" / "release-phase7-2-pr-ready.md"


def test_phase7_2_package_maps_all_pre_package_commits_once() -> None:
    payload = json.loads(PACKAGE.read_text(encoding="utf-8"))

    assert payload["phase"] == "7.2"
    assert payload["status"] == "PR_READY_INTERNAL"
    assert payload["pre_package_commit_count"] == 44

    commits = [
        commit
        for group in payload["review_groups"]
        for commit in group["commits"]
    ]
    assert len(commits) == 44
    assert len(set(commits)) == 44
    assert commits[0] == "e0304bf"
    assert commits[-1] == "2cd7fca"


def test_phase7_2_package_preserves_review_and_safety_boundaries() -> None:
    payload = json.loads(PACKAGE.read_text(encoding="utf-8"))

    assert payload["protected_path_review"]["commit"] == "8b421c9"
    assert payload["protected_path_review"]["changed_files"] == 5
    assert payload["dependencies"]["direct_additions"] == [
        "pyarrow>=14.0",
        "mcp>=2.2,<3",
    ]
    assert payload["security"]["secret_pattern_matches"] == 0
    assert payload["security"]["tracked_runtime_artifacts"] == 0
    assert payload["orders_enabled"] is False


def test_phase7_2_package_keeps_remote_actions_unperformed() -> None:
    payload = json.loads(PACKAGE.read_text(encoding="utf-8"))

    assert payload["remote_actions"] == {
        "branch_rename": "NOT_PERFORMED",
        "push": "NOT_PERFORMED",
        "pr_creation": "NOT_PERFORMED",
        "merge": "NOT_PERFORMED",
    }
    assert payload["merge_readiness"]["status"] == "CONDITIONAL_EXTERNAL_PENDING"
    assert payload["merge_readiness"]["docker_host_acceptance"] == "PENDING_EXTERNAL"


def test_phase7_2_report_contains_reviewer_handoff_sections() -> None:
    text = REPORT.read_text(encoding="utf-8")

    for marker in (
        "PR 제목",
        "리뷰 그룹",
        "Protected path",
        "Dependency review",
        "merge-auditor",
        "Rollback",
        "Docker Host Acceptance",
        "push 직전",
        "push하지 않는다",
        "merge하지 않는다",
    ):
        assert marker in text
