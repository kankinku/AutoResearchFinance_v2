from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from integrations.kis.live_gate import LiveApproval, validate_live_approval
from integrations.kis.permissions import ResearchPermissions, validate_research_permissions
from integrations.kis.research_adapter import ResearchKISAdapter


def test_research_adapter_has_read_only_interface() -> None:
    adapter = ResearchKISAdapter()

    assert adapter.historical_data("TEST") == ()
    assert not hasattr(adapter, "submit_order")
    validate_research_permissions(ResearchPermissions(order_permission=False, credential_ref=None))


def test_research_permissions_reject_order_or_credentials() -> None:
    with pytest.raises(PermissionError, match="order"):
        validate_research_permissions(
            ResearchPermissions(order_permission=True, credential_ref=None)
        )
    with pytest.raises(PermissionError, match="credential"):
        validate_research_permissions(
            ResearchPermissions(order_permission=False, credential_ref="KIS")
        )


def test_live_gate_requires_current_human_approval_and_exact_champion() -> None:
    approval = LiveApproval(
        champion_hash="champion-1",
        approved_by="human",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    assert validate_live_approval(approval, champion_hash="champion-1")
    with pytest.raises(PermissionError, match="champion"):
        validate_live_approval(approval, champion_hash="other")
    expired = LiveApproval("champion-1", "human", datetime.now(timezone.utc) - timedelta(seconds=1))
    with pytest.raises(PermissionError, match="expired"):
        validate_live_approval(expired, champion_hash="champion-1")
