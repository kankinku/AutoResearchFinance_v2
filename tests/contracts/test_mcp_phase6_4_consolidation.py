from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CURRENT = ROOT / "docs" / "operations" / "mcp-current-state.md"
COMPLETION = ROOT / "docs" / "operations" / "mcp-phase6-completion.json"

HISTORICAL_DOCS = (
    "mcp-phase3-6-1-tool-classification.md",
    "mcp-phase3-6-2-target-surface.md",
    "mcp-phase3-6-3-submit-intent-deprecation.md",
    "mcp-phase3-6-4-public-surface-transition.md",
    "mcp-phase3-6-completion.md",
    "mcp-phase4-feature-parity.md",
    "mcp-phase5-1-sdk-migration-design.md",
    "mcp-phase5-2-sdk-adapter-skeleton.md",
    "mcp-phase5-3-tool-dispatch-parity.md",
    "mcp-phase5-4-sdk-stdio-acceptance.md",
    "mcp-phase5-5-canonical-sdk-cutover.md",
    "mcp-phase5-completion.md",
    "mcp-phase6-1-post-cutover-stabilization.md",
    "mcp-phase6-2-neutral-payload-codec.md",
    "mcp-phase6-3-manual-jsonrpc-isolation.md",
    "mcp-phase6-4-contract-documentation-consolidation.md",
)


def test_phase6_4_current_state_is_single_operational_source_of_truth() -> None:
    text = CURRENT.read_text(encoding="utf-8")

    for marker in (
        "CURRENT_OPERATIONAL_SOURCE_OF_TRUTH",
        "official_sdk",
        "integrations.codex_mcp_server",
        "integrations.codex_mcp_manual_server",
        "13 public",
        "5 hidden legacy",
        "public contract = v1",
        "RuntimeSnapshot = v2",
        "orders_enabled=false",
        "codex_mcp_core",
        "codex_mcp_manual_adapter",
    ):
        assert marker in text


def test_phase6_4_completion_freezes_retention_policy() -> None:
    payload = json.loads(COMPLETION.read_text(encoding="utf-8"))

    assert payload["phase"] == "6"
    assert payload["status"] == "COMPLETE"
    assert payload["canonical_transport"] == "official_sdk"
    assert payload["public_tools"] == 13
    assert payload["hidden_legacy_dispatch"] == 5
    assert payload["manual_rollback"]["retained"] is True
    assert payload["manual_rollback"]["deletion_requires_separate_approval"] is True
    assert payload["hidden_legacy_dispatch_policy"]["retained"] is True
    assert (
        payload["hidden_legacy_dispatch_policy"]["deletion_requires_separate_approval"]
        is True
    )
    assert payload["orders_enabled"] is False


def test_phase6_4_historical_docs_are_marked_as_non_operational() -> None:
    for name in HISTORICAL_DOCS:
        text = (ROOT / "docs" / "operations" / name).read_text(encoding="utf-8")
        assert "역사적 단계 문서" in text
        assert "mcp-current-state.md" in text


def test_phase6_4_current_runtime_docs_point_to_current_state() -> None:
    for name in ("verification.md", "system-orchestrator.md"):
        text = (ROOT / "docs" / "operations" / name).read_text(encoding="utf-8")
        assert "mcp-current-state.md" in text
